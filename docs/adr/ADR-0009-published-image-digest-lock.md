# ADR-0009: Publish and digest-lock dashboard tools

- Status: accepted
- Date: 2026-10-01

## Context

Dashboard gates depend on a container with pinned Python, Node, Chromium,
Emscripten, and Servo tooling. Rebuilding that environment for every CI job is
slow, while a mutable image tag does not identify the tools used by a run.
Installed plugins also need a stable way to resolve the image without relying
on the repository checkout.

## Decision

Publish `ghcr.io/vibebb/dashboard-tools` with a commit-specific `-tools` tag.
The publish workflow validates the image with both dashboard examples, records
tool measurements, and proposes a digest lock update. The root lock is
`docker/image-digests.json`; the plugin pin is
`plugins/dashboard/tools-image.json`. The launcher and scheduled locked-image
check use the digest reference, not a mutable tag.

The CI workflow accepts a `workflow_call` ref so release and lock automation
can verify a specific branch or commit while retaining `workflow_dispatch`.
The digest-lock sweep only retries merges of automation-owned lock pull
requests; repository branch protection remains authoritative.

The Python, uv, Node, Emscripten, and Servo inputs remain versioned and
documented in the Dockerfile and `THIRD_PARTY_NOTICES.md`. Dependency reports
cover Python and uv pins, Docker base digests and Servo URL/SHA arguments,
runtime npm pins, generated Tauri scaffold pins, and GitHub Action SHAs.

## Consequences

- A successful first publish fills both null image pins through a reviewed
  bot pull request.
- CI can skip the scheduled locked-image gate before the first digest exists.
- GHCR must allow CI to read the published package.
- A digest identifies the published image, while the source revision label and
  measurement record provide build provenance and tool-version evidence.
