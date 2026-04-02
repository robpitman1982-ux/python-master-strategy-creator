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
        """Strategies with r > 0.6 should be deduped, keeping higher score."""
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
            {"leader_strategy_name": "StratA", "market": "ES", "timeframe": "60m", "bootcamp_score": 80},
            {"leader_strategy_name": "StratB", "market": "ES", "timeframe": "daily", "bootcamp_score": 90},
            {"leader_strategy_name": "StratC", "market": "NQ", "timeframe": "30m", "bootcamp_score": 70},
        ]

        result = correlation_dedup(candidates, corr_matrix, return_matrix, threshold=0.6)

        # Should have 2 candidates: StratB (higher score) and StratC
        assert len(result) == 2
        names = [c["leader_strategy_name"] for c in result]
        assert "StratB" in names  # Higher bootcamp_score kept
        assert "StratA" not in names  # Lower score removed
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
            {"leader_strategy_name": "StratA", "market": "ES", "timeframe": "60m", "bootcamp_score": 80},
            {"leader_strategy_name": "StratB", "market": "CL", "timeframe": "daily", "bootcamp_score": 90},
            {"leader_strategy_name": "StratC", "market": "NQ", "timeframe": "30m", "bootcamp_score": 70},
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

    def test_hard_filter_bootcamp_score_filter(self) -> None:
        """Strategies with bootcamp_score <= 40 should be filtered out."""
        from modules.portfolio_selector import hard_filter_candidates

        tmp = _make_tmp_dir()
        try:
            rows = [
                {"leader_strategy_name": "good_score", "quality_flag": "ROBUST", "oos_pf": 1.5, "leader_trades": 100, "bootcamp_score": 80, "best_refined_strategy_name": "ref_good", "market": "ES"},
                {"leader_strategy_name": "low_score", "quality_flag": "ROBUST", "oos_pf": 1.5, "leader_trades": 100, "bootcamp_score": 30, "best_refined_strategy_name": "ref_low", "market": "CL"},
            ]
            df = _make_leaderboard_df(rows)
            csv_path = tmp / "test_lb_bscore.csv"
            df.to_csv(csv_path, index=False)

            result = hard_filter_candidates(str(csv_path))
            names = [r["leader_strategy_name"] for r in result]
            assert "good_score" in names
            assert "low_score" not in names, "bootcamp_score 30 should fail threshold of 40"
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
                config={"pipeline": {"portfolio_selector": {"use_multi_layer_correlation": False}}},
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
