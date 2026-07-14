# Signed GitHub Releases and OTA

HomeHub uses GitHub Releases as transport, but does not trust GitHub transport
alone. Each release contains:

- `homehub-VERSION.tar.gz`
- `manifest.json` with version, filename and SHA-256
- `manifest.sig`, an Ed25519 signature over the exact manifest bytes

## One-time signing enrollment

Run `python tools/generate_signing_key.py`. It creates:

- `installer/update-public.key` — commit this public key before installing Pi
- `../HomeHub-GitHub-signing-secret.txt` — never commit this file

Add the private value as the repository Actions secret
`HOMEHUB_UPDATE_SIGNING_KEY`. Configure `updates.repository` as `OWNER/REPO`.

## Release

Update `VERSION` and `pyproject.toml`, commit, and tag `vVERSION`. The release
workflow runs tests, packages the source, signs the manifest and creates a GitHub
Release. If the signing secret is absent, release publication fails closed.

## Appliance update transaction

Updates can be checked and installed from either the touchscreen Settings panel
or the QR setup portal. HomeHub checks every six hours and offers **Update now**
or **Later** on the appliance when a newer signed release is found. Both controls
use the same verification transaction:

1. Read the latest GitHub Release metadata.
2. Download and verify `manifest.sig` with the enrolled public key.
3. Download the named artifact and verify its signed SHA-256.
4. Safely extract to a staging directory and run preflight.
5. Atomically switch `/opt/homehub/current`.
6. Restart the server and require matching version health within 45 seconds.
7. Restart the kiosk on success, or restore the previous link on failure.

HomeHub 1.1's server sandbox accidentally blocked its own narrowly scoped update
helper. The one-time move from 1.1.0 to 1.2.0 therefore uses the SSH command in
the migration guide. All later releases use the repaired on-screen transaction.
