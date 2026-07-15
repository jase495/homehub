from datetime import datetime

from homehub import engine
from homehub.engine import chosen_task_lists, event_body, fetch_tasks, public_config


class Result:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class TaskLists:
    def list(self, **_kwargs):
        return Result({"items": [
            {"id": "a", "title": "My Tasks"},
            {"id": "b", "title": "Wedding Bills"},
        ]})


class Service:
    def tasklists(self):
        return TaskLists()


def test_task_list_filter_remains_v5_compatible_by_name():
    assert chosen_task_lists(Service(), ["wedding bills"]) == [{"id": "b", "title": "Wedding Bills"}]


def test_task_list_filter_accepts_stable_google_id():
    assert chosen_task_lists(Service(), ["a"]) == [{"id": "a", "title": "My Tasks"}]


def test_event_body_supports_timed_edits():
    calendar, body = event_body({
        "title": "Dentist",
        "date": "2026-07-20",
        "startMinutes": 14 * 60,
        "durationMinutes": 90,
        "calendarId": "family",
    }, {"timezone": "Australia/Brisbane"})
    assert calendar == "family"
    assert body["summary"] == "Dentist"
    assert datetime.fromisoformat(body["start"]["dateTime"]).hour == 14
    assert datetime.fromisoformat(body["end"]["dateTime"]).hour == 15
    assert datetime.fromisoformat(body["end"]["dateTime"]).minute == 30


def test_public_config_is_calendar_tasks_only():
    payload = public_config({
        "title": "HomeHub",
        "timezone": "Australia/Brisbane",
        "weather": {"enabled": True},
    })
    assert "weather" not in payload


class TaskQuery:
    def __init__(self):
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["showCompleted"]:
            return Result({"items": [{
                "id": "done-1", "title": "Finished", "status": "completed", "completed": "2026-07-14T00:00:00Z",
            }]})
        return Result({"items": [
            {"id": "open-1", "title": "First open", "status": "needsAction"},
            {"id": "open-2", "title": "Second open", "status": "needsAction"},
        ]})


class TaskQueryService:
    def __init__(self):
        self.query = TaskQuery()

    def tasks(self):
        return self.query


def test_open_tasks_are_not_filtered_by_completed_min():
    service = TaskQueryService()
    open_tasks, completed = fetch_tasks(service, [{"id": "list-1", "title": "My Tasks"}], 50, 12)
    assert [task["id"] for task in open_tasks] == ["open-1", "open-2"]
    assert [task["id"] for task in completed] == ["done-1"]
    open_call, completed_call = service.query.calls
    assert "completedMin" not in open_call
    assert open_call["showCompleted"] is False
    assert completed_call["showHidden"] is True
    assert completed_call["completedMin"]


class EventMethods:
    def __init__(self):
        self.updated_body = None
        self.deleted = None

    def get(self, **_kwargs):
        return Result({
            "id": "event-1",
            "summary": "Old",
            "start": {"date": "2026-07-20"},
            "end": {"date": "2026-07-21"},
            "location": "Kitchen",
        })

    def update(self, **kwargs):
        self.updated_body = kwargs["body"]
        return Result({"id": "event-1", **kwargs["body"]})

    def delete(self, **kwargs):
        self.deleted = kwargs
        return Result({})


class CalendarService:
    def __init__(self):
        self.methods = EventMethods()

    def events(self):
        return self.methods


def test_event_update_replaces_all_day_start_instead_of_merging(monkeypatch, tmp_path):
    service = CalendarService()
    monkeypatch.setattr(engine, "services", lambda: (service, object()))
    monkeypatch.setattr(engine, "load_config", lambda: {"timezone": "Australia/Brisbane"})
    monkeypatch.setattr(engine, "current_data", lambda: {
        "writableCalendars": [{"id": "family", "title": "Family", "color": "#abc"}],
        "events": [{"id": "event-1", "calendarId": "family"}],
    })
    monkeypatch.setattr(engine, "atomic_write_json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(engine, "queue_sync", lambda: None)
    engine.update_event("event-1", {
        "title": "Timed now",
        "date": "2026-07-20",
        "startMinutes": 600,
        "durationMinutes": 60,
        "calendarId": "family",
        "allDay": False,
    })
    assert "dateTime" in service.methods.updated_body["start"]
    assert "date" not in service.methods.updated_body["start"]
    assert service.methods.updated_body["location"] == "Kitchen"


def test_event_delete_removes_cached_event(monkeypatch):
    service = CalendarService()
    written = {}
    monkeypatch.setattr(engine, "services", lambda: (service, object()))
    monkeypatch.setattr(engine, "current_data", lambda: {
        "events": [
            {"id": "event-1", "calendarId": "family"},
            {"id": "event-2", "calendarId": "family"},
        ],
    })
    monkeypatch.setattr(engine, "atomic_write_json", lambda _path, data, _mode: written.update(data))
    monkeypatch.setattr(engine, "queue_sync", lambda: None)
    engine.delete_event("event-1", "family")
    assert service.methods.deleted["eventId"] == "event-1"
    assert [event["id"] for event in written["events"]] == ["event-2"]
