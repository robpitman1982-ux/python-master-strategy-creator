#!/bin/bash
set -euo pipefail

CONFIG_FILE="${1:-cloud/config_es_all_timeframes_gcp96.yaml}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

exec python3 cloud/launch_gcp_run.py --config "$CONFIG_FILE"
