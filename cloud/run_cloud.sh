#!/bin/bash
# =============================================================
# Cloud Pipeline Runner for DigitalOcean
# Usage: ./cloud/run_cloud.sh [config_override.yaml]
# =============================================================

set -e

# --- Configuration ---
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DROPLET_NAME="strategy-engine-$(date +%Y%m%d-%H%M)"
DROPLET_SIZE="c-8"          # 8 vCPU dedicated, ~$0.095/hr
DROPLET_REGION="syd1"       # Sydney (closest to Melbourne)
DROPLET_IMAGE="docker-24-04" # Ubuntu 24.04 with Docker pre-installed
SSH_KEY_NAME="strategy-engine"
CONFIG_FILE="${1:-config.yaml}"
DATA_DIR="Data"
OUTPUT_DIR="Outputs"

echo "============================================"
echo " Strategy Engine Cloud Runner"
echo "============================================"
echo "Droplet:  $DROPLET_NAME"
echo "Size:     $DROPLET_SIZE"
echo "Region:   $DROPLET_REGION"
echo "Config:   $CONFIG_FILE"
echo "============================================"

# --- Step 1: Create Droplet ---
echo ""
echo "[1/7] Creating droplet..."
DROPLET_ID=$(doctl compute droplet create "$DROPLET_NAME" \
    --size "$DROPLET_SIZE" \
    --image "$DROPLET_IMAGE" \
    --region "$DROPLET_REGION" \
    --ssh-keys "$(doctl compute ssh-key list --format ID --no-header | head -1)" \
    --wait \
    --format ID \
    --no-header)

echo "Droplet created: ID=$DROPLET_ID"

# Get IP address
DROPLET_IP=$(doctl compute droplet get "$DROPLET_ID" --format PublicIPv4 --no-header)
echo "IP: $DROPLET_IP"

# Wait for SSH to be ready
echo "[2/7] Waiting for SSH..."
for i in $(seq 1 30); do
    if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@"$DROPLET_IP" "echo ready" 2>/dev/null; then
        break
    fi
    echo "  Attempt $i/30..."
    sleep 10
done

# --- Step 2: Upload project ---
echo ""
echo "[3/7] Uploading project files..."
ssh root@"$DROPLET_IP" "mkdir -p /app/Data /app/Outputs"

# Upload code (rsync is faster for many files)
rsync -az --exclude '.git' --exclude '__pycache__' --exclude 'Outputs' --exclude 'Data' \
    --exclude '.claude' --exclude '*.rtf' --exclude 'paste.md' \
    "$PROJECT_DIR/" root@"$DROPLET_IP":/app/

# Upload data files
echo "[4/7] Uploading data files..."
rsync -az "$PROJECT_DIR/$DATA_DIR/" root@"$DROPLET_IP":/app/Data/

# Upload config override if specified
if [ "$CONFIG_FILE" != "config.yaml" ]; then
    scp "$PROJECT_DIR/$CONFIG_FILE" root@"$DROPLET_IP":/app/config.yaml
fi

# --- Step 3: Build and run ---
echo ""
echo "[5/7] Building Docker image on droplet..."
ssh root@"$DROPLET_IP" "cd /app && docker build -t strategy-engine ."

echo ""
echo "[6/7] Running pipeline..."
START_TIME=$(date +%s)

ssh root@"$DROPLET_IP" "docker run --rm \
    -v /app/Data:/app/Data:ro \
    -v /app/Outputs:/app/Outputs \
    -v /app/config.yaml:/app/config.yaml:ro \
    strategy-engine \
    python master_strategy_engine.py --config config.yaml"

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
echo "Pipeline completed in ${ELAPSED}s ($((ELAPSED / 60))m $((ELAPSED % 60))s)"

# --- Step 4: Download results ---
echo ""
echo "[7/7] Downloading results..."
RESULTS_DIR="$PROJECT_DIR/cloud_results/${DROPLET_NAME}"
mkdir -p "$RESULTS_DIR"
rsync -az root@"$DROPLET_IP":/app/Outputs/ "$RESULTS_DIR/"
echo "Results saved to: $RESULTS_DIR"

# --- Step 5: Destroy droplet ---
echo ""
echo "Destroying droplet $DROPLET_NAME..."
doctl compute droplet delete "$DROPLET_ID" --force
echo "Droplet destroyed. Run complete."

# --- Summary ---
echo ""
echo "============================================"
echo " CLOUD RUN COMPLETE"
echo "============================================"
echo "Results:    $RESULTS_DIR"
echo "Runtime:    ${ELAPSED}s ($((ELAPSED / 60))m)"
echo "Est. cost:  ~\$$(echo "scale=2; $ELAPSED * 0.095 / 3600" | bc) (at \$0.095/hr)"
echo "============================================"
