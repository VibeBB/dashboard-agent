FROM ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 AS uv

FROM emscripten/emsdk:6.0.12@sha256:77638e6c215a65f25a704c0c831d5c2463a8c0468a58c6cb82489dbe621dfa05 AS emscripten

# mruby/mrubyc build stage: mrbc compiles UX .rb sources into bytecode
# that the Emscripten leg links into the mruby/c WASM VM. Mirrors the
# pins in firmware-agent (mruby 4.0.0, mrubyc master for the
# emscripten HAL).
FROM debian:13-slim@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f AS mruby

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG MRUBY_VERSION=4.0.0
ARG MRUBY_SHA256=e2ea271dbed14e9f2b33df773ae447b747dbc242ce2675022c0a57efea85a7b4
ARG MRUBYC_REF=2dec4802b09be1fc12f388d3c9267ffd9dc6c404
ARG MRUBYC_SHA256=0860de6a2b4e8adf682e14f3e0f1df7114abdb8749be23ea39cf0133f5b16b84

RUN apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install --no-install-recommends -y \
        bison \
        build-essential \
        ca-certificates \
        curl \
        ruby \
    && rm -rf /var/lib/apt/lists/*

RUN curl --fail --location --silent --show-error \
        --retry 8 --retry-delay 20 --retry-max-time 600 --retry-all-errors \
        --output /tmp/mruby.tar.gz \
        "https://github.com/mruby/mruby/archive/refs/tags/${MRUBY_VERSION}.tar.gz" \
    && echo "${MRUBY_SHA256}  /tmp/mruby.tar.gz" | sha256sum --check \
    && mkdir -p /opt/mruby-src /opt/mruby/bin \
    && tar -xzf /tmp/mruby.tar.gz -C /opt/mruby-src --strip-components=1 \
    && curl --fail --location --silent --show-error \
        --retry 8 --retry-delay 20 --retry-max-time 600 --retry-all-errors \
        --output /tmp/mrubyc.tar.gz \
        "https://github.com/mrubyc/mrubyc/archive/${MRUBYC_REF}.tar.gz" \
    && echo "${MRUBYC_SHA256}  /tmp/mrubyc.tar.gz" | sha256sum --check \
    && mkdir -p /opt/mrubyc \
    && tar -xzf /tmp/mrubyc.tar.gz -C /opt/mrubyc --strip-components=1 \
    && rm /tmp/mruby.tar.gz /tmp/mrubyc.tar.gz

WORKDIR /opt/mruby-src
RUN ruby ./minirake -j"$(nproc)" && cp build/host/bin/mrbc /opt/mruby/bin/mrbc \
    && PATH=/opt/mruby/bin:$PATH make -C /opt/mrubyc

FROM debian:13-slim@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f

ARG IMAGE_REVISION=unknown
ARG NODE_VERSION=26.11.1
# sha256 of https://nodejs.org/dist/v26.11.1/node-v26.11.1-linux-x64.tar.xz
ARG NODE_SHA256=3883bfc73f9a680ca4eab04b196068aaaab1373ffa77d8fc1a4408222495b651
ARG SERVO_URL=https://github.com/servo/servo/releases/download/v0.7.0/servo-x86_64-linux-gnu.tar.gz
ARG SERVO_SHA256=728eba1be1cc1851e05dfaa90e18f98ab8644dd2355bedb0b8a5e89795ebe333

# Fail the build when the left side of a verification pipe (curl|sha256sum)
# breaks instead of silently passing the right side.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV EMSDK=/emsdk \
    EM_CACHE=/opt/emscripten-cache \
    HOME=/tmp \
    PATH="/opt/dashboard/.venv/bin:/opt/servo/servo:/opt/mruby/bin:/emsdk:/emsdk/upstream/emscripten:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    DASHBOARD_MRUBYC_DIR=/opt/mrubyc \
    SERVO_BIN=/opt/servo/servo/servoshell \
    PYTHONPYCACHEPREFIX=/tmp/dashboard-pycache \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python

LABEL org.opencontainers.image.source="https://github.com/VibeBB/dashboard-agent" \
      org.opencontainers.image.licenses="BSD-3-Clause" \
      org.opencontainers.image.revision="${IMAGE_REVISION}" \
      dashboard.node.version="${NODE_VERSION}"

COPY --from=uv /uv /uvx /usr/local/bin/
COPY --from=emscripten /emsdk /emsdk
COPY --from=mruby /opt/mruby /opt/mruby
COPY --from=mruby /opt/mrubyc /opt/mrubyc

# Debian slim snapshots lag the pcre2 security update (10.46-1~deb13u3,
# CVE-2026-103111); apply --only-upgrade inside the build regardless of
# which snapshot the pinned digest carries (idempotent when already fixed).
RUN for attempt in 1 2 3 4 5; do \
        apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 update \
        && apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 install --no-install-recommends -y \
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
            libatomic1 \
        && apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 install --only-upgrade --no-install-recommends -y \
            libpcre2-8-0 \
        && rm -rf /var/lib/apt/lists/* \
        && break; \
        [ "$attempt" = 5 ] && exit 1; \
        echo "::warning::apt update+install attempt ${attempt} failed; retrying"; \
        sleep $((attempt * 30)); \
    done

# Node.js official tarball — the same sha256-verified external-download
# pattern as the other tools in this image (and the ux-tools migration).
# Provides /usr/local/bin/{node,nodejs,npm,npx} with npm bundled; libatomic1
# above is required by the x64 node binary. The openssl archs prune mirrors
# the upstream image's ~34MB header cleanup.
RUN curl --fail --location --silent --show-error \
        --retry 8 --retry-delay 20 --retry-max-time 600 --retry-all-errors \
        --output /tmp/node.tar.xz \
        "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
    && echo "${NODE_SHA256}  /tmp/node.tar.xz" | sha256sum --check \
    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 --no-same-owner \
    && rm -f /tmp/node.tar.xz \
    && ln -s /usr/local/bin/node /usr/local/bin/nodejs \
    && find /usr/local/include/node/openssl/archs -mindepth 1 -maxdepth 1 \
        ! -name "linux-x86_64" -exec rm -rf {} + \
    && ldd /usr/local/bin/node | tee /tmp/node-ldd.txt \
    && ! grep -F "not found" /tmp/node-ldd.txt \
    && node --version | grep -Fx "v${NODE_VERSION}" \
    && npm --version \
    && mkdir -p /usr/share/doc/node \
    && printf '%s\n' \
        "source=https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
        "version=v${NODE_VERSION}" \
        > /usr/share/doc/node/SOURCE

# The pinned emsdk stage vendors source-map-js 1.2.1 inside the emscripten
# toolchain (CVE-2026-93749, fixed in 1.2.2); upgrade the vendored copy and
# fail the build if the landed version is still vulnerable.
RUN npm --prefix /emsdk/upstream/emscripten install --no-save --no-audit --no-fund source-map-js@1.2.2 \
    && node -p "require('/emsdk/upstream/emscripten/node_modules/source-map-js/package.json').version" | grep -qx '1.2.2'

RUN curl --fail --location --silent --show-error \
        --retry 8 --retry-delay 20 --retry-max-time 600 --retry-all-errors \
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
        /opt/mruby \
        /opt/mrubyc \
        /opt/emscripten-cache \
        /opt/playwright \
        /opt/servo \
        /opt/uv-python \
    && chmod a+rx /usr/local/bin/dashboard-entrypoint

ENTRYPOINT ["/usr/local/bin/dashboard-entrypoint"]
