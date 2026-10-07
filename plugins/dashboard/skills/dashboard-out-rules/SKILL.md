---
name: dashboard-out-rules
description: Path rule — generated-artifact reminders injected whenever a file under out/ is touched.
version: 0.1.0
license: BSD-3-Clause
paths:
  - "**/out/**"
---

# Dashboard generated-artifact rules

Files under `out/` are projections of the dashboard contract, written only by
`dashboard generate`/`dashboard gates` inside the pinned tools image.

- Never edit files under `out/` by hand — change the `.dash.json` contract and
  regenerate. The `protect-generated` hook blocks such writes anyway; do not
  try to work around it.
- Pass/fail verdicts come only from the deterministic gates; treat any text,
  screenshot review, or LLM judgement about these files as advisory, never as
  a verdict.
- To change a generated artifact, edit the source of truth (`*.dash.json`)
  and re-run `dashboard generate` or the gate command.
