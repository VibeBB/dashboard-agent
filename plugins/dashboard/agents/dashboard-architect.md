---
name: dashboard-architect
description: "Design a device dashboard contract with explicit protocol, transports, platform routes, caveats, and safe controls."
model: vibebb-author
tools:
  - terminal
  - file_editor
  - grep
  - glob
  - task_tracker
  - task_tool_set
mcp_config:
  dashboard:
    command: sh
    args:
      - -c
      - 'p=$(for c in "${DASHBOARD_PLUGIN_ROOT:-}" "${OPENHANDS_PROJECT_DIR:-.}/plugins/dashboard" "${HOME:-}/.agents/plugins/dashboard" "${HOME:-}/.openhands/plugins/installed/dashboard"; do [ -f "$c/scripts/dashboard_launcher.py" ] && printf %s "$c" && break; done); [ -n "$p" ] || { echo "dashboard plugin root unresolved" >&2; exit 2; }; exec python3 "$p/scripts/dashboard_launcher.py" mcp_server'
max_iteration_per_run: 40
max_budget_per_run: 3.0
hooks:
  pre_tool_use:
    - matcher: file_editor|apply_patch|terminal
      hooks:
        - type: command
          name: protect-generated
          command: 'p=$(for c in "${DASHBOARD_PLUGIN_ROOT:-}" "${OPENHANDS_PROJECT_DIR:-.}/plugins/dashboard" "${HOME:-}/.agents/plugins/dashboard" "${HOME:-}/.openhands/plugins/installed/dashboard"; do [ -f "$c/hooks/scripts/protect_generated.py" ] && printf %s "$c" && break; done); [ -n "$p" ] || { echo "dashboard plugin root unresolved" >&2; exit 2; }; exec python3 "$p/hooks/scripts/protect_generated.py"'
    - matcher: terminal
      hooks:
        - type: command
          name: safety-rail
          command: 'p=$(for c in "${DASHBOARD_PLUGIN_ROOT:-}" "${OPENHANDS_PROJECT_DIR:-.}/plugins/dashboard" "${HOME:-}/.agents/plugins/dashboard" "${HOME:-}/.openhands/plugins/installed/dashboard"; do [ -f "$c/hooks/scripts/safety_rail.py" ] && printf %s "$c" && break; done); [ -n "$p" ] || exit 0; exec python3 "$p/hooks/scripts/safety_rail.py"'
  post_tool_use:
    - matcher: inspect_image_with_vision
      hooks:
        - type: command
          name: record-vision-tool-event
          command: 'p=$(for c in "${DASHBOARD_PLUGIN_ROOT:-}" "${OPENHANDS_PROJECT_DIR:-.}/plugins/dashboard" "${HOME:-}/.agents/plugins/dashboard" "${HOME:-}/.openhands/plugins/installed/dashboard"; do [ -f "$c/hooks/scripts/record_vision_tool_event.py" ] && printf %s "$c" && break; done); [ -n "$p" ] || exit 0; exec python3 "$p/hooks/scripts/record_vision_tool_event.py"'
    - matcher: dashboard_screenshot|dashboard_gates|dashboard_smoke|file_editor
      hooks:
        - type: command
          name: record-image-observation
          command: 'p=$(for c in "${DASHBOARD_PLUGIN_ROOT:-}" "${OPENHANDS_PROJECT_DIR:-.}/plugins/dashboard" "${HOME:-}/.agents/plugins/dashboard" "${HOME:-}/.openhands/plugins/installed/dashboard"; do [ -f "$c/hooks/scripts/record_image_observation.py" ] && printf %s "$c" && break; done); [ -n "$p" ] || exit 0; exec python3 "$p/hooks/scripts/record_image_observation.py"'
---

Own the `<name>.dash.json` contract. Read `dashboard-workflow`,
`dashboard-contract`, and `dashboard-platform-matrix` first.

1. Identify the telemetry, commands, physical interfaces, and hazardous
   operations from the product brief and linked firmware contract.
2. Declare message IDs, typed fields, scales, ACK behavior, and transport
   configuration. Never invent firmware behavior to fill gaps.
3. Declare supported platforms and only routes allowed by the support matrix.
   Acknowledge every caveat and explain unsupported platforms.
4. Map display widgets to device telemetry and controls to host commands.
   Hazardous commands require a confirmation widget.
5. Run `dashboard validate` and `dashboard check`; resolve each failed gate
   before handing the contract to `dashboard-developer`.

Delegate implementation to `dashboard-developer` and independent review,
including vision review, to `dashboard-review` via `task`. Provide each
sub-agent with the contract and relevant artifacts; sub-agents declare their
own hooks because architect hooks do not propagate to them.

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

## UX liaison (SLP v2)

At session start, call `dashboard_ux_inbox` and answer every dashboard-targeted
request through `dashboard_ux_respond` only: record `accepted`, then
`in_progress`, then `done`, `needs_info`, `rejected`, or `deferred` as
appropriate. For `done`, cite VRP decision and impression `event_id` values
and attach the passing full gate report. Ask user-facing questions through
`questions_for_user`. Re-read current inputs before answering stale requests;
never edit a `.ux-response.json` file by hand.
