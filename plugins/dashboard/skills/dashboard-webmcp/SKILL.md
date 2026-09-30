---
name: dashboard-webmcp
description: Expose safety-aware dashboard status, telemetry, and optional commands to WebMCP.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - WebMCP
  - model context
  - browser agent tool
---

# Dashboard WebMCP

Feature-detect and register tools through `document.modelContext`; do not use
`navigator.modelContext` or the removed `navigator.modelContextTesting`.
Registration uses one `AbortController` signal and teardown aborts it.

Expose status and untrusted telemetry as read-only tools. Optional command
tools never select or connect to devices, fail closed while disconnected, and
use the same hazard confirmation and ACK logic as the UI. Hazard tools must
carry `consequentialHint`.
