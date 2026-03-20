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

# Resolve project directory so relative paths work regardless of cwd
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# GCP username detected dynamically after SSH is ready (Step 2b)
GCP_USER="pending"
REMOTE_HOME="pending"

echo "============================================"
echo " GCP Strategy Engine — Automated Run"
echo "============================================"
echo "Config:    $CONFIG_FILE"
echo "Machine:   $MACHINE_TYPE"
echo "Zone:      $ZONE"
echo "Data dir:  $DATA_DIR"
echo "Output:    $OUTPUT_DIR"
echo "============================================"

# Step 1: Create VM
echo "[1/7] Creating VM..."
# Delete existing instance if present
if gcloud compute instances list --filter="name=$INSTANCE_NAME" --format="value(name)" 2>/dev/null | grep -q "$INSTANCE_NAME"; then
    echo "  Existing instance found. Deleting..."
    gcloud compute instances delete "$INSTANCE_NAME" --zone="$ZONE" --quiet
    sleep 15
fi

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

echo "  VM created."

# Step 2: Wait for SSH
echo "[2/7] Waiting for SSH..."
for i in $(seq 1 40); do
    if gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="echo ready" 2>/dev/null | grep -q "ready"; then
        echo "  SSH ready (attempt $i)."
        break
    fi
    echo "  Attempt $i/40..."
    sleep 10
done

# Step 2b: Detect actual remote username
echo "[2b] Detecting remote username..."
GCP_USER=$(gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="whoami" 2>/dev/null | tr -d '[:space:]')
REMOTE_HOME=$(gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command='echo $HOME' 2>/dev/null | tr -d '[:space:]')

if [ -z "$GCP_USER" ]; then
    GCP_ACCOUNT=$(gcloud config get-value account 2>/dev/null)
    GCP_USER=$(echo "$GCP_ACCOUNT" | cut -d@ -f1 | tr '.' '_')
    [ -z "$GCP_USER" ] && GCP_USER="rob"
fi
[ -z "$REMOTE_HOME" ] && REMOTE_HOME="/home/${GCP_USER}"

echo "  Remote user: $GCP_USER"
echo "  Remote home: $REMOTE_HOME"

# Step 3: Create upload dir — use full path, not tilde
echo "[3/7] Preparing upload directory..."
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="mkdir -p ${REMOTE_HOME}/uploads"

# Step 4: Upload data + config — use full remote paths
echo "[4/7] Uploading data files..."
CSV_COUNT=0
for csv in "$DATA_DIR"/*.csv; do
    [ -f "$csv" ] || continue
    echo "  Uploading $(basename "$csv")..."
    gcloud compute scp "$csv" "${INSTANCE_NAME}:${REMOTE_HOME}/uploads/" --zone="$ZONE"
    CSV_COUNT=$((CSV_COUNT + 1))
done

if [ $CSV_COUNT -eq 0 ]; then
    echo "ERROR: No CSV files found in $DATA_DIR"
    exit 1
fi

echo "  Uploading config..."
gcloud compute scp "$CONFIG_FILE" "${INSTANCE_NAME}:${REMOTE_HOME}/uploads/config.yaml" --zone="$ZONE"
echo "  All uploads complete."

# Step 5: Poll for completion
echo "[5/7] Waiting for engine to complete..."
echo "  (This typically takes 4-5 hours for a 4-timeframe ES sweep)"
POLL_START=$(date +%s)
LAST_STATUS=""

while true; do
    sleep 60
    ELAPSED=$(( ($(date +%s) - POLL_START) / 60 ))

    STATUS=$(gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" \
        --command="cat /tmp/engine_status 2>/dev/null || echo PENDING" 2>/dev/null || echo "SSH_ERROR")
    STATUS=$(echo "$STATUS" | tr -d '[:space:]')

    if [ "$STATUS" != "$LAST_STATUS" ]; then
        echo "  [${ELAPSED}m] Status changed: $STATUS"
        LAST_STATUS="$STATUS"
    fi

    # Log tail every 5 minutes
    if [ $((ELAPSED % 5)) -eq 0 ] && [ $ELAPSED -gt 0 ]; then
        LOG_LINE=$(gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" \
            --command="sudo tail -1 /tmp/engine_run.log 2>/dev/null" 2>/dev/null || true)
        if [ -n "$LOG_LINE" ]; then
            echo "  [${ELAPSED}m] $LOG_LINE"
        fi
    fi

    if [[ "$STATUS" == "COMPLETED" ]]; then
        echo "  Engine completed!"
        break
    elif [[ "$STATUS" == FAILED* ]]; then
        echo "  Engine FAILED! Downloading logs..."
        break
    fi

    # Check for SPOT preemption
    VM_STATUS=$(gcloud compute instances describe "$INSTANCE_NAME" --zone="$ZONE" --format="value(status)" 2>/dev/null || echo "UNKNOWN")
    if [ "$VM_STATUS" = "TERMINATED" ] || [ "$VM_STATUS" = "STOPPED" ]; then
        echo "  [${ELAPSED}m] SPOT preempted! Restarting VM..."
        gcloud compute instances start "$INSTANCE_NAME" --zone="$ZONE"
        sleep 60
    fi
done

# Step 6: Copy outputs to user-accessible path, then download
echo "[6/7] Downloading results..."
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" \
    --command="sudo cp -r /root/python-master-strategy-creator/Outputs ${REMOTE_HOME}/outputs 2>/dev/null; sudo cp /tmp/engine_run.log ${REMOTE_HOME}/outputs/ 2>/dev/null; sudo chown -R ${GCP_USER}:${GCP_USER} ${REMOTE_HOME}/outputs/ 2>/dev/null"

mkdir -p "$OUTPUT_DIR"
gcloud compute scp --recurse "${INSTANCE_NAME}:${REMOTE_HOME}/outputs" "$OUTPUT_DIR/" --zone="$ZONE"

# Verify download got files
FILE_COUNT=$(find "$OUTPUT_DIR" -type f 2>/dev/null | wc -l)
if [ "$FILE_COUNT" -eq 0 ]; then
    echo "  WARNING: Download empty! Trying tar fallback..."
    gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" \
        --command="sudo tar czf /tmp/outputs.tar.gz -C /root/python-master-strategy-creator Outputs/ 2>/dev/null; sudo chmod 644 /tmp/outputs.tar.gz"
    gcloud compute scp "${INSTANCE_NAME}:/tmp/outputs.tar.gz" "$OUTPUT_DIR/outputs.tar.gz" --zone="$ZONE"
    if [ -f "$OUTPUT_DIR/outputs.tar.gz" ]; then
        tar -xzf "$OUTPUT_DIR/outputs.tar.gz" -C "$OUTPUT_DIR"
        rm -f "$OUTPUT_DIR/outputs.tar.gz"
        FILE_COUNT=$(find "$OUTPUT_DIR" -type f 2>/dev/null | wc -l)
        echo "  Fallback: got $FILE_COUNT files"
    fi
fi

if [ "$FILE_COUNT" -eq 0 ]; then
    echo "  CRITICAL: No files downloaded. Skipping VM destroy."
    echo "  Manual download: gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command='sudo tar czf /tmp/out.tar.gz -C /root/python-master-strategy-creator Outputs/'"
    echo "  Then: gcloud compute scp ${INSTANCE_NAME}:/tmp/out.tar.gz . --zone=$ZONE"
    exit 1  # Don't destroy
fi

echo "  Results in: $OUTPUT_DIR ($FILE_COUNT files)"

# Show quick summary
MASTER_LB=$(find "$OUTPUT_DIR" -name "master_leaderboard.csv" 2>/dev/null | head -1)
if [ -n "$MASTER_LB" ]; then
    echo ""
    echo "  === MASTER LEADERBOARD ==="
    head -12 "$MASTER_LB"
fi

# Step 7: DESTROY VM
echo "[7/7] Destroying VM..."
gcloud compute instances delete "$INSTANCE_NAME" --zone="$ZONE" --quiet
echo "  VM destroyed. No more billing."

TOTAL_MIN=$(( ($(date +%s) - POLL_START) / 60 ))
echo ""
echo "============================================"
echo " Run Complete — ${TOTAL_MIN} minutes"
echo " Results in: $OUTPUT_DIR"
echo " VM: DESTROYED"
echo "============================================"
