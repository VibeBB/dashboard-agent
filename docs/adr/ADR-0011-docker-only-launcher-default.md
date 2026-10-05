# ADR-0011: Docker-only launcher default

- Status: accepted
- Date: 2026-09-30

## Context

Running dashboard gates with the host environment can silently use different
browser and rendering tools than the published `dashboard-tools` image.

## Decision

The launcher defaults to Docker and requires both the Docker executable and a
resolvable tools image. `DASHBOARD_LAUNCH_MODE` accepts only `docker` or
explicit developer-only `host`; `host` requires `DASHBOARD_SRC` and is never an
automatic fallback. Missing Docker/image requirements fail closed and point
operators to Docker installation, image configuration, or `prewarm`. The
`prewarm` command continues to pull the configured image independently of
launch mode.

## Consequences

Plugin commands use the locked tools image by default. Developer host mode
must be explicitly selected and supplied a source package; it does not make an
installed plugin fall back to arbitrary host tools.
