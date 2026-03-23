#!/bin/bash
# Setup a clean dashboard venv on the strategy-console.
# Run once after a fresh git pull or if the venv is broken.
#
# Usage:
#   bash scripts/setup_dashboard_venv.sh
#
# After this runs, restart the dashboard:
#   sudo systemctl restart strategy-dashboard

set -e

cd "$(dirname "$0")/.."
echo "Working directory: $(pwd)"

# Pick the best available Python (prefer 3.12, fall back to 3.11, then system python3)
PY=""
for candidate in python3.12 python3.11 python3; do
    if command -v "$candidate" &>/dev/null; then
        PY="$candidate"
        echo "Using Python: $PY ($(${PY} --version))"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "ERROR: No suitable Python interpreter found. Install python3.12 first."
    exit 1
fi

echo "Creating venv..."
"$PY" -m venv venv --clear

echo "Activating venv..."
# shellcheck disable=SC1091
source venv/bin/activate

echo "Upgrading pip..."
pip install --upgrade pip --quiet

echo "Installing dashboard dependencies..."
pip install streamlit plotly pandas "numpy<2.2" PyYAML --quiet

echo "Installing project requirements..."
pip install -r requirements.txt --quiet

echo ""
echo "Dashboard venv ready."
echo "Restart with: sudo systemctl restart strategy-dashboard"
echo "Or run manually: venv/bin/streamlit run dashboard.py --server.port 8501"
