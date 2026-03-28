#!/bin/bash
# run_cl_nq.sh — Sequential sweep: CL then NQ
# Run from strategy-console: bash run_cl_nq.sh
# Each market launches a VM, waits for completion, force-deletes, then next.

set -e

REPO_DIR="/home/robpitman1982/python-master-strategy-creator"
cd "$REPO_DIR"
git pull

CONFIGS=(
    "cloud/config_cl_4tf_ondemand.yaml"
    "cloud/config_nq_4tf_ondemand.yaml"
)
MARKETS=("CL" "NQ")

echo "=========================================="
echo " CL + NQ SWEEP"
echo "=========================================="

for i in "${!CONFIGS[@]}"; do
    CONFIG="${CONFIGS[$i]}"
    MARKET="${MARKETS[$i]}"
    
    echo ""
    echo "=========================================="
    echo " Starting $MARKET — $(date)"
    echo "=========================================="
    
    python3 run_cloud_sweep.py --config "$CONFIG" --fire-and-forget
    
    if [ $? -ne 0 ]; then
        echo "ERROR: $MARKET launch failed. Skipping."
        continue
    fi
    
    echo "Waiting for $MARKET VM to finish..."
    
    while true; do
        STATUS=$(gcloud compute instances describe strategy-sweep --zone us-central1-c --format="value(status)" 2>/dev/null || echo "GONE")
        
        if [ "$STATUS" = "GONE" ]; then
            echo "$MARKET — VM already deleted. Done."
            break
        elif [ "$STATUS" = "TERMINATED" ] || [ "$STATUS" = "STOPPED" ]; then
            echo "$MARKET — VM terminated. Force deleting..."
            gcloud compute instances delete strategy-sweep --zone us-central1-c --quiet 2>/dev/null
            echo "$MARKET — Done."
            break
        else
            echo "  $(date +%H:%M:%S) — $MARKET VM status: $STATUS"
            sleep 60
        fi
    done
    
    echo ""
done

echo "=========================================="
echo " ALL DONE — $(date)"
echo "=========================================="
