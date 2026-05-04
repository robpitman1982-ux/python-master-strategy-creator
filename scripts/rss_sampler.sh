#!/bin/bash
# Sprint 98 RSS sampler. Polls RSS of the master_strategy_engine process tree
# every N seconds and writes a CSV with timestamp, parent_rss_kb,
# total_children_rss_kb, child_count, top5_child_rss_kb.
#
# Usage: ./rss_sampler.sh OUTPUT_CSV [INTERVAL_SECONDS]
set -u
OUT="${1:-/tmp/rss_sample.csv}"
INTERVAL="${2:-30}"
echo "ts,parent_pid,parent_rss_kb,total_children_rss_kb,child_count,top1_kb,top5_total_kb,total_rss_kb,total_swap_kb" > "$OUT"

while true; do
    # Find the parent master_strategy_engine.py (ppid=1)
    PARENT_PID=$(ps -eo pid,ppid,cmd | grep master_strategy_engine.py | grep -v grep | awk '$2==1 {print $1}' | head -1)
    if [ -z "$PARENT_PID" ]; then
        # No engine running; idle sample
        TOTAL_RSS=$(awk '/^MemAvailable/ {print $2; exit}' /proc/meminfo 2>/dev/null || echo 0)
        TOTAL_SWAP=$(awk '/^SwapFree/ {print $2; exit}' /proc/meminfo 2>/dev/null || echo 0)
        TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
        echo "$TS,,,,,0,0,0,0" >> "$OUT"
        sleep "$INTERVAL"
        continue
    fi

    # Parent RSS
    P_RSS=$(awk '/^VmRSS/ {print $2; exit}' /proc/$PARENT_PID/status 2>/dev/null || echo 0)

    # Child RSS (all master_strategy_engine processes except the parent)
    CHILD_RSS_LIST=$(pgrep -f master_strategy_engine.py | while read pid; do
        if [ "$pid" != "$PARENT_PID" ]; then
            awk '/^VmRSS/ {print $2; exit}' /proc/$pid/status 2>/dev/null || true
        fi
    done | sort -rn)
    CHILD_COUNT=$(echo "$CHILD_RSS_LIST" | grep -c '^[0-9]')
    TOTAL_CHILDREN_RSS=$(echo "$CHILD_RSS_LIST" | awk '{s+=$1} END {print s+0}')
    TOP1=$(echo "$CHILD_RSS_LIST" | head -1)
    TOP5_TOTAL=$(echo "$CHILD_RSS_LIST" | head -5 | awk '{s+=$1} END {print s+0}')
    TOTAL_RSS=$((P_RSS + TOTAL_CHILDREN_RSS))

    # System swap
    TOTAL_SWAP=$(awk '/^SwapTotal/ {tot=$2} /^SwapFree/ {free=$2} END {print tot-free}' /proc/meminfo)

    TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    echo "$TS,$PARENT_PID,$P_RSS,$TOTAL_CHILDREN_RSS,$CHILD_COUNT,${TOP1:-0},$TOP5_TOTAL,$TOTAL_RSS,$TOTAL_SWAP" >> "$OUT"

    sleep "$INTERVAL"
done
