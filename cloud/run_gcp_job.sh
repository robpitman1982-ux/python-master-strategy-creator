#!/bin/bash
# =============================================================
# GCP Automated Run — Strategy Discovery Engine
# Usage: bash cloud/run_gcp_job.sh [config_file]
# =============================================================
set -e

CONFIG_FILE="${1:-cloud/config_es_all_timeframes_gcp96.yaml}"
INSTANCE_NAME="strategy-sweep"
ZONE="australia-southeast2-a"
MACHINE_TYPE="n2-highcpu-96"
DATA_DIR="Data"
TIMESTAMP=$(date +%Y%m%d_%H%M)
OUTPUT_DIR="cloud_outputs_${TIMESTAMP}"
STARTUP_SCRIPT="cloud/gcp_startup.sh"

echo "============================================"
echo " GCP Strategy Engine — Automated Run"
echo "============================================"
echo "Config:  $CONFIG_FILE"
echo "Machine: $MACHINE_TYPE"
echo "Zone:    $ZONE"
echo "============================================"

# Step 1: Create VM
echo "[1/7] Creating VM..."
gcloud compute instances create "$INSTANCE_NAME" \
    --zone="$ZONE" \
    --machine-type="$MACHINE_TYPE" \
    --provisioning-model=SPOT \
    --instance-termination-action=STOP \
    --image-family=ubuntu-2404-lts-amd64 \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=120GB \
    --boot-disk-type=pd-ssd \
    --metadata-from-file startup-script="$STARTUP_SCRIPT"

# Step 2: Wait for SSH
echo "[2/7] Waiting for SSH..."
for i in $(seq 1 30); do
    if gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="echo ready" 2>/dev/null; then
        echo "  SSH ready."
        break
    fi
    echo "  Attempt $i/30..."
    sleep 10
done

# Step 3: Create upload dir
echo "[3/7] Preparing upload directory..."
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="mkdir -p ~/uploads"

# Step 4: Upload data + config
echo "[4/7] Uploading data files..."
for csv in "$DATA_DIR"/*.csv; do
    [ -f "$csv" ] || continue
    echo "  Uploading $(basename "$csv")..."
    gcloud compute scp "$csv" "${INSTANCE_NAME}:~/uploads/" --zone="$ZONE"
done
echo "  Uploading config..."
gcloud compute scp "$CONFIG_FILE" "${INSTANCE_NAME}:~/uploads/config.yaml" --zone="$ZONE"

# Step 5: Poll for completion
echo "[5/7] Waiting for engine to complete..."
echo "  (This typically takes 4-5 hours for a 4-timeframe ES sweep)"
POLL_START=$(date +%s)

while true; do
    sleep 60
    ELAPSED=$(( ($(date +%s) - POLL_START) / 60 ))

    STATUS=$(gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" \
        --command="cat /tmp/engine_status 2>/dev/null || echo PENDING" 2>/dev/null || echo "SSH_ERROR")
    STATUS=$(echo "$STATUS" | tr -d '[:space:]')

    echo "  [${ELAPSED}m] Status: $STATUS"

    if [[ "$STATUS" == "COMPLETED" ]]; then
        echo "  Engine completed!"
        break
    elif [[ "$STATUS" == FAILED* ]]; then
        echo "  Engine FAILED!"
        break
    fi
done

# Step 6: Download results
echo "[6/7] Downloading results to $OUTPUT_DIR..."
mkdir -p "$OUTPUT_DIR"
gcloud compute scp --recurse "${INSTANCE_NAME}:~/outputs/*" "$OUTPUT_DIR/" --zone="$ZONE"
echo "  Results in: $OUTPUT_DIR"

# Step 7: DESTROY VM
echo "[7/7] Destroying VM..."
gcloud compute instances delete "$INSTANCE_NAME" --zone="$ZONE" --quiet
echo "  VM destroyed. No more billing."

echo ""
echo "============================================"
echo " Run Complete — $(( ($(date +%s) - POLL_START) / 60 )) minutes"
echo " Results in: $OUTPUT_DIR"
echo " VM: DESTROYED"
echo "============================================"
