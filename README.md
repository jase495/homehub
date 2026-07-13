# HomeHub

HomeHub turns a Raspberry Pi 3 and a landscape touchscreen into a dedicated,
touch-first family calendar and Google Tasks appliance. It boots Raspberry Pi
OS Lite into Cage/Cog, keeps a local offline cache, sleeps the display on a
schedule, and exposes a phone-friendly private setup portal.

Version `1.1.0` is the calendar-first performance release. It removes weather,
reclaims that space for tasks, adds a dense month view and daily agenda, supports
event editing, and makes local touch actions immediate on Pi 3 hardware.

## Included

- Premium espresso/bronze dark month calendar for a 24-inch touchscreen
- Dense single-line event rows with up to six visible events per day
- Tap a day for its complete agenda, then add or edit an event
- Google Calendar read/create/edit and Google Tasks list/create/complete
- Immediate month navigation, modal opening and optimistic cloud writes
- On-screen and phone/PC access to signed OTA updates
- Inline SVG setup QR, visible sleep selectors and hidden mouse cursor
- Scheduled Wayland display power control
- Atomic JSON cache writes and offline-state display
- Quiet Plymouth boot screen, systemd services and hardened Pi installer
- Versioned GitHub Release artifacts with Ed25519 verification and rollback

## Important limitation

Google onboarding still needs a user-owned OAuth Desktop client. Google does
not permit HomeHub to collect a Gmail password. Until HomeHub has a registered,
hosted OAuth application, first authorization uses Google's loopback callback
and may require an SSH tunnel. See [Google setup](docs/GOOGLE_SETUP.md).

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

Build a release archive with `python tools/build_release.py`, copy it to the Pi,
extract it, and run:

```bash
sudo ./installer/install.sh
```

The installer retries interrupted package downloads, stages and preflights the
release before switching it live, and preserves Google credentials and settings.
See [migration](docs/MIGRATION.md) for fresh and in-place paths.

## Repository layout

```text
backend/homehub/       Python app, Google integration, cache, setup and updater
frontend/dashboard/   Touch dashboard
frontend/setup/       Phone/PC setup portal
installer/            Pi installer, boot theme, launcher and systemd units
tools/                Release/signing utilities
tests/                Unit and API tests
docs/                 Architecture, setup, migration and OTA operations
.github/workflows/     CI and signed GitHub Release packaging
```
