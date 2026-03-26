"""
Tests for modules/cross_dataset_evaluator.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.cross_dataset_evaluator import evaluate_cross_dataset_portfolio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_leaderboard_row(
    strategy_type: str = "mean_reversion",
    strategy_name: str = "ATR0.4_DIST1.2_MOM0",
    accepted: bool = True,
) -> dict:
    return {
        "strategy_type": strategy_type,
        "leader_strategy_name": strategy_name,
        "accepted_final": str(accepted),
        "quality_flag": "ROBUST",
        "leader_pf": 1.5,
        "leader_net_pnl": 12000.0,
        "leader_max_drawdown": 2000.0,
        "leader_trades": 120,
        "leader_trades_per_year": 12.0,
        "is_pf": 1.4,
        "oos_pf": 1.3,
        "recent_12m_pf": 1.2,
        "best_combo_strategy_name": strategy_name,
        "leader_hold_bars": 3,
        "leader_stop_distance_points": 1.0,
        "leader_min_avg_range": 0.0,
        "leader_momentum_lookback": 0,
        "leader_exit_type": "time_stop",
        "leader_trailing_stop_atr": None,
        "leader_profit_target_atr": None,
        "leader_signal_exit_reference": None,
        "leader_source": "refined",
    }


def _make_dummy_trades(n: int = 10) -> pd.DataFrame:
    """Return a minimal trades DataFrame with exit_time and net_pnl columns."""
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.DataFrame({"exit_time": dates, "net_pnl": [100.0] * n})


# ---------------------------------------------------------------------------
# Test 1: empty outputs directory → returns gracefully, no files created
# ---------------------------------------------------------------------------

def test_evaluate_cross_dataset_empty_returns_gracefully():
    """No leaderboard files → function returns without raising, no outputs created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        datasets = [
            {"market": "ES", "timeframe": "60m", "path": str(root / "dummy.csv")},
        ]
        # Should not raise
        evaluate_cross_dataset_portfolio(
            outputs_root=root,
            datasets=datasets,
            oos_split_date="2019-01-01",
        )

        assert not (root / "cross_timeframe_correlation_matrix.csv").exists()
        assert not (root / "cross_timeframe_portfolio_review.csv").exists()
        assert not (root / "cross_timeframe_yearly_stats.csv").exists()


# ---------------------------------------------------------------------------
# Test 2: single accepted strategy → correlation skipped, no crash
# ---------------------------------------------------------------------------

def test_evaluate_cross_dataset_single_strategy_skips_correlation():
    """One accepted strategy → no correlation matrix (need >= 2), no crash."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        ds_market, ds_tf = "ES", "60m"
        ds_dir = root / f"{ds_market}_{ds_tf}"
        ds_dir.mkdir()

        lb_df = pd.DataFrame([_make_leaderboard_row()])
        lb_df.to_csv(ds_dir / "family_leaderboard_results.csv", index=False)

        dummy_data_path = root / "dummy.csv"
        dummy_data_path.write_text("date,open,high,low,close,volume\n2020-01-01,3300,3310,3290,3305,1000\n")

        datasets = [{"market": ds_market, "timeframe": ds_tf, "path": str(dummy_data_path)}]

        # Patch _rebuild_strategy_from_leaderboard_row so we don't need real data
        with patch(
            "modules.cross_dataset_evaluator._rebuild_strategy_from_leaderboard_row",
            return_value=(_make_dummy_trades(), "FilterA,FilterB", object()),
        ):
            evaluate_cross_dataset_portfolio(
                outputs_root=root,
                datasets=datasets,
                oos_split_date="2019-01-01",
            )

        # With only 1 strategy, correlation matrix should NOT be created
        assert not (root / "cross_timeframe_correlation_matrix.csv").exists()


# ---------------------------------------------------------------------------
# Test 3: two strategies across two datasets → output files produced
# ---------------------------------------------------------------------------

def test_evaluate_cross_dataset_produces_output_files():
    """Two accepted strategies across two datasets → all three output files created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        datasets = []
        for market, tf in [("ES", "60m"), ("ES", "daily")]:
            ds_dir = root / f"{market}_{tf}"
            ds_dir.mkdir()

            lb_df = pd.DataFrame([_make_leaderboard_row(
                strategy_type="mean_reversion" if tf == "60m" else "trend",
                strategy_name=f"ATR0.4_{tf}",
            )])
            lb_df.to_csv(ds_dir / "family_leaderboard_results.csv", index=False)

            dummy_csv = root / f"dummy_{tf}.csv"
            dummy_csv.write_text("date,open,high,low,close,volume\n2020-01-01,3300,3310,3290,3305,1000\n")
            datasets.append({"market": market, "timeframe": tf, "path": str(dummy_csv)})

        dummy_price_df = pd.DataFrame({"Date": ["2020-01-01"], "Open": [3300.0]})

        with patch("modules.cross_dataset_evaluator.load_tradestation_csv", return_value=dummy_price_df), \
             patch(
                "modules.cross_dataset_evaluator._rebuild_strategy_from_leaderboard_row",
                return_value=(_make_dummy_trades(20), "FilterA,FilterB", object()),
             ):
            evaluate_cross_dataset_portfolio(
                outputs_root=root,
                datasets=datasets,
                oos_split_date="2019-01-01",
            )

        corr_path = root / "cross_timeframe_correlation_matrix.csv"
        review_path = root / "cross_timeframe_portfolio_review.csv"
        yearly_path = root / "cross_timeframe_yearly_stats.csv"

        assert corr_path.exists(), "cross_timeframe_correlation_matrix.csv should exist"
        assert review_path.exists(), "cross_timeframe_portfolio_review.csv should exist"
        assert yearly_path.exists(), "cross_timeframe_yearly_stats.csv should exist"

        # Both output files must be non-empty CSVs
        corr_df = pd.read_csv(corr_path, index_col=0)
        assert corr_df.shape[0] == 2
        assert corr_df.shape[1] == 2

        review_df = pd.read_csv(review_path)
        assert len(review_df) == 2
        assert "mc_max_dd_99" in review_df.columns
