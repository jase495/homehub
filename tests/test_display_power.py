from datetime import datetime

from homehub.display_power import should_be_off


def test_cross_midnight_sleep_window():
    schedule = {"enabled": True, "off": "22:00", "on": "06:00"}
    assert should_be_off(datetime(2026, 7, 12, 23, 0), schedule)
    assert should_be_off(datetime(2026, 7, 13, 5, 59), schedule)
    assert not should_be_off(datetime(2026, 7, 13, 6, 0), schedule)
    assert not should_be_off(datetime(2026, 7, 13, 14, 0), schedule)


def test_disabled_and_equal_times_never_sleep():
    assert not should_be_off(datetime.now(), {"enabled": False, "off": "22:00", "on": "06:00"})
    assert not should_be_off(datetime.now(), {"enabled": True, "off": "06:00", "on": "06:00"})

