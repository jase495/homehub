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
