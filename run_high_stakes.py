#!/usr/bin/env python3
"""Run portfolio selector for High Stakes $100K."""
import sys
import time
sys.path.insert(0, ".")

from modules.portfolio_selector import run_portfolio_selection

config = {
    "pipeline": {
        "portfolio_selector": {
            "prop_firm_program": "high_stakes",
            "prop_firm_target": 100_000,
            "n_min": 3,
            "n_max": 8,
            "candidate_cap": 60,
            "quality_flags": ["ROBUST", "ROBUST_BORDERLINE", "STABLE"],
            "bootcamp_score_min": 40,
            "oos_pf_threshold": 1.0,
            "n_sims_mc": 10_000,
            "n_sims_sizing": 1_000,
            "use_multi_layer_correlation": True,
            "use_regime_gate": True,
            "mc_method": "block_bootstrap",
        }
    }
}

print("=" * 60)
print("PORTFOLIO SELECTOR — High Stakes $100K")
print("=" * 60)
