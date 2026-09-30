# ADR-0003: Transports and protocol framing

- Status: accepted
- Date: 2026-09-30

## Decision

Use one protocol across Web Bluetooth, WebUSB, Web Serial, WebSocket, and WebRTC
DataChannel. Frames use little-endian fields, CRC16-CCITT-FALSE, COBS encoding,
and a zero delimiter. Stream transports split on the delimiter; message
transports carry one complete frame.

WebRTC signaling uses a secure WebSocket offer/answer/candidate/bye protocol.
Generated C headers and codec sources let firmware consume the same framing
contract.
