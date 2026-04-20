#!/bin/bash
# sync-handover.sh
# Installed on g9 at /usr/local/bin/sync-handover (mode 755, root-owned).
#
# Purpose: pulls latest HANDOVER.md (and any other repo changes) into Hermes's
# working clone so the file Hermes reads is always current.
#
# Invoked by:
#   1. Latitude after Claude pushes:    ssh g9-ts "sudo /usr/local/bin/sync-handover"
#   2. Root cron (safety net):          */5 * * * * /usr/local/bin/sync-handover --quiet
#
# Pull policy: fast-forward only. If Hermes has local commits not yet pushed,
# this script warns but does NOT merge — Hermes is responsible for push
# discipline. If there's a real conflict, script exits non-zero and the file
# stays on the last-synced state until a human resolves.
#
# The clone is owned hermes:agents. This script runs as root (via sudo or cron),
# but runs git commands as hermes via `sudo -u hermes` so file perms stay clean.

set -euo pipefail

CLONE_DIR=/data/hermes/psc-handover
QUIET=0
if [ "${1:-}" = "--quiet" ]; then
  QUIET=1
fi

log() {
  if [ "${QUIET}" -eq 0 ]; then
    echo "$@"
  fi
}

if [ ! -d "${CLONE_DIR}/.git" ]; then
  echo "ERROR: ${CLONE_DIR} is not a git clone." >&2
  exit 1
fi

cd "${CLONE_DIR}"

# Fetch from origin
sudo -u hermes git fetch --quiet origin main

LOCAL=$(sudo -u hermes git rev-parse main)
REMOTE=$(sudo -u hermes git rev-parse origin/main)
BASE=$(sudo -u hermes git merge-base main origin/main)

if [ "${LOCAL}" = "${REMOTE}" ]; then
  log "OK: already in sync at ${LOCAL:0:8}"
  exit 0
fi

if [ "${LOCAL}" = "${BASE}" ]; then
  # Fast-forward possible
  sudo -u hermes git merge --ff-only origin/main --quiet
  log "OK: fast-forwarded to $(sudo -u hermes git rev-parse --short main)"
  log "    HANDOVER.md now at $(stat -c%s HANDOVER.md) bytes, $(stat -c%y HANDOVER.md)"
  exit 0
fi

if [ "${REMOTE}" = "${BASE}" ]; then
  # Local has commits origin doesn't. Hermes likely hasn't pushed yet.
  echo "WARN: local has unpushed commits. Hermes should 'git push' from ${CLONE_DIR}." >&2
  echo "WARN: local=${LOCAL:0:8}  origin=${REMOTE:0:8}" >&2
  exit 0
fi

# Diverged
echo "ERROR: branches diverged. local=${LOCAL:0:8}  origin=${REMOTE:0:8}  base=${BASE:0:8}" >&2
echo "ERROR: manual resolution needed in ${CLONE_DIR}" >&2
exit 2
