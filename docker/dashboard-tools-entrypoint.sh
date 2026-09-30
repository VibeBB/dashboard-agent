#!/bin/sh
set -eu

cache_seed="${EM_CACHE:-/opt/emscripten-cache}"
cache_runtime="$(mktemp -d /tmp/dashboard-emscripten-cache.XXXXXX)"
cp -R "$cache_seed"/. "$cache_runtime"/
chmod -R u+rwX "$cache_runtime"
export EM_CACHE="$cache_runtime"

exec "$@"
