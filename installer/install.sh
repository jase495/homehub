#!/usr/bin/env bash
set -euo pipefail

[[ "${EUID}" -eq 0 ]] || { echo "Run with: sudo ./installer/install.sh"; exit 1; }
SOURCE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '\r\n' <"$SOURCE/VERSION")"
ROOT=/opt/homehub
STATE=/var/lib/homehub

echo "Installing HomeHub ${VERSION}"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  cog cage wlopm jq rsync avahi-daemon python3 python3-venv python3-pip ca-certificates curl

systemctl stop homehub-kiosk.service homehub-server.service 2>/dev/null || true

# Preserve the hand-patched v5 installation wholesale before introducing the
# release/current/state layout. Nothing is deleted by the migration.
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

if [[ -n "$LEGACY" ]]; then
  for name in config.json credentials.json token.json weather-extrema.json; do
    [[ -f "$LEGACY/$name" ]] && install -o homehub -g homehub -m 0600 "$LEGACY/$name" "$STATE/$name"
  done
  [[ -f "$LEGACY/www/data.json" ]] && install -o homehub -g homehub -m 0640 "$LEGACY/www/data.json" "$STATE/cache.json"
fi

DEST="$ROOT/releases/$VERSION"
install -d -m 0755 "$DEST"
rsync -a --delete --exclude '.git' --exclude '.venv' --exclude 'dist' --exclude 'work' "$SOURCE/" "$DEST/"
ln -sfn "$DEST" "$ROOT/.current.new"
mv -Tf "$ROOT/.current.new" "$ROOT/current"

python3 -m venv "$ROOT/venv"
"$ROOT/venv/bin/pip" install --upgrade pip wheel
"$ROOT/venv/bin/pip" install -r "$DEST/requirements.txt"

install -m 0755 "$DEST/installer/homehub-apply-update" /usr/local/sbin/homehub-apply-update
install -m 0755 "$DEST/installer/homehub-queue-update" /usr/local/sbin/homehub-queue-update
install -m 0644 "$DEST/installer/systemd/homehub-server.service" /etc/systemd/system/homehub-server.service
install -m 0644 "$DEST/installer/systemd/homehub-kiosk.service" /etc/systemd/system/homehub-kiosk.service
install -d -m 0755 /etc/homehub
if [[ -f "$DEST/installer/update-public.key" ]]; then
  install -m 0644 "$DEST/installer/update-public.key" /etc/homehub/update-public.key
fi

cat >/etc/sudoers.d/homehub-appliance <<'EOF'
homehub ALL=(root) NOPASSWD: /usr/local/sbin/homehub-queue-update *
homehub ALL=(root) NOPASSWD: /bin/systemctl restart homehub-kiosk.service, /usr/bin/systemctl restart homehub-kiosk.service
homehub ALL=(root) NOPASSWD: /sbin/reboot, /usr/sbin/reboot
EOF
chmod 0440 /etc/sudoers.d/homehub-appliance

timedatectl set-timezone Australia/Brisbane || true
hostnamectl set-hostname homehub || true
CMDLINE=/boot/firmware/cmdline.txt
if [[ -f "$CMDLINE" ]]; then
  for token in quiet loglevel=3 vt.global_cursor_default=0 consoleblank=0 systemd.show_status=false logo.nologo; do
    grep -qw "$token" "$CMDLINE" || sed -i "1 s/$/ $token/" "$CMDLINE"
  done
fi
BOOTCFG=/boot/firmware/config.txt
if [[ -f "$BOOTCFG" ]] && ! grep -q '^dtparam=watchdog=on' "$BOOTCFG"; then
  printf '\n# HomeHub appliance watchdog\ndtparam=watchdog=on\n' >>"$BOOTCFG"
fi
install -d /etc/systemd/system.conf.d
cat >/etc/systemd/system.conf.d/10-homehub-watchdog.conf <<'EOF'
[Manager]
RuntimeWatchdogSec=20s
RebootWatchdogSec=2min
EOF

chown -R root:root "$ROOT/releases"
chown -R homehub:homehub "$STATE"
chmod 0755 "$DEST/installer/"*.sh "$DEST/installer/kiosk-session.sh"
systemctl daemon-reload
systemctl disable --now getty@tty1.service 2>/dev/null || true
systemctl mask getty@tty1.service
systemctl enable homehub-server.service homehub-kiosk.service
systemctl restart homehub-server.service homehub-kiosk.service

echo "HomeHub ${VERSION} is starting. The touchscreen will show the first-run QR wizard."
