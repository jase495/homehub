#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-/opt/homehub/current}"
/opt/homehub/venv/bin/pip install -q -r "$ROOT/requirements.txt"
install -m 0644 "$ROOT/installer/systemd/homehub-server.service" /etc/systemd/system/homehub-server.service
install -m 0644 "$ROOT/installer/systemd/homehub-kiosk.service" /etc/systemd/system/homehub-kiosk.service
systemctl daemon-reload
systemctl restart homehub-server.service
