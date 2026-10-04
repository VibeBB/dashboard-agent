---
name: dashboard-servo
description: Run the Servo WebDriver smoke test without weakening its assertions.
version: 0.1.1
license: BSD-3-Clause
triggers:
  - Servo
  - browser smoke
  - WebDriver
---

# Servo smoke

Servo is a rendering and network-route smoke engine, not a hardware API gate.
The generated smart-kettle page must report Bluetooth, USB, and Serial absent,
WebSocket present, hardware routes unavailable, and the WebSocket route
available. The smoke test starts Servo headlessly with timeouts, polls
`window.__dashboard`, and kills the process group on exit. If WebDriver is
unreliable, report the evidence instead of weakening checks.
