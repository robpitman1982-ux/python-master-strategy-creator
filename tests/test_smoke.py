"""
Smoke tests for the strategy discovery engine.
These tests are fast and do NOT require the full ES 60m CSV.
They generate synthetic OHLCV data inline.
"""
from __future__ import annotations

import json
import os
import tempfile

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Synthetic data helper
# ---------------------------------------------------------------------------

def make_synthetic_ohlcv(n_bars: int = 500, start_price: float = 4500.0, seed: int = 42) -> pd.DataFrame:
    """
    Generate a synthetic OHLCV DataFrame with a DatetimeIndex.
    Prices follow a random walk around start_price with realistic
    high > open/close > low relationships.
    The index spans at least 2015-01-01 to 2025-12-31 so the IS/OOS
    split at 2019-01-01 divides the sample roughly in half.
    """
    rng = np.random.default_rng(seed)
    n = n_bars

    # Business-hour frequency gives ~n_bars per run but we want spanning years.
    # Use hourly frequency starting 2015-01-02 so 500 bars covers several years.
    # To guarantee the date range, we just create n_bars hourly bars but ensure
    # we have enough by using a fixed daily spacing approach:
    #   span 2015-01-02 to 2025-12-31 = ~11 years × ~252 trading days × ~7 bars/day = ~19,000 bars
    # For the smoke tests we use a shorter but still IS/OOS-split-spanning range.
    # We distribute n_bars evenly across 2015-2025 (3650 calendar days).

    dates = pd.date_range(start="2015-01-02", periods=n, freq="h")

    # Random walk for close prices
    returns = rng.normal(0, 0.002, size=n)
    close = start_price * np.cumprod(1 + returns)

    # Build OHLC with realistic relationships
    bar_ranges = rng.uniform(2, 20, size=n)
    high = close + bar_ranges * rng.uniform(0.3, 0.7, size=n)
    low = close - bar_ranges * rng.uniform(0.3, 0.7, size=n)
    open_ = low + (high - low) * rng.uniform(0.1, 0.9, size=n)

    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": rng.integers(1000, 50000, size=n).astype(float)},
        index=dates,
    )
    return df


# ---------------------------------------------------------------------------
# Test 1: Config loader
# ---------------------------------------------------------------------------

def test_config_loader():
    from modules.config_loader import get_nested, load_config

    # Should return a dict (even if file missing)
    cfg = load_config(path="nonexistent_path_xyz.yaml")
    assert isinstance(cfg, dict)

    # get_nested: missing key returns default
    result = get_nested(cfg, "does_not_exist", default="sentinel")
    assert result == "sentinel"

    # get_nested: deeply nested missing key
    result2 = get_nested({"a": {"b": 1}}, "a", "c", default=99)
    assert result2 == 99

    # get_nested: hit existing key
    result3 = get_nested({"engine": {"initial_capital": 100_000}}, "engine", "initial_capital", default=0)
    assert result3 == 100_000


# ---------------------------------------------------------------------------
# Test 2: Feature builder
# ---------------------------------------------------------------------------

def test_feature_builder():
    from modules.feature_builder import add_precomputed_features

    df = make_synthetic_ohlcv(n_bars=500)
    df_feat = add_precomputed_features(
        df,
        sma_lengths=[20, 50],
        avg_range_lookbacks=[14, 20],
        momentum_lookbacks=[10],
    )

    expected_cols = ["sma_20", "sma_50", "avg_range_20", "atr_14", "mom_diff_10", "bar_range", "true_range"]
    for col in expected_cols:
        assert col in df_feat.columns, f"Missing expected column: {col}"

    # Tail rows (after warmup of 50 bars) should have no NaN for computed columns
    tail = df_feat.iloc[60:]
    for col in expected_cols:
        n_nan = tail[col].isna().sum()
        assert n_nan == 0, f"Column {col} has {n_nan} NaN values in tail rows"


# ---------------------------------------------------------------------------
# Test 3: EngineConfig
# ---------------------------------------------------------------------------

def test_engine_config():
    from modules.engine import EngineConfig

    cfg = EngineConfig()
    assert cfg.initial_capital > 0
    assert 0 < cfg.risk_per_trade < 1
    assert cfg.dollars_per_point > 0
    assert isinstance(cfg.oos_split_date, str)

    # Custom instantiation
    cfg2 = EngineConfig(
        initial_capital=50_000.0,
        risk_per_trade=0.02,
        symbol="ES",
        commission_per_contract=3.00,
        slippage_ticks=2,
        tick_value=12.50,
        dollars_per_point=50.0,
        oos_split_date="2020-01-01",
    )
    assert cfg2.initial_capital == 50_000.0
    assert cfg2.symbol == "ES"
    assert cfg2.oos_split_date == "2020-01-01"


# ---------------------------------------------------------------------------
# Test 4: Engine run minimal
# ---------------------------------------------------------------------------

class _AlwaysBuyAfterWarmup:
    """Simple strategy: buy after 60-bar warmup, hold and stop via engine."""
    name = "AlwaysBuyWarmup"
    hold_bars = 3
    stop_distance_atr = 1.0

    def generate_signal(self, data: pd.DataFrame, i: int) -> int:
        if i > 60 and i % 20 == 0:  # sparse signals to avoid running out of capital
            return 1
        return 0


def test_engine_run_minimal():
    from modules.engine import EngineConfig, MasterStrategyEngine
    from modules.feature_builder import add_precomputed_features

    df = make_synthetic_ohlcv(n_bars=500)
    df = add_precomputed_features(df, avg_range_lookbacks=[20])  # needed for atr_20 stop

    cfg = EngineConfig(
        initial_capital=250_000.0,
        risk_per_trade=0.01,
        oos_split_date="2019-01-01",
    )

    strategy = _AlwaysBuyAfterWarmup()
    engine = MasterStrategyEngine(data=df, config=cfg)
    engine.run(strategy=strategy)

    results = engine.results()
    assert isinstance(results, dict)

    # Verify expected keys exist
    expected_keys = [
        "Strategy", "Total Trades", "Net PnL", "Profit Factor",
        "Quality Flag", "IS Trades", "OOS Trades", "Quality Score", "Consistency Flag",
    ]
    for key in expected_keys:
        assert key in results, f"Missing key in engine.results(): {key}"


# ---------------------------------------------------------------------------
# Test 5: Consistency module
# ---------------------------------------------------------------------------

def _make_mock_trades(year_pnls: dict[int, float]):
    """Create minimal mock trade objects for consistency testing."""
    from types import SimpleNamespace
    import datetime

    trades = []
    for year, pnl in year_pnls.items():
        t = SimpleNamespace(
            exit_time=pd.Timestamp(f"{year}-06-15"),
            pnl=pnl,
        )
        trades.append(t)
    return trades


def test_consistency_module():
    from modules.consistency import analyse_yearly_consistency

    # CONSISTENT case: 8/10 profitable years, max streak = 1
    consistent_pnls = {y: (100.0 if y % 5 != 0 else -50.0) for y in range(2011, 2021)}
    trades = _make_mock_trades(consistent_pnls)
    result = analyse_yearly_consistency(trades)

    assert "pct_profitable_years" in result
    assert "max_consecutive_losing_years" in result
    assert "consistency_flag" in result
    assert result["consistency_flag"] == "CONSISTENT", f"Expected CONSISTENT, got {result['consistency_flag']}"
    assert result["pct_profitable_years"] > 0.6

    # INCONSISTENT case: 3/10 profitable years
    inconsistent_pnls = {y: (100.0 if y % 3 == 0 else -50.0) for y in range(2011, 2021)}
    trades2 = _make_mock_trades(inconsistent_pnls)
    result2 = analyse_yearly_consistency(trades2)
    assert result2["consistency_flag"] in ("INCONSISTENT", "MIXED")

    # INSUFFICIENT_DATA: fewer than 5 years
    small_trades = _make_mock_trades({2020: 100.0, 2021: 200.0})
    result3 = analyse_yearly_consistency(small_trades)
    assert result3["consistency_flag"] == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Test 6: Filter combination generation
# ---------------------------------------------------------------------------

def test_filter_combination_generation():
    from modules.filter_combinator import generate_filter_combinations

    class FA: pass
    class FB: pass
    class FC: pass
    class FD: pass

    filter_classes = [FA, FB, FC, FD]
    combos = generate_filter_combinations(filter_classes, min_filters=2, max_filters=3)

    # C(4,2) + C(4,3) = 6 + 4 = 10
    assert len(combos) == 10, f"Expected 10 combos, got {len(combos)}"

    # All elements should be lists
    for combo in combos:
        assert isinstance(combo, list)
        assert 2 <= len(combo) <= 3


# ---------------------------------------------------------------------------
# Test 7: Strategy type factory
# ---------------------------------------------------------------------------

def test_strategy_type_factory():
    from modules.strategy_types import get_strategy_type, list_strategy_types

    trend = get_strategy_type("trend")
    mr = get_strategy_type("mean_reversion")
    bo = get_strategy_type("breakout")

    for st in (trend, mr, bo):
        assert st is not None
        assert hasattr(st, "get_filter_classes")
        assert hasattr(st, "get_active_refinement_grid_for_combo")

    types = list_strategy_types()
    assert isinstance(types, list)
    assert len(types) >= 3
    assert "trend" in types
    assert "mean_reversion" in types
    assert "breakout" in types


# ---------------------------------------------------------------------------
# Test 8: Quality score range
# ---------------------------------------------------------------------------

def test_quality_score_range():
    from modules.engine import EngineConfig, MasterStrategyEngine
    from modules.feature_builder import add_precomputed_features

    df = make_synthetic_ohlcv(n_bars=500)
    df = add_precomputed_features(df, avg_range_lookbacks=[20])

    cfg = EngineConfig(initial_capital=250_000.0, oos_split_date="2019-01-01")
    strategy = _AlwaysBuyAfterWarmup()
    engine = MasterStrategyEngine(data=df, config=cfg)
    engine.run(strategy=strategy)

    results = engine.results()
    qs_raw = str(results.get("Quality Score", "0"))
    qs = float(qs_raw.replace("$", "").replace(",", "").strip())
    assert 0.0 <= qs <= 1.0, f"Quality score {qs} out of [0, 1] range"


# ---------------------------------------------------------------------------
# Test 9: Progress tracker
# ---------------------------------------------------------------------------

def test_progress_tracker():
    from modules.progress import ProgressTracker

    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = ProgressTracker(output_dir=tmpdir, dataset_label="TEST_60m")
        tracker.set_families(["trend", "mean_reversion"])

        tracker.start_family("trend")
        tracker.update_sweep(5, 10)
        tracker.update_sweep(10, 10)
        tracker.log_promotion(count=3, cap=20)
        tracker.update_refinement(4, 8)
        tracker.update_refinement(8, 8)
        tracker.end_family("trend")

        tracker.start_family("mean_reversion")
        tracker.end_family("mean_reversion")

        tracker.log_done()

        # status.json should have been written
        status_path = os.path.join(tmpdir, "status.json")
        assert os.path.exists(status_path), "status.json was not written"

        with open(status_path) as f:
            status = json.load(f)

        assert "current_stage" in status
        assert "dataset" in status
        assert status["dataset"] == "TEST_60m"


# ---------------------------------------------------------------------------
# Test 10: Master leaderboard aggregator
# ---------------------------------------------------------------------------

def test_master_leaderboard():
    from modules.master_leaderboard import aggregate_master_leaderboard

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create mock directory structure: tmpdir/ES_60m/family_leaderboard_results.csv
        ds_dir = os.path.join(tmpdir, "ES_60m")
        os.makedirs(ds_dir)

        leaderboard_data = pd.DataFrame([
            {
                "strategy_type": "mean_reversion",
                "leader_strategy_name": "RefinedMR_HB5_ATR0.75_DIST0.8_MOM0",
                "accepted_final": True,
                "quality_flag": "ROBUST",
                "leader_pf": 1.42,
                "leader_avg_trade": 85.0,
                "leader_net_pnl": 45000.0,
                "leader_trades": 210,
                "is_pf": 1.09,
                "oos_pf": 1.86,
                "recent_12m_pf": 1.5,
                "leader_hold_bars": 5,
                "leader_stop_distance_points": 0.75,
                "best_combo_filters": "DistanceBelowSMA,TwoBarDown,ReversalUp",
            },
            {
                "strategy_type": "trend",
                "leader_strategy_name": "ComboTrend_xxx",
                "accepted_final": False,
                "quality_flag": "BROKEN_IN_OOS",
                "leader_pf": 0.82,
                "leader_avg_trade": -10.0,
                "leader_net_pnl": -5000.0,
                "leader_trades": 150,
                "is_pf": 1.30,
                "oos_pf": 0.70,
                "recent_12m_pf": 0.9,
                "leader_hold_bars": 6,
                "leader_stop_distance_points": 1.25,
                "best_combo_filters": "TrendDirection,Pullback,Recovery",
            },
        ])

        leaderboard_data.to_csv(os.path.join(ds_dir, "family_leaderboard_results.csv"), index=False)

        # Run aggregator
        result_df = aggregate_master_leaderboard(outputs_root=tmpdir, min_pf=1.0, min_oos_pf=1.0)

        assert not result_df.empty, "Expected non-empty result DataFrame"
        # Only the accepted_final=True row should survive
        assert len(result_df) == 1, f"Expected 1 row, got {len(result_df)}"

        # Check market/timeframe extracted correctly
        assert "market" in result_df.columns
        assert "timeframe" in result_df.columns
        assert result_df.iloc[0]["market"] == "ES"
        assert result_df.iloc[0]["timeframe"] == "60m"

        # Check rank column exists
        assert "rank" in result_df.columns


# ---------------------------------------------------------------------------
# Test 11: Timeframe multiplier
# ---------------------------------------------------------------------------

def test_timeframe_multiplier():
    from modules.config_loader import get_timeframe_multiplier

    assert get_timeframe_multiplier("5m") == 12.0
    assert get_timeframe_multiplier("60m") == 1.0
    assert abs(get_timeframe_multiplier("daily") - (60 / 390)) < 0.001
    assert get_timeframe_multiplier("15m") == 4.0
    assert get_timeframe_multiplier("30m") == 2.0
    assert get_timeframe_multiplier("1m") == 60.0
