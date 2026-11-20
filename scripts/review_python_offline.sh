#!/bin/sh
# Usage: scripts/review_python_offline.sh /absolute/path/to/python [pytest args...]
# Requires Linux unshare and ip. Only loopback is enabled; no external routes.
set -eu
PYTHON_BIN=$1
shift
REVIEW_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
REVIEW_HOME=$(mktemp -d /tmp/honeyos-review-home.XXXXXX)
cd "$REVIEW_ROOT"
exec unshare -Urn sh -eu -c '
    ip link set lo up
    review_home=$1
    python_bin=$2
    shift 2
    exec env -i HOME="$review_home" XDG_CONFIG_HOME="$review_home/.config"         XDG_CACHE_HOME="$review_home/.cache" HONEYOS_HOME="$review_home/.honeyos"         PATH=/usr/bin:/bin         LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1         "$python_bin" -m pytest --import-mode=importlib "$@"
' sh "$REVIEW_HOME" "$PYTHON_BIN" "$@"
