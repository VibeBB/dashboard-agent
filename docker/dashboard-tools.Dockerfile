FROM ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21 AS uv

FROM emscripten/emsdk:6.0.10@sha256:e077d54e2b8970575ebc4f185ac1de0b95c05f2b266134d4ba27449af7aebf65 AS emscripten

FROM node:26-trixie-slim@sha256:930557a230abacbc3f4fd9b8648abf8f4bee1e17cb72195dcdfb2f709bc85b33

ARG IMAGE_REVISION=unknown
ARG SERVO_URL=https://github.com/servo/servo/releases/download/v0.7.0/servo-x86_64-linux-gnu.tar.gz
ARG SERVO_SHA256=728eba1be1cc1851e05dfaa90e18f98ab8644dd2355bedb0b8a5e89795ebe333

# Fail the build when the left side of a verification pipe (curl|sha256sum)
# breaks instead of silently passing the right side.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

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

# The pinned base digest still ships libpcre2-8-0 10.46-1~deb13u2; upgrade it
# to ~deb13u3 (CVE-2026-103111) inside the build via --only-upgrade.
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
    && apt-get -o Acquire::Retries=5 install --only-upgrade --no-install-recommends -y \
        libpcre2-8-0 \
    && rm -rf /var/lib/apt/lists/*

# The pinned emsdk stage vendors source-map-js 1.2.1 inside the emscripten
# toolchain (CVE-2026-93749, fixed in 1.2.2); upgrade the vendored copy and
# fail the build if the landed version is still vulnerable.
RUN npm --prefix /emsdk/upstream/emscripten install --no-save --no-audit --no-fund source-map-js@1.2.2 \
    && node -p "require('/emsdk/upstream/emscripten/node_modules/source-map-js/package.json').version" | grep -qx '1.2.2'

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
# The uv-managed CPython bundles pip with vendored copies of urllib3,
# msgpack, and setuptools that nothing in the image invokes — dependencies
# install via uv and the shipped venv is pip-less — so strip the payload
# instead of shipping unused vulnerable vendored packages.
RUN uv python install 3.14 \
    && rm -rf /opt/uv-python/bin/pip* \
              /opt/uv-python/cpython-*/bin/pip* \
              /opt/uv-python/cpython-*/lib/python3.*/site-packages/pip \
              /opt/uv-python/cpython-*/lib/python3.*/site-packages/pip-*.dist-info \
              /opt/uv-python/cpython-*/lib/python3.*/ensurepip \
              /root/.cache/uv \
    && uv sync --locked --no-dev --no-group sdk-check

WORKDIR /opt/dashboard/runtime
RUN npm ci \
    && npx playwright install --with-deps chromium \
    && npx tsc -p . \
    && node --test test/

WORKDIR /opt/dashboard
RUN python -m dashboard generate examples/smart-kettle/smart-kettle.dash.json \
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

# Tighten the login.defs umask to 027 (Lynis AUTH-9328): the image has no
# interactive users, so files created at runtime stay group-readable only.
RUN printf 'UMASK 027\n' >> /etc/login.defs

RUN chmod -R a+rX \
        /emsdk \
        /opt/dashboard \
        /opt/emscripten-cache \
        /opt/playwright \
        /opt/servo \
        /opt/uv-python \
    && chmod a+rx /usr/local/bin/dashboard-entrypoint

ENTRYPOINT ["/usr/local/bin/dashboard-entrypoint"]
