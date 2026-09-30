---
name: dashboard-workflow
description: End-to-end dashboard workflow from contract to generated app and full gates.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - dashboard
  - connected device
  - telemetry
---

# Dashboard workflow

The `<name>.dash.json` contract is the source of truth. Generated application
files and reports under `out/` are protected projections.

1. Capture device behavior and interface constraints; request missing facts.
2. Define protocol messages, transports, supported platforms, and widget
   bindings using `dashboard-contract`.
3. Run static gates with `dashboard check`.
4. Generate the application and protocol artifacts with `dashboard generate`.
5. Run full gates in the pinned dashboard-tools image, including real Chromium
   WebRTC loopback and the Servo WebDriver smoke test.
6. After layout changes, use `dashboard screenshot <contract>` to capture
   desktop and mobile renders for advisory visual review.
7. Export the protocol to firmware-agent or write a `<name>.dash-request.json`
   for a sibling when a contract change is needed.

Hazardous commands require confirmation. Never expose device selection through
WebMCP or connect to a device without a user gesture.
