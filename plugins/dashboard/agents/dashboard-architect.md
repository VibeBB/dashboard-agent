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
