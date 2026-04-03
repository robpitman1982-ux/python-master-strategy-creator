"""
Parity tests: vectorized engine MUST produce IDENTICAL trades to original engine.

Zero tolerance — not "similar", not "close enough". IDENTICAL.
Same trades, same entry prices, same exit prices, same PnL, same trade count.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.engine import MasterStrategyEngine, EngineConfig
from modules.strategies import BaseStrategy, ExitConfig, ExitType
from modules.feature_builder import add_precomputed_features
from modules.vectorized_trades import vectorized_backtest


# ── Synthetic Data ─────────────────────────────────────────────

def make_test_data(n_bars: int = 2000, seed: int = 42, start_price: float = 4500.0) -> pd.DataFrame:
    """Generate synthetic OHLCV with precomputed features (ATR, SMA)."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2010-01-02", periods=n_bars, freq="h")

    returns = rng.normal(0, 0.003, n_bars)
    close = start_price * np.cumprod(1 + returns)
    bar_range = rng.uniform(5, 30, n_bars)
    high = close + bar_range * rng.uniform(0.3, 0.7, n_bars)
    low = close - bar_range * rng.uniform(0.3, 0.7, n_bars)
    open_ = low + (high - low) * rng.uniform(0.2, 0.8, n_bars)

    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close,
         "volume": rng.integers(1000, 50000, n_bars).astype(float)},
        index=dates,
    )
    df = add_precomputed_features(df, sma_lengths=[10, 20, 50], avg_range_lookbacks=[20])
    return df


def make_signals(n_bars: int, frequency: int = 30, offset: int = 50) -> np.ndarray:
    """Deterministic signal pattern: every *frequency* bars starting at *offset*."""
    signals = np.zeros(n_bars, dtype=bool)
    for i in range(offset, n_bars, frequency):
        signals[i] = True
    return signals


# ── Minimal strategy for parity testing ────────────────────────

class _ParityStrategy(BaseStrategy):
    """Thin wrapper so the original engine can be driven with an ExitConfig."""
    name = "ParityTest"

    def __init__(self, exit_config=None, hold_bars=5, filters=None):
        self.hold_bars = hold_bars
        self.stop_distance_points = 10.0
        self.exit_config = exit_config
        self.filters = filters or []

    def generate_signal(self, data, i):
        return 0  # never used — precomputed_signals is always provided


class _MockFilter:
    """Provides ``fast_length`` so the engine can resolve the fast-SMA column."""
    def __init__(self, fast_length=10):
        self.fast_length = fast_length


# ── Comparison helpers ─────────────────────────────────────────

def capture_trades(engine: MasterStrategyEngine) -> list[dict]:
    """Normalise the original engine's trade list to plain dicts."""
    return [
        {
            "entry_time": t.entry_time,
            "entry_price": t.entry_price,
            "exit_time": t.exit_time,
            "exit_price": t.exit_price,
            "exit_reason": t.exit_reason,
            "pnl": t.pnl,
            "bars_held": t.bars_held,
            "direction": t.direction,
            "contracts": t.contracts,
        }
        for t in engine.trades
    ]


def compare_trades(old_trades: list[dict], new_trades: list[dict],
                   tolerance: float = 1e-10) -> None:
    """Assert two trade lists are identical within *tolerance*."""
    assert len(old_trades) == len(new_trades), (
        f"Trade count mismatch: old={len(old_trades)}, new={len(new_trades)}"
    )
    for i, (old, new) in enumerate(zip(old_trades, new_trades)):
        assert old["entry_time"] == new["entry_time"], (
            f"Trade {i}: entry_time {old['entry_time']} != {new['entry_time']}")
        assert abs(old["entry_price"] - new["entry_price"]) < tolerance, (
            f"Trade {i}: entry_price {old['entry_price']:.10f} != {new['entry_price']:.10f}")
        assert abs(old["exit_price"] - new["exit_price"]) < tolerance, (
            f"Trade {i}: exit_price {old['exit_price']:.10f} != {new['exit_price']:.10f}")
        assert old["exit_reason"] == new["exit_reason"], (
            f"Trade {i}: exit_reason {old['exit_reason']} != {new['exit_reason']}")
        assert abs(old["pnl"] - new["pnl"]) < tolerance, (
            f"Trade {i}: pnl {old['pnl']:.10f} != {new['pnl']:.10f}")
        assert old["bars_held"] == new["bars_held"], (
            f"Trade {i}: bars_held {old['bars_held']} != {new['bars_held']}")
        assert old["direction"] == new["direction"], (
            f"Trade {i}: direction {old['direction']} != {new['direction']}")
        assert old["contracts"] == new["contracts"], (
            f"Trade {i}: contracts {old['contracts']} != {new['contracts']}")


# ── Runner: execute both engines with identical parameters ─────

def run_both(
    data: pd.DataFrame,
    signals: np.ndarray,
    hold_bars: int = 5,
    stop_distance_atr: float = 2.0,
    exit_type: str = "time_stop",
    direction: str = "long",
    profit_target_atr: float | None = None,
    trailing_stop_atr: float | None = None,
    early_exit_bars: int | None = None,
    break_even_atr: float | None = None,
    break_even_lock_atr: float = 0.0,
    signal_exit_reference: str | None = None,
    sma_fast_length: int | None = None,
) -> tuple[list[dict], list[dict]]:
    """Return (original_trades, vectorized_trades)."""
    config = EngineConfig(direction=direction)

    ec = ExitConfig(
        exit_type=ExitType(exit_type),
        hold_bars=hold_bars,
        stop_distance_points=10.0,  # placeholder — overridden by stop_distance_atr
        profit_target_atr=profit_target_atr,
        trailing_stop_atr=trailing_stop_atr,
        signal_exit_reference=signal_exit_reference,
        break_even_atr=break_even_atr,
        break_even_lock_atr=break_even_lock_atr,
        early_exit_bars=early_exit_bars,
    )

    filters = [_MockFilter(fast_length=sma_fast_length)] if sma_fast_length else []
    strategy = _ParityStrategy(exit_config=ec, hold_bars=hold_bars, filters=filters)

    # ---- Original engine ----
    engine = MasterStrategyEngine(data.copy(), config)
    engine.run(strategy, hold_bars=hold_bars, stop_distance_atr=stop_distance_atr,
               precomputed_signals=signals)
    orig = capture_trades(engine)

    # ---- Vectorized engine ----
    atr = data["atr_20"].values if "atr_20" in data.columns else np.full(len(data), 10.0)
    sma_arr = None
    if signal_exit_reference == "fast_sma" and sma_fast_length:
        col = f"sma_{sma_fast_length}"
        if col in data.columns:
            sma_arr = data[col].values

    result = vectorized_backtest(
        signal_mask=signals,
        close=data["close"].values,
        high=data["high"].values,
        low=data["low"].values,
        atr=atr,
        timestamps=data.index,
        hold_bars=hold_bars,
        stop_distance_atr=stop_distance_atr,
        exit_type=exit_type,
        direction=direction,
        initial_capital=config.initial_capital,
        risk_per_trade=config.risk_per_trade,
        commission_per_contract=config.commission_per_contract,
        slippage_ticks=config.slippage_ticks,
        tick_value=config.tick_value,
        dollars_per_point=config.dollars_per_point,
        profit_target_atr=profit_target_atr,
        trailing_stop_atr=trailing_stop_atr,
        signal_exit_sma=sma_arr,
        early_exit_bars=early_exit_bars,
        break_even_atr=break_even_atr,
        break_even_lock_atr=break_even_lock_atr,
    )
    vec = result["trades"]
    return orig, vec


# ===================================================================
# Test 1: time_stop exit (most common — ~80 % of strategies)
# ===================================================================

def test_parity_time_stop_long_daily():
    data = make_test_data(2000, seed=42)
    signals = make_signals(len(data), frequency=30, offset=50)
    orig, vec = run_both(data, signals, hold_bars=5, stop_distance_atr=2.0,
                         exit_type="time_stop", direction="long")
    assert len(orig) > 0, "Expected at least one trade"
    compare_trades(orig, vec)


def test_parity_time_stop_short_daily():
    data = make_test_data(2000, seed=42)
    signals = make_signals(len(data), frequency=30, offset=50)
    orig, vec = run_both(data, signals, hold_bars=5, stop_distance_atr=2.0,
                         exit_type="time_stop", direction="short")
    assert len(orig) > 0
    compare_trades(orig, vec)


# ===================================================================
# Test 2: protective stop hit
# ===================================================================

def test_parity_stop_hit_long():
    data = make_test_data(2000, seed=99)
    signals = make_signals(len(data), frequency=15, offset=50)
    orig, vec = run_both(data, signals, hold_bars=10, stop_distance_atr=0.3,
                         exit_type="time_stop", direction="long")
    assert len(orig) > 0
    stop_count = sum(1 for t in orig if t["exit_reason"] == "STOP")
    assert stop_count > 0, "Expected some STOP exits with tight stops"
    compare_trades(orig, vec)


def test_parity_stop_hit_short():
    data = make_test_data(2000, seed=99)
    signals = make_signals(len(data), frequency=15, offset=50)
    orig, vec = run_both(data, signals, hold_bars=10, stop_distance_atr=0.3,
                         exit_type="time_stop", direction="short")
    assert len(orig) > 0
    stop_count = sum(1 for t in orig if t["exit_reason"] == "STOP")
    assert stop_count > 0
    compare_trades(orig, vec)


# ===================================================================
# Test 3: profit target hit
# ===================================================================

def test_parity_profit_target_long():
    data = make_test_data(2000, seed=55)
    signals = make_signals(len(data), frequency=20, offset=50)
    orig, vec = run_both(data, signals, hold_bars=10, stop_distance_atr=2.0,
                         exit_type="profit_target", direction="long",
                         profit_target_atr=0.5)
    assert len(orig) > 0
    pt = sum(1 for t in orig if t["exit_reason"] == "PROFIT_TARGET")
    assert pt > 0, "Expected some PROFIT_TARGET exits"
    compare_trades(orig, vec)


def test_parity_profit_target_short():
    data = make_test_data(2000, seed=55)
    signals = make_signals(len(data), frequency=20, offset=50)
    orig, vec = run_both(data, signals, hold_bars=10, stop_distance_atr=2.0,
                         exit_type="profit_target", direction="short",
                         profit_target_atr=0.5)
    assert len(orig) > 0
    pt = sum(1 for t in orig if t["exit_reason"] == "PROFIT_TARGET")
    assert pt > 0
    compare_trades(orig, vec)


# ===================================================================
# Test 4: trailing stop
# ===================================================================

def test_parity_trailing_stop_long():
    data = make_test_data(2000, seed=77)
    signals = make_signals(len(data), frequency=20, offset=50)
    orig, vec = run_both(data, signals, hold_bars=15, stop_distance_atr=2.0,
                         exit_type="trailing_stop", direction="long",
                         trailing_stop_atr=1.5)
    assert len(orig) > 0
    ts = sum(1 for t in orig if t["exit_reason"] == "TRAILING_STOP")
    assert ts > 0, "Expected some TRAILING_STOP exits"
    compare_trades(orig, vec)


def test_parity_trailing_stop_short():
    data = make_test_data(2000, seed=77)
    signals = make_signals(len(data), frequency=20, offset=50)
    orig, vec = run_both(data, signals, hold_bars=15, stop_distance_atr=2.0,
                         exit_type="trailing_stop", direction="short",
                         trailing_stop_atr=1.5)
    assert len(orig) > 0
    ts = sum(1 for t in orig if t["exit_reason"] == "TRAILING_STOP")
    assert ts > 0
    compare_trades(orig, vec)


# ===================================================================
# Test 5: signal exit (close >= fast_sma for long MR)
# ===================================================================

def test_parity_signal_exit():
    data = make_test_data(2000, seed=88)
    signals = make_signals(len(data), frequency=25, offset=50)
    orig, vec = run_both(data, signals, hold_bars=20, stop_distance_atr=2.0,
                         exit_type="signal_exit", direction="long",
                         signal_exit_reference="fast_sma", sma_fast_length=10)
    assert len(orig) > 0
    se = sum(1 for t in orig if t["exit_reason"] == "SIGNAL_EXIT")
    assert se > 0, "Expected some SIGNAL_EXIT exits"
    compare_trades(orig, vec)


# ===================================================================
# Test 6: early exit (losing after N bars)
# ===================================================================

def test_parity_early_exit():
    data = make_test_data(2000, seed=44)
    signals = make_signals(len(data), frequency=20, offset=50)
    orig, vec = run_both(data, signals, hold_bars=10, stop_distance_atr=2.0,
                         exit_type="time_stop", direction="long",
                         early_exit_bars=3)
    assert len(orig) > 0
    ee = sum(1 for t in orig if t["exit_reason"] == "EARLY_EXIT")
    assert ee > 0, "Expected some EARLY_EXIT exits"
    compare_trades(orig, vec)


# ===================================================================
# Test 7: break-even stop modifier
# ===================================================================

def test_parity_break_even_stop():
    data = make_test_data(2000, seed=33)
    signals = make_signals(len(data), frequency=20, offset=50)
    orig, vec = run_both(data, signals, hold_bars=15, stop_distance_atr=2.0,
                         exit_type="time_stop", direction="long",
                         break_even_atr=0.5, break_even_lock_atr=0.1)
    assert len(orig) > 0
    compare_trades(orig, vec)


# ===================================================================
# Test 8: full strategy (realistic parameters, many trades)
# ===================================================================

def test_parity_full_strategy_es_daily():
    data = make_test_data(3000, seed=42)
    signals = make_signals(len(data), frequency=15, offset=100)
    orig, vec = run_both(data, signals, hold_bars=8, stop_distance_atr=1.5,
                         exit_type="time_stop", direction="long")
    assert len(orig) > 5
    compare_trades(orig, vec)


def test_parity_full_strategy_es_60m():
    data = make_test_data(5000, seed=123)
    signals = make_signals(len(data), frequency=20, offset=100)
    orig, vec = run_both(data, signals, hold_bars=5, stop_distance_atr=2.0,
                         exit_type="time_stop", direction="long")
    assert len(orig) > 10
    compare_trades(orig, vec)


# ===================================================================
# Test 9: position sizing varies (ATR-based stop → different contracts)
# ===================================================================

def test_parity_position_sizing():
    data = make_test_data(2000, seed=42)
    signals = make_signals(len(data), frequency=25, offset=50)
    orig, vec = run_both(data, signals, hold_bars=5, stop_distance_atr=1.0,
                         exit_type="time_stop", direction="long")
    assert len(orig) > 0
    compare_trades(orig, vec)


# ===================================================================
# Test 10: short strategies
# ===================================================================

def test_parity_short_mean_reversion():
    data = make_test_data(2000, seed=66)
    signals = make_signals(len(data), frequency=20, offset=50)
    orig, vec = run_both(data, signals, hold_bars=5, stop_distance_atr=2.0,
                         exit_type="time_stop", direction="short")
    assert len(orig) > 0
    compare_trades(orig, vec)


def test_parity_short_breakout():
    data = make_test_data(2000, seed=77)
    signals = make_signals(len(data), frequency=25, offset=50)
    orig, vec = run_both(data, signals, hold_bars=8, stop_distance_atr=1.5,
                         exit_type="profit_target", direction="short",
                         profit_target_atr=1.0)
    assert len(orig) > 0
    compare_trades(orig, vec)


# ===================================================================
# Edge cases
# ===================================================================

def test_parity_no_signals():
    data = make_test_data(500, seed=42)
    signals = np.zeros(len(data), dtype=bool)
    orig, vec = run_both(data, signals, hold_bars=5, stop_distance_atr=2.0)
    assert len(orig) == 0
    assert len(vec) == 0


def test_parity_signal_on_last_bar():
    data = make_test_data(500, seed=42)
    signals = np.zeros(len(data), dtype=bool)
    signals[-1] = True
    orig, vec = run_both(data, signals, hold_bars=5, stop_distance_atr=2.0)
    compare_trades(orig, vec)


def test_parity_overlapping_signals():
    """Signals closer than hold_bars — overlap prevention must match."""
    data = make_test_data(500, seed=42)
    signals = np.zeros(len(data), dtype=bool)
    signals[50] = True
    signals[52] = True  # 2 bars after first → blocked by hold_bars=5
    signals[58] = True  # first trade exits at 55 → next allowed at 56 → 58 ok
    orig, vec = run_both(data, signals, hold_bars=5, stop_distance_atr=2.0)
    compare_trades(orig, vec)


def test_parity_short_data():
    """Fewer bars than hold_bars."""
    data = make_test_data(10, seed=42)
    signals = np.zeros(len(data), dtype=bool)
    signals[2] = True
    orig, vec = run_both(data, signals, hold_bars=20, stop_distance_atr=2.0)
    compare_trades(orig, vec)


# ===================================================================
# Task 7: Full sweep parity test (real data)
# ===================================================================

_ES_DAILY = "Data/ES_daily_2008_2026_tradestation.csv"


@pytest.mark.skipif(
    not __import__("pathlib").Path(_ES_DAILY).exists(),
    reason="ES daily data not available",
)
def test_full_sweep_parity_es_daily():
    """Run real strategy combos through both engines and compare every trade.

    Uses the MeanReversionStrategyType to generate filter combinations,
    then runs each combo through both the original and vectorized engines
    with identical parameters.  Zero tolerance on all trades.
    """
    from modules.data_loader import load_tradestation_csv
    from modules.feature_builder import add_precomputed_features
    from modules.strategy_types.strategy_factory import get_strategy_type
    from modules.filter_combinator import generate_filter_combinations
    from modules.vectorized_signals import compute_combined_signal_mask
    from modules.vectorized_trades import vectorized_backtest

    # Load real data
    data = load_tradestation_csv(_ES_DAILY, debug=False)
    data = add_precomputed_features(
        data, sma_lengths=[10, 20, 50, 200],
        avg_range_lookbacks=[10, 20],
        momentum_lookbacks=[5, 10, 20],
    )

    cfg = EngineConfig(
        symbol="ES", timeframe="daily", direction="long",
        oos_split_date="2019-01-01",
    )

    st = get_strategy_type("mean_reversion")
    filter_classes = st.get_filter_classes()

    # Generate a subset of combos (3 filters, first 20 combos)
    combos = list(generate_filter_combinations(
        filter_classes,
        min_filters=st.min_filters_per_combo,
        max_filters=st.min_filters_per_combo,
    ))[:20]

    hb = st.default_hold_bars
    sda = st.default_stop_distance_points  # this is actually stop_distance_atr

    total_trades_checked = 0
    for combo_classes in combos:
        filter_objects = st.build_filter_objects_from_classes(combo_classes, timeframe="daily")
        strategy = st.build_combinable_strategy(
            filters=filter_objects,
            hold_bars=hb,
            stop_distance_points=sda,
        )
        signal_mask = compute_combined_signal_mask(filter_objects, data)

        # Original engine
        eng_orig = MasterStrategyEngine(data, cfg)
        eng_orig.run(strategy=strategy, precomputed_signals=signal_mask)
        orig_trades = capture_trades(eng_orig)

        # Vectorized engine
        eng_vec = MasterStrategyEngine(data, cfg)
        eng_vec.run_vectorized(strategy=strategy, precomputed_signals=signal_mask)
        vec_trades = capture_trades(eng_vec)

        compare_trades(orig_trades, vec_trades)
        total_trades_checked += len(orig_trades)

    assert total_trades_checked > 50, (
        f"Expected 50+ trades across all combos, got {total_trades_checked}"
    )


# ===================================================================
# Task 8: Benchmark — measure vectorized speedup
# ===================================================================

def _benchmark_single_strategy(data, signals, hold_bars, stop_distance_atr,
                                direction="long", n_runs=5):
    """Time both engines on the same data/signals and return (orig_s, vec_s)."""
    import time

    config = EngineConfig(direction=direction)
    ec = ExitConfig(exit_type=ExitType.TIME_STOP, hold_bars=hold_bars,
                    stop_distance_points=10.0)
    strategy = _ParityStrategy(exit_config=ec, hold_bars=hold_bars)

    atr_arr = data["atr_20"].values if "atr_20" in data.columns else np.full(len(data), 10.0)
    from modules.vectorized_trades import vectorized_backtest

    # Warm-up
    eng = MasterStrategyEngine(data, config)
    eng.run(strategy, hold_bars=hold_bars, stop_distance_atr=stop_distance_atr,
            precomputed_signals=signals)

    # Original engine
    t0 = time.perf_counter()
    for _ in range(n_runs):
        eng = MasterStrategyEngine(data, config)
        eng.run(strategy, hold_bars=hold_bars, stop_distance_atr=stop_distance_atr,
                precomputed_signals=signals)
    orig_s = (time.perf_counter() - t0) / n_runs

    # Vectorized engine
    t0 = time.perf_counter()
    for _ in range(n_runs):
        vectorized_backtest(
            signal_mask=signals,
            close=data["close"].values,
            high=data["high"].values,
            low=data["low"].values,
            atr=atr_arr,
            timestamps=data.index,
            hold_bars=hold_bars,
            stop_distance_atr=stop_distance_atr,
            direction=direction,
            initial_capital=config.initial_capital,
            risk_per_trade=config.risk_per_trade,
            commission_per_contract=config.commission_per_contract,
            slippage_ticks=config.slippage_ticks,
            tick_value=config.tick_value,
            dollars_per_point=config.dollars_per_point,
        )
    vec_s = (time.perf_counter() - t0) / n_runs

    return orig_s, vec_s


def test_vectorized_speedup_synthetic():
    """Vectorized should be significantly faster on medium-sized data."""
    data = make_test_data(10000, seed=42)
    signals = make_signals(len(data), frequency=20, offset=50)
    orig_s, vec_s = _benchmark_single_strategy(data, signals, hold_bars=5,
                                                stop_distance_atr=2.0)
    speedup = orig_s / vec_s if vec_s > 0 else float("inf")
    print(f"\nBenchmark (10K bars synthetic):")
    print(f"  Original:   {orig_s*1000:.1f} ms")
    print(f"  Vectorized: {vec_s*1000:.1f} ms")
    print(f"  Speedup:    {speedup:.1f}x")
    assert speedup > 2, f"Expected at least 2x speedup, got {speedup:.1f}x"


@pytest.mark.skipif(
    not __import__("pathlib").Path(_ES_DAILY).exists(),
    reason="ES daily data not available",
)
def test_vectorized_speedup_daily():
    """Benchmark on real ES daily data (~2800 bars)."""
    from modules.data_loader import load_tradestation_csv

    data = load_tradestation_csv(_ES_DAILY, debug=False)
    data = add_precomputed_features(data, sma_lengths=[10, 20, 50],
                                     avg_range_lookbacks=[20])
    signals = make_signals(len(data), frequency=15, offset=50)
    orig_s, vec_s = _benchmark_single_strategy(data, signals, hold_bars=5,
                                                stop_distance_atr=2.0, n_runs=10)
    speedup = orig_s / vec_s if vec_s > 0 else float("inf")
    print(f"\nBenchmark ES daily ({len(data)} bars):")
    print(f"  Original:   {orig_s*1000:.1f} ms")
    print(f"  Vectorized: {vec_s*1000:.1f} ms")
    print(f"  Speedup:    {speedup:.1f}x")
    assert speedup > 3, f"Expected at least 3x speedup on daily, got {speedup:.1f}x"


_ES_60M = "Data/ES_60m_2008_2026_tradestation.csv"


@pytest.mark.skipif(
    not __import__("pathlib").Path(_ES_60M).exists(),
    reason="ES 60m data not available",
)
def test_vectorized_speedup_60m():
    """Benchmark on real ES 60m data (~53K bars)."""
    from modules.data_loader import load_tradestation_csv

    data = load_tradestation_csv(_ES_60M, debug=False)
    data = add_precomputed_features(data, sma_lengths=[10, 20, 50],
                                     avg_range_lookbacks=[20])
    signals = make_signals(len(data), frequency=20, offset=50)
    orig_s, vec_s = _benchmark_single_strategy(data, signals, hold_bars=5,
                                                stop_distance_atr=2.0, n_runs=5)
    speedup = orig_s / vec_s if vec_s > 0 else float("inf")
    print(f"\nBenchmark ES 60m ({len(data)} bars):")
    print(f"  Original:   {orig_s*1000:.1f} ms")
    print(f"  Vectorized: {vec_s*1000:.1f} ms")
    print(f"  Speedup:    {speedup:.1f}x")
    assert speedup > 10, f"Expected at least 10x speedup on 60m, got {speedup:.1f}x"


_ES_15M = "Data/ES_15m_2008_2026_tradestation.csv"


@pytest.mark.skipif(
    not __import__("pathlib").Path(_ES_15M).exists(),
    reason="ES 15m data not available",
)
def test_vectorized_speedup_15m():
    """Benchmark on real ES 15m data (~231K bars) — highest speedup expected."""
    from modules.data_loader import load_tradestation_csv

    data = load_tradestation_csv(_ES_15M, debug=False)
    data = add_precomputed_features(data, sma_lengths=[10, 20, 50],
                                     avg_range_lookbacks=[20])
    signals = make_signals(len(data), frequency=20, offset=50)
    orig_s, vec_s = _benchmark_single_strategy(data, signals, hold_bars=5,
                                                stop_distance_atr=2.0, n_runs=3)
    speedup = orig_s / vec_s if vec_s > 0 else float("inf")
    print(f"\nBenchmark ES 15m ({len(data)} bars):")
    print(f"  Original:   {orig_s*1000:.1f} ms")
    print(f"  Vectorized: {vec_s*1000:.1f} ms")
    print(f"  Speedup:    {speedup:.1f}x")
    assert speedup > 20, f"Expected at least 20x speedup on 15m, got {speedup:.1f}x"
