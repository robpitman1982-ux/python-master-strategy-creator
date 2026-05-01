#!/usr/bin/env bash
# Install the strategy dashboard as a systemd user service on c240.
# Run once from inside the repo: bash scripts/install_dashboard_service.sh
# After install, the dashboard starts on boot and restarts on crash.
# Access at http://<c240-tailscale-ip>:8501

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_STREAMLIT="$HOME/venv/bin/streamlit"
SERVICE_NAME="strategy-dashboard"
SERVICE_FILE="$HOME/.config/systemd/user/${SERVICE_NAME}.service"
PORT=8501

# Verify streamlit is where we expect it
if [[ ! -x "$VENV_STREAMLIT" ]]; then
    echo "ERROR: streamlit not found at $VENV_STREAMLIT"
    echo "Install it: ~/venv/bin/pip install streamlit plotly"
    exit 1
fi

echo "Repo:      $REPO_DIR"
echo "Streamlit: $VENV_STREAMLIT"
echo "Port:      $PORT"
echo ""

mkdir -p "$(dirname "$SERVICE_FILE")"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Strategy Discovery Dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=${REPO_DIR}
ExecStart=${VENV_STREAMLIT} run dashboard.py --server.port ${PORT} --server.headless true --server.address 0.0.0.0
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

echo "Service file written to: $SERVICE_FILE"

# Enable lingering so user services survive logout
loginctl enable-linger "$USER" 2>/dev/null || true

systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"
systemctl --user restart "$SERVICE_NAME"

sleep 2
systemctl --user status "$SERVICE_NAME" --no-pager

echo ""
echo "Done. Dashboard is running on port $PORT."
echo "Access at: http://$(hostname -I | awk '{print $1}'):${PORT}"
echo ""
echo "Useful commands:"
echo "  systemctl --user status $SERVICE_NAME"
echo "  systemctl --user restart $SERVICE_NAME"
echo "  journalctl --user -u $SERVICE_NAME -f"
