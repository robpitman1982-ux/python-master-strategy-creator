#!/usr/bin/env bash
set -e

cd ~/python-master-strategy-creator

echo "Updating strategy-console from GitHub..."
git pull origin main

echo "Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt

echo "Restarting dashboard service..."
systemctl restart strategy-dashboard || true

echo "Current commit:"
git rev-parse HEAD
