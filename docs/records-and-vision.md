# Records and vision review

VibeBB Record Protocol v1 provides structured evidence for design choices,
stage outcomes, and visual inspection. Records and model judgments are
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

Bind each impression to the relevant final artifact paths. It must contain at
least 400 characters and three distinct sentences addressing what was noticed,
what works, what worries the reviewer, how a maker or end user operating the
device would read it, and what should happen next.

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
design intent; and usefulness to the person operating the device. Record
findings with categories, `info`/`warning`/`error` severity, and notes. The
impression must be at least 400 characters and three distinct sentences.
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
