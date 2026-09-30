# ADR-0004: Dashboard tools image and pins

- Status: accepted
- Date: 2026-09-30

## Decision

Run Chromium, Emscripten, and Servo checks inside a Debian 13
`node:26-trixie-slim` image rather than Alpine because those tools depend on
glibc. Pin Node, uv, TypeScript, esbuild, Playwright, browser type definitions,
and image digests.

## WebRTC gate isolation

The launcher runs tool containers in the `dashboard-isolated` internal Docker
network, which has no Internet egress. With only loopback available, Chromium
gathered no ICE candidates for the real DataChannel test. On the internal
network, Chromium enumerated the non-default-route interface only after the
page context was granted camera and microphone permissions. The test keeps
`iceServers: []` and establishes a real connection.

## Consequences

The TypeScript 7.1 development build is an intentional exact pin. Tool
installation and full gates are isolated from the host environment.
