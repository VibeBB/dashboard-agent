# Dashboard tools image

`dashboard-tools.Dockerfile` builds the pinned Python, Node, Chromium,
Emscripten, and Servo environment used by the dashboard launcher and CI gates.
The image runs generated examples with the launcher's internal Docker network;
gate execution does not need outbound network access.

Node.js comes from the upstream `nodejs.org` tarball — `NODE_VERSION` and
`NODE_SHA256` args pin and verify the download (sha256-verified, the same
pattern as every other external fetch in the image); the dependency checker
tracks `NODE_VERSION` against the `nodejs/node` tag feed.

Build a local image from the repository root:

```bash
docker buildx build --load \
  -f docker/dashboard-tools.Dockerfile \
  -t dashboard-tools:local \
  --build-arg IMAGE_REVISION="$(git rev-parse HEAD)" .
```

The `Publish dashboard images` workflow pushes
`ghcr.io/vibebb/dashboard-tools:<commit>-tools` and `:latest`, measures the
published toolchain, and runs both example gates through
`plugins/dashboard/scripts/dashboard_launcher.py`. It then opens a bot pull
request that records the immutable image digest in both
`docker/image-digests.json` and `plugins/dashboard/tools-image.json`. Do not
edit generated digest-lock values manually.

When a digest is present, pull and print the locked reference with:

```bash
uv run python scripts/pull_locked_image.py --entry dashboard_tools
uv run python scripts/print_locked_image.py --entry dashboard_tools
```

The initial null digest is intentional: the first successful publish writes
the pin. CI skips the locked-image smoke until that pin exists. Published
packages must be readable by unauthenticated CI pulls, or the locked-image
workflow must be updated to authenticate before changing package visibility.

The measurement record contains each probe command and its raw output:

```bash
uv run python scripts/measure_image_tools.py \
  --image-ref dashboard-tools:local \
  --out /tmp/dashboard-tools-measurement.json
```

Each published image receives GitHub build provenance. The digest lock records
its attestation URL, and locked-image checks verify it against this repository's
publisher workflow when present. Existing pins without attestation metadata
continue with a warning until the next publish.
