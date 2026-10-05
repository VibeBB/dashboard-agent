# Improvement notes

This file tracks completed improvements and open follow-ups.

## Completed improvements

- Removed `auto` from `DASHBOARD_LAUNCH_MODE`; supported modes are `docker`
  (default) and explicit developer-only `host`.
- Removed the unused `protocol_sha` projection.
- Added VRP v1 and SLP v2 as local, validated dashboard-side implementations.
- Added advisory vision-review hints without changing MCP image-path or gate
  verdict behavior.
- Render contract units in telemetry values, gauge/chart readouts, and
  human-readable command controls; sliders show their current value and unit.
- Distinguish hazardous cards and buttons, show the confirmation badge, and
  identify unavailable routes with human-readable transport labels.

## Open follow-ups

- Add a mock transport to `runtime/scripts/screenshot.mjs` so screenshots can
  render a connected state and hazard-confirmation state deterministically.
- Include a rendered platform-route matrix as a vision-review point, in
  addition to desktop/mobile/Servo/intake images.
- Add property-based tests for liaison path validation and dependency-graph
  edge cases (cycles, stale inputs, and malformed dependency files). This was
  the earlier deferred testing idea.
- Investigate the Servo render showing both `websocket (chrome)` and
  `websocket (tauri)` connect buttons; their route behavior is unchanged.
- Decide at the VibeBB family level whether to install `require-records` Stop
  hooks on sub-agent definitions. Plugin lifecycle hooks do not propagate to
  sub-agents; the current per-agent hooks enforce generated-file and safety
  guards but not Stop-record requirements.

The deterministic gates and schemas should remain authoritative while these
items are evaluated.
