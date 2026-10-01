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
