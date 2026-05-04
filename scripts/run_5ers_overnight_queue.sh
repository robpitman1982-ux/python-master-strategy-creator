#!/usr/bin/env bash
# Per-host queue runner for the5ers overnight 5m sweep.
# Usage: ./run_5ers_overnight_queue.sh <market1> <market2> ...
# Logs progress to /tmp/5ers_queue_progress.log and per-market /tmp/5ers_<MARKET>.log.

set -u  # treat unset vars as error
# NOT set -e: we want to keep queue going even if one market crashes.

cd /home/rob/python-master-strategy-creator
source /home/rob/venv/bin/activate

PROGRESS=/tmp/5ers_queue_progress.log
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Queue started: $*" >> "$PROGRESS"

for MARKET in "$@"; do
    CFG="configs/local_sweeps/${MARKET}_5m_5ers.yaml"
    LOG="/tmp/5ers_${MARKET}.log"

    if [ ! -f "$CFG" ]; then
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] SKIP ${MARKET} — config not found: $CFG" >> "$PROGRESS"
        continue
    fi

    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] START ${MARKET}" >> "$PROGRESS"
    START_TS=$(date +%s)

    python master_strategy_engine.py --config "$CFG" > "$LOG" 2>&1
    EXIT_CODE=$?

    ELAPSED=$(( $(date +%s) - START_TS ))
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] DONE ${MARKET} (exit=0, elapsed=${ELAPSED}s)" >> "$PROGRESS"
    else
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] FAIL ${MARKET} (exit=${EXIT_CODE}, elapsed=${ELAPSED}s) — continuing queue" >> "$PROGRESS"
    fi
done

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Queue COMPLETE" >> "$PROGRESS"
