from __future__ import annotations

import subprocess
import time
from datetime import datetime

from .config import load_config


def minutes(value: str) -> int:
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


def should_be_off(now: datetime, settings: dict) -> bool:
    if not settings.get("enabled", True):
        return False
    off = minutes(str(settings.get("off", "22:00")))
    on = minutes(str(settings.get("on", "06:00")))
    current = now.hour * 60 + now.minute
    if off == on:
        return False
    return current >= off or current < on if off > on else off <= current < on


def set_power(on: bool) -> bool:
    try:
        result = subprocess.run(["/usr/bin/wlopm", "--on" if on else "--off", "*"], capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def main() -> None:
    time.sleep(4)
    last_desired: bool | None = None
    last_command = 0.0
    while True:
        desired_off = should_be_off(datetime.now(), load_config().get("sleep", {}))
        now = time.monotonic()
        if last_desired is None or desired_off != last_desired or (desired_off and now - last_command >= 60):
            if set_power(not desired_off):
                last_desired, last_command = desired_off, now
        time.sleep(15)


if __name__ == "__main__":
    main()
