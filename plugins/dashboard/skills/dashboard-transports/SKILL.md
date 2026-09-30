---
name: dashboard-transports
description: Configure browser hardware and network transports safely.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - Web Bluetooth
  - WebUSB
  - Web Serial
  - WebSocket
  - WebRTC
---

# Dashboard transports

Use a secure context and explicit user gesture for Bluetooth, USB, and Serial
device selection. Validate BLE characteristic properties, claim only the
declared WebUSB interface, and close readers, writers, sockets, and peer
connections on teardown.

Network transports use `wss://` except loopback development WebSocket URLs.
WebRTC uses the dashboard-offerer JSON signaling protocol and sends one
complete framed message per DataChannel message. Stream transports split
COBS frames on the zero delimiter.
