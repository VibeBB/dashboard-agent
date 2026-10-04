---
name: dashboard-platform-matrix
description: Select browser routes and acknowledge support caveats.
version: 0.1.1
license: BSD-3-Clause
triggers:
  - platform support
  - browser compatibility
  - Bluefy
  - BSD
---

# Platform matrix

Use `dashboard matrix` and the shared matrix descriptions in
`src/dashboard/matrix.py`. Contracts declare operating systems and browser
routes explicitly. A missing route is unsupported, not an implicit promise.

Linux Web Bluetooth requires its flag/BlueZ caveat. Android USB and Serial have
driver and limited-support caveats. iOS Bluetooth is available only through
Bluefy, with a notification caveat; other iOS browsers can use supported
network transports. iOS and iPadOS must be declared independently, although
their matrix support pairs are identical. Private IPv4, link-local, and `*.local` network routes
require acknowledgement of local-network access.

ChromeOS Chrome supports all five transports. A WebUSB interface may be claimed
by an OS driver, and managed device APIs may be restricted; check your admin
policy. iPadOS Safari and its other listed browsers support WebSocket/WebRTC;
Bluefy adds Bluetooth with the notification caveat. The matrix has no iPadOS
WebUSB or Web Serial routes. BSD Chromium ports offer only WebSocket and
WebRTC. BSD Chromium disables Web Bluetooth, omits Web Serial, and has fake-only
or unverified WebUSB backends; do not offer hardware routes. See
`docs/research/bsd-chromium.md`.

Tauri v2 is an explicit `tauri` shell route, separate from browser hardware
APIs. It supports native BLE on Windows, macOS, Linux, Android, iOS, and
iPadOS; native serial is available on Windows, macOS, Linux, and Android.
Tauri's iOS target covers iPadOS. Linux WebRTC depends on the WebKitGTK build.
Require a user gesture to connect, and never expose device selection through
WebMCP. See the `dashboard-tauri` skill for contract and gate details.
