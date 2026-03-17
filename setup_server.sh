#!/usr/bin/env bash
# setup_server.sh — Run once on a fresh Ubuntu 24.04 droplet to prepare the environment.
# Usage: bash setup_server.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_DIR/venv"

echo "=== 1/4  Ensuring Python 3.11+ is available ==="
if ! command -v python3.11 &>/dev/null; then
    apt-get update -qq
    apt-get install -y python3.11 python3.11-venv python3.11-dev gcc g++ 2>&1 | tail -5
fi
python3.11 --version

echo ""
echo "=== 2/4  Creating virtual environment at $VENV_DIR ==="
python3.11 -m venv "$VENV_DIR"

echo ""
echo "=== 3/4  Installing dependencies ==="
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install -r "$REPO_DIR/requirements.txt"
echo "Installed packages:"
"$VENV_DIR/bin/pip" list --format=columns | grep -E "numpy|pandas|pyyaml|PyYAML"

echo ""
echo "=== 4/4  Creating output directories ==="
mkdir -p "$REPO_DIR/Data"
mkdir -p "$REPO_DIR/Outputs/logs"
chmod 755 "$REPO_DIR/Data" "$REPO_DIR/Outputs"

echo ""
echo "✅  Setup complete."
echo "   Next: upload your CSV file to $REPO_DIR/Data/"
echo "   Then: bash run_engine.sh"
