#!/usr/bin/env bash
set -e

cd ~/python-master-strategy-creator

SERVICE_RESTART_OK=1

echo "Updating strategy-console from GitHub..."
git pull origin main

echo "Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt

echo "Restarting dashboard service..."
if ! systemctl restart strategy-dashboard; then
  SERVICE_RESTART_OK=0
  echo "WARNING: strategy-dashboard restart failed. Check systemctl status strategy-dashboard" >&2
fi

echo "Current commit:"
git rev-parse HEAD

if [ "$SERVICE_RESTART_OK" -eq 1 ]; then
  echo "Deploy summary: code updated, dependencies installed, dashboard restart requested successfully."
else
  echo "Deploy summary: code updated, dependencies installed, but dashboard restart failed."
fi
