FROM ghcr.io/astral-sh/uv:0.12.21 AS uv

FROM emscripten/emsdk:6.0.10@sha256:e077d54e2b8970575ebc4f185ac1de0b95c05f2b266134d4ba27449af7aebf65 AS emscripten

FROM node:26-trixie-slim@sha256:ec7758ee051e457b468b32bde57b0879010b325bb9862718e9615225ce4aaae1

ARG IMAGE_REVISION=unknown
ARG SERVO_URL=https://github.com/servo/servo/releases/download/v0.6.0/servo-x86_64-linux-gnu.tar.gz
ARG SERVO_SHA256=ad951ede1a1a73899b822c9464f6bdb3ec25b531b27cd806671d79ac8b6a60d0

ENV EMSDK=/emsdk \
    EM_CACHE=/opt/emscripten-cache \
    HOME=/tmp \
    PATH="/opt/dashboard/.venv/bin:/opt/servo/servo:/emsdk:/emsdk/upstream/emscripten:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    SERVO_BIN=/opt/servo/servo/servoshell \
    PYTHONPYCACHEPREFIX=/tmp/dashboard-pycache \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python

LABEL org.opencontainers.image.source="https://github.com/VibeBB/dashboard-agent" \
      org.opencontainers.image.licenses="BSD-3-Clause" \
      org.opencontainers.image.revision="${IMAGE_REVISION}"

COPY --from=uv /uv /uvx /usr/local/bin/
COPY --from=emscripten /emsdk /emsdk

RUN apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install --no-install-recommends -y \
        ca-certificates \
        curl \
        git \
        python3 \
        python3-venv \
        libdbus-1-3 \
        libegl1 \
        libgl1-mesa-dri \
        libgstreamer1.0-0 \
        libgstreamer-gl1.0-0 \
        libgstreamer-plugins-bad1.0-0 \
        libgstreamer-plugins-base1.0-0 \
        libgtk-3-0 \
        libwayland-client0 \
        libx11-6 \
        libxcomposite1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxkbcommon0 \
        libxrandr2 \
        libxrender1 \
        fonts-dejavu-core \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN curl --fail --location --silent --show-error \
        --retry 5 --retry-delay 10 --retry-all-errors \
        --output /tmp/servo.tar.gz "${SERVO_URL}" \
    && echo "${SERVO_SHA256}  /tmp/servo.tar.gz" | sha256sum --check \
    && mkdir -p /opt/servo \
    && tar -xzf /tmp/servo.tar.gz -C /opt/servo \
    && rm /tmp/servo.tar.gz \
    && test -x /opt/servo/servo/servoshell \
    && ldd /opt/servo/servo/servoshell | tee /tmp/servo-ldd.txt \
    && ! grep -F "not found" /tmp/servo-ldd.txt

WORKDIR /opt/dashboard
COPY pyproject.toml uv.lock .python-version README.md LICENSE ./
COPY src ./src
COPY runtime ./runtime
COPY examples ./examples
COPY scripts ./scripts
COPY docker/dashboard-tools-entrypoint.sh /usr/local/bin/dashboard-entrypoint
RUN uv python install 3.12 \
    && uv sync --locked --no-dev --no-group sdk-check \
    && cd runtime \
    && npm ci \
    && npx playwright install --with-deps chromium \
    && npx tsc -p . \
    && node --test test/ \
    && cd /opt/dashboard \
    && python -m dashboard generate examples/smart-kettle/smart-kettle.dash.json \
    && python -m dashboard generate examples/bench-meter/bench-meter.dash.json \
    && emcc --version \
    && node --version \
    && /opt/servo/servo/servoshell --version

RUN python - <<'PY'
import shutil
import tempfile
from pathlib import Path

from dashboard.wasm import build_codec_parity

output = Path(tempfile.mkdtemp(prefix="dashboard-wasm-cache-", dir="/tmp"))
try:
    result = build_codec_parity(Path("/opt/dashboard"), output)
    if not result.ok:
        raise SystemExit(result.detail)
finally:
    shutil.rmtree(output, ignore_errors=True)
PY

RUN chmod -R a+rX \
        /emsdk \
        /opt/dashboard \
        /opt/emscripten-cache \
        /opt/playwright \
        /opt/servo \
        /opt/uv-python \
    && chmod a+rx /usr/local/bin/dashboard-entrypoint

ENTRYPOINT ["/usr/local/bin/dashboard-entrypoint"]
