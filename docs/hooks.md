# Hooks

Plugin-level hooks are defined in `plugins/dashboard/hooks/hooks.json`.
Commands resolve the installed plugin in this order: `$DASHBOARD_PLUGIN_ROOT`,
`$OPENHANDS_PROJECT_DIR/plugins/dashboard`, `$HOME/.agents/plugins/dashboard`,
`$HOME/.openhands/plugins/installed/dashboard`, then
`$HOME/plugins/installed/dashboard` and
`$OH_PERSISTENCE_DIR/plugins/installed/dashboard`. The last two candidates
resolve the plugin inside an OpenHands docker conversation runtime (inner
`HOME=/var/openhands/.openhands`), where `dashboard_launcher.py` then fails
closed with guidance — docker is unavailable there by design.

## Plugin lifecycle hooks

| Event | Matcher | Hook/script | Behavior and failure mode | Scope |
| --- | --- | --- | --- | --- |
| `session_start` | `*` | `dashboard-doctor` → launcher `doctor --warn` | Probes the pinned toolchain. If the launcher resolves, `--warn` returns probe failures as JSON without stopping the session; an unresolved plugin root exits 1. | Repository-specific launcher entry. |
| `session_start` | `*` | `intake-attachments` → `hooks/scripts/intake_attachments.py` | Copies supported user image attachments into hash-named `intake/attachments/` files and appends their provenance to `manifest.jsonl`. Missing event data is a no-op; errors are reported on stderr and the hook exits 0. | Repository-specific. |
| `session_start` | `*` | `ensure-llm-profiles` → `hooks/scripts/ensure_llm_profiles.py` | Copies the active OpenHands profile to missing `vibebb-author`, `vibebb-review`, and `oracle` slots; never overwrites existing profiles. Reports missing/unreadable profiles and vision capability (probed for the two VibeBB lanes only); advisory and always exits 0. | Shared canonical hook. |
| `session_start` | `*` | `ensure-agent-profiles` → `hooks/scripts/ensure_agent_profiles.py` | Writes `~/.openhands/agent-profiles/vibebb-dashboard.json` when missing: `agent_kind=openhands`, `llm_profile_ref=vibebb-author`, MCP scoped to `dashboard`, no secrets. Advisory and always exits 0. | Shared canonical hook. |
| `session_start` | `*` | `require-records` → `hooks/scripts/require_records.py session-start` | Initializes the session marker used to relate changed artifacts and observations to the current session. Missing plugin root is a no-op; script errors are handled as a skipped, non-blocking hook. | Shared canonical hook. |
| `user_prompt_submit` | `*` | `intake-attachments` | Repeats attachment intake for newly supplied images. Failures are logged but non-blocking. | Repository-specific. |
| `pre_tool_use` | `file_editor\|apply_patch\|terminal` | `protect-generated` → `hooks/scripts/protect_generated.py` | Blocks edits to generated dashboard projections, VRP logs/status, and liaison responses; these must be regenerated or written through tools. Invalid hook JSON or unresolved plugin root exits 2; a protected write exits 2; unrelated actions pass. | Repository-specific. |
| `pre_tool_use` | `terminal` | `safety-rail` → `hooks/scripts/safety_rail.py` | Denies the explicit destructive-command denylist, including destructive root/home removal, block-device writes, broad process kills, and prohibited git operations. Invalid input or a denied command exits 2; other commands pass. | Shared canonical hook. |
| `stop` | `*` (first) | `require-records` → `hooks/scripts/require_records.py stop` | Revalidates VRP records; checks changed protected artifacts, required stage impressions/decisions, and observed-image vision reviews; writes `records-status.json`. Missing records deny Stop at most twice. After the configured limit, it records the remaining gap and allows finishing. Missing plugin root and caught hook errors are non-blocking. | Shared canonical hook. |
| `stop` | `*` | `intake-attachments` | Final attachment intake before status reporting; errors are non-blocking. | Repository-specific. |
| `stop` | `*` | `report-dashboard-status` → `hooks/scripts/report_dashboard_status.py` | Adds dashboard gate/report and pending dashboard-targeted UX request status to the Stop context. An unexpected failure is written to stderr and exits 1. | Repository-specific. |
| `post_tool_use` | `inspect_image_with_vision` | `record-vision-tool-event` → `hooks/scripts/record_vision_tool_event.py` | Appends tool/event/image provenance to `observations/dashboard/vision-tool-events.jsonl` for later review. It is best effort; logging errors are reported but exit 0. | Repository-specific. |
| `post_tool_use` | `dashboard_screenshot\|dashboard_gates\|dashboard_smoke\|file_editor` | `record-image-observation` → `hooks/scripts/record_image_observation.py` | Records images exposed by dashboard tools and images viewed with `file_editor` command `view` under `observations/dashboard/image-observations.jsonl`; supports captured app images and intake images. It is best effort; logging errors are reported but exit 0. | Repository-specific. |

`records-policy.json` sets `max_stop_denials` to 2. Stop-hook records are
advisory, and an exhausted denial budget does not change any gate result.

## Per-agent hooks

Each of the three agent frontmatter files repeats these tool hooks because
plugin-level hooks do not propagate to spawned agents:

| Event | Matcher | Script | Behavior/failure |
| --- | --- | --- | --- |
| `pre_tool_use` | `file_editor\|apply_patch\|terminal` | `protect_generated.py` | Same protected-path guard and deny behavior as the plugin hook. An unresolved root is a hard denial for this tool hook. |
| `pre_tool_use` | `terminal` | `safety_rail.py` | Same shared destructive-command guard; denied commands exit 2. Missing script/root is a no-op for this safety hook. |
| `post_tool_use` | `inspect_image_with_vision` | `record_vision_tool_event.py` | Best-effort image/vision tool event logging. |
| `post_tool_use` | `dashboard_screenshot\|dashboard_gates\|dashboard_smoke\|file_editor` | `record_image_observation.py` | Best-effort dashboard/intake image observation logging. |

No agent frontmatter currently declares a `require-records` Stop hook. Whether
to add per-sub-agent record enforcement is a family-level decision tracked in
[Improvement notes](improvement-notes.md).

## Shared-hook normalized AST hashes

`scripts/check_shared_hooks.py` checks these canonical normalized AST
SHA-256 digests (not raw file hashes):

| Hook file | Canonical normalized AST SHA-256 | Required by this plugin |
| --- | --- | --- |
| `ensure_llm_profiles.py` | `8cb8ea31ef79d00a26e4a8b0259f2a668e6dc0d976fba1d61f019ada95b94aa6` | Yes |
| `ensure_agent_profiles.py` | `81cf8a503e249c29e4a67901b58004bde0037e4e7d969b3287f5087ca7e25152` | Yes |
| `_provenance.py` | `129bc2a98d85c300026ef50dabe90940c4b3c0e7054fb02d52d1d1dee3b18672` | No |
| `safety_rail.py` | `1a9f3f72fec383f046db2ca8805a7190c33daa86daf42f06c3cd27e3f8be245b` | Yes |
| `_records.py` | `f793baeb1f3194b3e519ddc86c01928439a84a5531925303593b11dc473b65ad` | Yes |
| `require_records.py` | `f16ef9a9e8a53a3228d386246bb81564bb94ccf7cbfe4ac694f1ff03098680cf` | Yes |

Changes to shared hooks must preserve the canonical hash across the VibeBB
plugin family and update `EXPECTED` in the check script. Attachment intake,
generated-file protection, dashboard status reporting, and image observation
hooks are intentionally repository-specific. Shared workflow copies have a
separate `scripts/check_shared_workflows.py` guard.
