#!/bin/bash
# run_remaining_markets.sh — Sequential sweep: SI, HG, RTY, YM
# Run overnight from strategy-console after GC completes

REPO_DIR="/home/robpitman1982/python-master-strategy-creator"
cd "$REPO_DIR"
git pull

CONFIGS=(
    "cloud/config_si_4tf_ondemand.yaml"
    "cloud/config_hg_4tf_ondemand.yaml"
    "cloud/config_rty_4tf_ondemand.yaml"
    "cloud/config_ym_4tf_ondemand.yaml"
)
MARKETS=("SI" "HG" "RTY" "YM")

echo "=========================================="
echo " REMAINING MARKETS SWEEP — SI HG RTY YM"
echo "=========================================="

BUCKET="gs://strategy-artifacts-robpitman/runs/"

for i in "${!CONFIGS[@]}"; do
    CONFIG="${CONFIGS[$i]}"
    MARKET="${MARKETS[$i]}"
    
    echo ""
    echo "=========================================="
    echo " Starting $MARKET — $(date)"
    echo "=========================================="
    
    RUNS_BEFORE=$(gcloud storage ls "$BUCKET" 2>/dev/null | wc -l)
    
    python3 run_cloud_sweep.py --config "$CONFIG" --fire-and-forget
    
    if [ $? -ne 0 ]; then
        echo "ERROR: $MARKET launch failed. Skipping."
        continue
    fi
    
    echo "Waiting for $MARKET VM to finish..."
    
    while true; do
        STATUS=$(gcloud compute instances describe strategy-sweep --zone us-central1-c --format="value(status)" 2>/dev/null || echo "GONE")
        
        if [ "$STATUS" = "GONE" ]; then
            echo "$MARKET — VM self-deleted."
            break
        elif [ "$STATUS" = "TERMINATED" ] || [ "$STATUS" = "STOPPED" ]; then
            echo "$MARKET — VM terminated. Waiting 30s for upload..."
            sleep 30
            echo "Force deleting VM..."
            gcloud compute instances delete strategy-sweep --zone us-central1-c --quiet 2>/dev/null
            break
        else
            echo "  $(date +%H:%M:%S) — $MARKET VM status: $STATUS"
            sleep 60
        fi
    done
    
    RUNS_AFTER=$(gcloud storage ls "$BUCKET" 2>/dev/null | wc -l)
    if [ "$RUNS_AFTER" -gt "$RUNS_BEFORE" ]; then
        LATEST=$(gcloud storage ls "$BUCKET" 2>/dev/null | sort | tail -1)
        echo "SUCCESS: $MARKET artifacts uploaded -> $LATEST"
        STATUS_JSON=$(gcloud storage cat "${LATEST}run_status.json" 2>/dev/null || echo "NO_STATUS")
        if echo "$STATUS_JSON" | grep -q '"completed"'; then
            echo "CONFIRMED: $MARKET engine completed successfully"
        else
            echo "WARNING: $MARKET status unclear."
        fi
    else
        echo "FAILED: $MARKET artifacts NOT found in bucket!"
    fi
    
    echo ""
    echo "--- $MARKET finished at $(date) ---"
    echo ""
done

echo "=========================================="
echo " ALL DONE — $(date)"
echo "=========================================="
