#!/bin/bash
# =============================================================
# GCP Startup Script — Strategy Discovery Engine
# Runs as root on first boot. Sets up environment, waits for
# data files, then runs the engine.
# =============================================================
set -e

REPO_URL="https://github.com/robpitman1982-ux/python-master-strategy-creator.git"
WORK_DIR="/root/python-master-strategy-creator"
# GCP SCP runs as the OS Login user, which lands in /home/<username>/
# We look for data in /home/*/uploads/ (the run script puts them there)
UPLOAD_SCAN_DIR="/home"
LOG_FILE="/var/log/engine-startup.log"

exec > >(tee -a "$LOG_FILE") 2>&1
echo "=== GCP Startup Script started at $(date -u) ==="

# --- Install dependencies ---
echo "[1/6] Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3-pip python3-venv git tmux > /dev/null 2>&1

# --- Clone repo ---
echo "[2/6] Cloning repository..."
cd /root
if [ -d "$WORK_DIR" ]; then
    cd "$WORK_DIR" && git pull
else
    git clone "$REPO_URL"
    cd "$WORK_DIR"
fi

# --- Create venv ---
echo "[3/6] Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --quiet numpy pandas pyyaml pytest

# --- Create Data directory ---
mkdir -p Data Outputs

# --- Wait for ALL data files ---
echo "[4/6] Waiting for data files to appear..."
# We need at least 1 CSV file. But we also wait an extra 60 seconds
# after the first file appears to allow remaining uploads to complete.
WAITED=0
MAX_WAIT=1800
DATA_FOUND=0
FIRST_FOUND_AT=0

while [ $WAITED -lt $MAX_WAIT ]; do
    CSV_COUNT=$(find $UPLOAD_SCAN_DIR -maxdepth 3 -name "ES_*.csv" -o -name "CL_*.csv" -o -name "NQ_*.csv" -o -name "GC_*.csv" 2>/dev/null | wc -l)

    if [ "$CSV_COUNT" -gt 0 ] && [ "$FIRST_FOUND_AT" -eq 0 ]; then
        FIRST_FOUND_AT=$WAITED
        echo "  First CSV found after ${WAITED}s. Waiting 60s for remaining uploads..."
    fi

    # Wait 60 seconds after first file to let all uploads complete
    if [ "$FIRST_FOUND_AT" -gt 0 ] && [ $((WAITED - FIRST_FOUND_AT)) -ge 60 ]; then
        CSV_COUNT=$(find $UPLOAD_SCAN_DIR -maxdepth 3 -name "ES_*.csv" -o -name "CL_*.csv" -o -name "NQ_*.csv" -o -name "GC_*.csv" 2>/dev/null | wc -l)
        echo "  Found $CSV_COUNT CSV file(s) total. Proceeding."
        DATA_FOUND=1
        break
    fi

    sleep 10
    WAITED=$((WAITED + 10))
    if [ $((WAITED % 60)) -eq 0 ]; then
        echo "  Still waiting for data files... (${WAITED}s elapsed)"
    fi
done

if [ $DATA_FOUND -eq 0 ]; then
    echo "ERROR: No data files found after ${MAX_WAIT}s. Exiting."
    exit 1
fi

# --- Move data files to correct location ---
echo "[5/6] Moving data files and config..."

# Copy ALL CSVs from any user's upload directory
for csv_file in $(find $UPLOAD_SCAN_DIR -maxdepth 3 -name "*.csv" 2>/dev/null); do
    cp "$csv_file" "$WORK_DIR/Data/"
    echo "  Copied: $(basename $csv_file)"
done

# Copy config if uploaded (look for .yaml files)
UPLOADED_CONFIG=$(find $UPLOAD_SCAN_DIR -maxdepth 3 -name "*.yaml" 2>/dev/null | head -1)
if [ -n "$UPLOADED_CONFIG" ]; then
    cp "$UPLOADED_CONFIG" "$WORK_DIR/config.yaml"
    echo "  Using uploaded config: $(basename $UPLOADED_CONFIG)"
else
    echo "  No config uploaded, using repo default"
fi

echo "  Data files in place:"
ls -la "$WORK_DIR/Data/"
echo "  Config:"
head -5 "$WORK_DIR/config.yaml"

# --- Run the engine ---
echo "[6/6] Starting engine..."
cd "$WORK_DIR"
source venv/bin/activate

echo "RUNNING" > /tmp/engine_status
# Clear any old log
rm -f /tmp/engine_run.log

python master_strategy_engine.py > /tmp/engine_run.log 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "COMPLETED" > /tmp/engine_status
    echo "=== Engine completed successfully at $(date -u) ==="
else
    echo "FAILED:$EXIT_CODE" > /tmp/engine_status
    echo "=== Engine FAILED with exit code $EXIT_CODE at $(date -u) ==="
fi

# --- Copy outputs to a user-accessible location ---
# Find the first non-root user home directory
USER_HOME=$(find /home -maxdepth 1 -mindepth 1 -type d 2>/dev/null | head -1)
if [ -n "$USER_HOME" ]; then
    mkdir -p "$USER_HOME/outputs"
    cp -r "$WORK_DIR/Outputs/"* "$USER_HOME/outputs/" 2>/dev/null || true
    cp /tmp/engine_run.log "$USER_HOME/outputs/" 2>/dev/null || true
    # Fix permissions so the SCP user can download
    chown -R "$(basename $USER_HOME)":"$(basename $USER_HOME)" "$USER_HOME/outputs/" 2>/dev/null || true
    echo "Outputs copied to $USER_HOME/outputs/"
fi

# Also copy to /tmp/engine_outputs as a guaranteed fallback path
sudo mkdir -p /tmp/engine_outputs
sudo cp -r "$WORK_DIR/Outputs/"* /tmp/engine_outputs/ 2>/dev/null || true
sudo cp /tmp/engine_run.log /tmp/engine_outputs/ 2>/dev/null || true
sudo chmod -R 755 /tmp/engine_outputs
echo "Outputs also available at /tmp/engine_outputs/"

echo "=== Startup script finished at $(date -u) ==="
