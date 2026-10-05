# Agents

All three agent definitions configure the same `dashboard` stdio MCP server
through `plugins/dashboard/scripts/dashboard_launcher.py mcp_server`. Each
declares its own pre/post-tool hooks; OpenHands plugin-level lifecycle hooks do
not automatically propagate to sub-agents.

| Agent | Model profile | Iteration / budget | SDK tools | Hooks | Responsibility |
| --- | --- | --- | --- | --- | --- |
| `dashboard-architect` | `vibebb-author` | 40 / 3.0 | `terminal`, `file_editor`, `grep`, `glob`, `task_tracker`, `task_tool_set` | Pre: `protect-generated`, `safety-rail`. Post: `record-vision-tool-event`, `record-image-observation`. | Owns the `.dash.json` brief and contract: protocol, transport/platform routes, caveats, widgets, safety declarations, validation, and static-gate resolution. It is the liaison lead for UX-creator requests. |
| `dashboard-developer` | `vibebb-author` | 40 / 3.0 | `terminal`, `file_editor`, `grep`, `glob`, `task_tracker` | Pre: `protect-generated`, `safety-rail`. Post: `record-vision-tool-event`, `record-image-observation`. | Implements runtime behavior and integration, preserves contract-driven generation and safety, runs focused tests and full gates, and records implementation decisions/evidence. |
| `dashboard-review` | `vibebb-review` | 30 / 2.0 | `terminal`, `file_editor`, `grep`, `glob`, `task_tracker` | Pre: `protect-generated`, `safety-rail`. Post: `record-vision-tool-event`, `record-image-observation`. | Independently reviews contract, gates, runtime safety, protocol compatibility, generated-file freshness, and desktop/mobile/Servo/intake visuals. Reports reproducible evidence and does not edit a contract merely to hide a failure. |

The `ensure-llm-profiles` SessionStart hook copies the current OpenHands
`active_profile` into missing `vibebb-author` and `vibebb-review` profiles. It
does not overwrite existing profiles; operators can configure these lanes
independently. The review profile should use a vision-capable model for direct
render inspection.

## Delegation

The architect delegates implementation to `dashboard-developer` and
independent review/vision review to `dashboard-review` through the SDK `task`
tool. Each sub-agent declares its own pre/post-tool hooks because parent/plugin
hooks do not propagate. The current agent frontmatter does not install
`require-records` as a per-agent Stop hook; whether the family should provide
such enforcement for sub-agent sessions remains an explicit improvement
decision (see [Improvement notes](improvement-notes.md)).

## Shared responsibilities

Every agent is instructed to:

- treat the contract as the source of truth and generated files as read-only
  projections;
- keep deterministic gate verdicts authoritative;
- confirm hazardous controls in the UI and preserve that confirmation for
  WebMCP commands;
- leave required decision, stage-impression, and vision-review records;
- respond to UX liaison requests through `dashboard_ux_respond`, never by
  editing a response artifact by hand.

Hook matchers and failure behavior are documented in [Hooks](hooks.md).
