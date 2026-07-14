from datetime import datetime

import pytest

from homehub.display_power import desired_power, next_boundary, set_power, should_be_off


def test_cross_midnight_sleep_window():
    schedule = {"enabled": True, "off": "22:00", "on": "06:00"}
    assert should_be_off(datetime(2026, 7, 12, 23, 0), schedule)
    assert should_be_off(datetime(2026, 7, 13, 5, 59), schedule)
    assert not should_be_off(datetime(2026, 7, 13, 6, 0), schedule)
    assert not should_be_off(datetime(2026, 7, 13, 14, 0), schedule)


def test_disabled_and_equal_times_never_sleep():
    assert not should_be_off(datetime.now(), {"enabled": False, "off": "22:00", "on": "06:00"})
    assert not should_be_off(datetime.now(), {"enabled": True, "off": "06:00", "on": "06:00"})


def test_manual_modes_override_the_schedule():
    now = datetime(2026, 7, 14, 23, 0).astimezone()
    schedule = {"enabled": True, "off": "22:00", "on": "06:00"}
    assert desired_power(now, schedule, {"mode": "away"}) == (True, "away")
    assert desired_power(now, schedule, {"mode": "away", "peekUntil": now.timestamp() + 20}) == (False, "preview")
    assert desired_power(now, schedule, {"mode": "home", "overrideOnUntil": now.timestamp() + 3600}) == (False, "manual-wake")


def test_sleep_now_ends_at_the_next_wake_boundary():
    now = datetime(2026, 7, 14, 23, 0)
    assert next_boundary(now, "06:00") == datetime(2026, 7, 15, 6, 0)


def test_automatic_power_method_falls_back_to_wlr_randr(monkeypatch):
    monkeypatch.setattr(
        "homehub.display_power._set_with_wlopm",
        lambda _on: (_ for _ in ()).throw(RuntimeError("protocol unavailable")),
    )
    monkeypatch.setattr(
        "homehub.display_power._set_with_wlr_randr",
        lambda on, known: (["HDMI-A-1"], "wlr-randr"),
    )
    assert set_power(False, "auto") == ("wlr-randr", ["HDMI-A-1"])


def test_selected_power_method_reports_a_real_failure(monkeypatch):
    monkeypatch.setattr(
        "homehub.display_power._set_with_wlopm",
        lambda _on: (_ for _ in ()).throw(RuntimeError("not supported")),
    )
    with pytest.raises(RuntimeError, match="wlopm: not supported"):
        set_power(False, "wlopm")
