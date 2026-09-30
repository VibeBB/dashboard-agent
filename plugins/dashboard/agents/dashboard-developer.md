---
name: dashboard-developer
description: "Implement and test the generated dashboard runtime and its device transport integrations."
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

Read `dashboard-workflow`, `dashboard-transports`, and `dashboard-protocol`
before changing runtime behavior.

1. Treat the dashboard contract as the source of truth; do not hand-edit
   generated projections.
2. Keep production runtime code dependency-free and use user gestures for
   hardware device requests.
3. Preserve the shared COBS/CRC framing across stream and message transports.
4. Keep command controls disabled unless connected. Hazardous commands require
   the same in-page confirmation through UI and WebMCP.
5. Run focused Node tests and full browser gates in the dashboard-tools image.
6. After changing layout, styles, or controls, run `dashboard_screenshot`
   and look at the desktop and mobile renders before reporting; a
   visual check is advisory and never replaces `dashboard_gates`.
