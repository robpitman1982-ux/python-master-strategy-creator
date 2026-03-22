#!/bin/bash
set -e

cd ~/python-master-strategy-creator

echo "Pulling latest repo..."
git pull origin main

echo "Updating environment..."
source venv/bin/activate
pip install -r requirements.txt

echo "Restarting dashboard..."
systemctl restart strategy-dashboard

echo "Done."
git rev-parse HEAD
