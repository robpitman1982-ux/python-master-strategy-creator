#!/bin/bash
# Sequential runner for 9 new-market 30m+15m SPOT sweeps
# Run from: ~/python-master-strategy-creator on strategy-console
# Usage: nohup bash cloud/run_new_markets_30m15m.sh > /tmp/new_markets_runner.log 2>&1 &

set -e
cd "$(dirname "$0")/.."

CONFIGS=(
    "cloud/config_ad_30m15m_spot.yaml"
    "cloud/config_bp_30m15m_spot.yaml"
    "cloud/config_btc_30m15m_spot.yaml"
    "cloud/config_ec_30m15m_spot.yaml"
    "cloud/config_jy_30m15m_spot.yaml"
    "cloud/config_ng_30m15m_spot.yaml"
    "cloud/config_ty_30m15m_spot.yaml"
    "cloud/config_us_30m15m_spot.yaml"
    "cloud/config_w_30m15m_spot.yaml"
)

echo "=========================================="
echo "NEW MARKETS 30m+15m SPOT SWEEP RUNNER"
echo "Starting: $(date)"
echo "Total configs: ${#CONFIGS[@]}"
echo "=========================================="

for i in "${!CONFIGS[@]}"; do
    CONFIG="${CONFIGS[$i]}"
    MARKET=$(echo "$CONFIG" | sed 's/.*config_\(.*\)_30m15m_spot.yaml/\1/' | tr '[:lower:]' '[:upper:]')
    N=$((i + 1))

    echo ""
    echo "=========================================="
    echo "[$N/${#CONFIGS[@]}] Starting $MARKET — $(date)"
    echo "Config: $CONFIG"
    echo "=========================================="

    # Launch the sweep VM
    PYTHONPATH=. python3 cloud/launch_gcp_run.py --config "$CONFIG"
    LAUNCH_EXIT=$?

    if [ $LAUNCH_EXIT -ne 0 ]; then
        echo "ERROR: launch_gcp_run.py failed for $MARKET (exit $LAUNCH_EXIT)"
        echo "Skipping to next market..."
        continue
    fi

    echo "[$N/${#CONFIGS[@]}] $MARKET sweep completed and uploaded — $(date)"
    echo ""
done

echo "=========================================="
echo "ALL DONE — $(date)"
echo "=========================================="

# Verify no VMs left running
echo "Final VM check:"
gcloud compute instances list --format='table(name,zone,status)' 2>/dev/null || true
