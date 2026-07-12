# Architecture

```text
Google Calendar/Tasks ─┐
Ecowitt local/cloud ───┼─> background sync ─> atomic cache.json
                       │                         │
setup portal ──────────┴─> Flask API <──────────┤
                                                 v
                                       Cage + Cog dashboard

GitHub Release -> signed manifest -> SHA-256 artifact -> staging release
                                                       -> atomic current link
                                                       -> health check
                                                       -> keep or rollback
```

The application is immutable and versioned under `/opt/homehub/releases`.
`/opt/homehub/current` points at the active version. All writable household
state lives in `/var/lib/homehub`; secrets are mode `0600` and never enter a
release archive.

The backend uses a background sync thread so network latency does not block
touch UI reads. The dashboard reads the local cache and writes only explicit
event/task/settings actions. Cache files are atomically replaced, so power loss
cannot expose half-written JSON.

The Pi 3 performance profile avoids CSS backdrop blur, large animated composite
layers and repeated QR generation. Cog receives a fresh runtime cache at boot,
while the QR SVG is cached by setup URL.

## Security boundaries

- Dashboard mutation routes are LAN-local by deployment, but are not user-authenticated.
- Setup routes require a long random token embedded in the physical QR.
- Gmail passwords never pass through HomeHub; Google access uses OAuth tokens.
- OTA accepts only a manifest signed by the enrolled Ed25519 public key, then
  verifies the artifact SHA-256 from that signed manifest.
- The setup service runs unprivileged. A narrow root helper queues update work.

