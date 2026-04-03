#!/bin/bash
# run_all_markets.sh — Sequential sweep of all 8 markets
# Run from strategy-console: bash run_all_markets.sh
# Each market launches a VM, waits for it to finish, then launches the next.
# On-demand VMs — no preemption risk.

set -e

REPO_DIR="/home/robpitman1982/python-master-strategy-creator"
cd "$REPO_DIR"
git pull

CONFIGS=(
    "cloud/config_es_4tf_ondemand.yaml"
    "cloud/config_nq_4tf_ondemand.yaml"
    "cloud/config_cl_4tf_ondemand.yaml"
    "cloud/config_gc_4tf_ondemand.yaml"
    "cloud/config_si_4tf_ondemand.yaml"
    "cloud/config_hg_4tf_ondemand.yaml"
    "cloud/config_rty_4tf_ondemand.yaml"
    "cloud/config_ym_4tf_ondemand.yaml"
)

MARKETS=("ES" "NQ" "CL" "GC" "SI" "HG" "RTY" "YM")

echo "=========================================="
echo " ALL-MARKETS SWEEP — 8 markets x 4 TFs"
echo "=========================================="
echo ""

TOTAL=${#CONFIGS[@]}
COMPLETED=0
FAILED=0
START_TIME=$(date +%s)

for i in "${!CONFIGS[@]}"; do
    CONFIG="${CONFIGS[$i]}"
    MARKET="${MARKETS[$i]}"
    IDX=$((i + 1))
    
    echo ""
    echo "=========================================="
    echo " [$IDX/$TOTAL] Starting $MARKET sweep"
    echo " Config: $CONFIG"
    echo " Time: $(date)"
    echo "=========================================="
    
    # Launch fire-and-forget
    python3 run_cloud_sweep.py --config "$CONFIG" --fire-and-forget
    
    if [ $? -ne 0 ]; then
        echo "ERROR: $MARKET launch failed. Skipping to next market."
        FAILED=$((FAILED + 1))
        continue
    fi
    
    echo ""
    echo "Waiting for $MARKET VM to finish and self-delete..."
    
    # Poll every 60 seconds — handle TERMINATED VMs that didn't fully delete
    while true; do
        STATUS=$(gcloud compute instances describe strategy-sweep --zone us-central1-c --format="value(status)" 2>/dev/null || echo "GONE")
        
        if [ "$STATUS" = "GONE" ]; then
            echo "$MARKET complete — VM self-deleted."
            COMPLETED=$((COMPLETED + 1))
            break
        elif [ "$STATUS" = "TERMINATED" ] || [ "$STATUS" = "STOPPED" ]; then
            echo "$MARKET — VM terminated. Force deleting..."
            gcloud compute instances delete strategy-sweep --zone us-central1-c --quiet 2>/dev/null
            COMPLETED=$((COMPLETED + 1))
            echo "$MARKET complete."
            break
        else
            echo "  $(date +%H:%M:%S) — $MARKET VM status: $STATUS"
            sleep 60
        fi
    done
    
    echo ""
done

END_TIME=$(date +%s)
ELAPSED=$(( (END_TIME - START_TIME) / 60 ))

echo ""
echo "=========================================="
echo " ALL-MARKETS SWEEP COMPLETE"
echo " Completed: $COMPLETED / $TOTAL"
echo " Failed: $FAILED"
echo " Total time: ${ELAPSED} minutes"
echo " Time: $(date)"
echo "=========================================="
