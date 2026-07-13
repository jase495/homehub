from datetime import datetime

from homehub.engine import chosen_task_lists, event_body, public_config


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
