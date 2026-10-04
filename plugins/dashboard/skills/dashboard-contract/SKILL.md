---
name: dashboard-contract
description: Author and validate dashboard JSON contracts and their typed protocol.
version: 0.1.1
license: BSD-3-Clause
triggers:
  - dashboard contract
  - telemetry schema
  - device command
---

# Dashboard contract

Use a versioned `<name>.dash.json` document with system `dashboard` and
artifact kind `dashboard_contract`. Protocol message IDs are unique bytes
0–254; 255 is reserved for ACK frames. Field scale maps human values to wire
values. ACK is valid only for host-to-device commands.

Every transport must be referenced by a declared platform route. Display
widgets bind to device-to-host fields; controls bind to host-to-device messages.
Hazardous controls require `confirm: true`. Link firmware contracts as copied,
SHA-256-pinned imports; never edit sibling inputs.
