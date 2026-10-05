# MCP server

The stdio server is `dashboard` and exposes 16 tools. It is started by the
plugin launcher and delegates to the same service layer as the CLI. MCP
annotations mark five tools read-only; all other tools can write files, run
gates, or append records.

`contract_path` and optional output paths are workspace-resolved paths.
Unless otherwise noted, tools return a JSON object with `verdict`, `stage`,
and stage-specific fields. A gate operation can return `verdict=fail` while
still returning its complete report and evidence.

| Tool | Read/write | Inputs | Successful output and behavior |
| --- | --- | --- | --- |
| `dashboard_doctor` | Read | None | Toolchain `checks` and a `verdict`; probes expected tool versions. |
| `dashboard_matrix` | Read | None | Implemented OS/browser/transport rows and caveat text. |
| `dashboard_validate` | Read | `contract_path` (required) | Validates contract schema and returns a small contract summary or validation failure. |
| `dashboard_generate` | Write | `contract_path` (required), `out_dir` (optional) | Generates app/projections and returns output directory, paths, and contract digest. |
| `dashboard_check` | Write | `contract_path` (required), `out_dir` (optional) | Runs static checks; writes JSON/Markdown report artifacts. |
| `dashboard_gates` | Write | `contract_path` (required), `out_dir` (optional) | Runs full gates; writes reports and returns image paths and vision-review hints for captured output. |
| `dashboard_smoke` | Write | `contract_path` (required), `out_dir` (optional) | Runs Servo against generated output; returns smoke detail, optional `servo.png`, and vision-review hints. |
| `dashboard_screenshot` | Write | `contract_path` (required), `out_dir` (optional) | Requires fresh generated files; captures desktop/mobile PNGs and returns their paths, hashes, and vision-review hints. |
| `dashboard_protocol_export` | Write | `contract_path` (required), `out_dir` (optional) | Writes and returns the dashboard protocol interchange artifact. |
| `dashboard_request` | Write | `contract_path`, `target`, `risk`, `change`, `rationale` (required); `out_dir`, `failing_checks`, `decision_refs` (optional) | Writes DashboardRequest v2 with contract and optional linked firmware-contract hashes. `target` is one of `bard`, `circuit`, `doc`, `firmware`, `fpga`, `mech`, `prodeng`, `sim`, `wire`, `ux-creator`; high risk requires a known decision event ID. |
| `dashboard_ux_inbox` | Read | `liaison_dir` (optional) | Returns request entries and `new`/`answered`/`stale`/`blocked` counts, malformed paths, other-target count, and `all_final`. |
| `dashboard_ux_respond` | Write | SLP `UxRespondInput` JSON schema: request, status; optional reason, artifacts, gate verdicts, decision/impression refs, user questions, liaison directory | Validates and atomically writes `<id>.ux-response.json`; returns the response and path, or a structured refusal. |
| `dashboard_record_decision` | Write | VRP `DecisionInput` model schema | Appends a decision event; evidence files are hashed by the writer. |
| `dashboard_record_impression` | Write | VRP `StageImpressionInput` model schema | Appends a long-form stage impression bound to file/tree hashes. |
| `dashboard_record_vision_review` | Write | VRP `VisionReviewInput` model schema | Appends an advisory image/event-bound review. |
| `dashboard_records_status` | Read | None | Returns VRP log counts and the most recent Stop-hook verdict. |

Record input schemas are the Pydantic JSON schemas of their corresponding
models. Their fields and validation requirements are summarized in
[Contracts](contracts.md#vrp-v1-records).

## Errors

Service-level validation, filesystem, and gate errors are normally returned as
JSON with `verdict=fail`, a `stage`, and `detail`; a gate failure also includes
the report. Expected record validation and write failures are structured
record-stage failures and do not become an MCP protocol error. If argument
validation or another exception escapes dispatch, the server returns
`verdict=fail`, `detail`, and `error_type` with `isError=true`. An unknown tool
also returns a failure and sets `isError=true`. CLI commands use JSON and
nonzero exit status for failed verdicts.

## Inline images

Only `dashboard_screenshot`, `dashboard_gates`, and `dashboard_smoke` can
return MCP image content. The first content block is always JSON text; its
`images` list is replaced with `inline_images` metadata. Following blocks are
PNG/JPEG image content when eligible. At most eight images of at most 4 MiB
each are attached per call. Oversized or excess files remain in the JSON
metadata with their SHA-256 and a reason; missing files are marked unavailable.
Other tools—including all three VRP record tools—are text-only.

The `vision_review` hints do not contain invented review prose. Each hint
provides `image_path`, `sha256`, a checklist slug (`dashboard-desktop`,
`dashboard-mobile`, `servo-render`, or fallback `dashboard-image`), and
`record_with: "dashboard_record_vision_review"`.
