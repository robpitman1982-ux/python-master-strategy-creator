"""
Tests for vectorized filter mask() methods.

For every filter class:
1. Create synthetic data (500+ bars) with all required features
2. Compute mask via filter.mask(data)
3. Compute expected via [filter.passes(data, i) for i in range(len(data))]
4. Assert mask equals expected for every bar

Also tests:
- compute_combined_signal_mask() correctness
- engine precomputed_signals path produces identical results to bar-by-bar
- Benchmark: vectorized mask vs bar-by-bar loop
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest

# Re-use make_synthetic_ohlcv from test_smoke
from tests.test_smoke import make_synthetic_ohlcv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def add_all_features(data: pd.DataFrame) -> pd.DataFrame:
    """Add all precomputed features needed by the filter tests."""
    from modules.feature_builder import add_precomputed_features
    return add_precomputed_features(
        data,
        sma_lengths=[5, 10, 20, 50, 200],
        avg_range_lookbacks=[5, 10, 20],
        momentum_lookbacks=[5, 8, 10, 14],
    )


# ---------------------------------------------------------------------------
# Parameterized filter list
# Each entry: (FilterClass, kwargs)
# ---------------------------------------------------------------------------

from modules.filters import (
    AboveLongTermSMAFilter,
    BelowFastSMAFilter,
    BreakoutCloseStrengthFilter,
    BreakoutDistanceFilter,
    BreakoutRetestFilter,
    BreakoutTrendFilter,
    CloseAboveFastSMAFilter,
    CloseNearLowFilter,
    CompressionFilter,
    DistanceBelowSMAFilter,
    DownCloseFilter,
    ExpansionBarFilter,
    HigherLowFilter,
    LowVolatilityRegimeFilter,
    MomentumFilter,
    PriorRangePositionFilter,
    PullbackFilter,
    RangeBreakoutFilter,
    RecoveryTriggerFilter,
    ReversalUpBarFilter,
    RisingBaseFilter,
    StretchFromLongTermSMAFilter,
    ThreeBarDownFilter,
    TightRangeFilter,
    TrendDirectionFilter,
    TrendSlopeFilter,
    TwoBarDownFilter,
    TwoBarUpFilter,
    UpCloseFilter,
    VolatilityFilter,
)

ALL_FILTERS = [
    # Trend family
    (TrendDirectionFilter, {"fast_length": 50, "slow_length": 200}),
    (PullbackFilter, {"fast_length": 50}),
    (RecoveryTriggerFilter, {"fast_length": 50}),
    (VolatilityFilter, {"lookback": 20, "min_atr_mult": 1.0}),
    (MomentumFilter, {"lookback": 10}),
    (UpCloseFilter, {}),
    (TwoBarUpFilter, {}),
    (TrendSlopeFilter, {"fast_length": 50, "slope_bars": 5}),
    (CloseAboveFastSMAFilter, {"fast_length": 50}),
    (HigherLowFilter, {}),
    # Breakout family
    (CompressionFilter, {"lookback": 20, "max_atr_mult": 0.75}),
    (RangeBreakoutFilter, {"lookback": 20}),
    (ExpansionBarFilter, {"lookback": 20, "expansion_multiplier": 1.5}),
    (BreakoutRetestFilter, {"lookback": 20, "atr_buffer_mult": 0.0}),
    (BreakoutTrendFilter, {"fast_length": 50, "slow_length": 200}),
    (BreakoutCloseStrengthFilter, {"close_position_threshold": 0.60}),
    (PriorRangePositionFilter, {"lookback": 20, "min_position_in_range": 0.50}),
    (BreakoutDistanceFilter, {"lookback": 20, "min_breakout_atr": 0.10}),
    (RisingBaseFilter, {"lookback": 5}),
    (TightRangeFilter, {"lookback": 20, "max_bar_range_mult": 0.85}),
    # Mean reversion family
    (BelowFastSMAFilter, {"fast_length": 20}),
    (DistanceBelowSMAFilter, {"fast_length": 20, "min_distance_atr": 0.3}),
    (DownCloseFilter, {}),
    (TwoBarDownFilter, {}),
    (ReversalUpBarFilter, {}),
    (LowVolatilityRegimeFilter, {"lookback": 20, "max_atr_mult": 1.0}),
    (AboveLongTermSMAFilter, {"slow_length": 200}),
    (ThreeBarDownFilter, {}),
    (CloseNearLowFilter, {"max_close_position": 0.35}),
    (StretchFromLongTermSMAFilter, {"slow_length": 200, "min_distance_atr": 0.5}),
]

ALL_FILTER_IDS = [cls.__name__ for cls, _ in ALL_FILTERS]


@pytest.fixture(scope="module")
def test_data():
    """Synthetic 600-bar DataFrame with all features precomputed."""
    raw = make_synthetic_ohlcv(n_bars=600, seed=42)
    return add_all_features(raw)


# ---------------------------------------------------------------------------
# STEP 1 test: mask() == passes() for every bar, every filter
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filter_cls,kwargs", ALL_FILTERS, ids=ALL_FILTER_IDS)
def test_mask_matches_bar_by_bar(test_data, filter_cls, kwargs):
    """Vectorized mask() must produce identical results to passes() for every bar."""
    f = filter_cls(**kwargs)
    data = test_data

    # Bar-by-bar reference
    expected = [f.passes(data, i) for i in range(len(data))]

    # Vectorized mask
    mask = f.mask(data)

    assert isinstance(mask, pd.Series), f"{filter_cls.__name__}: mask() must return pd.Series"
    assert len(mask) == len(data), f"{filter_cls.__name__}: mask length mismatch"
    assert mask.dtype == bool, f"{filter_cls.__name__}: mask dtype must be bool"

    mismatches = [(i, expected[i], mask.iloc[i]) for i in range(len(data)) if expected[i] != mask.iloc[i]]

    assert not mismatches, (
        f"{filter_cls.__name__}: mask() differs from passes() at {len(mismatches)} bars. "
        f"First 5 mismatches (bar, expected, got): {mismatches[:5]}"
    )


# ---------------------------------------------------------------------------
# STEP 2 test: compute_combined_signal_mask correctness
# ---------------------------------------------------------------------------

def test_combined_signal_mask_matches_generate_signal(test_data):
    """compute_combined_signal_mask() AND must match the bar-by-bar generate_signal() output."""
    from modules.filters import TrendDirectionFilter, PullbackFilter, RecoveryTriggerFilter
    from modules.vectorized_signals import compute_combined_signal_mask

    filters = [
        TrendDirectionFilter(fast_length=50, slow_length=200),
        PullbackFilter(fast_length=50),
        RecoveryTriggerFilter(fast_length=50),
    ]

    data = test_data

    # Bar-by-bar via generate_signal logic
    expected = []
    for i in range(len(data)):
        sig = 1
        for f in filters:
            if not f.passes(data, i):
                sig = 0
                break
        expected.append(sig)

    # Vectorized
    combined = compute_combined_signal_mask(filters, data)

    assert isinstance(combined, np.ndarray), "compute_combined_signal_mask must return numpy array"
    assert len(combined) == len(data)

    mismatches = [(i, expected[i], int(combined[i])) for i in range(len(data)) if expected[i] != int(combined[i])]
    assert not mismatches, (
        f"Combined mask differs from bar-by-bar at {len(mismatches)} bars. "
        f"First 5: {mismatches[:5]}"
    )


def test_combined_signal_mask_empty_filters(test_data):
    """Empty filter list should return all-False array."""
    from modules.vectorized_signals import compute_combined_signal_mask
    result = compute_combined_signal_mask([], test_data)
    assert isinstance(result, np.ndarray)
    assert not result.any(), "Empty filter list should produce all-False mask"


# ---------------------------------------------------------------------------
# STEP 3 test: engine precomputed_signals == bar-by-bar generate_signal
# ---------------------------------------------------------------------------

def test_engine_precomputed_signals_matches_normal_run(test_data):
    """Engine with precomputed_signals must produce identical trades to bar-by-bar path."""
    from modules.engine import EngineConfig, MasterStrategyEngine
    from modules.filters import TrendDirectionFilter, PullbackFilter, RecoveryTriggerFilter
    from modules.vectorized_signals import compute_combined_signal_mask

    # Build a simple inline strategy
    class _SimpleStrategy:
        name = "TestStrategy"
        hold_bars = 6
        stop_distance_atr = 1.25
        filters = [
            TrendDirectionFilter(fast_length=50, slow_length=200),
            PullbackFilter(fast_length=50),
            RecoveryTriggerFilter(fast_length=50),
        ]
        exit_config = None
        direction = "LONG_ONLY"

        def generate_signal(self, data, i):
            for f in self.filters:
                if not f.passes(data, i):
                    return 0
            return 1

    data = test_data
    strategy = _SimpleStrategy()

    cfg = EngineConfig(
        initial_capital=250_000.0,
        risk_per_trade=0.01,
        commission_per_contract=2.0,
        slippage_ticks=2,
        tick_value=12.50,
        dollars_per_point=50.0,
        oos_split_date="2019-01-01",
    )

    # Run bar-by-bar (old path)
    engine_old = MasterStrategyEngine(data=data, config=cfg)
    engine_old.run(strategy=strategy)
    results_old = engine_old.results()

    # Run with precomputed signals (new path)
    signal_mask = compute_combined_signal_mask(strategy.filters, data)
    engine_new = MasterStrategyEngine(data=data, config=cfg)
    engine_new.run(strategy=strategy, precomputed_signals=signal_mask)
    results_new = engine_new.results()

    # Both runs must produce the same trade count and PnL
    assert results_old["Total Trades"] == results_new["Total Trades"], (
        f"Trade count mismatch: old={results_old['Total Trades']}, new={results_new['Total Trades']}"
    )
    assert results_old["Net PnL"] == results_new["Net PnL"], (
        f"Net PnL mismatch: old={results_old['Net PnL']}, new={results_new['Net PnL']}"
    )


# ---------------------------------------------------------------------------
# STEP 5 benchmark test: vectorized vs loop speed
# ---------------------------------------------------------------------------

def test_vectorized_vs_loop_speed():
    """Benchmark: vectorized mask() must be at least 5x faster than bar-by-bar loop."""
    raw = make_synthetic_ohlcv(n_bars=50_000, seed=7)
    data = add_all_features(raw)

    filter_obj = TrendDirectionFilter(fast_length=50, slow_length=200)

    # Bar-by-bar
    start = time.perf_counter()
    loop_result = [filter_obj.passes(data, i) for i in range(len(data))]
    loop_time = time.perf_counter() - start

    # Vectorized
    start = time.perf_counter()
    mask_result = filter_obj.mask(data)
    mask_time = time.perf_counter() - start

    speedup = loop_time / mask_time if mask_time > 0 else float("inf")
    print(f"\nLoop: {loop_time:.3f}s  Mask: {mask_time:.3f}s  Speedup: {speedup:.1f}x")

    assert speedup > 5, f"Expected at least 5x speedup, got {speedup:.1f}x"

    # Correctness check
    assert list(mask_result) == loop_result, "Benchmark data: mask() differs from passes()"
