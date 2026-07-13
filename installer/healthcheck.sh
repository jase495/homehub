#!/usr/bin/env bash
set -euo pipefail
curl -fsS http://127.0.0.1:8080/api/health
echo
curl -fsS http://127.0.0.1:8080/api/data | python3 -c 'import json,sys; d=json.load(sys.stdin); print("status:",d.get("status"),"events:",len(d.get("events",[])),"tasks:",len(d.get("tasks",[])))'
