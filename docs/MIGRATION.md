# Fresh installation and legacy migration

## Upgrade from signed HomeHub 1.0.0

Reflashing is not required. After the `1.1.0` GitHub Release is published:

1. Open **Settings** on the touchscreen.
2. Tap **Check for update**.
3. Tap **Install 1.1.0**, then tap once more to confirm.
4. Leave HomeHub powered while it verifies, installs and health-checks the release.
5. When the calendar returns, reboot once so the quiet HomeHub boot theme and
   console suppression take effect.

The atomic updater preserves `/var/lib/homehub`, including Google credentials,
tokens, selected calendars and task lists, screen schedule and cached data. It
automatically restores 1.0.0 if the 1.1.0 server fails its health check.

## Recommended: fresh reflash

1. Flash Raspberry Pi OS Lite 32-bit using Raspberry Pi Imager.
2. Configure hostname `homehub`, Wi-Fi, Australia/Brisbane, and SSH.
3. Copy the versioned HomeHub release archive to the Pi and extract it.
4. Run `sudo ./installer/install.sh`.
5. Reboot, scan the first-run QR, and complete the wizard.

This gives the cleanest appliance and avoids carrying forward WebKit caches or
hand-edited v5 files. Google must be connected again unless you separately copy
the old `credentials.json` and `token.json` into `/var/lib/homehub` with owner
`homehub:homehub` and mode `0600`.

## In-place legacy migration

Running the installer on the current Pi detects the direct `/opt/homehub` v5
layout. It stops the two services and moves the whole legacy tree to a timestamped
directory under `/var/backups`. It copies these into `/var/lib/homehub`:

- `config.json`
- `credentials.json`
- `token.json`
- `www/data.json` as `cache.json`

It then installs the release/current layout. The legacy backup is not deleted.

HomeHub 1.1 ignores and removes legacy weather data from the live cache. Existing
Google credentials, selected calendars, selected task lists and screen schedule
remain intact.

## Rollback

OTA rollback is automatic if `/api/health` does not report the new version in
45 seconds. For manual rollback:

```bash
sudo ln -sfn /opt/homehub/releases/PREVIOUS /opt/homehub/current
sudo /opt/homehub/current/installer/activate.sh /opt/homehub/current
sudo systemctl restart homehub-kiosk.service
```
