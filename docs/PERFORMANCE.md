# Raspberry Pi 3 performance profile

HomeHub 1.3 preserves the performance work introduced in 1.1:

- events are indexed by day once instead of rescanned 42 times per render;
- one delegated pointer handler replaces per-cell and per-event listeners;
- month navigation and modal opening perform no network request;
- task completion and event/task creation or editing update the screen optimistically;
- Google writes no longer trigger a full synchronous Calendar and Tasks sync;
- weather polling and rendering are removed;
- the stylesheet uses solid surfaces with no blur, animation or gradients;
- the footer is removed, giving the calendar more height with less paint work;
- the setup QR is cached and loaded only after Settings is already visible;
- Cog/WPE receives a fresh temporary cache each boot.
- network status is a small independent 15-second request; Wi-Fi scanning runs
  only when the Network panel is opened and never blocks calendar interaction.

The performance contract is immediate visual response for navigation, day
opening, Settings, task completion and event submission. Google confirmation
still depends on the network, but it happens after the interface has responded.

For repeatable testing, use a populated month and verify 20 consecutive taps on
Previous, Next, Settings and day cells. No action should need a second press.
