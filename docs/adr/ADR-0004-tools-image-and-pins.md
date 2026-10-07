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

## Amendment (2026-10-07): Node.js via verified tarball

The runtime stage now builds on `debian:13-slim` and installs Node.js
from the upstream `nodejs.org` tarball, verified against the pinned
`NODE_SHA256` and versioned by the `NODE_VERSION` ARG, replacing the
`node:26-trixie-slim` base. The glibc rationale for Debian over Alpine
is unchanged — the base is still Debian 13. The measured difference
between the two bases was `adduser` (the unused `node` uid) and
`libatomic1` (required by the x64 Node binary, added to the apt list).
Rationale: the version becomes an auditable ARG tracked by the
dependency checker instead of an opaque tag (the pinned node image
shipped 26.10.0 while docs recorded 26.11), and every external fetch in
the image is now checksum-verified — the same migration
UX-creator-agent made in #120.
