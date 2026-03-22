#!/bin/bash
set -e

cd ~/python-master-strategy-creator

source venv/bin/activate

exec streamlit run dashboard.py \
    --server.port 8501 \
    --server.address 0.0.0.0
