# Improvement notes

These are implementation notes, not current runtime guarantees or work
included in the documentation rebuild.

## Completed in the launcher/runtime refactor

- Removed `auto` from `DASHBOARD_LAUNCH_MODE`; supported modes are `docker`
  (default) and explicit developer-only `host`.
- Removed the unused `protocol_sha` projection.
- Added VRP v1 and SLP v2 as local, validated dashboard-side implementations.
- Added advisory vision-review hints without changing MCP image-path or gate
  verdict behavior.

## Open follow-ups

- Add a mock transport to `runtime/scripts/screenshot.mjs` so screenshots can
  render a connected state and hazard-confirmation state deterministically.
- Include a rendered platform-route matrix as a vision-review point, in
  addition to desktop/mobile/Servo/intake images.
- Add property-based tests for liaison path validation and dependency-graph
  edge cases (cycles, stale inputs, and malformed dependency files). This was
  the earlier deferred testing idea.
- Decide at the VibeBB family level whether to install `require-records` Stop
  hooks on sub-agent definitions. Plugin lifecycle hooks do not propagate to
  sub-agents; the current per-agent hooks enforce generated-file and safety
  guards but not Stop-record requirements.

The deterministic gates and schemas should remain authoritative while these
items are evaluated.
