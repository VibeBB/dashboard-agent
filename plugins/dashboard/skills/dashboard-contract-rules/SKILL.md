---
name: dashboard-contract-rules
description: Path rule — schema and provenance reminders injected whenever a *.dash.json file is touched.
version: 0.1.0
license: BSD-3-Clause
paths:
  - "**/*.dash.json"
---

# Dashboard contract file rules

- `*.dash.json` follows the `DashboardContract` schema in
  `src/dashboard/contract.py` (`artifact_kind: dashboard_contract`). It is
  the single source of truth — protocol messages, transports, platform
  routes, widgets, controls, and safety declarations all live here.
- Protocol message IDs are unique bytes 0–254; 255 is reserved for ACK
  frames. Hazardous controls require `confirm: true`. Every transport must
  be referenced by a declared platform route.
- Sibling inputs (e.g. `firmware_contract` + `firmware_sha256`, `ImportRef`
  entries) are hash-pinned copies — record their digest, never edit the
  sibling artifact itself.
- Generated projections under `out/` (app, protocol headers, manifest,
  reports, screenshots) are never hand-edited — change the contract and
  regenerate.
