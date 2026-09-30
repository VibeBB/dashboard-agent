# ADR-0002: Platform declarations and support matrix

- Status: accepted
- Date: 2026-09-30

## Decision

Each dashboard declares supported or unsupported operating systems and
browser-specific transport routes. A data-only matrix centralizes API support
and caveat text, including Linux Bluetooth, Android USB/serial, Bluefy, and
local-network endpoints. BSD Chromium ports offer only WebSocket and WebRTC
because Web Bluetooth is disabled, Web Serial is not built, and WebUSB is
fake-only on FreeBSD/NetBSD or unverified on OpenBSD. iOS and iPadOS remain
independent contract declarations with identical browser/transport support pairs.

## Consequences

Undeclared platforms remain out of scope. Unsupported platforms receive a
visible reason, and every route caveat must be acknowledged in its contract.
