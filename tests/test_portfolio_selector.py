"""Tests for portfolio_selector module."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_leaderboard_df(rows: list[dict]) -> pd.DataFrame:
    """Build a mock leaderboard DataFrame with all required columns."""
    defaults = {
        "rank": 1,
        "market": "ES",
        "timeframe": "60m",
        "strategy_type": "mean_reversion",
        "leader_strategy_name": "TestStrat",
        "quality_flag": "ROBUST",
        "leader_pf": 2.0,
        "leader_avg_trade": 500.0,
        "leader_net_pnl": 50000.0,
        "leader_trades": 100,
        "oos_pf": 1.8,
        "bootcamp_score": 80.0,
        "dataset": "ES_60m_2008_2026_tradestation.csv",
        "best_refined_strategy_name": "RefinedMR_test",
        "run_id": "test-run-001",
        "accepted_final": True,
    }
    full_rows = []
    for i, r in enumerate(rows):
        row = {**defaults, **r}
        row.setdefault("rank", i + 1)
        full_rows.append(row)
    return pd.DataFrame(full_rows)


def _make_tmp_dir() -> Path:
    """Create a temp dir that works around Windows tmp_path permission issues."""
    return Path(tempfile.mkdtemp(prefix="test_portfolio_selector_"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHardFilter:
    """Test Stage 1: hard_filter_candidates."""

    def test_hard_filter_removes_weak_candidates(self) -> None:
        from modules.portfolio_selector import hard_filter_candidates

        tmp = _make_tmp_dir()
        try:
            rows = [
                # 3 REGIME_DEPENDENT — should be removed
                {"leader_strategy_name": "bad1", "quality_flag": "REGIME_DEPENDENT", "oos_pf": 2.0, "leader_trades": 100, "bootcamp_score": 70},
                {"leader_strategy_name": "bad2", "quality_flag": "REGIME_DEPENDENT", "oos_pf": 2.0, "leader_trades": 100, "bootcamp_score": 70},
                {"leader_strategy_name": "bad3", "quality_flag": "REGIME_DEPENDENT", "oos_pf": 2.0, "leader_trades": 100, "bootcamp_score": 70},
                # 2 with low OOS PF — should be removed
                {"leader_strategy_name": "low_pf1", "quality_flag": "ROBUST", "oos_pf": 1.2, "leader_trades": 100, "bootcamp_score": 60},
                {"leader_strategy_name": "low_pf2", "quality_flag": "STABLE", "oos_pf": 1.3, "leader_trades": 100, "bootcamp_score": 60},
                # 1 with low trades — should be removed
                {"leader_strategy_name": "low_trades", "quality_flag": "ROBUST", "oos_pf": 1.8, "leader_trades": 30, "bootcamp_score": 60},
                # 4 valid candidates
                {"leader_strategy_name": "good1", "quality_flag": "ROBUST", "oos_pf": 1.8, "leader_trades": 100, "bootcamp_score": 85, "best_refined_strategy_name": "good1r"},
                {"leader_strategy_name": "good2", "quality_flag": "STABLE", "oos_pf": 1.5, "leader_trades": 80, "bootcamp_score": 75, "best_refined_strategy_name": "good2r"},
                {"leader_strategy_name": "good3", "quality_flag": "ROBUST", "oos_pf": 2.1, "leader_trades": 200, "bootcamp_score": 90, "best_refined_strategy_name": "good3r"},
                {"leader_strategy_name": "good4", "quality_flag": "STABLE", "oos_pf": 1.6, "leader_trades": 60, "bootcamp_score": 72, "best_refined_strategy_name": "good4r"},
            ]
            df = _make_leaderboard_df(rows)
            csv_path = tmp / "test_lb.csv"
            df.to_csv(csv_path, index=False)

            result = hard_filter_candidates(str(csv_path))
            assert len(result) == 4
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_deduplication_keeps_best(self) -> None:
        from modules.portfolio_selector import hard_filter_candidates

        tmp = _make_tmp_dir()
        try:
            rows = [
                {
                    "leader_strategy_name": "StratA",
                    "best_refined_strategy_name": "SameStrat",
                    "market": "ES",
                    "quality_flag": "ROBUST",
                    "oos_pf": 1.8,
                    "leader_trades": 100,
                    "bootcamp_score": 80,
                },
                {
                    "leader_strategy_name": "StratB",
                    "best_refined_strategy_name": "SameStrat",
                    "market": "ES",
                    "quality_flag": "ROBUST",
                    "oos_pf": 1.9,
                    "leader_trades": 120,
                    "bootcamp_score": 70,
                },
            ]
            df = _make_leaderboard_df(rows)
            csv_path = tmp / "test_lb_dedup.csv"
            df.to_csv(csv_path, index=False)

            result = hard_filter_candidates(str(csv_path))
            assert len(result) == 1
            assert result[0]["bootcamp_score"] == 80
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestCorrelation:
    """Test Stage 4: correlation-based rejection in sweep_combinations."""

    def test_correlation_rejects_high_pairs(self) -> None:
        from modules.portfolio_selector import sweep_combinations

        rng = np.random.RandomState(42)
        n_days = 500

        # A and B are highly correlated (~0.6+)
        base = rng.randn(n_days)
        noise = rng.randn(n_days) * 0.5
        col_a = base + noise * 0.3
        col_b = base + noise * 0.4

        # C and D are independent
        col_c = rng.randn(n_days) * 200
        col_d = rng.randn(n_days) * 200

        return_matrix = pd.DataFrame({
            "ES_60m_StratA": col_a,
            "CL_daily_StratB": col_b,
            "NQ_30m_StratC": col_c,
            "ES_daily_StratD": col_d,
        })
        corr_matrix = return_matrix.corr()

        # Verify A-B correlation is actually high
        assert abs(corr_matrix.loc["ES_60m_StratA", "CL_daily_StratB"]) > 0.4

        candidates = [
            {"leader_strategy_name": "StratA", "market": "ES", "timeframe": "60m", "strategy_type": "mean_reversion", "oos_pf": 1.8},
            {"leader_strategy_name": "StratB", "market": "CL", "timeframe": "daily", "strategy_type": "trend", "oos_pf": 1.7},
            {"leader_strategy_name": "StratC", "market": "NQ", "timeframe": "30m", "strategy_type": "breakout", "oos_pf": 1.6},
            {"leader_strategy_name": "StratD", "market": "ES", "timeframe": "daily", "strategy_type": "short_trend", "oos_pf": 1.5},
        ]

        results = sweep_combinations(candidates, corr_matrix, return_matrix, n_min=3, n_max=3)

        # No combination should contain both StratA and StratB
        for r in results:
            names = r["strategy_names"]
            assert not ("ES_60m_StratA" in names and "CL_daily_StratB" in names), \
                f"High-correlation pair should be rejected: {names}"


class TestPortfolioMC:
    """Test Stage 5: portfolio_monte_carlo."""

    def test_portfolio_mc_returns_valid_rate(self) -> None:
        from modules.portfolio_selector import portfolio_monte_carlo
        from modules.prop_firm_simulator import The5ersBootcampConfig

        rng = np.random.RandomState(42)
        config = The5ersBootcampConfig()

        trade_lists = {
            "strat_a": list(rng.normal(500, 2000, 100)),
            "strat_b": list(rng.normal(500, 2000, 100)),
            "strat_c": list(rng.normal(500, 2000, 100)),
        }

        result = portfolio_monte_carlo(trade_lists, config, n_sims=100, seed=42)

        assert 0.0 <= result["pass_rate"] <= 1.0
        assert 0.0 <= result["step1_pass_rate"] <= 1.0
        assert 0.0 <= result["step2_pass_rate"] <= 1.0
        assert 0.0 <= result["step3_pass_rate"] <= 1.0
        assert "p95_worst_dd_pct" in result
        assert "avg_trades_to_pass" in result


class TestEndToEnd:
    """Test full pipeline with mock data."""

    def test_report_written(self) -> None:
        from modules.portfolio_selector import run_portfolio_selection

        tmp = _make_tmp_dir()
        try:
            # Each candidate must have a UNIQUE market_timeframe so they get
            # separate strategy_returns.csv files with the right columns.
            configs = [
                ("ES", "60m", "mean_reversion"),
                ("CL", "daily", "trend"),
                ("NQ", "30m", "breakout"),
                ("ES", "daily", "short_trend"),
                ("CL", "60m", "short_breakout"),
                ("NQ", "daily", "mean_reversion_vol_dip"),
            ]

            rows = []
            for i, (market, tf, stype) in enumerate(configs):
                rows.append({
                    "leader_strategy_name": f"Strat{i}",
                    "best_refined_strategy_name": f"RefinedStrat{i}",
                    "market": market,
                    "timeframe": tf,
                    "strategy_type": stype,
                    "quality_flag": "ROBUST",
                    "oos_pf": 1.8 + i * 0.1,
                    "leader_trades": 100 + i * 10,
                    "bootcamp_score": 80 + i,
                    "dataset": f"{market}_{tf}_2008_2026_tradestation.csv",
                    "run_id": "test-run",
                })

            lb_df = _make_leaderboard_df(rows)
            lb_path = tmp / "ultimate_leaderboard_bootcamp.csv"
            lb_df.to_csv(lb_path, index=False)

            # Create mock strategy_returns.csv files — one per unique market_tf
            runs_base = tmp / "runs"
            rng = np.random.RandomState(123)
            dates = pd.date_range("2010-01-01", periods=500, freq="D")

            for i, (market, tf, _) in enumerate(configs):
                folder = runs_base / "test-run" / "Outputs" / f"{market}_{tf}"
                folder.mkdir(parents=True, exist_ok=True)

                returns = np.zeros(len(dates))
                trade_mask = rng.random(len(dates)) < 0.3
                returns[trade_mask] = rng.normal(500, 2000, trade_mask.sum())

                returns_df = pd.DataFrame({
                    "exit_time": dates,
                    f"Strat{i}": returns,
                })
                returns_df.to_csv(folder / "strategy_returns.csv", index=False)

            output_dir = tmp / "output"
            output_dir.mkdir()

            result = run_portfolio_selection(
                leaderboard_path=str(lb_path),
                runs_base_path=str(runs_base),
                output_dir=str(output_dir),
                n_sims_mc=100,       # Small for speed
                n_sims_sizing=50,    # Small for speed
            )

            # Check report was written
            report_path = output_dir / "portfolio_selector_report.csv"
            assert report_path.exists(), "portfolio_selector_report.csv not created"

            report_df = pd.read_csv(report_path)
            assert "rank" in report_df.columns
            assert "strategy_names" in report_df.columns
            assert "step3_pass_rate" in report_df.columns
            assert len(report_df) > 0

            # Check correlation matrix was written
            matrix_path = output_dir / "portfolio_selector_matrix.csv"
            assert matrix_path.exists(), "portfolio_selector_matrix.csv not created"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
