# HomeHub

HomeHub turns a Raspberry Pi 3 and a landscape touchscreen into a dedicated,
touch-first family calendar and Google Tasks appliance. It boots Raspberry Pi
OS Lite into Cage/Cog, keeps a local offline cache, sleeps the display on a
schedule, and exposes a phone-friendly private setup portal.

Version `1.3.0` is the calendar-and-tasks data-integrity release. It fixes the
Google Tasks query that could hide open jobs, adds complete task and event
management, repairs all-day event editing, and makes network status and Wi-Fi
setup available directly on the appliance.

## Included

- Premium espresso/bronze dark month calendar for a 24-inch touchscreen
- Dense single-line event rows with up to six visible events per day
- Tap a day for its complete agenda, then add or edit an event
- Google Calendar read/create/edit/delete with safe all-day/timed conversion
- Google Tasks list/create/edit/complete/undo/delete, with 50 open jobs cached
- Immediate month navigation, modal opening and optimistic cloud writes
- On-screen and phone/PC access to signed OTA updates
- Prominent current date, smaller time and a visible household subtitle
- Colour-coded Wi-Fi/Ethernet status, SSID display and touchscreen Wi-Fi setup
- Inline SVG setup QR, visible sleep selectors and globally hidden mouse cursor
- Automatic, Wayland and KMS screen-power methods with a 10-second test
- Home, Sleep now and persistent Away modes with touch-to-preview resume
- Six-hour signed update checks with Update now or Later notification
- Atomic JSON cache writes and offline-state display
- High-resolution vector-derived Plymouth boot screen and hardened Pi installer
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
An in-place 1.2 upgrade also installs NetworkManager when needed; no reflash is
required.
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
