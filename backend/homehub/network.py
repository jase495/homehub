from __future__ import annotations

import json
import os
import socket
import subprocess
from typing import Any


def local_ipv4() -> str:
    """Return the address other devices should use to reach HomeHub."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("1.1.1.1", 80))
        return str(probe.getsockname()[0])
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        probe.close()


def _run(arguments: list[str], *, input_text: str | None = None, timeout: int = 15) -> str:
    result = subprocess.run(
        arguments,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env={**os.environ, "LC_ALL": "C", "LANG": "C"},
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "NetworkManager command failed").strip())
    return result.stdout


def _split_terse(line: str) -> list[str]:
    fields: list[str] = []
    value: list[str] = []
    escaped = False
    for character in line.rstrip("\r\n"):
        if escaped:
            value.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            fields.append("".join(value))
            value = []
        else:
            value.append(character)
    if escaped:
        value.append("\\")
    fields.append("".join(value))
    return fields


def network_status() -> dict[str, Any]:
    base: dict[str, Any] = {
        "ok": True,
        "available": False,
        "state": "offline",
        "type": "offline",
        "device": "",
        "ssid": "",
        "connection": "",
        "signal": None,
        "security": "",
        "connectivity": "unknown",
        "ip": local_ipv4(),
    }
    try:
        connectivity = _run(["nmcli", "-t", "-f", "CONNECTIVITY", "general"]).strip().lower()
        rows = _run([
            "nmcli", "-t", "-e", "yes", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status",
        ])
    except (FileNotFoundError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return {**base, "error": str(exc)}

    base["available"] = True
    base["connectivity"] = connectivity or "unknown"
    active: tuple[str, str, str] | None = None
    for row in rows.splitlines():
        fields = _split_terse(row)
        if len(fields) < 4 or fields[2].lower() not in {"connected", "connected (externally)"}:
            continue
        device_type = fields[1].lower()
        if device_type == "ethernet":
            active = (fields[0], "ethernet", fields[3])
            break
        if device_type == "wifi" and active is None:
            active = (fields[0], "wifi", fields[3])

    if active:
        base.update({"device": active[0], "type": active[1], "connection": active[2]})
        if active[1] == "wifi":
            try:
                wifi_rows = _run([
                    "nmcli", "-t", "-e", "yes", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list",
                    "ifname", active[0], "--rescan", "no",
                ])
                for row in wifi_rows.splitlines():
                    fields = _split_terse(row)
                    if len(fields) >= 4 and fields[0] == "*":
                        base.update({
                            "ssid": fields[1],
                            "signal": int(fields[2]) if fields[2].isdigit() else None,
                            "security": fields[3],
                        })
                        break
            except (RuntimeError, subprocess.TimeoutExpired):
                base["ssid"] = active[2]

    if not active:
        base["state"] = "offline"
    elif connectivity == "full":
        base["state"] = "online"
    else:
        base["state"] = "limited"
    return base


def scan_wifi() -> dict[str, Any]:
    rows = _run([
        "nmcli", "-t", "-e", "yes", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes",
    ], timeout=30)
    networks: dict[str, dict[str, Any]] = {}
    for row in rows.splitlines():
        fields = _split_terse(row)
        if len(fields) < 4 or not fields[1]:
            continue
        item = {
            "active": fields[0] == "*",
            "ssid": fields[1],
            "signal": int(fields[2]) if fields[2].isdigit() else 0,
            "security": fields[3],
            "secured": bool(fields[3] and fields[3] != "--"),
        }
        existing = networks.get(item["ssid"])
        if existing is None or item["active"] or item["signal"] > existing["signal"]:
            networks[item["ssid"]] = item
    return {
        "ok": True,
        "networks": sorted(networks.values(), key=lambda item: (not item["active"], -item["signal"], item["ssid"].casefold())),
    }


def validate_wifi_request(value: dict[str, Any]) -> dict[str, str]:
    ssid = str(value.get("ssid") or "").strip()
    password = str(value.get("password") or "")
    if not ssid or len(ssid.encode("utf-8")) > 32:
        raise ValueError("Choose a valid Wi-Fi network name")
    if len(password) > 63:
        raise ValueError("Wi-Fi password is too long")
    if password and len(password) < 8:
        raise ValueError("Wi-Fi passwords must contain at least 8 characters")
    return {"ssid": ssid, "password": password}


def connect_wifi(request_file: str) -> None:
    with open(request_file, encoding="utf-8") as handle:
        request = validate_wifi_request(json.load(handle))
    arguments = ["nmcli", "--wait", "30", "--ask", "device", "wifi", "connect", request["ssid"]]
    input_text = None
    if request["password"]:
        # --ask reads the secret from stdin, keeping it out of process lists,
        # service logs and shell history.
        input_text = request["password"] + "\n"
    _run(arguments, input_text=input_text, timeout=45)
