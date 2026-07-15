#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
test -f "$ROOT/VERSION"
test -f "$ROOT/backend/homehub/app.py"
test -f "$ROOT/frontend/dashboard/index.html"
test -f "$ROOT/installer/activate.sh"
PYTHONPATH="$ROOT/backend" python3 -m compileall -q "$ROOT/backend"
grep -q 'id="settingsModal"' "$ROOT/frontend/dashboard/index.html"
grep -q 'qrSvg' "$ROOT/frontend/dashboard/app.js"
grep -q 'id="dayModal"' "$ROOT/frontend/dashboard/index.html"
grep -q 'id="checkUpdate"' "$ROOT/frontend/dashboard/index.html"
grep -q 'def update_event' "$ROOT/backend/homehub/engine.py"
test -f "$ROOT/installer/configure-appliance.sh"
test -f "$ROOT/installer/plymouth/homehub.script"
test -f "$ROOT/installer/plymouth/homehub-logo.svg"
test -f "$ROOT/installer/homehub-control"
test -f "$ROOT/installer/homehub-network"
python3 -m py_compile "$ROOT/installer/homehub-network"
grep -q 'id="networkModal"' "$ROOT/frontend/dashboard/index.html"
grep -q 'def restore_task' "$ROOT/backend/homehub/engine.py"
grep -q 'def delete_event' "$ROOT/backend/homehub/engine.py"
python3 - "$ROOT/installer/plymouth/homehub-logo.svg" <<'PY'
import sys
import xml.etree.ElementTree as ET

ET.parse(sys.argv[1])
PY
