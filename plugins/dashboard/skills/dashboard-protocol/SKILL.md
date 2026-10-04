---
name: dashboard-protocol
description: Define and export the COBS/CRC16 device protocol.
version: 0.1.1
license: BSD-3-Clause
triggers:
  - COBS
  - CRC16
  - protocol export
---

# Dashboard protocol

Frames contain message ID, sequence, little-endian fields, and CRC16
CCITT-FALSE before COBS encoding and a trailing zero delimiter. ACK ID 255
contains the acknowledged message ID, sequence, and status. ACK matching uses
both ID and sequence.

Run `dashboard protocol-export <contract>` to produce the JSON interchange
artifact. The generated C header and codec copy are projections; update the
contract and regenerate instead of editing those files.
