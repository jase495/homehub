# Architecture

```text
Google Calendar and Tasks -> background sync -> atomic cache.json
                                      |                 |
setup portal ----------------------> Flask API <---------+
                                                        |
                                                        v
                                               Cage + Cog dashboard

GitHub Release -> signed manifest -> SHA-256 artifact -> staging release
                                                       -> atomic current link
                                                       -> health check
                                                       -> keep or rollback
```

Application releases are immutable under `/opt/homehub/releases`.
`/opt/homehub/current` points to the active version. Writable household state
lives in `/var/lib/homehub`; secrets are mode `0600` and never enter an archive.

The month view is entirely local. Events are indexed by date once when cached
data changes, and the calendar uses one delegated pointer handler rather than a
listener on every cell and event. Month navigation and settings never wait for
Google. Event and task mutations update the display optimistically, then the
backend writes to Google and refreshes the cache in a background thread.

The Pi 3 presentation avoids full-screen blur, animation, large shadows and
layered gradients. Cage/Cog receives a fresh runtime cache each boot, and the QR
SVG is cached by setup URL.

## Security boundaries

- Dashboard mutation routes are LAN-local by deployment but not authenticated.
- Setup routes require the long random token embedded in the physical QR.
- Gmail passwords never pass through HomeHub; Google access uses OAuth tokens.
- OTA accepts only a manifest signed by the enrolled Ed25519 public key and
  verifies the artifact SHA-256 named by that manifest.
- The app runs unprivileged. Narrow root helpers perform update and reboot work.
