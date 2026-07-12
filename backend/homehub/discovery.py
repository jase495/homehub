from __future__ import annotations

import concurrent.futures
import ipaddress
import json
import socket
import urllib.error
import urllib.request
from typing import Any

KNOWN_PATHS = ("/get_livedata_info", "/get_station_info", "/api/livedata")


def local_ipv4() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def _probe(host: str, timeout: float = 0.35) -> dict[str, Any] | None:
    for path in KNOWN_PATHS:
        url = f"http://{host}{path}"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "HomeHub/1"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if "json" not in (response.headers.get("Content-Type") or ""):
                    continue
                payload = json.loads(response.read(64_000))
            text = json.dumps(payload).casefold()
            if any(word in text for word in ("ecowitt", "wh40", "gw1000", "gw1100", "outdoor")):
                return {"ip": host, "url": f"http://{host}", "endpoint": path, "model": "Ecowitt-compatible gateway"}
        except (OSError, ValueError, urllib.error.URLError):
            continue
    return None


def scan_weather_lan() -> list[dict[str, Any]]:
    """Best-effort Ecowitt discovery; manual IP remains the reliable fallback."""
    ip = local_ipv4()
    if ip.startswith("127."):
        return []
    network = ipaddress.ip_network(f"{ip}/24", strict=False)
    hosts = [str(host) for host in network.hosts() if str(host) != ip]
    found: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
        for result in pool.map(_probe, hosts):
            if result:
                found.append(result)
    return found

