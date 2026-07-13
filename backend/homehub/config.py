from __future__ import annotations

import json
import os
import secrets
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(os.getenv("HOMEHUB_APP_ROOT", Path(__file__).resolve().parents[2]))
STATE_DIR = Path(os.getenv("HOMEHUB_STATE_DIR", "/var/lib/homehub"))
CONFIG_PATH = STATE_DIR / "config.json"
CACHE_PATH = STATE_DIR / "cache.json"
CREDENTIALS_PATH = STATE_DIR / "credentials.json"
TOKEN_PATH = STATE_DIR / "token.json"

DEFAULT_CONFIG: dict[str, Any] = {
    # These keys intentionally retain the v5 schema so an installed appliance
    # can migrate without translating household choices or Google list names.
    "title": "HomeHub",
    "subtitle": "",
    "timezone": "Australia/Brisbane",
    "setup_token": "",
    "calendar_ids": [],
    "event_calendar_id": "primary",
    "task_lists": [],
    "default_task_list": "",
    "max_tasks": 12,
    "max_completed_tasks": 4,
    "sync_seconds": 60,
    "display_rotation": 0,
    "milestone": {"enabled": False, "label": "", "date": ""},
    "sleep": {
        "enabled": True,
        "off": "22:00",
        "on": "06:00",
    },
    "updates": {
        "repository": "jase495/homehub",
        "channel": "stable",
        "public_key_path": "/etc/homehub/update-public.key",
        "auto_check": True,
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def atomic_write_json(path: Path, data: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def load_config() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if CONFIG_PATH.exists():
        existing = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config = deep_merge(DEFAULT_CONFIG, existing)
    if not config["setup_token"]:
        config["setup_token"] = secrets.token_urlsafe(24)
    if config != existing:
        atomic_write_json(CONFIG_PATH, config)
    return config


def save_config(update: dict[str, Any]) -> dict[str, Any]:
    config = deep_merge(load_config(), update)
    atomic_write_json(CONFIG_PATH, config)
    return config
