# Fresh installation and migration

## One-time upgrade from HomeHub 1.1.0

Reflashing is not required. Version 1.1.0's service sandbox blocked the update,
restart-display and reboot helpers even though the buttons appeared to succeed.
After the `1.2.0` release is published, run this once over SSH:

```bash
sudo /usr/local/sbin/homehub-apply-update --version 1.2.0
```

Leave HomeHub powered while it downloads, verifies, installs and health-checks
the signed release. Reboot once after the calendar returns so the new
high-resolution boot theme is placed into the initramfs:

```bash
sudo reboot
```

From 1.2.0 onward, signed updates, display restart and reboot work from both the
touchscreen Settings panel and QR setup portal.

## Upgrade from HomeHub 1.2.0 to 1.3.0

Use **Settings → Software update → Check for update → Install 1.3.0** on the
touchscreen, or use the same signed-update controls in the QR portal. HomeHub
keeps Google authorization, selected calendars and task lists, cached data and
screen-power state. The activation step installs NetworkManager if the base image
does not already provide it, then adds only the exact Wi-Fi helper permission.

After the first 1.3 sync, old task-list names are accepted as before. The next
portal save automatically records stable Google task-list IDs. No manual
migration and no reflash are required.

The atomic updater preserves `/var/lib/homehub`, including Google credentials,
tokens, selected calendars and task lists, subtitle, screen schedule, power mode
and cached data. It restores the previous release automatically if the new server
does not pass its version health check.

## Recommended fresh installation

1. Flash Raspberry Pi OS Lite 32-bit using Raspberry Pi Imager.
2. Configure hostname `homehub`, Wi-Fi, Australia/Brisbane, and SSH.
3. Copy and extract the versioned HomeHub release archive on the Pi.
4. Run `sudo ./installer/install.sh`.
5. Reboot, scan the first-run QR, and complete the wizard.

The installer retries interrupted downloads, stages and preflights the new
release before switching it live, and does not remove an earlier working release.

## In-place legacy v5 migration

Running the installer on the direct `/opt/homehub` v5 layout stops the services
and moves the legacy tree to a timestamped directory under `/var/backups`. It
copies `config.json`, `credentials.json`, `token.json`, and cached `data.json`
into the managed state directory before starting the versioned release layout.

HomeHub ignores legacy weather configuration and data. Google credentials,
selected calendars, task lists and screen schedule remain intact.

## Manual rollback

OTA rollback is automatic. For an explicit rollback:

```bash
sudo ln -sfn /opt/homehub/releases/PREVIOUS /opt/homehub/current
sudo /opt/homehub/current/installer/activate.sh /opt/homehub/current
sudo systemctl restart homehub-kiosk.service
```
