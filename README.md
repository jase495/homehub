# HomeHub

HomeHub turns a Raspberry Pi 3 and a landscape touchscreen into a dedicated,
touch-first family calendar, Google Tasks and compact farm-weather appliance.
It boots Raspberry Pi OS Lite directly into Cage/Cog, keeps a local offline
cache, sleeps the display on a schedule, and exposes a phone-friendly private
setup portal.

This repository is the maintainable successor to the hand-patched HomeHub v5
installation. Version `1.0.0` reconstructs the latest known working behavior
from that installation and makes releases, migrations and rollback explicit.
The prepared OTA source is `jase495/homehub`; it should be a public repository
so the appliance can check releases without storing a GitHub access token.

## Included

- Premium espresso/bronze dark month calendar for a 24-inch touchscreen
- Google Calendar read/create and Google Tasks list/create/complete operations
- On-screen setup QR using inline SVG (reliable in Cog/WPE)
- Phone/PC setup portal with protected setup token
- Visible WPE-compatible sleep/wake selectors and hidden idle cursor
- Scheduled Wayland display power control
- Ecowitt local/cloud adapters, cached readings and observed daily high/low
- Atomic JSON cache writes and offline-state display
- systemd services, Pi installer and legacy v5 migration
- Versioned GitHub Release artifacts with Ed25519 signature verification
- Atomic install switch and automatic rollback after a failed health check

## Important current limitations

These are deliberately visible rather than hidden behind optimistic UI:

1. **Google onboarding still needs a user-owned OAuth Desktop client.** Google
   does not permit HomeHub to collect a Gmail password. Until HomeHub is a
   registered hosted OAuth application, the first authorization uses the
   loopback callback and may require an SSH tunnel. See
   [docs/GOOGLE_SETUP.md](docs/GOOGLE_SETUP.md).
2. **Ecowitt LAN discovery is best-effort.** Gateway firmware exposes different
   endpoint families. Manual gateway IP and Ecowitt cloud fallback are fully
   supported; automatic discovery is marked beta.
3. **OTA signing must be enrolled once.** Generate a signing key, put the
   private key in the GitHub Actions secret, and install the public key on the
   Pi. Unsigned updates are always rejected.

## Development on Windows

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[test]"
$env:HOMEHUB_STATE_DIR = "$PWD\work\state"
python -m homehub.app
```

Open `http://127.0.0.1:8080`. Run tests with `pytest`.

## Pi installation and migration

Build a release archive with `python tools/build_release.py`, copy it to the
Pi, extract it, and run:

```bash
sudo ./installer/install.sh
```

The installer detects a legacy `/opt/homehub` v5 layout, backs it up, migrates
configuration, Google credentials/token and cache into `/var/lib/homehub`, and
installs this version without deleting the backup. Detailed commissioning and
rollback steps are in [docs/MIGRATION.md](docs/MIGRATION.md).

## Repository layout

```text
backend/homehub/       Python app, integrations, cache, setup and updater
frontend/dashboard/   Touch dashboard
frontend/setup/       Phone/PC setup portal
installer/            Pi installer, launcher and systemd units
tools/                Release/signing utilities
tests/                Unit and API tests
docs/                 Architecture, setup, migration and OTA operations
.github/workflows/     CI and signed GitHub Release packaging
```
