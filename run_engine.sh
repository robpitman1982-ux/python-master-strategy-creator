#!/usr/bin/env bash
# run_engine.sh — Activate venv and run the strategy engine in the background.
# Logs are written to Outputs/logs/<timestamp>.log
# Safe to disconnect SSH after starting — nohup keeps it running.
#
# Usage:
#   bash run_engine.sh                         # uses default config.yaml
#   bash run_engine.sh --config cloud/config_full_es.yaml

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_DIR/venv"
LOG_DIR="$REPO_DIR/Outputs/logs"

if [[ ! -d "$VENV_DIR" ]]; then
    echo "ERROR: venv not found at $VENV_DIR — run setup_server.sh first." >&2
    exit 1
fi

mkdir -p "$LOG_DIR"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/run_${TIMESTAMP}.log"

# Pass any extra arguments (e.g. --config) through to master_strategy_engine.py
EXTRA_ARGS="${@:-}"

echo "Starting engine..."
echo "  Config args : ${EXTRA_ARGS:-<default config.yaml>}"
echo "  Log file    : $LOG_FILE"
echo ""

nohup "$VENV_DIR/bin/python" "$REPO_DIR/master_strategy_engine.py" $EXTRA_ARGS \
    > "$LOG_FILE" 2>&1 &

PID=$!
echo "Engine running as PID $PID"
echo "  tail -f $LOG_FILE     — to follow output"
echo "  kill $PID             — to stop"
echo ""
echo "PID saved to $REPO_DIR/engine.pid"
echo "$PID" > "$REPO_DIR/engine.pid"
