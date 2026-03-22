#!/usr/bin/env bash
set -e
cd ~/python-master-strategy-creator
git pull origin main
sudo systemctl restart strategy-dashboard
