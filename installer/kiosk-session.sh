#!/usr/bin/env bash
set -u

export HOME=/run/homehub-kiosk-home
export XDG_CACHE_HOME=/run/homehub-kiosk-cache
export XDG_CONFIG_HOME=/run/homehub-kiosk-config
export XDG_DATA_HOME=/run/homehub-kiosk-data
install -d -m 0700 "$HOME" "$XDG_CACHE_HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME"

/opt/homehub/venv/bin/python -m homehub.display_power &
POWER_PID=$!
trap 'kill "$POWER_PID" 2>/dev/null || true' EXIT INT TERM

VERSION=$(tr -d '\r\n' </opt/homehub/current/VERSION)
exec /usr/bin/cog --platform=wl "http://127.0.0.1:8080/?v=${VERSION}"
