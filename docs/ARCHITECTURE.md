# Architecture

```text
Google Calendar and Tasks -> background sync -> atomic cache.json
                                      |                 |
setup portal ----------------------> Flask API <---------+
NetworkManager <--- narrow helper -----^                 |
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
- The app runs unprivileged. Narrow root helpers perform update, reboot and
  explicitly requested Wi-Fi connection changes. Wi-Fi secrets are written to
  a mode-0600 handoff file, never passed on the process command line, and removed
  after NetworkManager consumes them.

## Google Tasks consistency

Open and completed tasks are deliberately fetched in separate paginated API
queries. Open tasks have no completion timestamp, while first-party completed
tasks are hidden rows. Mixing both into a request constrained by `completedMin`
filters out open jobs. HomeHub therefore applies that constraint and
`showHidden` only to the completed-task query.

Task-list configuration stores stable Google list IDs as of 1.3 while still
accepting list titles saved by v5, 1.0, 1.1 or 1.2.

## Network management

The header polls read-only NetworkManager status every 15 seconds and shows
Ethernet, Wi-Fi SSID, limited connectivity or offline state. Wi-Fi scans require
the physical QR setup token. A connection request is validated by the
unprivileged server, written to `/var/lib/homehub/network-request.json`, then
handed to the exact sudo-allowed `homehub-network apply` action. The helper
schedules the switch after returning HTTP so the setup page can display a useful
handoff message before its old connection disappears.

## Display power state

The display worker runs inside Cage's Wayland session. Automatic mode first
tries the output-power protocol (`wlopm`) and falls back to KMS output management
(`wlr-randr`), recording the active method, outputs and any error in
`/var/lib/homehub/display-status.json`. Household intent is stored separately in
`display-state.json` so Away mode survives reboots. Sleep now expires at the next
configured wake time; Away never expires. A touch while the output is asleep
temporarily wakes it to a Resume Home screen.
