#!/bin/bash
# ingest-handover.sh
# Installed on g9 at /usr/local/bin/ingest-handover (mode 755, root-owned).
# Invoked by: ssh g9-ts "sudo /usr/local/bin/ingest-handover"
# Expects /tmp/HANDOVER.md to exist (just scp'd in by caller).
#
# Side effects:
#   - Moves /tmp/HANDOVER.md -> /data/shared/handover/HANDOVER.md (hermes:agents 640)
#   - Ensures symlink /home/hermes/.hermes/memories/HANDOVER.md -> canonical
#
# Design: latest-only, overwrite each time. No archive.

set -euo pipefail

SRC=/tmp/HANDOVER.md
DST_DIR=/data/shared/handover
DST=${DST_DIR}/HANDOVER.md
SYMLINK=/home/hermes/.hermes/memories/HANDOVER.md

if [ ! -f "${SRC}" ]; then
  echo "ERROR: ${SRC} not found. scp HANDOVER.md to g9 first." >&2
  exit 1
fi

# Ensure dest dir exists with correct ownership/perms
mkdir -p "${DST_DIR}"
chown hermes:agents "${DST_DIR}"
chmod 2775 "${DST_DIR}"

# Move into place (overwrites previous)
mv "${SRC}" "${DST}"
chown hermes:agents "${DST}"
chmod 640 "${DST}"

# Ensure symlink in hermes's memory dir
mkdir -p "$(dirname "${SYMLINK}")"
chown hermes:hermes "$(dirname "${SYMLINK}")"

# If a regular file exists at symlink path, back it up before replacing
if [ -f "${SYMLINK}" ] && [ ! -L "${SYMLINK}" ]; then
  mv "${SYMLINK}" "${SYMLINK}.bak.$(date +%s)"
fi

# Create/refresh symlink (runs as root, readable by hermes)
ln -sfn "${DST}" "${SYMLINK}"
chown -h hermes:hermes "${SYMLINK}"

echo "OK: handover ingested"
echo "  canonical: ${DST} ($(stat -c%s "${DST}") bytes, $(stat -c%y "${DST}"))"
echo "  symlink:   ${SYMLINK} -> $(readlink -f "${SYMLINK}")"
