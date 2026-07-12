from homehub.engine import chosen_task_lists, normalize_rain_mm, normalize_temp


class Result:
    def __init__(self, value): self.value = value
    def execute(self): return self.value


class TaskLists:
    def list(self, **_kwargs):
        return Result({"items": [{"id": "a", "title": "My Tasks"}, {"id": "b", "title": "Wedding Bills"}]})


class Service:
    def tasklists(self): return TaskLists()


def test_task_list_filter_remains_v5_compatible_by_name():
    assert chosen_task_lists(Service(), ["wedding bills"]) == [{"id": "b", "title": "Wedding Bills"}]


def test_weather_unit_normalization():
    assert normalize_temp(68, "F") == 20.0
    assert normalize_rain_mm(1, "in") == 25.4

