# Records and vision review

VibeBB Record Protocol (VRP) v2 provides structured evidence for design
choices, stage outcomes, and visual inspection; the family specification is
`wire-agent` `docs/records-protocol.md`. Records and model judgments are
advisory. They cannot change a deterministic gate's `pass` or `fail` verdict.

## Required record stages

Agent guidance requires an impression after the final regeneration of each
stage:

1. `contract` — author and validate the `.dash.json`.
2. `generate` — produce final generated app and optional shell.
3. `gates` — record static and full gate results.
4. `visual-review` — inspect screenshots and Servo output.
5. `liaison` — answer UX requests and bind the evidence.
6. `handoff` — summarize final outputs and open questions.

Bind each impression to the relevant final artifact paths. It needs:

- prose of at least 400 characters and three distinct sentences, refused when
  it nearly duplicates an earlier impression of the same stage;
- `facets`: two or more `observed`, `works`, `concerns` (id, severity,
  `about`, anchor), `feelings.maker` / `feelings.user`, and `next_actions`;
- two or more `claims`, each quoting an exact token (`anchor`) of a cited
  artifact (a widget label, unit, or command name), checked against the bytes;
- `confidence`, `unknowns`, optional `insights`, and an `upstream` answer for
  every sister impression taken in.

## Decision examples

Record a VRP decision for each non-trivial design choice, including:

- a transport per platform/browser route and why (Web Bluetooth, Web Serial,
  WebUSB, network route, or Tauri);
- acknowledged matrix caveats;
- framing, `max_frame_bytes`, ACK behavior/timeouts, and reconnect policy;
- widget kind and message/field binding;
- hazardous controls and their confirmation requirement;
- WebMCP control exposure;
- Tauri shell and target list, optional WASM modules, and firmware-contract
  binding.

Each decision gives first principles, at least two options with pros and cons,
the chosen option, a 200+ character rationale, evidence, assumptions,
unknowns, residual risks, and a condition for revisiting it. Evidence files
are hashed when recorded.

## Vision review points

Review every image actually viewed:

| Image source | Checklist slug |
| --- | --- |
| Desktop Chromium screenshot | `dashboard-desktop` |
| Mobile Chromium screenshot | `dashboard-mobile` |
| Servo-rendered screenshot | `servo-render` |
| User-provided intake image | `intake-image` |

Judge more than legibility. Compare the render with the contract and product
intent: every widget, label, and unit; visibly distinct hazardous controls;
obvious connection state; a clear unsupported-platform message; ambiguity;
design intent; and usefulness to the person operating the device. Confirm
command-field units and slider readouts are visible, and hazardous controls
clearly state when confirmation is required. Record findings with categories,
`info`/`warning`/`error` severity, and notes. The impression must be at least
400 characters and three distinct sentences.

The current Servo render shows both `websocket (chrome)` and
`websocket (tauri)` connect buttons. Track this as an investigation; visual
review must not alter route-selection behavior.
Bind the record to image bytes or the vision-tool event; never invent measured
values or prose from a tool hint.

## `vision_review` tool hints

The screenshot, full-gates, and smoke service payloads return
`vision_review[]` alongside the unchanged `images[]` path list. Each hint has:

- `image_path`;
- `sha256` of the image bytes;
- `checklist`, selected by filename: `desktop.png` → `dashboard-desktop`,
  `mobile.png` → `dashboard-mobile`, `servo.png` → `servo-render`, otherwise
  `dashboard-image`;
- `record_with: "dashboard_record_vision_review"`.

The hint is an instruction for the agent to create its own review; it is not
the review itself. MCP attaches image bytes only for screenshot, full-gates,
and smoke tools, within the image limits documented in
[Performance and limits](performance-and-limits.md).

## Stop-hook enforcement and logs

`require_records.py stop` validates VRP JSONL using a stdlib mirror, checks
session-local record coverage for protected artifact changes and observed
images, and writes the latest result to
`observations/dashboard/records-status.json`. Missing required records can
deny Stop twice. After the configured limit, the hook records the gap and
permits finishing; it never alters a gate report.

Workspace evidence locations:

| Path | Purpose |
| --- | --- |
| `observations/dashboard/decisions.jsonl` | Decisions, options, hashed evidence, risks, revisit conditions. |
| `observations/dashboard/impressions.jsonl` | Stage conclusions tied to artifact/tree hashes. |
| `observations/dashboard/vision-reviews.jsonl` | Advisory image reviews tied to image bytes or tool event. |
| `observations/dashboard/image-observations.jsonl` | Post-tool image-observation events. |
| `observations/dashboard/vision-tool-events.jsonl` | Post-tool vision-tool provenance/events. |
| `observations/dashboard/records-status.json` | Most recent Stop-hook verdict and any remaining record gap. |
| `intake/attachments/manifest.jsonl` | Attachment path/hash metadata for images copied into intake. |

## Generated-file protection

Do not hand-edit generated contract projections, reports, protocol exports,
manifest, screenshots, or liaison response files. The generated-file hook also
protects VRP logs/status and `liaison/*.ux-response.json`. Use generation,
`dashboard_ux_respond`, and the VRP record tools/CLI writers. Artifact patterns
and ignored trees are listed in `records-policy.json` and
[Contracts](contracts.md#recordspolicyjson).

## VRP v2 logs

`observations/dashboard/` holds `decisions.jsonl`, `impressions.jsonl`,
`vision-reviews.jsonl`, `reconciles.jsonl`, `insights.jsonl`, `reads.jsonl`,
and `song-receipts.jsonl`. Every line carries `schema_version` 2, `sequence`,
`prev_event_id`, `writer`, and `event_id` (the SHA-256 of the canonical
record). The writer verifies the chain before appending and refuses a log that
was edited, truncated, or reordered; readers report such a log under
`integrity_problems` and never resolve references into it. A log written
entirely by VRP v1 is renamed to `<name>.v1.jsonl` on the first v2 write.

`dashboard_records_digest` lists open sister concerns, disputes, unanswered
reads, insights, split reviews, and undelivered songs;
`dashboard_records_search` filters every plugin's impressions. Answer each
sister impression acted on in `upstream` (`adopted`, `deferred`, `disputed`, or
`noted`) or with `dashboard_record_read`. A disputed concern cannot be raised
again while the artifact bytes are unchanged, and a rejected insight returns
only with `revisits` and a reason (`dashboard_record_insight`).

## Blind second review of screenshots

`dual_review_globs` (`**/*.screens/*.png`) make every desktop/mobile
screenshot a dual-review image. After the primary review, the
`dashboard-blind-review` sub-agent records a `blind` review behind the
`blind-guard` hook, which hides earlier reviews, records, advisory reports,
liaison answers, and bard songs. `dashboard_record_reconcile` compares
`[primary, blind]`; a split gets one `tiebreak` round (at most two rounds) and
stays `unknown` when unresolved. The Stop hook owes the blind review and the
reconcile until both exist for the current image bytes.

## Songs from bard

bard may deliver `liaison/<id>.bard-song.json` addressed to `dashboard`. The
dashboard answers with `dashboard_record_song_receipt`; the receipt is
advisory, never feeds a gate, and never asks bard for another song, so the
exchange cannot loop. The `protect-generated` hook denies hand edits to song
deliveries.

## Session-scoped Stop status

The Stop hook excludes a record with an explicit different session ID,
even when its timestamp is recent. Legacy records without an ID are
eligible only from the session start through the following 24 hours;
their use is reported as an attribution warning. Missing session
identity or a missing start marker also leaves attribution unverified.
Reviews bind both the resolved image path and its SHA-256; an event ID
cannot substitute for that binding. Supply an explicit `image_path` to
the review writer so it records the current bytes. Legacy reference-only
reviews remain readable but do not discharge image-review obligations.

Stop writes `observations/<plugin>/records-status.json` and a
`observations/<plugin>/.sessions/<session>.status.json` snapshot:

| Field | Meaning |
| --- | --- |
| `stop_permission` | `deny` while the configured refusal budget remains, then `allow` |
| `record_compliance` | `fail` for missing evidence, `unknown` for attribution warnings, otherwise `pass` |
| `run_completion` | `unknown`; only the execution workflow can establish completion |
| `acceptance` | `unknown`; only the product acceptance workflow can establish it |
| `checkpoint` | Session marker containing the start time and refusal count |

An exhausted refusal budget permits termination while preserving the
unresolved problems. The compatibility `verdict` describes the hook's
problem list only; consumers must use the explicit fields above and must
not infer product acceptance from Stop permission or the absence of
record problems. Reviewer identity propagation and derived-image
ownership require a separate recording contract; this status does not
claim to verify them.

## Session attribution

Pass the native `session_id` from the SessionStart record context in record-tool
inputs. The writer also accepts `OPENHANDS_SESSION_ID` when supplied by the SDK
process; conflicting explicit and environment identities are rejected. The ID is
included in the record hash. Writers never infer it from shared marker files.

Delegated SessionStart hooks expose only native record context (`record-context`), without
recalling earlier review prose. Ordinary plugin SessionStart retains sister-concern recall.

Delegate independent reviews with an opaque `primary_event_id`, the resolved image
path and SHA-256; never send the earlier findings. Reviewers keep their own native
`session_id`. The writer and Stop resolve that reference into an intact primary
with the same plugin, path and hash and a different native session. Every review
role has its own session. Reconciliation belongs to the primary's session.

A copied image has its own round. Historical inputs without identity remain
supported, with bounded timestamp attribution and an unknown compliance warning
at Stop; they cannot satisfy explicitly scoped writer rounds.

Stop permission, record compliance, run completion and acceptance are separate
status fields. Reaching the refusal budget permits stopping while preserving gaps;
it does not establish execution completion or product acceptance.

### Coordinating a delegated primary

When delegating the primary visual review, pass your native `session_id` as
`coordinator_session_id` in the task prompt. The delegate records its own
`session_id` and that coordinator on the primary, then returns the opaque
`primary_event_id` and image path/SHA. The blind reviewer receives only these
references and its own native record context. Do not copy the primary's prose
into the blind review prompt.

The primary author or its declared coordinator can reconcile the bound reviews.
The coordinator's Stop hook retains the independent-review and reconciliation
obligations; the primary delegate reports the handoff without starting another
review loop. A primary started through delegated `record-context` must name its
coordinator. Record-capable delegates also declare their own Stop hook, so a
legacy primary without coordination cannot silently lose its review debt.
An uncoordinated record from another native session remains outside this run.

These checks concern record attribution and review bookkeeping. SDK startup,
plugin loading, and deterministic tests do not establish LLM judgment quality,
GUI operation, released-image compatibility, or product acceptance.
