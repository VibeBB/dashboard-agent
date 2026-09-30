---
description: Run static or full dashboard gates and report artifacts.
allowed-tools:
  - terminal
---

Run `dashboard check <contract>` for static gates or `dashboard gates
<contract>` for full runtime, browser, WASM, and Servo checks. Full gates require
the pinned dashboard-tools image. Use `dashboard screenshot <contract>` to
capture the fresh generated app at desktop and mobile sizes for advisory review.
