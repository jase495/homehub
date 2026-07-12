# Raspberry Pi 3 performance profile

The v5 UI's full-screen backdrop blur, large shadows, animated composite layers,
fresh WebKit QR request and persistent cache could make a simple settings tap
take several seconds on a Pi 3.

v6 applies these controls:

- no `backdrop-filter` on full-screen modals;
- smaller static shadows and minimal transitions;
- `touch-action: manipulation` on touch targets;
- QR encoded once per setup URL and delivered inline as SVG;
- fresh Cog/WPE runtime cache on every kiosk boot;
- cache-busted dashboard URL by application version;
- background Google/weather sync independent of cached API reads;
- no desktop environment or Chromium.

The target is visual response on the next rendered frame for local modal and
navigation actions. Google writes still depend on network latency and therefore
show an explicit busy state.

