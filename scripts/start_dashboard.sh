#!/usr/bin/env bash
set -e
cd ~/python-master-strategy-creator
source venv/bin/activate
streamlit run dashboard.py --server.port 8501
