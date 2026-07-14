#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/homehub/current}"

install -m 0755 "$ROOT/installer/homehub-apply-update" /usr/local/sbin/homehub-apply-update
install -m 0755 "$ROOT/installer/homehub-queue-update" /usr/local/sbin/homehub-queue-update
install -m 0755 "$ROOT/installer/homehub-control" /usr/local/sbin/homehub-control
install -m 0644 "$ROOT/installer/systemd/homehub-server.service" /etc/systemd/system/homehub-server.service
install -m 0644 "$ROOT/installer/systemd/homehub-kiosk.service" /etc/systemd/system/homehub-kiosk.service
install -d -m 0755 /etc/homehub
if [[ -f "$ROOT/installer/update-public.key" ]]; then
  install -m 0644 "$ROOT/installer/update-public.key" /etc/homehub/update-public.key
fi

cat >/etc/sudoers.d/homehub-appliance <<'EOF'
homehub ALL=(root) NOPASSWD: /usr/local/sbin/homehub-queue-update *
homehub ALL=(root) NOPASSWD: /usr/local/sbin/homehub-control restart-display
homehub ALL=(root) NOPASSWD: /usr/local/sbin/homehub-control reboot
EOF
chmod 0440 /etc/sudoers.d/homehub-appliance

CMDLINE=/boot/firmware/cmdline.txt
if [[ -f "$CMDLINE" ]]; then
  # Remove every physical virtual-terminal console. Diagnostics remain in the
  # journal (and on the Pi serial console when it is configured), while tty1 is
  # reserved for the Plymouth/Cage appliance presentation.
  sed -E -i 's/(^|[[:space:]])console=tty[0-9]+([[:space:]]|$)/ /g; s/[[:space:]]+/ /g; s/^ //; s/ $//' "$CMDLINE"
  for token in quiet splash plymouth.ignore-serial-consoles loglevel=0 rd.systemd.show_status=false systemd.show_status=false udev.log_level=3 vt.global_cursor_default=0 consoleblank=0 logo.nologo; do
    grep -qw "$token" "$CMDLINE" || sed -i "1 s/$/ $token/" "$CMDLINE"
  done
fi

BOOTCFG=/boot/firmware/config.txt
if [[ -f "$BOOTCFG" ]]; then
  grep -q '^dtparam=watchdog=on' "$BOOTCFG" || printf '\n# HomeHub appliance watchdog\ndtparam=watchdog=on\n' >>"$BOOTCFG"
  grep -q '^disable_splash=1' "$BOOTCFG" || printf '\n# Hide the firmware rainbow screen; Plymouth owns the appliance boot.\ndisable_splash=1\n' >>"$BOOTCFG"
  grep -q '^auto_initramfs=1' "$BOOTCFG" || printf '\n# Load the HomeHub Plymouth theme before root filesystem checks.\nauto_initramfs=1\n' >>"$BOOTCFG"
fi

install -d /etc/systemd/system.conf.d
cat >/etc/systemd/system.conf.d/10-homehub-watchdog.conf <<'EOF'
[Manager]
RuntimeWatchdogSec=20s
RebootWatchdogSec=2min
ShowStatus=false
EOF

if command -v plymouth-set-default-theme >/dev/null 2>&1; then
  THEME=/usr/share/plymouth/themes/homehub
  install -d -m 0755 "$THEME"
  install -m 0644 "$ROOT/installer/plymouth/homehub.plymouth" "$THEME/homehub.plymouth"
  install -m 0644 "$ROOT/installer/plymouth/homehub.script" "$THEME/homehub.script"
  install -m 0644 "$ROOT/installer/plymouth/homehub-logo.svg" "$THEME/homehub-logo.svg"
  if command -v rsvg-convert >/dev/null 2>&1; then
    rsvg-convert --width 720 --height 320 \
      --output "$THEME/homehub-logo.png" "$THEME/homehub-logo.svg"
  else
    echo "Warning: vector boot-logo renderer is unavailable." >&2
  fi
  if plymouth-set-default-theme homehub; then
    update-initramfs -u || echo "Warning: initramfs refresh failed; HomeHub will still boot normally." >&2
  else
    echo "Warning: HomeHub Plymouth theme could not be selected." >&2
  fi
fi

systemctl daemon-reload
systemctl disable --now getty@tty1.service 2>/dev/null || true
systemctl mask getty@tty1.service 2>/dev/null || true
systemctl enable homehub-server.service homehub-kiosk.service
