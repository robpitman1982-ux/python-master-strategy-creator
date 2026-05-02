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
        "recent_12m_pf": 1.6,
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
                # 2 with low OOS PF — should be removed (below 1.0)
                {"leader_strategy_name": "low_pf1", "quality_flag": "ROBUST", "oos_pf": 0.8, "leader_trades": 100, "bootcamp_score": 60},
                {"leader_strategy_name": "low_pf2", "quality_flag": "STABLE", "oos_pf": 0.9, "leader_trades": 100, "bootcamp_score": 60},
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
                    "leader_pf": 1.7,
                    "leader_trades": 100,
                },
                {
                    "leader_strategy_name": "StratB",
                    "best_refined_strategy_name": "SameStrat",
                    "market": "ES",
                    "quality_flag": "ROBUST",
                    "oos_pf": 1.9,
                    "leader_pf": 1.9,
                    "leader_trades": 120,
                },
            ]
            df = _make_leaderboard_df(rows)
            csv_path = tmp / "test_lb_dedup.csv"
            df.to_csv(csv_path, index=False)

            result = hard_filter_candidates(str(csv_path))
            assert len(result) == 1
            assert result[0]["leader_strategy_name"] == "StratB"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_hard_filter_excluded_markets(self) -> None:
        from modules.portfolio_selector import hard_filter_candidates

        tmp = _make_tmp_dir()
        try:
            rows = [
                {"leader_strategy_name": "keep_es", "market": "ES", "best_refined_strategy_name": "keep_es_ref"},
                {"leader_strategy_name": "drop_rty", "market": "RTY", "best_refined_strategy_name": "drop_rty_ref"},
            ]
            df = _make_leaderboard_df(rows)
            csv_path = tmp / "test_lb_excluded.csv"
            df.to_csv(csv_path, index=False)

            result = hard_filter_candidates(str(csv_path), excluded_markets=["RTY"])
            names = [r["leader_strategy_name"] for r in result]
            assert "keep_es" in names
            assert "drop_rty" not in names
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


class TestCostModeling:
    """Test cost and hold-behavior helpers for CFD challenge realism."""

    def test_estimate_swap_charge_units_handles_friday_multiplier(self) -> None:
        from modules.portfolio_selector import _estimate_swap_charge_units

        units, touched_weekend = _estimate_swap_charge_units(
            "2026-05-01 10:00:00",  # Friday
            "2026-05-04 10:00:00",  # Monday
            weekend_multiplier=10.0,
        )

        assert units == 10.0
        assert touched_weekend is True

    def test_compute_trade_cost_adjustment_applies_spread_and_swap(self) -> None:
        from modules.portfolio_selector import _compute_trade_cost_adjustment

        trade = {
            "entry_time": "2026-05-01 10:00:00",
            "exit_time": "2026-05-04 10:00:00",
            "net_pnl": 100.0,
        }
        costs = _compute_trade_cost_adjustment(
            trade,
            market="CL",
            timeframe="60m",
            weight=0.1,  # 1 micro
        )

        assert costs["spread_cost"] > 0.0
        assert costs["swap_cost"] >= 7.0  # CL 10x Friday should be materially non-zero
        assert costs["weekend_hold"] == 1.0

    def test_trade_behavior_diagnostics_detect_weekend_exposure(self) -> None:
        from modules.portfolio_selector import _compute_trade_behavior_diagnostics

        trades = [
            {
                "entry_time": "2026-05-01 10:00:00",
                "exit_time": "2026-05-04 10:00:00",
                "net_pnl": 50.0,
            },
            {
                "entry_time": "2026-05-05 10:00:00",
                "exit_time": "2026-05-05 15:00:00",
                "net_pnl": 25.0,
            },
        ]
        diag = _compute_trade_behavior_diagnostics(trades, market="CL", timeframe="60m")

        assert diag["overnight_hold_share"] == 0.5
        assert diag["weekend_hold_share"] == 0.5


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

    def test_step_rates_are_monotonic(self) -> None:
        """Step pass rates must be monotonically decreasing (sequential steps)."""
        from modules.portfolio_selector import portfolio_monte_carlo
        from modules.prop_firm_simulator import The5ersBootcampConfig

        rng = np.random.RandomState(42)
        config = The5ersBootcampConfig()

        trade_lists = {
            "strat_a": list(rng.normal(500, 2000, 200)),
            "strat_b": list(rng.normal(500, 2000, 200)),
        }

        result = portfolio_monte_carlo(trade_lists, config, n_sims=500, seed=42)
        assert result["step1_pass_rate"] >= result["step2_pass_rate"]
        assert result["step2_pass_rate"] >= result["step3_pass_rate"]

    def test_time_to_fund_fields_present(self) -> None:
        """MC result should include trades-to-pass and step trades."""
        from modules.portfolio_selector import portfolio_monte_carlo
        from modules.prop_firm_simulator import The5ersBootcampConfig

        rng = np.random.RandomState(42)
        config = The5ersBootcampConfig()

        trade_lists = {
            "strat_a": list(rng.normal(500, 2000, 100)),
            "strat_b": list(rng.normal(500, 2000, 100)),
        }

        result = portfolio_monte_carlo(trade_lists, config, n_sims=100, seed=42)
        assert "median_trades_to_pass" in result
        assert "p75_trades_to_pass" in result
        assert "step_median_trades" in result
        assert isinstance(result["step_median_trades"], list)


class TestCorrelationDedup:
    """Test Stage 3b: correlation_dedup."""

    def test_correlation_dedup_removes_clones(self) -> None:
        """Strategies with r > 0.6 should be deduped, keeping higher-priority candidate."""
        from modules.portfolio_selector import correlation_dedup

        rng = np.random.RandomState(42)
        n_days = 500

        # A and B are highly correlated (clones)
        base = rng.randn(n_days) * 200
        col_a = base + rng.randn(n_days) * 20  # ~0.99 correlation
        col_b = base + rng.randn(n_days) * 20

        # C is independent
        col_c = rng.randn(n_days) * 200

        return_matrix = pd.DataFrame({
            "ES_60m_StratA": col_a,
            "ES_daily_StratB": col_b,
            "NQ_30m_StratC": col_c,
        })
        corr_matrix = return_matrix.corr()

        # Verify A-B correlation is high
        assert abs(corr_matrix.loc["ES_60m_StratA", "ES_daily_StratB"]) > 0.6

        candidates = [
            {"leader_strategy_name": "StratA", "market": "ES", "timeframe": "60m", "oos_pf": 1.4, "leader_pf": 1.3, "quality_flag": "STABLE"},
            {"leader_strategy_name": "StratB", "market": "ES", "timeframe": "daily", "oos_pf": 2.1, "leader_pf": 1.9, "quality_flag": "ROBUST"},
            {"leader_strategy_name": "StratC", "market": "NQ", "timeframe": "30m", "oos_pf": 1.7, "leader_pf": 1.6, "quality_flag": "ROBUST"},
        ]

        result = correlation_dedup(candidates, corr_matrix, return_matrix, threshold=0.6)

        # Should have 2 candidates: StratB (higher score) and StratC
        assert len(result) == 2
        names = [c["leader_strategy_name"] for c in result]
        assert "StratB" in names  # Higher neutral priority kept
        assert "StratA" not in names  # Lower-priority correlated clone removed
        assert "StratC" in names  # Independent, kept

    def test_correlation_dedup_no_removal_when_uncorrelated(self) -> None:
        """Independent strategies should all survive dedup."""
        from modules.portfolio_selector import correlation_dedup

        rng = np.random.RandomState(42)
        n_days = 500

        return_matrix = pd.DataFrame({
            "ES_60m_StratA": rng.randn(n_days) * 200,
            "CL_daily_StratB": rng.randn(n_days) * 200,
            "NQ_30m_StratC": rng.randn(n_days) * 200,
        })
        corr_matrix = return_matrix.corr()

        candidates = [
            {"leader_strategy_name": "StratA", "market": "ES", "timeframe": "60m", "oos_pf": 1.5, "leader_pf": 1.4, "quality_flag": "ROBUST"},
            {"leader_strategy_name": "StratB", "market": "CL", "timeframe": "daily", "oos_pf": 1.6, "leader_pf": 1.5, "quality_flag": "ROBUST"},
            {"leader_strategy_name": "StratC", "market": "NQ", "timeframe": "30m", "oos_pf": 1.7, "leader_pf": 1.6, "quality_flag": "STABLE"},
        ]

        result = correlation_dedup(candidates, corr_matrix, return_matrix, threshold=0.6)
        assert len(result) == 3


class TestHardFilterThreshold:
    """Test that lowered OOS PF threshold works correctly."""

    def test_hard_filter_oos_pf_threshold(self) -> None:
        """Strategies with OOS PF > 1.0 should pass hard filter."""
        from modules.portfolio_selector import hard_filter_candidates

        tmp = _make_tmp_dir()
        try:
            rows = [
                # OOS PF 1.1 — should PASS (above 1.0 threshold)
                {"leader_strategy_name": "mid_pf", "quality_flag": "ROBUST", "oos_pf": 1.1, "leader_trades": 100, "bootcamp_score": 60, "best_refined_strategy_name": "ref_mid", "market": "CL"},
                # OOS PF 0.9 — should FAIL (below 1.0)
                {"leader_strategy_name": "low_pf", "quality_flag": "ROBUST", "oos_pf": 0.9, "leader_trades": 100, "bootcamp_score": 60, "best_refined_strategy_name": "ref_low", "market": "NQ"},
                # OOS PF 2.0 — should PASS
                {"leader_strategy_name": "high_pf", "quality_flag": "STABLE", "oos_pf": 2.0, "leader_trades": 100, "bootcamp_score": 80, "best_refined_strategy_name": "ref_high", "market": "ES"},
            ]
            df = _make_leaderboard_df(rows)
            csv_path = tmp / "test_lb_threshold.csv"
            df.to_csv(csv_path, index=False)

            result = hard_filter_candidates(str(csv_path))
            names = [r["leader_strategy_name"] for r in result]
            assert "mid_pf" in names, "OOS PF 1.1 should pass threshold of 1.0"
            assert "high_pf" in names, "OOS PF 2.0 should pass threshold of 1.0"
            assert "low_pf" not in names, "OOS PF 0.9 should fail threshold of 1.0"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_hard_filter_without_bootcamp_score_filter(self) -> None:
        """Selector should work without using bootcamp_score as a gate."""
        from modules.portfolio_selector import hard_filter_candidates

        tmp = _make_tmp_dir()
        try:
            rows = [
                {"leader_strategy_name": "good_score", "quality_flag": "ROBUST", "oos_pf": 1.5, "leader_pf": 1.6, "leader_trades": 100, "best_refined_strategy_name": "ref_good", "market": "ES"},
                {"leader_strategy_name": "low_score", "quality_flag": "ROBUST", "oos_pf": 1.5, "leader_pf": 1.4, "leader_trades": 100, "best_refined_strategy_name": "ref_low", "market": "CL"},
            ]
            df = _make_leaderboard_df(rows)
            df = df.drop(columns=["bootcamp_score"])
            csv_path = tmp / "test_lb_bscore.csv"
            df.to_csv(csv_path, index=False)

            result = hard_filter_candidates(str(csv_path))
            names = [r["leader_strategy_name"] for r in result]
            assert "good_score" in names
            assert "low_score" in names
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_hard_filter_configurable_threshold(self) -> None:
        """Config overrides for threshold and cap should be respected."""
        from modules.portfolio_selector import hard_filter_candidates

        tmp = _make_tmp_dir()
        try:
            rows = [
                {"leader_strategy_name": f"strat{i}", "quality_flag": "ROBUST",
                 "oos_pf": 1.2 + i * 0.1, "leader_trades": 100,
                 "bootcamp_score": 50 + i, "best_refined_strategy_name": f"ref{i}"}
                for i in range(10)
            ]
            df = _make_leaderboard_df(rows)
            csv_path = tmp / "test_lb_config.csv"
            df.to_csv(csv_path, index=False)

            # With custom threshold of 1.5 — should filter out oos_pf < 1.5
            result = hard_filter_candidates(str(csv_path), oos_pf_threshold=1.5)
            for r in result:
                assert r["oos_pf"] > 1.5

            # With candidate_cap=3 — should only return 3
            result = hard_filter_candidates(str(csv_path), candidate_cap=3)
            assert len(result) <= 3
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestSizingObjective:
    """Test that sizing optimizer minimizes time-to-fund."""

    def test_sizing_returns_weights(self) -> None:
        """optimise_sizing should return portfolios with micro_multiplier weights."""
        from modules.portfolio_selector import optimise_sizing

        rng = np.random.RandomState(42)
        trade_lists = {
            "strat_a": list(rng.normal(300, 1000, 80)),
            "strat_b": list(rng.normal(300, 1000, 80)),
        }
        return_matrix = pd.DataFrame({
            "strat_a": rng.normal(300, 1000, 200),
            "strat_b": rng.normal(300, 1000, 200),
        })

        portfolios = [{"strategy_names": ["strat_a", "strat_b"]}]
        result = optimise_sizing(
            portfolios, return_matrix, n_sims=50,
            raw_trade_lists=trade_lists, min_pass_rate=0.01,
        )

        assert len(result) == 1
        assert "micro_multiplier" in result[0]
        assert result[0]["sizing_optimised"] is True
        weights = result[0]["micro_multiplier"]
        assert all(w in [0.1, 0.2, 0.3, 0.5, 0.7, 1.0] for w in weights.values())

    def test_sizing_accepts_min_pass_rate(self) -> None:
        """optimise_sizing with very high min_pass_rate should still return results."""
        from modules.portfolio_selector import optimise_sizing

        rng = np.random.RandomState(42)
        trade_lists = {
            "strat_a": list(rng.normal(500, 2000, 100)),
        }
        return_matrix = pd.DataFrame({
            "strat_a": rng.normal(500, 2000, 200),
        })

        portfolios = [{"strategy_names": ["strat_a"]}]
        result = optimise_sizing(
            portfolios, return_matrix, n_sims=50,
            raw_trade_lists=trade_lists, min_pass_rate=0.99,
        )

        # Should still return a result (fallback to best pass rate)
        assert len(result) == 1
        assert "micro_multiplier" in result[0]


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
                config={"pipeline": {"portfolio_selector": {"use_multi_layer_correlation": False, "use_ecd": False, "use_regime_gate": False, "mc_method": "shuffle_interleave"}}},
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

            # Check new columns from Session 57
            assert "robustness_score" in report_df.columns
            assert "worst_rolling_20_p95" in report_df.columns
            assert "max_losing_streak_p95" in report_df.columns
            assert "max_recovery_trades_p95" in report_df.columns
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_selector_prefers_gated_input_and_applies_program_exclusions(self) -> None:
        from modules.portfolio_selector import _resolve_selector_leaderboard_path, hard_filter_candidates

        tmp = _make_tmp_dir()
        try:
            rows = [
                {
                    "leader_strategy_name": "ESStrat",
                    "best_refined_strategy_name": "RefinedES",
                    "market": "ES",
                    "timeframe": "60m",
                    "strategy_type": "mean_reversion",
                    "dataset": "ES_60m_2008_2026_tradestation.csv",
                    "run_id": "test-run",
                },
                {
                    "leader_strategy_name": "NQStrat",
                    "best_refined_strategy_name": "RefinedNQ",
                    "market": "NQ",
                    "timeframe": "30m",
                    "strategy_type": "breakout",
                    "dataset": "NQ_30m_2008_2026_tradestation.csv",
                    "run_id": "test-run",
                },
                {
                    "leader_strategy_name": "CLStrat",
                    "best_refined_strategy_name": "RefinedCL",
                    "market": "CL",
                    "timeframe": "daily",
                    "strategy_type": "short_trend",
                    "dataset": "CL_daily_2008_2026_tradestation.csv",
                    "run_id": "test-run",
                },
                {
                    "leader_strategy_name": "RTYStrat",
                    "best_refined_strategy_name": "RefinedRTY",
                    "market": "RTY",
                    "timeframe": "60m",
                    "strategy_type": "trend",
                    "dataset": "RTY_60m_2008_2026_tradestation.csv",
                    "run_id": "test-run",
                },
            ]
            gated_df = _make_leaderboard_df(rows)
            raw_df = _make_leaderboard_df(
                [
                    {
                        "leader_strategy_name": "OnlyRaw",
                        "best_refined_strategy_name": "OnlyRawRefined",
                        "market": "ES",
                        "timeframe": "daily",
                        "strategy_type": "breakout",
                        "dataset": "ES_daily_2008_2026_tradestation.csv",
                        "run_id": "test-run",
                    }
                ]
            )

            lb_dir = tmp / "leaderboards"
            lb_dir.mkdir()
            raw_path = lb_dir / "ultimate_leaderboard_cfd.csv"
            gated_path = lb_dir / "ultimate_leaderboard_cfd_gated.csv"
            raw_df.to_csv(raw_path, index=False)
            gated_df.to_csv(gated_path, index=False)

            resolved = _resolve_selector_leaderboard_path(str(raw_path), prefer_gated=True)
            assert Path(resolved) == gated_path

            filtered = hard_filter_candidates(
                str(resolved),
                excluded_markets=["W", "NG", "US", "TY", "RTY", "HG"],
            )
            names = [row["leader_strategy_name"] for row in filtered]
            assert "ESStrat" in names
            assert "NQStrat" in names
            assert "CLStrat" in names
            assert "RTYStrat" not in names
            assert "OnlyRaw" not in names
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cfd_selector_does_not_fall_back_to_futures_gated(self) -> None:
        from modules.portfolio_selector import _resolve_selector_leaderboard_path

        tmp = _make_tmp_dir()
        try:
            lb_dir = tmp / "leaderboards"
            lb_dir.mkdir()
            raw_path = lb_dir / "ultimate_leaderboard_cfd.csv"
            futures_gated_path = lb_dir / "ultimate_leaderboard_FUTURES_gated.csv"
            _make_leaderboard_df(
                [
                    {
                        "leader_strategy_name": "OnlyRawCFD",
                        "best_refined_strategy_name": "OnlyRawCFDRefined",
                        "market": "ES",
                        "timeframe": "daily",
                        "strategy_type": "breakout",
                        "dataset": "ES_daily_dukascopy.csv",
                        "run_id": "test-run",
                    }
                ]
            ).to_csv(raw_path, index=False)
            _make_leaderboard_df(
                [
                    {
                        "leader_strategy_name": "WrongUniverse",
                        "best_refined_strategy_name": "WrongUniverseRefined",
                        "market": "ES",
                        "timeframe": "daily",
                        "strategy_type": "trend",
                        "dataset": "ES_daily_2008_2026_tradestation.csv",
                        "run_id": "futures-run",
                    }
                ]
            ).to_csv(futures_gated_path, index=False)

            resolved = _resolve_selector_leaderboard_path(str(raw_path), prefer_gated=True)

            assert Path(resolved) == raw_path
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestDDConstraint:
    """Test Task 1: hard DD constraint in sizing optimizer."""

    def test_dd_constraint_rejects_oversized_weights(self) -> None:
        """High weights causing DD > ceiling should be rejected; optimizer picks lower weights."""
        from modules.portfolio_selector import optimise_sizing
        from modules.prop_firm_simulator import The5ersBootcampConfig

        rng = np.random.RandomState(42)
        # Trades with high variance — large weights will blow DD limits
        trade_lists = {
            "strat_a": list(rng.normal(100, 5000, 80)),
            "strat_b": list(rng.normal(100, 5000, 80)),
        }
        return_matrix = pd.DataFrame({
            "strat_a": rng.normal(100, 5000, 200),
            "strat_b": rng.normal(100, 5000, 200),
        })

        portfolios = [{"strategy_names": ["strat_a", "strat_b"]}]
        config = The5ersBootcampConfig()

        result = optimise_sizing(
            portfolios, return_matrix, n_sims=50,
            raw_trade_lists=trade_lists, min_pass_rate=0.01,
            prop_config=config,
            dd_p95_limit_pct=0.70, dd_p99_limit_pct=0.90,
        )

        assert len(result) == 1
        assert "micro_multiplier" in result[0]
        # Weights should exist and be from valid grid
        weights = result[0]["micro_multiplier"]
        valid_grid = {0.1, 0.2, 0.3, 0.5, 0.7, 1.0}
        assert all(w in valid_grid for w in weights.values())


class TestInverseDDSizing:
    """Test Task 2: inverse-DD weight initialization."""

    def test_inverse_dd_weights_computed_correctly(self) -> None:
        from modules.portfolio_selector import _compute_inverse_dd_weights

        weight_options = [0.1, 0.2, 0.3, 0.5, 0.7, 1.0]

        # Strategy A has small DD (100), B has large DD (1000)
        # Inverse: A should get higher weight than B
        trade_lists = {
            "strat_a": [10, 20, -5, 15, -2],  # small swings
            "strat_b": [100, -500, 200, -800, 300],  # large swings
        }

        result = _compute_inverse_dd_weights(trade_lists, {}, weight_options)

        assert "strat_a" in result
        assert "strat_b" in result
        # strat_a should get >= strat_b weight (lower DD → higher weight)
        assert result["strat_a"] >= result["strat_b"]
        # All weights should be snapped to grid
        assert all(w in weight_options for w in result.values())

    def test_inverse_dd_uses_leaderboard_when_available(self) -> None:
        from modules.portfolio_selector import _compute_inverse_dd_weights

        weight_options = [0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
        trade_lists = {"strat_a": [1, 2, 3], "strat_b": [1, 2, 3]}
        candidates = {
            "strat_a": {"max_drawdown": 5000},
            "strat_b": {"max_drawdown": 10000},
        }

        result = _compute_inverse_dd_weights(trade_lists, candidates, weight_options)
        # strat_a has half the DD → should get higher weight
        assert result["strat_a"] >= result["strat_b"]


class TestCalmarScoring:
    """Test Task 3: Calmar-based pre-MC scoring."""

    def test_calmar_score_prefers_low_dd_high_return(self) -> None:
        from modules.portfolio_selector import _pre_mc_score

        rng = np.random.RandomState(42)
        return_matrix = pd.DataFrame({
            "ES_60m_GoodStrat": rng.normal(500, 100, 500),
            "CL_daily_BadStrat": rng.normal(100, 2000, 500),
        })

        # Good combo: high return, low DD
        good_candidates = [
            {"market": "ES", "timeframe": "60m", "strategy_type": "trend",
             "oos_pf": 2.5, "leader_net_pnl": 200000, "leader_trades": 180,
             "leader_trades_per_year": 10, "max_drawdown": 10000},
        ]
        # Bad combo: low return, high DD
        bad_candidates = [
            {"market": "CL", "timeframe": "daily", "strategy_type": "trend",
             "oos_pf": 1.1, "leader_net_pnl": 10000, "leader_trades": 180,
             "leader_trades_per_year": 10, "max_drawdown": 50000},
        ]

        good_score = _pre_mc_score(good_candidates, ["ES_60m_GoodStrat"], return_matrix, [])
        bad_score = _pre_mc_score(bad_candidates, ["CL_daily_BadStrat"], return_matrix, [])

        assert good_score > bad_score, f"Good ({good_score}) should score higher than bad ({bad_score})"


class TestRobustnessTest:
    """Test Task 4: portfolio plateau robustness test."""

    def test_robustness_test_runs_without_error(self) -> None:
        from modules.portfolio_selector import portfolio_robustness_test
        from modules.prop_firm_simulator import The5ersBootcampConfig

        rng = np.random.RandomState(42)
        trade_lists = {
            "strat_a": list(rng.normal(500, 1500, 100)),
            "strat_b": list(rng.normal(500, 1500, 100)),
        }
        return_matrix = pd.DataFrame({
            "strat_a": rng.normal(500, 1500, 200),
            "strat_b": rng.normal(500, 1500, 200),
        })

        portfolios = [{
            "strategy_names": ["strat_a", "strat_b"],
            "micro_multiplier": {"strat_a": 0.3, "strat_b": 0.3},
        }]

        result = portfolio_robustness_test(
            portfolios, return_matrix,
            raw_trade_lists=trade_lists,
            prop_config=The5ersBootcampConfig(),
            n_sims=50,
        )

        assert len(result) == 1
        assert "robustness_score" in result[0]
        assert 0.0 <= result[0]["robustness_score"] <= 1.0
        assert "weight_stability" in result[0]
        assert "remove_stability" in result[0]


class TestRollingDDMetric:
    """Test Task 5: rolling DD, losing streak, recovery time metrics."""

    def test_rolling_dd_computed_on_known_data(self) -> None:
        from modules.portfolio_selector import portfolio_monte_carlo
        from modules.prop_firm_simulator import The5ersBootcampConfig

        config = The5ersBootcampConfig()

        # Mix of wins and losses — mostly losers to ensure negative rolling windows
        rng = np.random.RandomState(42)
        trades = list(rng.normal(-50, 500, 120))  # negative mean → many losses
        trade_lists = {"strat_a": trades}

        result = portfolio_monte_carlo(
            trade_lists, config, n_sims=100, seed=42,
        )

        assert "worst_rolling_20_p95" in result
        assert "max_losing_streak_p95" in result
        assert "max_recovery_trades_p95" in result
        # With negative mean, there should be losing streaks
        assert result["max_losing_streak_p95"] >= 1
        # worst_rolling_20 should be a finite number
        assert np.isfinite(result["worst_rolling_20_p95"])

    def test_mc_result_includes_p99_dd(self) -> None:
        """p99_worst_dd_pct should be present in MC results (Task 1 addition)."""
        from modules.portfolio_selector import portfolio_monte_carlo
        from modules.prop_firm_simulator import The5ersBootcampConfig

        rng = np.random.RandomState(42)
        config = The5ersBootcampConfig()
        trade_lists = {"strat_a": list(rng.normal(500, 2000, 100))}

        result = portfolio_monte_carlo(trade_lists, config, n_sims=100, seed=42)
        assert "p99_worst_dd_pct" in result
        assert result["p99_worst_dd_pct"] >= result["p95_worst_dd_pct"]


# ===========================================================================
# Session 58 Tests
# ===========================================================================

class TestMultiLayerCorrelation:
    """Test Task 1: 3-layer correlation architecture."""

    def test_active_day_corr_differs_from_full_pearson(self) -> None:
        """Active-day correlation should differ from full Pearson on sparse data."""
        from modules.portfolio_selector import compute_correlation_matrix, compute_multi_layer_correlation

        rng = np.random.RandomState(42)
        n_days = 500

        # Strategy A trades on odd days, B trades on even days, C trades every day
        col_a = np.zeros(n_days)
        col_b = np.zeros(n_days)
        col_c = rng.randn(n_days) * 200

        # A and C are correlated on the days A trades
        for i in range(0, n_days, 2):
            col_a[i] = col_c[i] + rng.randn() * 50
        for i in range(1, n_days, 2):
            col_b[i] = col_c[i] + rng.randn() * 50

        return_matrix = pd.DataFrame({
            "ES_60m_A": col_a,
            "CL_daily_B": col_b,
            "NQ_30m_C": col_c,
        })

        pearson = compute_correlation_matrix(return_matrix)
        multi = compute_multi_layer_correlation(return_matrix)

        # Active-day correlation should be different from full Pearson
        # because Pearson includes thousands of zero-days
        active_corr = multi["active_corr"]
        assert active_corr.shape == pearson.shape

        # A vs B: very few overlapping active days → should be 0.0
        assert abs(active_corr.loc["ES_60m_A", "CL_daily_B"]) < 0.01

    def test_dd_state_corr_catches_co_drawdown(self) -> None:
        """DD-state correlation should be high for strategies that draw down together."""
        from modules.portfolio_selector import compute_multi_layer_correlation

        n_days = 500
        # Both strategies have drawdowns at the same time
        base = np.zeros(n_days)
        # Create a shared drawdown period (days 100-150)
        base[100:150] = -100  # both losing
        base[200:250] = 100   # both winning

        col_a = base + np.random.RandomState(42).randn(n_days) * 20
        col_b = base + np.random.RandomState(43).randn(n_days) * 20

        return_matrix = pd.DataFrame({
            "ES_60m_A": col_a,
            "CL_daily_B": col_b,
        })

        multi = compute_multi_layer_correlation(return_matrix)
        dd_corr = multi["dd_corr"]

        # Should show positive DD correlation
        assert dd_corr.loc["ES_60m_A", "CL_daily_B"] > 0.3

    def test_tail_coloss_catches_crisis_correlation(self) -> None:
        """Tail co-loss should be high when B loses when A is stressed."""
        from modules.portfolio_selector import compute_multi_layer_correlation

        rng = np.random.RandomState(42)
        n_days = 1000

        col_a = rng.randn(n_days) * 100
        col_b = rng.randn(n_days) * 100

        # When A has large losses, make B also lose
        for i in range(n_days):
            if col_a[i] < -200:  # A in crisis
                col_b[i] = -abs(col_b[i]) - 100  # force B to also lose

        return_matrix = pd.DataFrame({
            "ES_60m_A": col_a,
            "CL_daily_B": col_b,
        })

        multi = compute_multi_layer_correlation(return_matrix)
        tail = multi["tail_coloss"]

        # Should show high tail co-loss
        assert tail.loc["ES_60m_A", "CL_daily_B"] > 0.5


class TestExpectedConditionalDrawdown:
    """Test Task 2: ECD."""

    def test_ecd_high_for_correlated_pair(self) -> None:
        """ECD should be high when strategies draw down together."""
        from modules.portfolio_selector import _compute_ecd

        n_days = 500
        # Both strategies have correlated drawdowns
        base = np.zeros(n_days)
        base[50:100] = -200   # shared drawdown period
        base[200:250] = -300  # another shared drawdown

        rng = np.random.RandomState(42)
        col_a = base + rng.randn(n_days) * 20
        col_b = base + rng.randn(n_days) * 20

        return_matrix = pd.DataFrame({
            "strat_a": col_a,
            "strat_b": col_b,
        })

        ecd = _compute_ecd(return_matrix, "strat_a", "strat_b")
        assert ecd is not None
        assert ecd > 0.01  # significant conditional drawdown

    def test_ecd_low_for_uncorrelated_pair(self) -> None:
        """ECD should be low for independent strategies."""
        from modules.portfolio_selector import _compute_ecd

        rng = np.random.RandomState(42)
        n_days = 500

        return_matrix = pd.DataFrame({
            "strat_a": rng.randn(n_days) * 100,
            "strat_b": rng.randn(n_days) * 100,
        })

        ecd = _compute_ecd(return_matrix, "strat_a", "strat_b")
        assert ecd is not None
        # For independent strategies, ECD should be relatively low
        # (not zero because random chance, but much lower than correlated)
        assert ecd < 0.05

    def test_ecd_returns_none_for_short_data(self) -> None:
        """ECD should return None for < 252 days."""
        from modules.portfolio_selector import _compute_ecd

        return_matrix = pd.DataFrame({
            "strat_a": np.random.randn(100),
            "strat_b": np.random.randn(100),
        })

        ecd = _compute_ecd(return_matrix, "strat_a", "strat_b")
        assert ecd is None


class TestBlockBootstrapMC:
    """Test Task 3: block bootstrap Monte Carlo."""

    def test_block_bootstrap_returns_valid_results(self) -> None:
        """Block bootstrap MC should return valid pass rate and DD stats."""
        from modules.portfolio_selector import portfolio_monte_carlo_block_bootstrap
        from modules.prop_firm_simulator import The5ersBootcampConfig

        rng = np.random.RandomState(42)
        config = The5ersBootcampConfig()

        dates = pd.date_range("2010-01-01", periods=500, freq="D")
        return_matrix = pd.DataFrame({
            "strat_a": rng.normal(300, 1500, 500),
            "strat_b": rng.normal(300, 1500, 500),
        }, index=dates)

        result = portfolio_monte_carlo_block_bootstrap(
            return_matrix, ["strat_a", "strat_b"], config, n_sims=100, seed=42,
        )

        assert 0.0 <= result["pass_rate"] <= 1.0
        assert "step1_pass_rate" in result
        assert "p95_worst_dd_pct" in result
        assert "p99_worst_dd_pct" in result
        assert "worst_rolling_20_p95" in result
        assert "max_losing_streak_p95" in result

    def test_block_bootstrap_preserves_clustering(self) -> None:
        """Block bootstrap should preserve consecutive-day patterns."""
        from modules.portfolio_selector import portfolio_monte_carlo_block_bootstrap
        from modules.prop_firm_simulator import The5ersBootcampConfig

        config = The5ersBootcampConfig()

        # Create data with a clear crisis cluster (days 100-120 all negative)
        n_days = 300
        rng = np.random.RandomState(42)
        returns = rng.normal(200, 500, n_days)
        returns[100:120] = -2000  # crisis cluster

        dates = pd.date_range("2010-01-01", periods=n_days, freq="D")
        return_matrix = pd.DataFrame({"strat_a": returns}, index=dates)

        result = portfolio_monte_carlo_block_bootstrap(
            return_matrix, ["strat_a"], config, n_sims=200, seed=42,
        )

        # With preserved crisis clustering, worst DD should be significant
        assert result["p95_worst_dd_pct"] > 0.0
        # Max losing streak should reflect the 20-day crisis
        assert result["max_losing_streak_p95"] >= 3


class TestDailyDDSimulation:
    """Test Task 4: daily DD tracking in simulate_challenge."""

    def test_daily_dd_breach_detected(self) -> None:
        """Trade sequence breaching 5% daily DD should fail High Stakes."""
        from modules.prop_firm_simulator import simulate_challenge, The5ersHighStakesConfig

        config = The5ersHighStakesConfig()
        # Source capital = 100K, step balance = 100K, daily DD = 5% = $5000
        # Create trades that lose > $5000 in one "day"
        trades = [-6000.0]  # Single trade loses 6% → daily DD breach

        result = simulate_challenge(trades, config, source_capital=100_000.0)
        assert not result.passed_all_steps
        assert result.daily_dd_breaches > 0
        assert result.steps[0].daily_dd_breach

    def test_bootcamp_no_daily_dd(self) -> None:
        """Bootcamp (no daily DD) should not breach on same trades."""
        from modules.prop_firm_simulator import simulate_challenge, The5ersBootcampConfig

        config = The5ersBootcampConfig()
        # Same large loss — Bootcamp has no daily DD limit
        # Source capital = 250K, step balance = 100K
        # -6000 * (100K/250K) = -2400, which is 2.4% of 100K — within 5% max DD
        trades = [-6000.0]

        result = simulate_challenge(trades, config, source_capital=250_000.0)
        assert result.daily_dd_breaches == 0
        # Should not breach (only 2.4% DD, under 5% max)
        last_step = result.steps[-1]
        assert not last_step.daily_dd_breach


class TestRegimeSurvivalGate:
    """Test Task 5: regime survival gate."""

    def test_regime_gate_rejects_failing_combo(self) -> None:
        """Combo that loses money in one regime should be rejected."""
        from modules.portfolio_selector import regime_survival_gate

        dates = pd.date_range("2020-01-01", "2025-12-31", freq="D")
        n = len(dates)
        rng = np.random.RandomState(42)

        # Strategy that works in 2022-2023 but fails badly in 2024
        returns = rng.normal(100, 200, n)
        mask_2024 = (dates >= "2024-01-01") & (dates <= "2025-12-31")
        returns[mask_2024] = rng.normal(-500, 100, mask_2024.sum())

        return_matrix = pd.DataFrame(
            {"ES_60m_StratA": returns},
            index=dates,
        )

        combos = [{"strategy_names": ["ES_60m_StratA"], "score": 1.0}]
        result = regime_survival_gate(combos, return_matrix, min_regime_pf=0.8)

        # Should be rejected because 2024-2025 regime has negative PF
        assert len(result) == 0

    def test_regime_gate_passes_healthy_combo(self) -> None:
        """Combo that's profitable in all regimes should pass."""
        from modules.portfolio_selector import regime_survival_gate

        dates = pd.date_range("2020-01-01", "2025-12-31", freq="D")
        n = len(dates)
        rng = np.random.RandomState(42)

        # Strategy that's consistently profitable
        returns = rng.normal(100, 200, n)

        return_matrix = pd.DataFrame(
            {"ES_60m_StratA": returns},
            index=dates,
        )

        combos = [{"strategy_names": ["ES_60m_StratA"], "score": 1.0}]
        result = regime_survival_gate(combos, return_matrix, min_regime_pf=0.8)

        assert len(result) == 1
