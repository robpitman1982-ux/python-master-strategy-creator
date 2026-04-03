#!/usr/bin/env python3
"""
Cloud Portfolio Selector — Runs portfolio selection on a 96-vCPU GCP VM.

Usage (from strategy-console):
    python3 run_cloud_portfolio.py [--config cloud/config_portfolio.yaml] [--fire-and-forget]

This script:
1. Bundles the repo + Outputs/runs data (strategy_returns.csv files) to GCS
2. Spins up an n2-highcpu-96 VM
3. Runs generate_returns.py (parallel rebuild) then portfolio_selector
4. Downloads results and self-destructs

The key parallelisation: ProcessPoolExecutor across the MC simulations
for each portfolio combination, and across weight combos in sizing.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


