#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/homehub/current}"
export PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-180}"
export PIP_RETRIES="${PIP_RETRIES:-20}"
export PIP_RESUME_RETRIES="${PIP_RESUME_RETRIES:-20}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-/var/cache/homehub-pip}"
install -d -m 0755 "$PIP_CACHE_DIR"

install_dependencies() {
  local attempt
  for attempt in 1 2 3 4; do
    if /opt/homehub/venv/bin/pip install -q --disable-pip-version-check -r "$ROOT/requirements.txt"; then
      return 0
    fi
    echo "Dependency download interrupted. Retrying (${attempt}/4)..." >&2
    sleep 5
  done
  return 1
}

install_dependencies

if ! command -v plymouth-set-default-theme >/dev/null 2>&1; then
  for attempt in 1 2 3; do
    apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y plymouth plymouth-themes && break
    echo "Boot theme package install interrupted. Retrying (${attempt}/3)..." >&2
    sleep 5
  done
fi

"$ROOT/installer/configure-appliance.sh" "$ROOT"
systemctl restart homehub-server.service
