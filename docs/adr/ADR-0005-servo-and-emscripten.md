# ADR-0005: Servo and Emscripten roles

- Status: accepted
- Date: 2026-09-30

## Decision

Use Emscripten to build the portable C codec and compare CRC/COBS behavior
against the TypeScript implementation. Use Servo only as a browser smoke
engine: its expected lack of hardware APIs verifies that WebSocket UI remains
usable and hardware routes degrade gracefully.

## Consequences

Neither Servo nor WebAssembly replaces real Chromium hardware-mock E2E tests.
If the required toolchain or WebDriver checks are unreliable, report the
failure rather than weakening the gate.
