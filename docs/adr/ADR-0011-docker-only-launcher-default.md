# ADR-0011: Docker-only launcher default

- Status: accepted
- Date: 2026-09-30

## Context

Running dashboard gates with the host environment can silently use different
browser and rendering tools than the published `dashboard-tools` image.

## Decision

The launcher defaults to Docker and requires both the Docker executable and a
resolvable tools image. Missing requirements fail closed; `DASHBOARD_LAUNCH_MODE=host`
explicitly opts into host execution, while `auto` retains the prior
Docker-when-available behavior. The `prewarm` command continues to pull the
configured image independently of launch mode.

## Consequences

Plugin commands use the locked tools image by default. Developers without
Docker or an image can select host mode explicitly, and warning-mode hooks
continue to emit their existing non-blocking failure result.
