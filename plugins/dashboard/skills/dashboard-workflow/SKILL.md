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

## Records you must leave (VibeBB Record Protocol — mandatory, unprompted)

Record a `dashboard_record_decision` for every non-trivial choice: transport
per platform/browser route and why (Web Bluetooth vs Web Serial vs WebUSB vs
Tauri), acknowledged caveats, framing and `max_frame_bytes`, ACK timeouts and
reconnect behavior, widget kind per field, hazard and confirmation on
controls, WebMCP exposure (`expose_controls`), Tauri shell/targets, WASM
modules, and firmware contract binding. Include first principles, at least
two options with pros and cons, the chosen option, a rationale of 200+
characters, evidence, assumptions, unknowns, residual risks, and a revisit
trigger.

Close each stage with `dashboard_record_impression` after its final
regeneration: `contract` (.dash.json authored and validated), `generate`,
`gates` (static and full), `visual-review` (screenshots and Servo), `liaison`
(UX requests answered), and `handoff`. Bind the relevant artifact paths and
write at least 400 characters and three distinct sentences about what you
noticed, what works, what worries you, how a maker or end user operating the
device would read it, and what to do next.

Record `dashboard_record_vision_review` every time you look at a desktop or
mobile screenshot, Servo render, or intake image. Judge accuracy against the
contract (every widget, label, and unit; visually distinct hazardous controls;
obvious connection state; clear unsupported-platform message), ambiguity,
design intent, and usefulness to the end user operating the device—not only
legibility. Use checklist slugs `dashboard-desktop`, `dashboard-mobile`,
`servo-render`, or `intake-image`, bind `image_path` or the vision event, and
write at least 400 characters and three sentences. Records are advisory;
deterministic gates remain authoritative. `dashboard_records_status` shows
what is still owed.
