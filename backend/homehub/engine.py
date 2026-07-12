#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .config import (
    CACHE_PATH as DATA_PATH,
    CONFIG_PATH,
    STATE_DIR,
    TOKEN_PATH,
    load_config as load_merged_config,
)

WEATHER_EXTREMA_PATH = STATE_DIR / "weather-extrema.json"
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/tasks",
]
SYNC_LOCK = threading.RLock()
TOKEN_LOCK = threading.Lock()
CONFIG_LOCK = threading.Lock()


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def atomic_write_json(path: Path, payload: Any, mode: int | None = None) -> None:
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
        "subtitle": config.get("subtitle", "Family Organiser"),
        "timezone": config.get("timezone", "Australia/Brisbane"),
        "sleep": config.get("sleep", {"enabled": True, "off": "22:00", "on": "06:00"}),
        "milestone": config.get("milestone", {"enabled": False}),
        "weather": {
            "enabled": bool(config.get("weather", {}).get("enabled", False)) if isinstance(config.get("weather"), dict) else False,
            "source": str(config.get("weather", {}).get("source", "disabled")) if isinstance(config.get("weather"), dict) else "disabled",
        },
    }


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def get_credentials() -> Credentials:
    with TOKEN_LOCK:
        if not TOKEN_PATH.exists():
            raise FileNotFoundError("Google authorisation is not complete yet")
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            tmp = TOKEN_PATH.with_suffix(".tmp")
            tmp.write_text(creds.to_json(), encoding="utf-8")
            os.chmod(tmp, 0o600)
            os.replace(tmp, TOKEN_PATH)
        if not creds.valid:
            raise RuntimeError("Google token is invalid; authorise HomeHub again")
        return creds


def services() -> tuple[Any, Any]:
    creds = get_credentials()
    return (
        build("calendar", "v3", credentials=creds, cache_discovery=False),
        build("tasks", "v1", credentials=creds, cache_discovery=False),
    )


def chosen_calendars(service: Any, configured_ids: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    token = None
    while True:
        response = service.calendarList().list(pageToken=token).execute()
        entries.extend(response.get("items", []))
        token = response.get("nextPageToken")
        if not token:
            break
    if configured_ids:
        wanted = set(configured_ids)
        return [entry for entry in entries if entry.get("id") in wanted]
    selected = [entry for entry in entries if entry.get("selected") or entry.get("primary")]
    return selected or [entry for entry in entries if entry.get("primary")]


def fetch_events(service: Any, calendars: list[dict[str, Any]], start: datetime, end: datetime) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for calendar in calendars:
        token = None
        while True:
            response = service.events().list(
                calendarId=calendar["id"], timeMin=iso_utc(start), timeMax=iso_utc(end),
                singleEvents=True, orderBy="startTime", maxResults=2500, pageToken=token,
            ).execute()
            for event in response.get("items", []):
                if event.get("status") == "cancelled":
                    continue
                start_obj, end_obj = event.get("start", {}), event.get("end", {})
                events.append({
                    "id": event.get("id"), "title": event.get("summary") or "(No title)",
                    "start": start_obj.get("dateTime") or start_obj.get("date"),
                    "end": end_obj.get("dateTime") or end_obj.get("date"),
                    "allDay": "date" in start_obj, "location": event.get("location", ""),
                    "calendar": calendar.get("summary", ""), "calendarId": calendar.get("id", ""),
                    "color": event.get("backgroundColor") or calendar.get("backgroundColor", "#4f8ee8"),
                })
            token = response.get("nextPageToken")
            if not token:
                break
    return sorted(events, key=lambda item: (item.get("start") or "", item.get("title") or ""))


def chosen_task_lists(service: Any, configured_names: list[str]) -> list[dict[str, Any]]:
    lists: list[dict[str, Any]] = []
    token = None
    while True:
        response = service.tasklists().list(maxResults=100, pageToken=token).execute()
        lists.extend(response.get("items", []))
        token = response.get("nextPageToken")
        if not token:
            break
    if not configured_names:
        return lists
    wanted = {name.casefold() for name in configured_names}
    return [item for item in lists if item.get("title", "").casefold() in wanted]


def task_payload(task: dict[str, Any], task_list: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task.get("id"), "taskListId": task_list.get("id"),
        "title": task.get("title") or "(Untitled task)", "notes": task.get("notes", ""),
        "due": task.get("due"), "completed": task.get("completed"),
        "list": task_list.get("title", "Tasks"), "readOnly": bool(task.get("assignmentInfo")),
    }


def fetch_tasks(service: Any, lists: list[dict[str, Any]], max_open: int, max_completed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    open_tasks: list[dict[str, Any]] = []
    completed_tasks: list[dict[str, Any]] = []
    completed_min = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat().replace("+00:00", "Z")
    for task_list in lists:
        token = None
        while True:
            response = service.tasks().list(
                tasklist=task_list["id"], showCompleted=True, showHidden=False, showAssigned=True,
                completedMin=completed_min, maxResults=100, pageToken=token,
            ).execute()
            for task in response.get("items", []):
                if task.get("deleted"):
                    continue
                item = task_payload(task, task_list)
                if task.get("status") == "completed":
                    completed_tasks.append(item)
                else:
                    open_tasks.append(item)
            token = response.get("nextPageToken")
            if not token:
                break
    open_tasks.sort(key=lambda item: (item.get("due") is None, item.get("due") or "9999", item.get("list") or "", item.get("title") or ""))
    completed_tasks.sort(key=lambda item: item.get("completed") or "", reverse=True)
    return open_tasks[:max_open], completed_tasks[:max_completed]



def default_weather() -> dict[str, Any]:
    return {
        "enabled": False,
        "status": "disabled",
        "source": "disabled",
        "summary": "Weather disabled",
        "checkedAt": None,
        "updatedAt": None,
        "outdoorTemp": None,
        "todayHigh": None,
        "todayLow": None,
        "outdoorHumidity": None,
        "indoorTemp": None,
        "rainToday": None,
        "rainMonth": None,
        "wind": None,
        "items": [],
        "error": None,
    }


def as_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    # Strip simple unit suffixes such as "24.5 °C" or "0.3mm".
    cleaned = ""
    for char in text:
        if char.isdigit() or char in ".-":
            cleaned += char
        elif cleaned:
            break
    try:
        return float(cleaned)
    except ValueError:
        return None


def value_from_leaf(obj: Any) -> tuple[float | None, str]:
    if isinstance(obj, dict):
        for key in ("value", "val", "data", "now"):
            if key in obj:
                value = as_number(obj.get(key))
                if value is not None:
                    return value, str(obj.get("unit") or obj.get("uom") or obj.get("units") or "")
        for value in obj.values():
            found, unit = value_from_leaf(value)
            if found is not None:
                return found, unit
    elif isinstance(obj, list):
        for value in obj:
            found, unit = value_from_leaf(value)
            if found is not None:
                return found, unit
    else:
        return as_number(obj), ""
    return None, ""


def get_path(data: Any, *path: str) -> Any:
    obj = data
    for part in path:
        if not isinstance(obj, dict) or part not in obj:
            return None
        obj = obj[part]
    return obj


def normalize_temp(value: float | None, unit: str = "") -> float | None:
    if value is None:
        return None
    unit_l = unit.lower()
    if "f" in unit_l and "c" not in unit_l:
        return round((value - 32) * 5 / 9, 1)
    return round(value, 1)


def normalize_rain_mm(value: float | None, unit: str = "") -> float | None:
    if value is None:
        return None
    unit_l = unit.lower()
    if "in" in unit_l and "min" not in unit_l:
        return round(value * 25.4, 1)
    return round(value, 1)


def normalize_wind_kmh(value: float | None, unit: str = "") -> float | None:
    if value is None:
        return None
    unit_l = unit.lower()
    if "mph" in unit_l:
        return round(value * 1.60934, 1)
    if "m/s" in unit_l or "ms" == unit_l:
        return round(value * 3.6, 1)
    return round(value, 1)


def first_value(data: Any, paths: list[tuple[str, ...]], normalizer=lambda value, unit: value) -> float | None:
    for path in paths:
        obj = get_path(data, *path)
        value, unit = value_from_leaf(obj)
        if value is not None:
            return normalizer(value, unit)
    return None


def fetch_url_json(url: str, timeout: int = 10) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "HomeHub/4"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        payload = response.read(512_000).decode(charset, errors="replace")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Weather response was not a JSON object")
    return data


def update_daily_extrema(outdoor: float | None) -> tuple[float | None, float | None]:
    if outdoor is None:
        state = read_json(WEATHER_EXTREMA_PATH, {})
        return state.get("high"), state.get("low")
    cfg = load_config()
    tz = ZoneInfo(cfg.get("timezone", "Australia/Brisbane"))
    today = datetime.now(tz).date().isoformat()
    state = read_json(WEATHER_EXTREMA_PATH, {})
    if state.get("date") != today:
        state = {"date": today, "high": outdoor, "low": outdoor}
    else:
        state["high"] = max(float(state.get("high", outdoor)), outdoor)
        state["low"] = min(float(state.get("low", outdoor)), outdoor)
    atomic_write_json(WEATHER_EXTREMA_PATH, state, 0o640)
    return round(float(state["high"]), 1), round(float(state["low"]), 1)


def parse_ecowitt_cloud(payload: dict[str, Any]) -> dict[str, Any]:
    if str(payload.get("code", "0")) not in {"0", "200"} and payload.get("data") is None:
        raise ValueError(str(payload.get("msg") or "Ecowitt returned an error"))
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    outdoor = first_value(data, [("outdoor", "temperature"), ("outdoor", "temp"), ("tempf",)], normalize_temp)
    outdoor_hum = first_value(data, [("outdoor", "humidity"), ("humidity",)])
    indoor = first_value(data, [("indoor", "temperature"), ("indoor", "temp"), ("tempinf",)], normalize_temp)
    rain_today = first_value(data, [("rainfall", "daily"), ("rainfall", "day"), ("dailyrainin",), ("rain_day",)], normalize_rain_mm)
    rain_month = first_value(data, [("rainfall", "monthly"), ("monthlyrainin",), ("rain_month",)], normalize_rain_mm)
    wind = first_value(data, [("wind", "wind_speed"), ("wind", "speed"), ("windspeedmph",)], normalize_wind_kmh)
    high = first_value(data, [("outdoor", "temperature", "max"), ("outdoor", "temperature", "high"), ("outdoor", "temp", "max")], normalize_temp)
    low = first_value(data, [("outdoor", "temperature", "min"), ("outdoor", "temperature", "low"), ("outdoor", "temp", "min")], normalize_temp)
    return weather_payload("ecowitt_cloud", outdoor, outdoor_hum, indoor, rain_today, rain_month, wind, high, low)


def flatten_weather_lists(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if any(k in obj for k in ("name", "title", "label")) and any(k in obj for k in ("value", "val", "data")):
                rows.append(obj)
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)
    walk(payload)
    return rows


def parse_ecowitt_local(payload: dict[str, Any]) -> dict[str, Any]:
    outdoor = outdoor_hum = indoor = rain_today = rain_month = wind = None
    for row in flatten_weather_lists(payload):
        name = str(row.get("name") or row.get("title") or row.get("label") or "").casefold()
        unit = str(row.get("unit") or row.get("uom") or row.get("units") or "")
        value = as_number(row.get("value", row.get("val", row.get("data"))))
        if value is None:
            continue
        if "outdoor" in name and ("temp" in name or "temperature" in name):
            outdoor = normalize_temp(value, unit)
        elif "outdoor" in name and "humid" in name:
            outdoor_hum = round(value)
        elif "indoor" in name and ("temp" in name or "temperature" in name):
            indoor = normalize_temp(value, unit)
        elif ("daily" in name or "today" in name) and "rain" in name:
            rain_today = normalize_rain_mm(value, unit)
        elif "monthly" in name and "rain" in name:
            rain_month = normalize_rain_mm(value, unit)
        elif "wind" in name and "gust" not in name and ("speed" in name or name.strip() == "wind"):
            wind = normalize_wind_kmh(value, unit)
    return weather_payload("ecowitt_local", outdoor, outdoor_hum, indoor, rain_today, rain_month, wind)


def weather_payload(source: str, outdoor: float | None, outdoor_hum: float | None, indoor: float | None, rain_today: float | None, rain_month: float | None, wind: float | None, high: float | None = None, low: float | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    tracked_high, tracked_low = update_daily_extrema(outdoor)
    high = high if high is not None else tracked_high
    low = low if low is not None else tracked_low
    items: list[dict[str, Any]] = []
    if outdoor is not None:
        items.append({"label": "Outside now", "value": f"{outdoor:.1f}", "unit": "°C", "kind": "temp"})
    if high is not None:
        items.append({"label": "Today's high", "value": f"{high:.1f}", "unit": "°C", "kind": "temp high"})
    if low is not None:
        items.append({"label": "Today's low", "value": f"{low:.1f}", "unit": "°C", "kind": "temp low"})
    if rain_today is not None:
        items.append({"label": "Rain today", "value": f"{rain_today:.1f}", "unit": "mm", "kind": "rain"})
    if rain_month is not None:
        items.append({"label": "Rain this month", "value": f"{rain_month:.1f}", "unit": "mm", "kind": "rain"})
    if indoor is not None:
        items.append({"label": "Inside", "value": f"{indoor:.1f}", "unit": "°C", "kind": "temp"})
    summary = "Weather live" if items else "Weather data empty"
    return {
        "enabled": True,
        "status": "online" if items else "empty",
        "source": source,
        "summary": summary,
        "checkedAt": now,
        "updatedAt": now,
        "outdoorTemp": outdoor,
        "todayHigh": high,
        "todayLow": low,
        "outdoorHumidity": outdoor_hum,
        "indoorTemp": indoor,
        "rainToday": rain_today,
        "rainMonth": rain_month,
        "wind": wind,
        "items": items[:6],
        "error": None,
    }


def fetch_weather(config: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    weather_config = config.get("weather", {}) if isinstance(config.get("weather"), dict) else {}
    if not weather_config.get("enabled", False):
        return default_weather()
    source = str(weather_config.get("source", "disabled"))
    refresh_seconds = int(weather_config.get("refresh_seconds", 300) or 300)
    if existing and isinstance(existing, dict) and existing.get("status") == "online" and existing.get("items"):
        updated = str(existing.get("updatedAt") or existing.get("checkedAt") or "")
        try:
            updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - updated_dt).total_seconds()
            if age < max(60, refresh_seconds):
                return existing
        except Exception:
            pass
    if source == "disabled":
        payload = default_weather()
        payload.update({"enabled": True, "status": "not_configured", "summary": "Weather not configured"})
        return payload
    try:
        if source == "ecowitt_cloud":
            cloud = weather_config.get("ecowitt_cloud", {}) if isinstance(weather_config.get("ecowitt_cloud"), dict) else {}
            app_key = str(cloud.get("application_key", "")).strip()
            api_key = str(cloud.get("api_key", "")).strip()
            mac = str(cloud.get("mac", "")).strip()
            if not app_key or not api_key or not mac:
                raise ValueError("Ecowitt cloud keys or MAC are missing")
            base_url = str(cloud.get("base_url") or "https://api.ecowitt.net/api/v3/device/real_time")
            query = urllib.parse.urlencode({"application_key": app_key, "api_key": api_key, "mac": mac, "call_back": "all"})
            return parse_ecowitt_cloud(fetch_url_json(f"{base_url}?{query}"))
        if source == "ecowitt_local":
            local = weather_config.get("ecowitt_local", {}) if isinstance(weather_config.get("ecowitt_local"), dict) else {}
            gateway = str(local.get("gateway_url", "")).strip().rstrip("/")
            if not gateway:
                raise ValueError("Ecowitt local gateway URL is missing")
            if not gateway.endswith("get_livedata_info"):
                gateway = f"{gateway}/get_livedata_info"
            return parse_ecowitt_local(fetch_url_json(gateway))
        raise ValueError(f"Unknown weather source: {source}")
    except Exception as exc:
        prior = existing or {}
        payload = prior if isinstance(prior, dict) and prior.get("items") else default_weather()
        payload = dict(payload)
        payload.update({
            "enabled": True,
            "status": "stale" if payload.get("items") else "error",
            "source": source,
            "checkedAt": datetime.now(timezone.utc).isoformat(),
            "summary": "Weather stale" if payload.get("items") else "Weather unavailable",
            "error": str(exc),
        })
        return payload

def base_empty_data() -> dict[str, Any]:
    config = load_config()
    return {
        "title": config.get("title", "HomeHub"), "subtitle": config.get("subtitle", "Family Organiser"),
        "timezone": config.get("timezone", "Australia/Brisbane"),
        "status": "setup_required" if not TOKEN_PATH.exists() else "starting",
        "updatedAt": None, "checkedAt": None, "lastError": None,
        "config": public_config(config), "calendars": [], "writableCalendars": [],
        "taskLists": [], "events": [], "tasks": [], "completedTasks": [],
        "weather": fetch_weather(config),
    }


def sync_data() -> dict[str, Any]:
    with SYNC_LOCK:
        config = load_config()
        tz_name = config.get("timezone", "Australia/Brisbane")
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
        first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        calendar_service, tasks_service = services()
        calendars = chosen_calendars(calendar_service, config.get("calendar_ids", []))
        events = fetch_events(calendar_service, calendars, first - timedelta(days=45), first + timedelta(days=200))
        task_lists = chosen_task_lists(tasks_service, config.get("task_lists", []))
        tasks, completed = fetch_tasks(
            tasks_service, task_lists, int(config.get("max_tasks", 18)), int(config.get("max_completed_tasks", 6))
        )
        existing = read_json(DATA_PATH, {})
        weather = fetch_weather(config, existing.get("weather") if isinstance(existing, dict) else None)
        writable = {"owner", "writer"}
        data = {
            "title": config.get("title", "HomeHub"), "subtitle": config.get("subtitle", "Family Organiser"),
            "timezone": tz_name, "status": "online", "updatedAt": datetime.now(timezone.utc).isoformat(),
            "checkedAt": datetime.now(timezone.utc).isoformat(), "lastError": None,
            "config": public_config(config),
            "calendars": [{"id": c.get("id"), "title": c.get("summary", ""), "color": c.get("backgroundColor", "#4f8ee8")} for c in calendars],
            "writableCalendars": [{"id": c.get("id"), "title": c.get("summary", ""), "color": c.get("backgroundColor", "#4f8ee8"), "primary": bool(c.get("primary"))} for c in calendars if c.get("accessRole") in writable],
            "taskLists": [{"id": t.get("id"), "title": t.get("title", "Tasks")} for t in task_lists],
            "events": events, "tasks": tasks, "completedTasks": completed,
            "weather": weather,
        }
        atomic_write_json(DATA_PATH, data, 0o640)
        return data


def current_data() -> dict[str, Any]:
    data = read_json(DATA_PATH, {})
    if not data:
        return base_empty_data()
    # Let settings changes appear immediately, even before the next cloud sync.
    config = load_config()
    data["config"] = public_config(config)
    data["title"] = config.get("title", data.get("title", "HomeHub"))
    data["subtitle"] = config.get("subtitle", data.get("subtitle", "Family Organiser"))
    if "weather" not in data:
        data["weather"] = fetch_weather(config)
    return data


def write_failure(message: str) -> dict[str, Any]:
    data = current_data()
    data["status"] = "setup_required" if not TOKEN_PATH.exists() else "stale"
    data["checkedAt"] = datetime.now(timezone.utc).isoformat()
    data["lastError"] = message
    atomic_write_json(DATA_PATH, data, 0o640)
    return data


def complete_task(task_list_id: str, task_id: str) -> dict[str, Any]:
    if not task_list_id or not task_id:
        raise ValueError("Missing task identifier")
    _, service = services()
    service.tasks().patch(tasklist=task_list_id, task=task_id, body={"status": "completed"}).execute()
    return sync_data()


def create_task(payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title", "")).strip()
    if not title:
        raise ValueError("Task title is required")
    config = load_config()
    _, service = services()
    lists = chosen_task_lists(service, config.get("task_lists", []))
    if not lists:
        raise ValueError("No Google Task list is available")
    requested = str(payload.get("taskListId", "")).strip()
    default_name = str(config.get("default_task_list", "")).casefold()
    task_list = next((item for item in lists if item.get("id") == requested), None)
    if task_list is None and default_name:
        task_list = next((item for item in lists if item.get("title", "").casefold() == default_name), None)
    task_list = task_list or lists[0]
    body: dict[str, Any] = {"title": title}
    due_text = str(payload.get("due", "")).strip()
    if due_text:
        try:
            due_date = datetime.strptime(due_text, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("Invalid task due date") from exc
        body["due"] = datetime(due_date.year, due_date.month, due_date.day, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    service.tasks().insert(tasklist=task_list["id"], body=body).execute()
    return sync_data()


def create_event(payload: dict[str, Any]) -> dict[str, Any]:
    config = load_config()
    title = str(payload.get("title", "")).strip()
    if not title:
        raise ValueError("Event title is required")
    try:
        event_date = datetime.strptime(str(payload.get("date", "")), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Invalid event date") from exc
    tz_name = config.get("timezone", "Australia/Brisbane")
    tz = ZoneInfo(tz_name)
    all_day = bool(payload.get("allDay"))
    calendar_id = str(payload.get("calendarId") or config.get("event_calendar_id") or "primary")
    body: dict[str, Any] = {"summary": title}
    if all_day:
        body["start"] = {"date": event_date.isoformat()}
        body["end"] = {"date": (event_date + timedelta(days=1)).isoformat()}
    else:
        start_minutes = int(payload.get("startMinutes", 540))
        duration = int(payload.get("durationMinutes", 60))
        if not 0 <= start_minutes <= 1439 or duration not in {30, 60, 90, 120, 180, 240}:
            raise ValueError("Invalid event time or duration")
        start_dt = datetime(event_date.year, event_date.month, event_date.day, start_minutes // 60, start_minutes % 60, tzinfo=tz)
        end_dt = start_dt + timedelta(minutes=duration)
        body["start"] = {"dateTime": start_dt.isoformat(), "timeZone": tz_name}
        body["end"] = {"dateTime": end_dt.isoformat(), "timeZone": tz_name}
    calendar_service, _ = services()
    calendar_service.events().insert(calendarId=calendar_id, body=body).execute()
    return sync_data()


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
    config["sleep"] = sleep
    save_config(config)
    data = current_data()
    data["config"] = public_config(config)
    atomic_write_json(DATA_PATH, data, 0o640)
    return data
