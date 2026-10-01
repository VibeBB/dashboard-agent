## SBOM attestations

The publisher generates an SPDX-2.3 SBOM for the digest-pinned tools image,
attests it with predicate type `https://spdx.dev/Document/v2.3`, and uploads
the artifact for 30 days. The returned URL is stored as `sbom_attestation`;
locked-image checks verify it when present and warn when absent.
## Launcher-side verification

`DASHBOARD_VERIFY_ATTESTATION` accepts `auto` (the default), `require`, or
`off`. Before pulling a lock-provided image, and on every `prewarm`, the
launcher uses `gh attestation verify` with the lock entry and publisher
workflow. `auto` prints one note and skips for an image override, missing
attestation, missing `gh`, or failed `gh auth status`; once verification
starts, failure or timeout prevents the pull. `require` makes skip conditions
errors, while `off` never verifies. Ordinary invocations do not re-verify a
locally present image, and `--warn` doctor paths never verify.
# ADR-0012: Attest published tools images

## Status

Accepted

## Context

The dashboard tools image is published to GHCR and pinned by digest. The digest
identifies image bytes but does not independently identify the workflow that
published them.

## Decision

The publishing workflow attaches GitHub build provenance to each published
tools image. The digest lock records the attestation URL when the image is
published. Locked-image checks verify recorded attestations against the
repository and publisher workflow; existing pins without metadata remain
usable with a warning until a new publish supplies provenance.

## Consequences

Image provenance is tied to the repository's publishing workflow without
inventing metadata for existing pins. Lock readers continue to accept the
optional attestation field.
