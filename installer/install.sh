#!/usr/bin/env bash
set -euo pipefail

[[ "${EUID}" -eq 0 ]] || { echo "Run with: sudo ./installer/install.sh"; exit 1; }
SOURCE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '\r\n' <"$SOURCE/VERSION")"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Invalid VERSION: $VERSION" >&2; exit 2; }
ROOT=/opt/homehub
STATE=/var/lib/homehub
export PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-180}"
export PIP_RETRIES="${PIP_RETRIES:-20}"
export PIP_RESUME_RETRIES="${PIP_RESUME_RETRIES:-20}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-/var/cache/homehub-pip}"
WHEELHOUSE="$PIP_CACHE_DIR/wheelhouse"
PREVIOUS_CURRENT=""
INSTALL_FINISHED=0

recover_previous_install() {
  local exit_code=$?
  if (( INSTALL_FINISHED == 0 )); then
    echo "Install did not complete; restoring the previous HomeHub service." >&2
    if [[ -n "$PREVIOUS_CURRENT" && -d "$PREVIOUS_CURRENT" ]]; then
      ln -sfn "$PREVIOUS_CURRENT" "$ROOT/.current.recovery"
      mv -Tf "$ROOT/.current.recovery" "$ROOT/current"
    fi
    systemctl daemon-reload 2>/dev/null || true
    systemctl start homehub-server.service homehub-kiosk.service 2>/dev/null || true
  fi
  exit "$exit_code"
}

trap recover_previous_install ERR

retry() {
  local attempt=1
  local maximum=4
  until "$@"; do
    if (( attempt >= maximum )); then
      echo "Command failed after ${maximum} attempts: $*" >&2
      return 1
    fi
    echo "Network interrupted. Retrying (${attempt}/${maximum}) in 5 seconds..." >&2
    sleep 5
    attempt=$((attempt + 1))
  done
}

echo "Installing HomeHub ${VERSION}"
retry apt-get update
retry env DEBIAN_FRONTEND=noninteractive apt-get install -y \
  cog cage wlopm jq rsync avahi-daemon python3 python3-venv python3-pip \
  ca-certificates curl plymouth plymouth-themes

# Resolve and download the complete dependency set before taking an installed
# appliance offline. If Wi-Fi drops here, the old HomeHub remains untouched.
install -d -m 0755 "$PIP_CACHE_DIR" "$WHEELHOUSE"
PREP_VENV="$(mktemp -d /var/tmp/homehub-pip-prep.XXXXXX)"
python3 -m venv "$PREP_VENV"
retry "$PREP_VENV/bin/pip" install --disable-pip-version-check --upgrade pip wheel
retry "$PREP_VENV/bin/pip" download --disable-pip-version-check --dest "$WHEELHOUSE" -r "$SOURCE/requirements.txt"
rm -rf "$PREP_VENV"
"$SOURCE/installer/preflight.sh" "$SOURCE"

if [[ -L "$ROOT/current" ]]; then
  PREVIOUS_CURRENT="$(readlink -f "$ROOT/current")"
fi
systemctl stop homehub-kiosk.service homehub-server.service 2>/dev/null || true

LEGACY=""
if [[ -d "$ROOT" && ! -d "$ROOT/releases" ]]; then
  LEGACY="/var/backups/homehub-v5-$(date +%Y%m%d-%H%M%S)"
  install -d -m 0700 /var/backups
  mv "$ROOT" "$LEGACY"
  echo "Legacy HomeHub preserved at $LEGACY"
fi

id homehub >/dev/null 2>&1 || useradd --system --home-dir "$STATE" --shell /usr/sbin/nologin homehub
install -d -o root -g root -m 0755 "$ROOT" "$ROOT/releases"
install -d -o homehub -g homehub -m 0750 "$STATE"
install -d -o root -g root -m 0755 "$PIP_CACHE_DIR" "$WHEELHOUSE"

if [[ -n "$LEGACY" ]]; then
  for name in config.json credentials.json token.json; do
    [[ -f "$LEGACY/$name" ]] && install -o homehub -g homehub -m 0600 "$LEGACY/$name" "$STATE/$name"
  done
  [[ -f "$LEGACY/www/data.json" ]] && install -o homehub -g homehub -m 0640 "$LEGACY/www/data.json" "$STATE/cache.json"
fi

DEST="$ROOT/releases/$VERSION"
STAGING="$ROOT/releases/.${VERSION}.installing"
rm -rf "$STAGING"
install -d -m 0755 "$STAGING"
rsync -a --delete --exclude '.git' --exclude '.venv' --exclude 'dist' --exclude 'work' "$SOURCE/" "$STAGING/"
chmod 0755 "$STAGING/installer/"*.sh "$STAGING/installer/kiosk-session.sh"
"$STAGING/installer/preflight.sh" "$STAGING"

python3 -m venv "$ROOT/venv"
retry "$ROOT/venv/bin/pip" install --disable-pip-version-check --upgrade pip wheel
retry "$ROOT/venv/bin/pip" install --disable-pip-version-check --find-links "$WHEELHOUSE" -r "$STAGING/requirements.txt"

rm -rf "$DEST"
mv "$STAGING" "$DEST"
ln -sfn "$DEST" "$ROOT/.current.new"
mv -Tf "$ROOT/.current.new" "$ROOT/current"

timedatectl set-timezone Australia/Brisbane || true
hostnamectl set-hostname homehub || true
"$DEST/installer/configure-appliance.sh" "$DEST"

chown -R root:root "$ROOT/releases"
chown -R homehub:homehub "$STATE"
systemctl restart homehub-server.service homehub-kiosk.service
INSTALL_FINISHED=1
trap - ERR

echo "HomeHub ${VERSION} is starting. The touchscreen will show the calendar when ready."
