#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .config import (
    CACHE_PATH as DATA_PATH,
    CONFIG_PATH,
    TOKEN_PATH,
    load_config as load_merged_config,
)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/tasks",
]
SYNC_LOCK = threading.RLock()
POST_WRITE_SYNC_LOCK = threading.Lock()
TOKEN_LOCK = threading.Lock()
CONFIG_LOCK = threading.Lock()
EVENT_DURATIONS = {30, 60, 90, 120, 180, 240}


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def atomic_write_json(path: Path, payload: Any, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if mode is not None:
        os.chmod(tmp, mode)
    os.replace(tmp, path)


def load_config() -> dict[str, Any]:
    return load_merged_config()


def save_config(config: dict[str, Any]) -> None:
    with CONFIG_LOCK:
        atomic_write_json(CONFIG_PATH, config, 0o640)


def public_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": config.get("title", "HomeHub"),
        "subtitle": config.get("subtitle", ""),
        "timezone": config.get("timezone", "Australia/Brisbane"),
        "sleep": config.get("sleep", {"enabled": True, "off": "22:00", "on": "06:00"}),
        "milestone": config.get("milestone", {"enabled": False}),
    }


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def get_credentials() -> Credentials:
    with TOKEN_LOCK:
        if not TOKEN_PATH.exists():
            raise FileNotFoundError("Google authorisation is not complete yet")
        credentials = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            tmp = TOKEN_PATH.with_suffix(".tmp")
            tmp.write_text(credentials.to_json(), encoding="utf-8")
            os.chmod(tmp, 0o600)
            os.replace(tmp, TOKEN_PATH)
        if not credentials.valid:
            raise RuntimeError("Google token is invalid; authorise HomeHub again")
        return credentials


def services() -> tuple[Any, Any]:
    credentials = get_credentials()
    return (
        build("calendar", "v3", credentials=credentials, cache_discovery=False),
        build("tasks", "v1", credentials=credentials, cache_discovery=False),
    )


def chosen_calendars(service: Any, configured_ids: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    page_token = None
    while True:
        response = service.calendarList().list(pageToken=page_token).execute()
        entries.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    if configured_ids:
        wanted = set(configured_ids)
        return [entry for entry in entries if entry.get("id") in wanted]
    selected = [entry for entry in entries if entry.get("selected") or entry.get("primary")]
    return selected or [entry for entry in entries if entry.get("primary")]


def fetch_events(
    service: Any,
    calendars: list[dict[str, Any]],
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for calendar in calendars:
        page_token = None
        editable_calendar = calendar.get("accessRole") in {"owner", "writer"}
        while True:
            response = service.events().list(
                calendarId=calendar["id"],
                timeMin=iso_utc(start),
                timeMax=iso_utc(end),
                singleEvents=True,
                orderBy="startTime",
                maxResults=2500,
                pageToken=page_token,
            ).execute()
            for event in response.get("items", []):
                if event.get("status") == "cancelled":
                    continue
                start_obj = event.get("start", {})
                end_obj = event.get("end", {})
                events.append({
                    "id": event.get("id"),
                    "title": event.get("summary") or "(No title)",
                    "start": start_obj.get("dateTime") or start_obj.get("date"),
                    "end": end_obj.get("dateTime") or end_obj.get("date"),
                    "allDay": "date" in start_obj,
                    "location": event.get("location", ""),
                    "calendar": calendar.get("summary", ""),
                    "calendarId": calendar.get("id", ""),
                    "color": event.get("backgroundColor") or calendar.get("backgroundColor", "#d49a55"),
                    "editable": bool(editable_calendar and not event.get("locked", False)),
                })
            page_token = response.get("nextPageToken")
            if not page_token:
                break
    return sorted(events, key=lambda item: (item.get("start") or "", item.get("title") or ""))


def list_task_lists(service: Any) -> list[dict[str, Any]]:
    task_lists: list[dict[str, Any]] = []
    page_token = None
    while True:
        response = service.tasklists().list(maxResults=100, pageToken=page_token).execute()
        task_lists.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return task_lists


def chosen_task_lists(service: Any, configured_selectors: list[str]) -> list[dict[str, Any]]:
    task_lists = list_task_lists(service)
    if not configured_selectors:
        return task_lists
    wanted = {str(value).casefold() for value in configured_selectors}
    return [
        item for item in task_lists
        if str(item.get("id", "")).casefold() in wanted
        or str(item.get("title", "")).casefold() in wanted
    ]


def task_payload(task: dict[str, Any], task_list: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task.get("id"),
        "taskListId": task_list.get("id"),
        "title": task.get("title") or "(Untitled task)",
        "notes": task.get("notes", ""),
        "due": task.get("due"),
        "completed": task.get("completed"),
        "list": task_list.get("title", "Tasks"),
        "readOnly": bool(task.get("assignmentInfo")),
    }


def fetch_tasks(
    service: Any,
    task_lists: list[dict[str, Any]],
    max_open: int,
    max_completed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    open_tasks: list[dict[str, Any]] = []
    completed_tasks: list[dict[str, Any]] = []
    completed_min = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat().replace("+00:00", "Z")
    def collect(task_list: dict[str, Any], completed: bool) -> None:
        page_token = None
        while True:
            arguments: dict[str, Any] = {
                "tasklist": task_list["id"],
                "showCompleted": completed,
                "showHidden": completed,
                "showAssigned": True,
                "maxResults": 100,
                "pageToken": page_token,
            }
            if completed:
                arguments["completedMin"] = completed_min
            response = service.tasks().list(
                **arguments,
            ).execute()
            for task in response.get("items", []):
                if task.get("deleted"):
                    continue
                item = task_payload(task, task_list)
                if task.get("status") == "completed":
                    if completed:
                        completed_tasks.append(item)
                else:
                    if not completed:
                        open_tasks.append(item)
            page_token = response.get("nextPageToken")
            if not page_token:
                break

    for task_list in task_lists:
        # An open Google Task has no completion timestamp. Fetching open and
        # completed rows separately avoids completedMin filtering every open
        # task out of the response. First-party completed tasks are hidden, so
        # that second query deliberately enables showHidden.
        collect(task_list, completed=False)
        collect(task_list, completed=True)
    open_tasks.sort(key=lambda item: (
        item.get("due") is None,
        item.get("due") or "9999",
        item.get("list") or "",
        item.get("title") or "",
    ))
    completed_tasks.sort(key=lambda item: item.get("completed") or "", reverse=True)
    return open_tasks[:max_open], completed_tasks[:max_completed]


def base_empty_data() -> dict[str, Any]:
    config = load_config()
    return {
        "title": config.get("title", "HomeHub"),
        "subtitle": config.get("subtitle", ""),
        "timezone": config.get("timezone", "Australia/Brisbane"),
        "status": "setup_required" if not TOKEN_PATH.exists() else "starting",
        "updatedAt": None,
        "checkedAt": None,
        "lastError": None,
        "config": public_config(config),
        "calendars": [],
        "writableCalendars": [],
        "taskLists": [],
        "availableTaskLists": [],
        "events": [],
        "tasks": [],
        "completedTasks": [],
    }


def sync_data() -> dict[str, Any]:
    with SYNC_LOCK:
        config = load_config()
        timezone_name = config.get("timezone", "Australia/Brisbane")
        local_timezone = ZoneInfo(timezone_name)
        now = datetime.now(local_timezone)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        calendar_service, tasks_service = services()
        calendars = chosen_calendars(calendar_service, config.get("calendar_ids", []))
        events = fetch_events(
            calendar_service,
            calendars,
            month_start - timedelta(days=45),
            month_start + timedelta(days=200),
        )
        available_task_lists = list_task_lists(tasks_service)
        configured_task_lists = config.get("task_lists", [])
        if configured_task_lists:
            wanted = {str(value).casefold() for value in configured_task_lists}
            task_lists = [
                item for item in available_task_lists
                if str(item.get("id", "")).casefold() in wanted
                or str(item.get("title", "")).casefold() in wanted
            ]
        else:
            task_lists = available_task_lists
        tasks, completed = fetch_tasks(
            tasks_service,
            task_lists,
            max(50, int(config.get("max_tasks", 50))),
            max(12, int(config.get("max_completed_tasks", 12))),
        )
        writable_roles = {"owner", "writer"}
        timestamp = datetime.now(timezone.utc).isoformat()
        data = {
            "title": config.get("title", "HomeHub"),
            "subtitle": config.get("subtitle", ""),
            "timezone": timezone_name,
            "status": "online",
            "updatedAt": timestamp,
            "checkedAt": timestamp,
            "lastError": None,
            "config": public_config(config),
            "calendars": [
                {
                    "id": calendar.get("id"),
                    "title": calendar.get("summary", ""),
                    "color": calendar.get("backgroundColor", "#d49a55"),
                }
                for calendar in calendars
            ],
            "writableCalendars": [
                {
                    "id": calendar.get("id"),
                    "title": calendar.get("summary", ""),
                    "color": calendar.get("backgroundColor", "#d49a55"),
                    "primary": bool(calendar.get("primary")),
                }
                for calendar in calendars
                if calendar.get("accessRole") in writable_roles
            ],
            "taskLists": [
                {"id": task_list.get("id"), "title": task_list.get("title", "Tasks")}
                for task_list in task_lists
            ],
            "availableTaskLists": [
                {"id": task_list.get("id"), "title": task_list.get("title", "Tasks")}
                for task_list in available_task_lists
            ],
            "events": events,
            "tasks": tasks,
            "completedTasks": completed,
        }
        atomic_write_json(DATA_PATH, data, 0o640)
        return data


def current_data() -> dict[str, Any]:
    data = read_json(DATA_PATH, {})
    if not data:
        return base_empty_data()
    config = load_config()
    data["config"] = public_config(config)
    data["title"] = config.get("title", data.get("title", "HomeHub"))
    data["subtitle"] = config.get("subtitle", data.get("subtitle", ""))
    data.pop("weather", None)
    return data


def write_failure(message: str) -> dict[str, Any]:
    data = current_data()
    data["status"] = "setup_required" if not TOKEN_PATH.exists() else "stale"
    data["checkedAt"] = datetime.now(timezone.utc).isoformat()
    data["lastError"] = message
    atomic_write_json(DATA_PATH, data, 0o640)
    return data


def queue_sync() -> None:
    """Refresh Google data after a mutation without holding up the touch UI."""
    if not POST_WRITE_SYNC_LOCK.acquire(blocking=False):
        return
    threading.Thread(target=_quiet_sync, daemon=True, name="homehub-post-write-sync").start()


def _quiet_sync() -> None:
    try:
        sync_data()
    except Exception as exc:
        write_failure(str(exc))
    finally:
        POST_WRITE_SYNC_LOCK.release()


def complete_task(task_list_id: str, task_id: str) -> dict[str, Any]:
    if not task_list_id or not task_id:
        raise ValueError("Missing task identifier")
    _, service = services()
    service.tasks().patch(tasklist=task_list_id, task=task_id, body={"status": "completed"}).execute()
    data = current_data()
    completed = next(
        (
            task
            for task in data.get("tasks", [])
            if task.get("taskListId") == task_list_id and task.get("id") == task_id
        ),
        None,
    )
    data["tasks"] = [
        task
        for task in data.get("tasks", [])
        if not (task.get("taskListId") == task_list_id and task.get("id") == task_id)
    ]
    if completed:
        completed = dict(completed)
        completed["completed"] = datetime.now(timezone.utc).isoformat()
        data["completedTasks"] = [completed, *data.get("completedTasks", [])]
    atomic_write_json(DATA_PATH, data, 0o640)
    queue_sync()
    return data


def restore_task(task_list_id: str, task_id: str) -> dict[str, Any]:
    if not task_list_id or not task_id:
        raise ValueError("Missing task identifier")
    _, service = services()
    restored = service.tasks().patch(
        tasklist=task_list_id,
        task=task_id,
        body={"status": "needsAction", "completed": None},
    ).execute()
    data = current_data()
    original = next((
        task for task in data.get("completedTasks", [])
        if task.get("taskListId") == task_list_id and task.get("id") == task_id
    ), None)
    data["completedTasks"] = [
        task for task in data.get("completedTasks", [])
        if not (task.get("taskListId") == task_list_id and task.get("id") == task_id)
    ]
    task_list = next(
        (item for item in data.get("taskLists", []) if item.get("id") == task_list_id),
        {"id": task_list_id, "title": original.get("list", "Tasks") if original else "Tasks"},
    )
    data["tasks"] = [task_payload(restored, task_list), *data.get("tasks", [])]
    atomic_write_json(DATA_PATH, data, 0o640)
    queue_sync()
    return data


def create_task(payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title", "")).strip()
    if not title:
        raise ValueError("Task title is required")
    config = load_config()
    _, service = services()
    task_lists = chosen_task_lists(service, config.get("task_lists", []))
    if not task_lists:
        raise ValueError("No Google Task list is available")
    requested = str(payload.get("taskListId", "")).strip()
    default_selector = str(config.get("default_task_list", "")).casefold()
    task_list = next((item for item in task_lists if item.get("id") == requested), None)
    if task_list is None and default_selector:
        task_list = next(
            (
                item for item in task_lists
                if str(item.get("id", "")).casefold() == default_selector
                or str(item.get("title", "")).casefold() == default_selector
            ),
            None,
        )
    task_list = task_list or task_lists[0]
    body: dict[str, Any] = {"title": title}
    due_text = str(payload.get("due", "")).strip()
    if due_text:
        try:
            due_date = datetime.strptime(due_text, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("Invalid task due date") from exc
        body["due"] = datetime(
            due_date.year,
            due_date.month,
            due_date.day,
            tzinfo=timezone.utc,
        ).isoformat().replace("+00:00", "Z")
    created = service.tasks().insert(tasklist=task_list["id"], body=body).execute()
    data = current_data()
    data["tasks"] = [*data.get("tasks", []), task_payload(created, task_list)]
    atomic_write_json(DATA_PATH, data, 0o640)
    queue_sync()
    return data


def _task_due(value: Any) -> str | None:
    due_text = str(value or "").strip()
    if not due_text:
        return None
    try:
        due_date = datetime.strptime(due_text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Invalid task due date") from exc
    return datetime(
        due_date.year,
        due_date.month,
        due_date.day,
        tzinfo=timezone.utc,
    ).isoformat().replace("+00:00", "Z")


def update_task(task_list_id: str, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not task_list_id or not task_id:
        raise ValueError("Missing task identifier")
    title = str(payload.get("title", "")).strip()
    if not title:
        raise ValueError("Task title is required")
    _, service = services()
    updated = service.tasks().patch(
        tasklist=task_list_id,
        task=task_id,
        body={"title": title, "due": _task_due(payload.get("due"))},
    ).execute()
    data = current_data()
    task_list = next(
        (item for item in data.get("taskLists", []) if item.get("id") == task_list_id),
        {"id": task_list_id, "title": "Tasks"},
    )
    replacement = task_payload(updated, task_list)
    data["tasks"] = [
        replacement if task.get("taskListId") == task_list_id and task.get("id") == task_id else task
        for task in data.get("tasks", [])
    ]
    atomic_write_json(DATA_PATH, data, 0o640)
    queue_sync()
    return data


def delete_task(task_list_id: str, task_id: str) -> dict[str, Any]:
    if not task_list_id or not task_id:
        raise ValueError("Missing task identifier")
    _, service = services()
    service.tasks().delete(tasklist=task_list_id, task=task_id).execute()
    data = current_data()
    for key in ("tasks", "completedTasks"):
        data[key] = [
            task for task in data.get(key, [])
            if not (task.get("taskListId") == task_list_id and task.get("id") == task_id)
        ]
    atomic_write_json(DATA_PATH, data, 0o640)
    queue_sync()
    return data


def event_body(payload: dict[str, Any], config: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    title = str(payload.get("title", "")).strip()
    if not title:
        raise ValueError("Event title is required")
    try:
        event_date = datetime.strptime(str(payload.get("date", "")), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Invalid event date") from exc
    timezone_name = config.get("timezone", "Australia/Brisbane")
    local_timezone = ZoneInfo(timezone_name)
    calendar_id = str(payload.get("calendarId") or config.get("event_calendar_id") or "primary")
    body: dict[str, Any] = {"summary": title}
    if bool(payload.get("allDay")):
        body["start"] = {"date": event_date.isoformat()}
        body["end"] = {"date": (event_date + timedelta(days=1)).isoformat()}
        return calendar_id, body

    try:
        start_minutes = int(payload.get("startMinutes", 540))
        duration = int(payload.get("durationMinutes", 60))
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid event time or duration") from exc
    if not 0 <= start_minutes <= 1439 or duration not in EVENT_DURATIONS:
        raise ValueError("Invalid event time or duration")
    start = datetime(
        event_date.year,
        event_date.month,
        event_date.day,
        start_minutes // 60,
        start_minutes % 60,
        tzinfo=local_timezone,
    )
    end = start + timedelta(minutes=duration)
    body["start"] = {"dateTime": start.isoformat(), "timeZone": timezone_name}
    body["end"] = {"dateTime": end.isoformat(), "timeZone": timezone_name}
    return calendar_id, body


def create_event(payload: dict[str, Any]) -> dict[str, Any]:
    calendar_id, body = event_body(payload, load_config())
    calendar_service, _ = services()
    created = calendar_service.events().insert(calendarId=calendar_id, body=body).execute()
    data = current_data()
    calendar = next(
        (item for item in data.get("writableCalendars", []) if item.get("id") == calendar_id),
        {"id": calendar_id, "title": "Calendar", "color": "#d49a55"},
    )
    data["events"] = [*data.get("events", []), event_from_google(created, calendar, True)]
    atomic_write_json(DATA_PATH, data, 0o640)
    queue_sync()
    return data


def update_event(event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    event_id = str(event_id).strip()
    if not event_id:
        raise ValueError("Missing event identifier")
    calendar_id, body = event_body(payload, load_config())
    calendar_service, _ = services()
    # Calendar PATCH merges nested start/end objects. Converting an all-day
    # event to a timed event can therefore leave both `date` and `dateTime`,
    # which Google rejects. Replace those fields on the complete event instead.
    existing = calendar_service.events().get(
        calendarId=calendar_id,
        eventId=event_id,
    ).execute()
    existing["summary"] = body["summary"]
    existing["start"] = body["start"]
    existing["end"] = body["end"]
    updated = calendar_service.events().update(
        calendarId=calendar_id,
        eventId=event_id,
        body=existing,
        sendUpdates="all",
    ).execute()
    data = current_data()
    calendar = next(
        (item for item in data.get("writableCalendars", []) if item.get("id") == calendar_id),
        {"id": calendar_id, "title": "Calendar", "color": "#d49a55"},
    )
    replacement = event_from_google(updated, calendar, True)
    data["events"] = [
        replacement if event.get("id") == event_id and event.get("calendarId") == calendar_id else event
        for event in data.get("events", [])
    ]
    atomic_write_json(DATA_PATH, data, 0o640)
    queue_sync()
    return data


def delete_event(event_id: str, calendar_id: str) -> dict[str, Any]:
    event_id = str(event_id).strip()
    calendar_id = str(calendar_id).strip()
    if not event_id or not calendar_id:
        raise ValueError("Missing event identifier")
    calendar_service, _ = services()
    calendar_service.events().delete(
        calendarId=calendar_id,
        eventId=event_id,
        sendUpdates="all",
    ).execute()
    data = current_data()
    data["events"] = [
        event for event in data.get("events", [])
        if not (event.get("id") == event_id and event.get("calendarId") == calendar_id)
    ]
    atomic_write_json(DATA_PATH, data, 0o640)
    queue_sync()
    return data


def event_from_google(
    event: dict[str, Any],
    calendar: dict[str, Any],
    editable: bool,
) -> dict[str, Any]:
    start = event.get("start", {})
    end = event.get("end", {})
    return {
        "id": event.get("id"),
        "title": event.get("summary") or "(No title)",
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "allDay": "date" in start,
        "location": event.get("location", ""),
        "calendar": calendar.get("title") or calendar.get("summary", ""),
        "calendarId": calendar.get("id", ""),
        "color": event.get("backgroundColor") or calendar.get("color", "#d49a55"),
        "editable": editable,
    }


def update_settings(payload: dict[str, Any]) -> dict[str, Any]:
    config = load_config()
    sleep = dict(config.get("sleep", {}))
    sleep["enabled"] = bool(payload.get("enabled", True))
    for key in ("off", "on"):
        value = str(payload.get(key, sleep.get(key, "")))
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError as exc:
            raise ValueError(f"Invalid {key} time") from exc
        sleep[key] = value
    method = str(payload.get("method", sleep.get("method", "auto")))
    if method not in {"auto", "wlopm", "wlr-randr"}:
        raise ValueError("Invalid screen power method")
    sleep["method"] = method
    config["sleep"] = sleep
    save_config(config)
    data = current_data()
    data["config"] = public_config(config)
    atomic_write_json(DATA_PATH, data, 0o640)
    return data
