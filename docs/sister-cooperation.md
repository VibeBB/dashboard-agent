# Sister-agent cooperation

Dashboard interoperability uses copied, hash-bound JSON artifacts and task
delegation, not imports from another agent's Python package or edits to sister
repositories.

## Imports and firmware binding

Contract `imports[]` accepts `from_system` values `firmware`, `circuit`,
`ux-creator`, `mech`, `wire`, `bard`, `fpga`, `sim`, `prodeng`, and `doc`.
Each entry identifies a copied artifact and its lowercase SHA-256. Relative
paths resolve from the `.dash.json` file; absolute paths pass through
unchanged. Static gate `imports.sha256` checks that the file exists and still
matches. When the artifact has an interchange envelope v3 sidecar
(`<artifact>.provenance.json`), the gate also checks it against the pinned
sha256, its sources and the `from_system` producer's intact VRP decision log;
any non-pass status fails. Authored sister contracts carry no sidecar and are
pinned by sha256 alone.

`device.firmware_contract` and `device.firmware_sha256` must be set together.
Relative firmware paths resolve from the `.dash.json` file; absolute paths
pass through unchanged. The `firmware.link` gate verifies the hash and checks
that the referenced JSON has `system: "firmware"` and
`artifact_kind: "firmware_contract"`. Dashboard generation and outbound
requests use this explicit binding rather than assuming a firmware
implementation from a product description.

A `fault` widget shows a status field as a fault for the user or service
technician. The firmware owns the table: `faults[]` in the pinned firmware
contract (`code` 1–65535, `name`, `severity`, `action`). The
`service.faults` gate fails when the widget has no firmware link, when the
linked contract has changed or cannot be read, when the table is missing,
empty, malformed or repeats a code, when the source field is not an unsigned
integer, or when a code does not fit that field. The generator embeds the
table as `faults` in `dashboard.config.json` and refuses an unusable one. At
runtime, code `0` reads "No fault"; a known code reads
`name (severity): action`; any other code reads "Unknown fault code N".

## Outbound DashboardRequest v2

`dashboard request` / `dashboard_request` writes
`<design>.<id>.dash-request.json` for one of `bard`, `circuit`, `doc`,
`firmware`, `fpga`, `mech`, `prodeng`, `sim`, `wire`, or `ux-creator`.
It contains the requested change/rationale, risk, failed gate IDs, dashboard
contract SHA-256, input path/hash records, and VRP decision event IDs. The
dashboard contract is always bound; a linked firmware contract is included
when configured. Decision refs must exist in `observations/dashboard/
decisions.jsonl`; high-risk requests require at least one. Refs resolve only
against an intact VRP v2 chain: a log that fails `verify_log` (forged, edited
or truncated lines) refuses every ref into it, for requests and liaison
responses alike.

Never change sister input files to make a request pass. `failing_checks`
describes observed deterministic evidence; it does not authorize a gate
exception.

## Inbound UX liaison: SLP v2

UX-creator requests use `<id>.ux-request.json`; dashboard replies are
`<id>.ux-response.json` in the same liaison directory, normally `liaison/`.
`dashboard_ux_inbox` scans sorted request files. Malformed JSON, schema errors,
ID/filename mismatch, invalid high-risk UX binding/job reference, unreadable
inputs, or invalid dashboard responses are surfaced in `malformed`; a bad
response is treated as no valid response. Requests targeting other agents are
not listed as dashboard work and increment `other_targets`.

### Inbox states

| State | Exact condition |
| --- | --- |
| `answered` | A valid response exists and each request input's current hash matches both the request and the response's `input_hashes`. `final` is true only for `done` or `rejected`. |
| `stale` | A request input is missing/changed from its request hash, or a response exists but the current hash differs from its input hash. Missing response input-hash keys count as mismatches. |
| `blocked` | There is no valid response, inputs are not stale, and a dependency lacks a valid non-stale `done` response, or the request participates in a detected dependency cycle. `blocked_by` lists dependencies that are not complete. |
| `new` | There is no response, inputs are current, dependencies are satisfied, and the request is not part of a cycle. |

Top-level `verdict` is fail when any request or response is malformed;
otherwise it is pass. Counts include the four states. `all_final` requires
every listed dashboard request to be final and not stale (and is true for an
empty inbox). A dependency is considered done only with a valid response and
current request inputs; it may target any agent in the same directory.

The `ux-inbox` result has `verdict`, `stage: "ux-inbox"`, `liaison_dir`,
`requests[]`, `malformed[]` (`path`, `detail`), `other_targets`, `counts`,
and `all_final`. Each request item contains `id`, `path`, `request_sha256`,
`state`, `final`, `stage`, `risk`, `purpose`, `requested_changes`,
`expected_deliverables`, `acceptance`, `depends_on`, and input snapshots
(`path`, requested `sha256`, and nullable `current_sha256`). It also includes
`stale_inputs`, `blocked_by`, `circular`, and either a response object
(`path`, `status`, `responded_at`) or `null`. `final` is true only for a valid
`done` or `rejected` response.

High-risk request validation binds a readable `.ux.json` input and requires
one `jobs[].id` value to appear as a rationale token matching
`[a-z][a-z0-9_]*`; a missing/unreadable contract or missing job token is
malformed.

### Response rules

`dashboard_ux_respond` accepts a strict `UxRespondInput`, resolves artifact
paths under the workspace, hashes files or stable directory trees, and writes
atomically. Statuses are `accepted`, `in_progress`, `done`, `rejected`,
`deferred`, and `needs_info`. Non-accepted/in-progress statuses need a reason
with at least 20 non-whitespace characters. Missing inputs are refused except
for `needs_info`, `rejected`, or `deferred`; missing hashes are omitted from
those responses.

For `done`, the tool refuses if any input is stale, any dependency lacks a
valid current `done` response, or either a known decision ref or an impression
ref is absent. The refs must name VRP event IDs in the appropriate logs:
decisions use `decisions.jsonl`; impression refs use `impressions.jsonl` or
`vision-reviews.jsonl`. It also requires at least one artifact that parses as
a `.dash-report.json` with `scope: "full"` and `verdict: "pass"`. For each
claimed `gate_verdict`, if its gate ID appears in a supplied report, the claim
must match that check; a `not_applicable` check cannot be claimed as pass or
fail. The response model itself requires at least one artifact and gate
verdict for `done`, with no fail/unknown claims.

Responses can be overwritten to progress a request. Agent instructions
recommend `accepted` → `in_progress` → a final/blocked outcome, ask user
questions through `questions_for_user`, re-read stale inputs, and prohibit
hand-editing `.ux-response.json`.

## prodeng factory test spec

A contract `factory` section pins prodeng's `factory-test-spec.json` by
SHA-256 and drives its UART commands over a `web_serial` transport from the
generated page. prodeng owns the spec: regenerate and re-pin it rather than
editing it, and `factory.spec` fails when the pinned bytes change.

The pinned spec must also carry prodeng's interchange envelope v3 sidecar,
`factory-test-spec.provenance.json`. A malformed sidecar, another producer,
other artifact bytes, a changed source, or a `decision_refs` id missing
from prodeng's intact VRP log fails `factory.spec`; because a factory run
drives real hardware, a missing sidecar or unreadable source fails it too
(`provenance unknown: ...`).

## Change control (ECR/ECO)

A change to a file that another agent pins by sha256 goes through
UX-creator's change records, never a silent re-pin. There is no human
approval step.

1. Raise `<id>.ecr.json` with the reason, the proposal and each file to
   change with its current sha256.
2. After regenerating, write `<id>.eco.json` with each file's `before` and
   `after` sha256, the gate report that passed it (verdict `pass`, citing
   the `after` sha256) and the AI review findings with their dispositions.
   A `blocker` closes only as `fixed`, and the author cannot review its own
   change.
3. `ux change <eco>` (MCP `ux_change_check`) finds every consumer that pins
   a changed file. It fails if one still pins the old sha256, or re-pinned
   without being listed in the ECO.

AI review findings can only stop a change. This plugin's deterministic
gates and the change check decide. The record formats are in
[UX-creator-agent `docs/sister-cooperation.md`](https://github.com/VibeBB/UX-creator-agent/blob/main/docs/sister-cooperation.md#change-control-ecreco-and-design-review).
