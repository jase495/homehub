from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .config import (
    DISPLAY_STATE_PATH,
    DISPLAY_STATUS_PATH,
    atomic_write_json,
    load_config,
)

VALID_METHODS = {"auto", "wlopm", "wlr-randr"}
DEFAULT_STATE: dict[str, Any] = {
    "mode": "home",
    "sleepUntil": 0.0,
    "overrideOnUntil": 0.0,
    "peekUntil": 0.0,
    "testUntil": 0.0,
}


def minutes(value: str) -> int:
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


def should_be_off(now: datetime, settings: dict[str, Any]) -> bool:
    if not settings.get("enabled", True):
        return False
    off = minutes(str(settings.get("off", "22:00")))
    on = minutes(str(settings.get("on", "06:00")))
    current = now.hour * 60 + now.minute
    if off == on:
        return False
    return current >= off or current < on if off > on else off <= current < on


def next_boundary(now: datetime, value: str) -> datetime:
    boundary_minutes = minutes(value)
    candidate = now.replace(
        hour=boundary_minutes // 60,
        minute=boundary_minutes % 60,
        second=0,
        microsecond=0,
    )
    return candidate if candidate > now else candidate + timedelta(days=1)


def _read_json(path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else dict(default)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return dict(default)


def display_state() -> dict[str, Any]:
    return {**DEFAULT_STATE, **_read_json(DISPLAY_STATE_PATH, DEFAULT_STATE)}


def display_status() -> dict[str, Any]:
    status = _read_json(DISPLAY_STATUS_PATH, {})
    state = display_state()
    return {
        "ok": True,
        "mode": state.get("mode", "home"),
        "currentlyOff": bool(status.get("currentlyOff", False)),
        "reason": status.get("reason", "starting"),
        "configuredMethod": status.get("configuredMethod", "auto"),
        "activeMethod": status.get("activeMethod", ""),
        "outputs": status.get("outputs", []),
        "lastError": status.get("lastError", ""),
        "lastChangedAt": status.get("lastChangedAt"),
        "sleepUntil": float(state.get("sleepUntil", 0) or 0),
        "peekUntil": float(state.get("peekUntil", 0) or 0),
        "testUntil": float(state.get("testUntil", 0) or 0),
    }


def request_display_action(action: str, now: datetime | None = None) -> dict[str, Any]:
    config = load_config()
    timezone = ZoneInfo(str(config.get("timezone", "Australia/Brisbane")))
    local_now = now or datetime.now(timezone)
    timestamp = local_now.timestamp()
    state = display_state()
    sleep = config.get("sleep", {})

    if action == "home":
        state.update({
            "mode": "home",
            "sleepUntil": 0.0,
            "peekUntil": 0.0,
            "testUntil": 0.0,
            # A deliberate early wake remains on until the next normal off time.
            "overrideOnUntil": next_boundary(local_now, str(sleep.get("off", "22:00"))).timestamp(),
        })
    elif action == "sleep_now":
        state.update({
            "mode": "sleep",
            "sleepUntil": next_boundary(local_now, str(sleep.get("on", "06:00"))).timestamp()
            if sleep.get("enabled", True) else 0.0,
            "overrideOnUntil": 0.0,
            "peekUntil": 0.0,
            "testUntil": 0.0,
        })
    elif action == "away":
        state.update({
            "mode": "away",
            "sleepUntil": 0.0,
            "overrideOnUntil": 0.0,
            "peekUntil": 0.0,
            "testUntil": 0.0,
        })
    elif action == "peek":
        state["peekUntil"] = timestamp + 30
    elif action == "test":
        state["testUntil"] = timestamp + 10
        state["peekUntil"] = 0.0
    elif action == "end_peek":
        state["peekUntil"] = 0.0
    else:
        raise ValueError("Unknown screen power action")

    atomic_write_json(DISPLAY_STATE_PATH, state, mode=0o644)
    return state


def desired_power(now: datetime, settings: dict[str, Any], state: dict[str, Any]) -> tuple[bool, str]:
    timestamp = now.timestamp()
    mode = str(state.get("mode", "home"))
    if float(state.get("testUntil", 0) or 0) > timestamp:
        return True, "test"
    if float(state.get("peekUntil", 0) or 0) > timestamp:
        return False, "preview"
    if mode == "away":
        return True, "away"
    if mode == "sleep":
        sleep_until = float(state.get("sleepUntil", 0) or 0)
        if not sleep_until or timestamp < sleep_until:
            return True, "sleep-now"
    if float(state.get("overrideOnUntil", 0) or 0) > timestamp:
        return False, "manual-wake"
    return should_be_off(now, settings), "schedule" if should_be_off(now, settings) else "home"


def _command(arguments: list[str], timeout: int = 8) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, capture_output=True, text=True, timeout=timeout, check=False)


def _wlopm_outputs() -> list[str]:
    if not shutil.which("wlopm"):
        return []
    result = _command([shutil.which("wlopm") or "/usr/bin/wlopm"])
    if result.returncode:
        return []
    outputs = []
    for line in result.stdout.splitlines():
        name = line.strip().split(maxsplit=1)[0] if line.strip() else ""
        if name:
            outputs.append(name)
    return outputs


def _wlr_outputs() -> list[str]:
    if not shutil.which("wlr-randr"):
        return []
    result = _command([shutil.which("wlr-randr") or "/usr/bin/wlr-randr"])
    if result.returncode:
        return []
    return [match.group(1) for line in result.stdout.splitlines() if (match := re.match(r"^(\S+)", line))]


def _set_with_wlopm(on: bool) -> tuple[list[str], str]:
    executable = shutil.which("wlopm")
    outputs = _wlopm_outputs()
    if not executable or not outputs:
        raise RuntimeError("Wayland output-power protocol is not available")
    result = _command([executable, "--on" if on else "--off", "*"])
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "wlopm failed").strip())
    return outputs, "wlopm"


def _set_with_wlr_randr(on: bool, known_outputs: list[str] | None = None) -> tuple[list[str], str]:
    executable = shutil.which("wlr-randr")
    outputs = _wlr_outputs() or list(known_outputs or [])
    if not executable or not outputs:
        raise RuntimeError("KMS output-management protocol is not available")
    errors = []
    for output in outputs:
        result = _command([executable, "--output", output, "--on" if on else "--off"])
        if result.returncode:
            errors.append((result.stderr or result.stdout or f"{output} failed").strip())
    if errors:
        raise RuntimeError("; ".join(errors))
    return outputs, "wlr-randr"


def set_power(on: bool, method: str = "auto", known_outputs: list[str] | None = None) -> tuple[str, list[str]]:
    requested = method if method in VALID_METHODS else "auto"
    candidates = [requested] if requested != "auto" else ["wlopm", "wlr-randr"]
    errors = []
    for candidate in candidates:
        try:
            outputs, active = (
                _set_with_wlopm(on)
                if candidate == "wlopm"
                else _set_with_wlr_randr(on, known_outputs)
            )
            return active, outputs
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            errors.append(f"{candidate}: {exc}")
    raise RuntimeError(" | ".join(errors) or "No display power method is available")


def _normalise_expired_state(now: datetime, state: dict[str, Any]) -> dict[str, Any]:
    timestamp = now.timestamp()
    changed = False
    if state.get("mode") == "sleep" and float(state.get("sleepUntil", 0) or 0) and timestamp >= float(state["sleepUntil"]):
        state.update({"mode": "home", "sleepUntil": 0.0})
        changed = True
    for key in ("peekUntil", "testUntil", "overrideOnUntil"):
        if float(state.get(key, 0) or 0) and timestamp >= float(state[key]):
            state[key] = 0.0
            changed = True
    if changed:
        atomic_write_json(DISPLAY_STATE_PATH, state, mode=0o644)
    return state


def main() -> None:
    time.sleep(3)
    last_desired: bool | None = None
    last_command = 0.0
    active_method = ""
    known_outputs: list[str] = []
    last_error = ""
    last_changed_at: str | None = None

    while True:
        config = load_config()
        settings = config.get("sleep", {})
        timezone = ZoneInfo(str(config.get("timezone", "Australia/Brisbane")))
        now = datetime.now(timezone)
        state = _normalise_expired_state(now, display_state())
        desired_off, reason = desired_power(now, settings, state)
        monotonic_now = time.monotonic()
        should_command = (
            last_desired is None
            or desired_off != last_desired
            or (desired_off and monotonic_now - last_command >= 60)
        )
        if should_command:
            try:
                active_method, known_outputs = set_power(
                    not desired_off,
                    str(settings.get("method", "auto")),
                    known_outputs,
                )
                last_desired = desired_off
                last_command = monotonic_now
                last_error = ""
                last_changed_at = now.isoformat()
            except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
                last_error = str(exc)

        atomic_write_json(DISPLAY_STATUS_PATH, {
            "currentlyOff": bool(last_desired),
            "reason": reason,
            "configuredMethod": settings.get("method", "auto"),
            "activeMethod": active_method,
            "outputs": known_outputs,
            "lastError": last_error,
            "lastChangedAt": last_changed_at,
        }, mode=0o644)
        time.sleep(1)


if __name__ == "__main__":
    main()
