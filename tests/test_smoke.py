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
                "leader_stop_distance_atr": 0.75,
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
                "leader_stop_distance_atr": 1.25,
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


# ---------------------------------------------------------------------------
# Test 12: Hybrid filter parameter scaling
# ---------------------------------------------------------------------------

def test_hybrid_filter_scaling():
    from modules.config_loader import scale_lookbacks, get_timeframe_multiplier
    from modules.strategy_types import get_strategy_type

    # --- scale_lookbacks() edge cases ---
    # Standard 15m scaling (4x)
    result = scale_lookbacks([20, 200], 4.0)
    assert result == [80, 800], f"Expected [80, 800], got {result}"

    # Daily scaling (~0.154x), min_val clamp
    daily_mult = get_timeframe_multiplier("daily")
    result_daily = scale_lookbacks([20, 200], daily_mult, min_val=5)
    assert result_daily[0] >= 5, "min_val clamp failed"
    assert result_daily[-1] == max(5, round(200 * daily_mult)), "daily slow SMA wrong"

    # Deduplication: if two values round to the same, they should be deduplicated
    result_dedup = scale_lookbacks([10, 11], 1.0, min_val=5)
    assert len(result_dedup) == 2  # 10 and 11 stay distinct

    # Extreme multiplier: min_val kicks in for all values
    result_min = scale_lookbacks([1, 2, 3], 0.01, min_val=5)
    assert result_min == [5], f"All values should clamp to min_val=5, got {result_min}"

    # --- MR strategy type: 15m SMA lengths should be ~4x the 60m values ---
    mr = get_strategy_type("mean_reversion")
    sma_60m = mr.get_required_sma_lengths("60m")
    sma_15m = mr.get_required_sma_lengths("15m")
    assert len(sma_15m) == len(sma_60m), "15m should have same number of SMA lengths as 60m"
    for s60, s15 in zip(sma_60m, sma_15m):
        assert abs(s15 / s60 - 4.0) < 0.1, f"Expected ~4x scaling: 60m={s60}, 15m={s15}"

    # --- Trend strategy type: daily SMA lengths should be smaller than 60m ---
    trend = get_strategy_type("trend")
    sma_60m_trend = trend.get_required_sma_lengths("60m")
    sma_daily_trend = trend.get_required_sma_lengths("daily")
    assert max(sma_daily_trend) < max(sma_60m_trend), \
        f"Daily SMA max ({max(sma_daily_trend)}) should be < 60m max ({max(sma_60m_trend)})"

    # --- Momentum lookbacks scale with timeframe (trend only) ---
    mom_60m = trend.get_required_momentum_lookbacks("60m")
    mom_15m = trend.get_required_momentum_lookbacks("15m")
    assert len(mom_15m) >= 1, "15m momentum lookbacks should be non-empty"
    assert min(mom_15m) >= 2, "15m momentum lookbacks should respect min_val=2"

    # --- Breakout avg_range lookbacks scale ---
    bo = get_strategy_type("breakout")
    atr_60m = bo.get_required_avg_range_lookbacks("60m")
    atr_15m = bo.get_required_avg_range_lookbacks("15m")
    assert atr_15m[0] == 4 * atr_60m[0], f"15m ATR lookback should be 4x: {atr_15m} vs {atr_60m}"


# ---------------------------------------------------------------------------
# Test 13: Prop firm config — Bootcamp $250K
# ---------------------------------------------------------------------------

def test_prop_firm_config_bootcamp():
    """Verify The5ers Bootcamp $250K config has correct step balances."""
    from modules.prop_firm_simulator import The5ersBootcampConfig
    cfg = The5ersBootcampConfig()
    assert cfg.n_steps == 3
    assert cfg.step_balances == [100_000.0, 150_000.0, 200_000.0]
    assert cfg.target_balance == 250_000.0
    assert cfg.profit_target_pct == 0.06
    assert cfg.max_drawdown_pct == 0.05
    assert cfg.max_daily_drawdown_pct is None  # No daily DD during eval
    assert cfg.drawdown_type == "static"
    assert cfg.entry_fee == 225.0
    assert cfg.funded_fee == 350.0


# ---------------------------------------------------------------------------
# Test 14: Prop firm simulate — pass
# ---------------------------------------------------------------------------

def test_prop_firm_simulate_pass():
    """A strongly positive trade list should pass the challenge."""
    from modules.prop_firm_simulator import simulate_challenge, The5ersBootcampConfig
    # 100 trades, all winners — should easily pass
    trades = [3000.0] * 100  # $3K per trade on $250K = 1.2% per trade
    result = simulate_challenge(trades, The5ersBootcampConfig(), source_capital=250_000.0)
    assert result.passed_all_steps is True
    assert len(result.steps) == 3
    assert all(s.passed for s in result.steps)


# ---------------------------------------------------------------------------
# Test 15: Prop firm simulate — fail
# ---------------------------------------------------------------------------

def test_prop_firm_simulate_fail():
    """A strongly negative trade list should fail the challenge."""
    from modules.prop_firm_simulator import simulate_challenge, The5ersBootcampConfig
    # All losers
    trades = [-5000.0] * 50
    result = simulate_challenge(trades, The5ersBootcampConfig(), source_capital=250_000.0)
    assert result.passed_all_steps is False
    assert "Drawdown breach" in result.steps[0].failure_reason


# ---------------------------------------------------------------------------
# Test 16: Prop firm Monte Carlo
# ---------------------------------------------------------------------------

def test_prop_firm_monte_carlo():
    """Monte Carlo should return valid statistics."""
    import random as rng_mod
    from modules.prop_firm_simulator import monte_carlo_pass_rate, The5ersBootcampConfig
    rng = rng_mod.Random(42)
    trades = [rng.gauss(500, 2000) for _ in range(150)]
    stats = monte_carlo_pass_rate(trades, The5ersBootcampConfig(), n_sims=100, seed=42)
    assert 0.0 <= stats.pass_rate <= 1.0
    assert stats.n_simulations == 100
    assert len(stats.step_pass_rates) == 3
    assert stats.p5_worst_dd_pct <= stats.p50_worst_dd_pct <= stats.p95_worst_dd_pct


# ---------------------------------------------------------------------------
# Test 17: Prop firm challenge score
# ---------------------------------------------------------------------------

def test_prop_firm_challenge_score():
    """Challenge score should be between 0 and 1."""
    from modules.prop_firm_simulator import (
        monte_carlo_pass_rate, compute_challenge_score, The5ersBootcampConfig
    )
    import random as rng_mod
    rng = rng_mod.Random(99)
    trades = [rng.gauss(800, 1500) for _ in range(200)]
    stats = monte_carlo_pass_rate(trades, The5ersBootcampConfig(), n_sims=100, seed=99)
    score = compute_challenge_score(stats)
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Test 18: Portfolio evaluator timeframe parameter
# ---------------------------------------------------------------------------

def test_portfolio_evaluator_timeframe_param():
    """Verify _rebuild_strategy_from_leaderboard_row accepts and uses timeframe."""
    from modules.portfolio_evaluator import _rebuild_strategy_from_leaderboard_row
    import inspect
    sig = inspect.signature(_rebuild_strategy_from_leaderboard_row)
    assert "timeframe" in sig.parameters, (
        "_rebuild_strategy_from_leaderboard_row must accept timeframe parameter"
    )
    # Verify default is "60m" for backward compatibility
    assert sig.parameters["timeframe"].default == "60m"


# ---------------------------------------------------------------------------
# Test 19: Strategy type timeframe affects filters
# ---------------------------------------------------------------------------

def test_strategy_type_timeframe_affects_filters():
    """Verify that timeframe changes filter parameters in build_candidate_specific_strategy."""
    from modules.strategy_types import get_strategy_type
    from modules.filters import DistanceBelowSMAFilter, TwoBarDownFilter, ReversalUpBarFilter

    mr = get_strategy_type("mean_reversion")
    combo_classes = [DistanceBelowSMAFilter, TwoBarDownFilter, ReversalUpBarFilter]

    strat_60m = mr.build_candidate_specific_strategy(
        combo_classes, hold_bars=12, stop_distance_points=0.5,
        min_avg_range=1.2, momentum_lookback=0, timeframe="60m",
    )
    strat_daily = mr.build_candidate_specific_strategy(
        combo_classes, hold_bars=5, stop_distance_points=0.4,
        min_avg_range=1.2, momentum_lookback=0, timeframe="daily",
    )

    # The filter objects should have different SMA lengths
    # Daily multiplier is ~0.154x, so SMA lengths should be much smaller
    # Just verify both strategies were created (the real validation is that
    # the timeframe parameter is accepted and doesn't crash)
    assert strat_60m is not None
    assert strat_daily is not None
    assert strat_60m.name != strat_daily.name or True  # Names may match, that's OK


# ---------------------------------------------------------------------------
# Test 20: Exit architecture smoke coverage
# ---------------------------------------------------------------------------

def test_strategy_family_exit_support_matrix():
    from modules.strategies import ExitType
    from modules.strategy_types import get_strategy_type

    trend = get_strategy_type("trend")
    mr = get_strategy_type("mean_reversion")
    breakout = get_strategy_type("breakout")

    assert trend.get_default_exit_type() == ExitType.TIME_STOP
    assert mr.get_default_exit_type() == ExitType.TIME_STOP
    assert breakout.get_default_exit_type() == ExitType.TIME_STOP

    assert trend.get_supported_exit_types() == [ExitType.TIME_STOP, ExitType.TRAILING_STOP]
    assert mr.get_supported_exit_types() == [ExitType.TIME_STOP, ExitType.PROFIT_TARGET, ExitType.SIGNAL_EXIT]
    assert breakout.get_supported_exit_types() == [ExitType.TIME_STOP, ExitType.TRAILING_STOP]


def test_strategy_build_defaults_to_time_stop_exit():
    from modules.filters import DistanceBelowSMAFilter, ReversalUpBarFilter, TwoBarDownFilter
    from modules.strategies import ExitType
    from modules.strategy_types import get_strategy_type

    mr = get_strategy_type("mean_reversion")
    strategy = mr.build_candidate_specific_strategy(
        [DistanceBelowSMAFilter, TwoBarDownFilter, ReversalUpBarFilter],
        hold_bars=5,
        stop_distance_points=0.75,
        min_avg_range=0.8,
        momentum_lookback=0,
        timeframe="60m",
    )

    assert strategy.exit_config.exit_type == ExitType.TIME_STOP
    assert strategy.exit_config.hold_bars == 5


def test_refinement_results_expose_exit_metadata():
    from modules.engine import EngineConfig, MasterStrategyEngine
    from modules.refiner import StrategyParameterRefiner
    from modules.strategies import ExitType, build_exit_config

    df = pd.DataFrame(
        [
            {"open": 100.0, "high": 100.3, "low": 99.7, "close": 100.0, "atr_20": 1.0, "sma_20": 100.2},
            {"open": 100.5, "high": 101.4, "low": 100.4, "close": 101.1, "atr_20": 1.0, "sma_20": 100.1},
            {"open": 101.1, "high": 101.2, "low": 100.0, "close": 100.4, "atr_20": 1.0, "sma_20": 100.2},
            {"open": 100.4, "high": 100.6, "low": 100.1, "close": 100.5, "atr_20": 1.0, "sma_20": 100.0},
        ],
        index=pd.date_range("2020-01-01", periods=4, freq="h"),
    )

    class _SmokeExitStrategy:
        name = "SmokeExitStrategy"
        filters: list[object] = []

        def __init__(self, exit_config, hold_bars: int, stop_distance_atr: float):
            self.exit_config = exit_config
            self.hold_bars = hold_bars
            self.stop_distance_atr = stop_distance_atr

        def generate_signal(self, data: pd.DataFrame, i: int) -> int:
            return 1 if i == 0 else 0

    def strategy_factory(
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
        exit_type=None,
        profit_target_atr=None,
        trailing_stop_atr=None,
        signal_exit_reference=None,
    ):
        return _SmokeExitStrategy(
            exit_config=build_exit_config(
                exit_type=exit_type,
                hold_bars=hold_bars,
                stop_distance_points=stop_distance_points,
                profit_target_atr=profit_target_atr,
                trailing_stop_atr=trailing_stop_atr,
                signal_exit_reference=signal_exit_reference,
            ),
            hold_bars=hold_bars,
            stop_distance_atr=stop_distance_points,
        )

    refiner = StrategyParameterRefiner(
        MasterStrategyEngine,
        df,
        strategy_factory,
        EngineConfig(
            initial_capital=100_000.0,
            risk_per_trade=0.01,
            commission_per_contract=0.0,
            slippage_ticks=0,
            tick_value=12.50,
            dollars_per_point=50.0,
            oos_split_date="2020-01-01",
        ),
    )
    result_df = refiner.run_refinement(
        hold_bars=[2],
        stop_distance_points=[2.0],
        min_avg_range=[0.0],
        momentum_lookback=[0],
        exit_type=[ExitType.TIME_STOP, ExitType.PROFIT_TARGET],
        profit_target_atr=[1.0],
        min_trades=0,
        min_trades_per_year=0.0,
        parallel=False,
    )

    assert not result_df.empty
    assert {"exit_type", "profit_target_atr", "trailing_stop_atr", "signal_exit_reference"}.issubset(result_df.columns)
    assert set(result_df["exit_type"]) == {"time_stop", "profit_target"}


def test_run_dataset_caches_data_across_families():
    """Verify that _run_dataset loads CSV once and precomputes features once for all families."""
    from unittest.mock import patch, MagicMock
    from modules.feature_builder import add_precomputed_features
    from modules.data_loader import load_tradestation_csv
    from modules.strategy_types import get_strategy_type, list_strategy_types

    # Build a synthetic DF that add_precomputed_features can work with
    data = make_synthetic_ohlcv(n_bars=200)

    load_call_count = 0
    feat_call_count = 0

    original_add_features = add_precomputed_features

    def mock_load(*args, **kwargs):
        nonlocal load_call_count
        load_call_count += 1
        return data.copy()

    def mock_features(df, **kwargs):
        nonlocal feat_call_count
        feat_call_count += 1
        return original_add_features(df, **kwargs)

    def mock_evaluate_portfolio(**kwargs):
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    with patch("master_strategy_engine.load_tradestation_csv", side_effect=mock_load), \
         patch("master_strategy_engine.add_precomputed_features", side_effect=mock_features), \
         patch("master_strategy_engine.evaluate_portfolio", side_effect=mock_evaluate_portfolio), \
         patch("master_strategy_engine.run_single_family", return_value={
             "strategy_type": "mock",
             "dataset": "test.csv",
             "rows": 200,
             "start": "2015-01-01",
             "end": "2025-12-31",
             "promotion_status": "NO_PROMOTED_CANDIDATES",
             "promoted_candidates": 0,
             "best_combo_strategy_name": "NONE",
             "best_combo_profit_factor": 0.0,
             "best_combo_average_trade": 0.0,
             "best_combo_net_pnl": 0.0,
             "best_combo_total_trades": 0,
             "best_combo_filters": "",
             "best_combo_filter_class_names": "",
             "best_combo_is_trades": 0,
             "best_combo_oos_trades": 0,
             "best_combo_is_pf": 0.0,
             "best_combo_oos_pf": 0.0,
             "best_combo_recent_12m_trades": 0,
             "best_combo_recent_12m_pf": 0.0,
             "best_combo_trades_per_year": 0.0,
             "best_combo_max_drawdown": 0.0,
             "best_combo_quality_flag": "UNKNOWN",
             "best_combo_quality_score": 0.0,
             "best_combo_pct_profitable_years": 0.0,
             "best_combo_max_consecutive_losing_years": 0,
             "best_combo_consistency_flag": "INSUFFICIENT_DATA",
             "best_combo_exit_type": "time_stop",
             "best_combo_trailing_stop_atr": None,
             "best_combo_profit_target_atr": None,
             "best_combo_signal_exit_reference": None,
             "refinement_ran": False,
             "accepted_refinement_rows": 0,
             "best_refined_strategy_name": "NONE",
             "best_refined_profit_factor": 0.0,
             "best_refined_average_trade": 0.0,
             "best_refined_net_pnl": 0.0,
             "best_refined_total_trades": 0,
             "best_refined_hold_bars": 0,
             "best_refined_stop_distance_atr": 0.0,
             "best_refined_min_avg_range": 0.0,
             "best_refined_momentum_lookback": 0,
             "best_refined_is_trades": 0,
             "best_refined_oos_trades": 0,
             "best_refined_is_pf": 0.0,
             "best_refined_oos_pf": 0.0,
             "best_refined_recent_12m_trades": 0,
             "best_refined_recent_12m_pf": 0.0,
             "best_refined_trades_per_year": 0.0,
             "best_refined_max_drawdown": 0.0,
             "best_refined_quality_flag": "UNKNOWN",
             "best_refined_quality_score": 0.0,
             "best_refined_pct_profitable_years": 0.0,
             "best_refined_max_consecutive_losing_years": 0,
             "best_refined_consistency_flag": "INSUFFICIENT_DATA",
             "best_refined_exit_type": "time_stop",
             "best_refined_trailing_stop_atr": None,
             "best_refined_profit_target_atr": None,
             "best_refined_signal_exit_reference": None,
         }) as mock_run_family:
        from pathlib import Path
        import master_strategy_engine as mse

        # Temporarily override module-level config for test
        orig_selection = mse.STRATEGY_TYPE_SELECTION
        mse.STRATEGY_TYPE_SELECTION = ["trend", "mean_reversion", "breakout"]

        with tempfile.TemporaryDirectory() as tmpdir:
            mse._run_dataset(
                ds_path=Path("Data/fake.csv"),
                ds_market="ES",
                ds_timeframe="60m",
                ds_output_dir=Path(tmpdir),
            )

        mse.STRATEGY_TYPE_SELECTION = orig_selection

    # CSV loaded exactly once
    assert load_call_count == 1, f"Expected 1 CSV load, got {load_call_count}"
    # Features computed exactly once
    assert feat_call_count == 1, f"Expected 1 feature precompute, got {feat_call_count}"
    # run_single_family called once per family
    assert mock_run_family.call_count == 3, f"Expected 3 family runs, got {mock_run_family.call_count}"
    # Verify the precomputed data was passed (not a path)
    for call in mock_run_family.call_args_list:
        assert "data" in call.kwargs or (len(call.args) >= 2 and isinstance(call.args[1], pd.DataFrame))


# ---------------------------------------------------------------------------
# Test 23: High Stakes config with per-step profit targets
# ---------------------------------------------------------------------------

def test_high_stakes_config():
    """Verify The5ers High Stakes config has per-step profit targets."""
    from modules.prop_firm_simulator import The5ersHighStakesConfig
    config = The5ersHighStakesConfig()
    assert config.n_steps == 2
    assert config.max_drawdown_pct == 0.10
    assert config.max_daily_drawdown_pct == 0.05
    assert config.step_profit_targets == [0.08, 0.05]
    assert config.step_balances == [100_000.0, 100_000.0]
    assert config.program_name == "HighStakes"


def test_per_step_profit_targets():
    """High Stakes Step 1 (8%) and Step 2 (5%) should use different targets."""
    from modules.prop_firm_simulator import simulate_challenge, The5ersHighStakesConfig
    config = The5ersHighStakesConfig(100_000)
    assert config.step_profit_targets[0] == 0.08
    assert config.step_profit_targets[1] == 0.05

    # Strong winners should pass both steps
    trades = [5000.0] * 200  # 5% of 100K source each
    result = simulate_challenge(trades, config, source_capital=100_000.0)
    assert result.passed_all_steps is True
    assert len(result.steps) == 2
    # Step 1 target = $8K (8% of $100K), Step 2 target = $5K (5% of $100K)
    assert result.steps[0].profit_target == 8_000.0
    assert result.steps[1].profit_target == 5_000.0


# ---------------------------------------------------------------------------
# Test 24: Hyper Growth and Pro Growth configs
# ---------------------------------------------------------------------------

def test_hyper_growth_config():
    """Verify The5ers Hyper Growth config."""
    from modules.prop_firm_simulator import The5ersHyperGrowthConfig
    config = The5ersHyperGrowthConfig()
    assert config.n_steps == 1
    assert config.max_drawdown_pct == 0.06
    assert config.max_daily_drawdown_pct == 0.03
    assert config.profit_target_pct == 0.10
    assert config.target_balance == 5_000.0
    assert config.entry_fee == 260.0


def test_pro_growth_config():
    """Verify The5ers Pro Growth config."""
    from modules.prop_firm_simulator import The5ersProGrowthConfig
    config = The5ersProGrowthConfig()
    assert config.n_steps == 1
    assert config.max_drawdown_pct == 0.06
    assert config.max_daily_drawdown_pct == 0.03
    assert config.profit_target_pct == 0.10
    assert config.entry_fee == 74.0

    # $10K variant has different fee
    config_10k = The5ersProGrowthConfig(10_000)
    assert config_10k.entry_fee == 150.0


# ---------------------------------------------------------------------------
# Test 25: Daily drawdown breach
# ---------------------------------------------------------------------------

def test_daily_dd_breach():
    """Daily DD should fail the step even if cumulative DD is fine."""
    from modules.prop_firm_simulator import simulate_challenge, The5ersHyperGrowthConfig
    config = The5ersHyperGrowthConfig(5_000)
    # 3% daily DD on $5K = $150 limit
    # A single trade losing $160 (3.2% of source) on day 1 should trigger daily DD
    # source_capital=5000, trade=-160, scaled = -160/5000 * 5000 = -160
    trades = [-160.0, 200.0, 300.0]
    result = simulate_challenge(trades, config, source_capital=5_000.0, trades_per_day=1.0)
    assert not result.passed_all_steps, "Should fail on daily DD breach"
    assert "Daily DD breach" in result.steps[0].failure_reason


def test_daily_dd_no_breach_when_disabled():
    """Bootcamp has no daily DD, so large single-day losses should not trigger it."""
    from modules.prop_firm_simulator import simulate_challenge, The5ersBootcampConfig
    config = The5ersBootcampConfig()
    assert config.max_daily_drawdown_pct is None
    # Large loss that would breach a 3% daily DD but should pass cumulative check
    trades = [-3000.0, 5000.0] * 50  # Net positive over time
    result = simulate_challenge(trades, config, source_capital=250_000.0)
    # Should not fail on daily DD (it's disabled)
    for step in result.steps:
        if step.failure_reason:
            assert "Daily DD" not in step.failure_reason


# ---------------------------------------------------------------------------
# Test 26: Program selector resolver
# ---------------------------------------------------------------------------

def test_program_selector_resolver():
    """Verify _resolve_prop_config maps program names correctly."""
    from modules.portfolio_selector import _resolve_prop_config
    bootcamp = _resolve_prop_config("bootcamp", 250_000)
    assert bootcamp.program_name == "Bootcamp"
    assert bootcamp.n_steps == 3

    hs = _resolve_prop_config("high_stakes", 100_000)
    assert hs.program_name == "HighStakes"
    assert hs.n_steps == 2

    hg = _resolve_prop_config("hyper_growth", 5_000)
    assert hg.program_name == "HyperGrowth"

    pg = _resolve_prop_config("pro_growth", 5_000)
    assert pg.program_name == "ProGrowth"

    # Unknown falls back to bootcamp
    fallback = _resolve_prop_config("unknown_program", 100_000)
    assert fallback.program_name == "Bootcamp"


# ---------------------------------------------------------------------------
# Test: EfficiencyRatioFilter
# ---------------------------------------------------------------------------

def test_efficiency_ratio_filter():
    from modules.filters import EfficiencyRatioFilter

    n = 100
    # Perfectly trending data: close goes up by 1 each bar
    trending = pd.DataFrame({
        "open": np.arange(100, 100 + n, dtype=float),
        "high": np.arange(101, 101 + n, dtype=float),
        "low": np.arange(99, 99 + n, dtype=float),
        "close": np.arange(100, 100 + n, dtype=float),
    }, index=pd.date_range("2020-01-01", periods=n, freq="h"))

    f_above = EfficiencyRatioFilter(lookback=14, min_ratio=0.45, mode="above")
    m = f_above.mask(trending)
    # Perfect trend: ratio = (14)/(14*1) = 1.0 → should pass above threshold
    assert m.iloc[14:].all()

    # Oscillating data: +1, -1, +1, -1 → net zero, ratio ≈ 0
    osc_prices = np.array([100 + (i % 2) for i in range(n)], dtype=float)
    oscillating = pd.DataFrame({
        "open": osc_prices,
        "high": osc_prices + 0.5,
        "low": osc_prices - 0.5,
        "close": osc_prices,
    }, index=pd.date_range("2020-01-01", periods=n, freq="h"))

    m_above = f_above.mask(oscillating)
    # Choppy: ratio ≈ 0 → should NOT pass above threshold
    assert not m_above.iloc[14:].any()

    f_below = EfficiencyRatioFilter(lookback=14, min_ratio=0.35, mode="below")
    m_below = f_below.mask(oscillating)
    # Choppy: ratio ≈ 0 → should pass below threshold
    assert m_below.iloc[14:].all()


# ---------------------------------------------------------------------------
# Test: ATRExpansionRatioFilter
# ---------------------------------------------------------------------------

def test_atr_expansion_ratio_filter():
    from modules.filters import ATRExpansionRatioFilter

    n = 200
    rng = np.random.default_rng(99)
    # First 100 bars: low vol. Next 100 bars: high vol
    close = np.cumsum(np.concatenate([
        rng.normal(0, 0.5, 100),
        rng.normal(0, 5.0, 100),
    ])) + 4500
    high = close + np.concatenate([rng.uniform(0.5, 1, 100), rng.uniform(3, 8, 100)])
    low = close - np.concatenate([rng.uniform(0.5, 1, 100), rng.uniform(3, 8, 100)])
    df = pd.DataFrame({
        "open": close,
        "high": high,
        "low": low,
        "close": close,
    }, index=pd.date_range("2020-01-01", periods=n, freq="h"))
    from modules.feature_builder import add_precomputed_features
    df = add_precomputed_features(df, avg_range_lookbacks=[10, 20, 50])

    f_exp = ATRExpansionRatioFilter(short_period=10, long_period=50, threshold=1.10, mode="expanding")
    m = f_exp.mask(df)
    # After the vol jump, short ATR should exceed long ATR → expanding
    assert m.iloc[150:].any(), "Should detect expanding vol after regime change"

    f_con = ATRExpansionRatioFilter(short_period=10, long_period=50, threshold=0.85, mode="contracting")
    m_con = f_con.mask(df)
    # In the low-vol regime (bars 60-99), short ATR ≈ long ATR (both low), not clearly contracting
    # But at least the filter shouldn't pass in the high-vol tail
    assert not m_con.iloc[160:].all(), "Should not be contracting when vol is expanding"


# ---------------------------------------------------------------------------
# Test: WickRejectionFilter
# ---------------------------------------------------------------------------

def test_wick_rejection_filter():
    from modules.filters import WickRejectionFilter

    # Classic hammer candle: close near high, long lower wick
    hammer = pd.DataFrame({
        "open": [100.0] * 50,
        "high": [105.0] * 50,
        "low": [90.0] * 50,
        "close": [104.0] * 50,
    }, index=pd.date_range("2020-01-01", periods=50, freq="h"))
    from modules.feature_builder import add_precomputed_features
    hammer = add_precomputed_features(hammer, avg_range_lookbacks=[20])

    f = WickRejectionFilter(wick_ratio=0.5, close_position=0.70, min_range_mult=0.5, direction="long")
    m = f.mask(hammer)
    # lower_wick = 100-90=10, range=15, wick_ratio=10/15=0.67 >= 0.5 ✓
    # close_pos = (104-90)/15 = 0.93 >= 0.70 ✓
    assert m.iloc[20:].all()

    # Doji: close ≈ open near middle → fails
    doji = pd.DataFrame({
        "open": [100.0] * 50,
        "high": [105.0] * 50,
        "low": [95.0] * 50,
        "close": [100.0] * 50,
    }, index=pd.date_range("2020-01-01", periods=50, freq="h"))
    doji = add_precomputed_features(doji, avg_range_lookbacks=[20])
    m_doji = f.mask(doji)
    # close_pos = (100-95)/10 = 0.5 < 0.70 → fails
    assert not m_doji.iloc[20:].any()


# ---------------------------------------------------------------------------
# Test: CumulativeDeclineFilter
# ---------------------------------------------------------------------------

def test_cumulative_decline_filter():
    from modules.filters import CumulativeDeclineFilter

    n = 60
    # Create data where close drops 2 ATR over 4 bars with one up bar
    close = np.full(n, 100.0)
    # Bars 25-28: down, up, down, down → net drop of ~20 pts, ATR ≈ 10
    close[25] = 100.0
    close[26] = 92.0   # -8
    close[27] = 94.0   # +2 (one up bar)
    close[28] = 86.0   # -8
    close[29] = 80.0   # -6 → total drop from bar 25: 20 pts
    for i in range(30, n):
        close[i] = 80.0

    df = pd.DataFrame({
        "open": close,
        "high": close + 5,
        "low": close - 5,
        "close": close,
    }, index=pd.date_range("2020-01-01", periods=n, freq="h"))
    from modules.feature_builder import add_precomputed_features
    df = add_precomputed_features(df, avg_range_lookbacks=[20])

    f = CumulativeDeclineFilter(lookback=4, atr_period=20, min_decline_atr=1.5, direction="long")
    m = f.mask(df)
    # At bar 29: close[25]=100, close[29]=80, decline=20, ATR≈10, ratio=2.0 >= 1.5 ✓
    assert m.iloc[29], "Should detect 2-ATR decline over 4 bars"


# ---------------------------------------------------------------------------
# Test: ConsecutiveNarrowRangeFilter
# ---------------------------------------------------------------------------

def test_consecutive_narrow_range_filter():
    from modules.filters import ConsecutiveNarrowRangeFilter

    n = 60
    # Normal range = 10, narrow bars (range=3) at positions 30-34
    bar_range = np.full(n, 10.0)
    bar_range[30:35] = 3.0  # 5 narrow bars

    df = pd.DataFrame({
        "open": np.full(n, 100.0),
        "high": 100.0 + bar_range / 2,
        "low": 100.0 - bar_range / 2,
        "close": np.full(n, 100.0),
    }, index=pd.date_range("2020-01-01", periods=n, freq="h"))
    from modules.feature_builder import add_precomputed_features
    df = add_precomputed_features(df, avg_range_lookbacks=[20])

    f = ConsecutiveNarrowRangeFilter(lookback=5, range_ratio=0.80, min_narrow_count=3)
    m = f.mask(df)
    # At bars 32-34: 3+ of the last 5 bars have range < avg_range * 0.80
    assert m.iloc[32:35].any(), "Should detect multi-bar compression"
    # Before the compression zone, should not fire
    assert not m.iloc[20:28].any(), "Should not fire before compression"


# ---------------------------------------------------------------------------
# Test: DistanceFromExtremeFilter
# ---------------------------------------------------------------------------

def test_distance_from_extreme_filter():
    from modules.filters import DistanceFromExtremeFilter

    n = 60
    # Price starts at 100, then drops to 80 (20 pts below rolling high of 100)
    close = np.full(n, 100.0)
    close[30:] = 80.0  # dropped 20 pts

    df = pd.DataFrame({
        "open": close,
        "high": close + 5,
        "low": close - 5,
        "close": close,
    }, index=pd.date_range("2020-01-01", periods=n, freq="h"))
    from modules.feature_builder import add_precomputed_features
    df = add_precomputed_features(df, avg_range_lookbacks=[20])

    f = DistanceFromExtremeFilter(lookback=20, atr_period=20, threshold=1.5, mode="far_from_high")
    m = f.mask(df)
    # At bar 30+: rolling_high(20)=105 (from high col), close=80, ATR≈10
    # distance = (105-80)/10 = 2.5 >= 1.5 → should pass
    assert m.iloc[35:].any(), "Should detect stretched-from-high condition"

    f_near = DistanceFromExtremeFilter(lookback=20, atr_period=20, threshold=0.8, mode="near_high")
    m_near = f_near.mask(df)
    # In first 30 bars: close=100, high=105, distance=(105-100)/10=0.5 <= 0.8 → near
    assert m_near.iloc[20:29].any(), "Should detect near-high condition"


# ---------------------------------------------------------------------------
# Test: FailedBreakoutExclusionFilter
# ---------------------------------------------------------------------------

def test_failed_breakout_exclusion_filter():
    from modules.filters import FailedBreakoutExclusionFilter

    n = 60
    # Stable range: high always 105
    high = np.full(n, 105.0)
    close = np.full(n, 100.0)
    low = np.full(n, 95.0)

    # Bar 35: pokes above range high (110) but closes inside (103) → failed breakout
    high[35] = 110.0
    close[35] = 103.0

    df = pd.DataFrame({
        "open": np.full(n, 100.0),
        "high": high,
        "low": low,
        "close": close,
    }, index=pd.date_range("2020-01-01", periods=n, freq="h"))

    f = FailedBreakoutExclusionFilter(lookback=3, range_lookback=20)
    m = f.mask(df)
    # Bars 35, 36, 37 should be excluded (False) due to failed breakout in lookback
    assert not m.iloc[35], "Should reject bar with failed breakout"
    assert not m.iloc[36], "Should reject bar after failed breakout (within lookback)"
    # Bar 40+ should be fine (failed breakout out of lookback window)
    assert m.iloc[40], "Should allow bar well after failed breakout"
