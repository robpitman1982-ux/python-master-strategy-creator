"""Regression tests for rebuild parity on short-side strategies.

Bug discovered Session 97: `_rebuild_strategy_from_leaderboard_row()` constructs
EngineConfig without setting `direction`, so it defaults to "long". Short
strategies (ShortMR, ShortTrend, ShortBreakout) were being rebuilt as long
trades, producing PARITY_FAILED on every accepted short row.

These tests run the engine end-to-end on a small synthetic dataset for both
a long-side and a short-side strategy, capture the leader net_pnl from the
sweep-style EngineConfig, then call the rebuild path and assert parity.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.engine import EngineConfig, MasterStrategyEngine
from modules.feature_builder import add_precomputed_features
from modules.portfolio_evaluator import _normalize_trade_columns, _rebuild_strategy_from_leaderboard_row
from modules.strategy_types import get_strategy_type
from modules.vectorized_signals import compute_combined_signal_mask


def _make_synthetic_5m_data(n_bars: int = 4000, seed: int = 7) -> pd.DataFrame:
    """Random-walk OHLC with mild mean-reverting overlay so both long and short
    strategies generate trades. Index is a regular 5-minute series."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01 09:00", periods=n_bars, freq="5min")
    drift = 0.0
    ret = rng.normal(drift, 0.5, size=n_bars)
    close = 100.0 + np.cumsum(ret)
    high = close + np.abs(rng.normal(0, 0.3, size=n_bars))
    low = close - np.abs(rng.normal(0, 0.3, size=n_bars))
    open_ = np.r_[close[0], close[:-1]] + rng.normal(0, 0.05, size=n_bars)
    df = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum.reduce([open_, high, close]),
            "low": np.minimum.reduce([open_, low, close]),
            "close": close,
            "volume": rng.integers(100, 1000, size=n_bars),
        },
        index=idx,
    )
    return df


def _build_leaderboard_row(
    strategy_type_name: str,
    filter_classes: list[str],
    hold_bars: int = 24,
    stop_distance_atr: float = 1.0,
    exit_type: str = "time_stop",
    signal_exit_reference: str | float = float("nan"),
) -> pd.Series:
    return pd.Series(
        {
            "strategy_type": strategy_type_name,
            "leader_source": "refined",
            "leader_strategy_name": "TestRefined",
            "best_combo_strategy_name": "TestCombo",
            "best_combo_filter_class_names": ",".join(filter_classes),
            "leader_hold_bars": hold_bars,
            "leader_stop_distance_atr": stop_distance_atr,
            "leader_min_avg_range": 0.0,
            "leader_momentum_lookback": 0,
            "leader_exit_type": exit_type,
            "leader_trailing_stop_atr": float("nan"),
            "leader_profit_target_atr": float("nan"),
            "leader_signal_exit_reference": signal_exit_reference,
            "leader_net_pnl": 0.0,
        }
    )


def _run_strategy_native(
    strategy_type_name: str,
    filter_class_names: list[str],
    data: pd.DataFrame,
    timeframe: str,
    market_symbol: str,
    hold_bars: int,
    stop_distance_atr: float,
    exit_type: str = "time_stop",
    signal_exit_reference: str | None = None,
) -> float:
    """Run a strategy through the engine the way the sweep does — with direction
    pulled from strategy_type.get_engine_direction(). Returns net_pnl."""
    strategy_type = get_strategy_type(strategy_type_name)
    direction = strategy_type.get_engine_direction()

    eval_data = add_precomputed_features(
        data.copy(),
        sma_lengths=strategy_type.get_required_sma_lengths(timeframe=timeframe),
        avg_range_lookbacks=strategy_type.get_required_avg_range_lookbacks(timeframe=timeframe),
        momentum_lookbacks=strategy_type.get_required_momentum_lookbacks(timeframe=timeframe),
    )

    combo_classes = [getattr(__import__("modules.filters", fromlist=[fc]), fc) for fc in filter_class_names]

    strategy = strategy_type.build_candidate_specific_strategy(
        combo_classes,
        hold_bars,
        stop_distance_atr,
        0.0,
        0,
        timeframe=timeframe,
        exit_type=exit_type,
        signal_exit_reference=signal_exit_reference,
    )

    filter_objects = strategy_type.build_filter_objects_from_classes(
        combo_classes, timeframe=timeframe
    )
    precomputed_signals = compute_combined_signal_mask(filter_objects, eval_data)

    cfg = EngineConfig(
        initial_capital=250_000.0,
        risk_per_trade=0.01,
        symbol=market_symbol,
        commission_per_contract=0,
        slippage_ticks=1,
        tick_value=0.01,
        dollars_per_point=1.0,
        timeframe=timeframe,
        direction=direction,
        use_vectorized_trades=True,
    )
    engine = MasterStrategyEngine(data=eval_data, config=cfg)
    # Match sweep dispatch (mean_reversion_strategy_type.py:116)
    engine.run_vectorized(strategy=strategy, precomputed_signals=precomputed_signals)

    trades_df = _normalize_trade_columns(engine.trades_dataframe())
    if trades_df is None or trades_df.empty:
        return 0.0
    return float(pd.to_numeric(trades_df["net_pnl"], errors="coerce").fillna(0.0).sum())


def _run_strategy_via_rebuild(
    strategy_type_name: str,
    filter_class_names: list[str],
    data: pd.DataFrame,
    timeframe: str,
    market_symbol: str,
    hold_bars: int,
    stop_distance_atr: float,
    tmp_path,
    exit_type: str = "time_stop",
    signal_exit_reference: str | float = float("nan"),
) -> float:
    row = _build_leaderboard_row(
        strategy_type_name, filter_class_names, hold_bars, stop_distance_atr,
        exit_type=exit_type, signal_exit_reference=signal_exit_reference,
    )
    trades_df, _filters_str, _cfg = _rebuild_strategy_from_leaderboard_row(
        row=row,
        data=data,
        outputs_dir=tmp_path,
        market_symbol=market_symbol,
        timeframe=timeframe,
    )
    if trades_df is None or trades_df.empty:
        return 0.0
    return float(pd.to_numeric(trades_df["net_pnl"], errors="coerce").fillna(0.0).sum())


@pytest.fixture
def synthetic_data():
    return _make_synthetic_5m_data()


def test_rebuild_parity_long_mean_reversion(synthetic_data, tmp_path):
    """Sanity: long strategies (which already worked) still rebuild with parity."""
    filter_class_names = ["DistanceBelowSMAFilter", "DownCloseFilter", "TwoBarDownFilter"]
    native_pnl = _run_strategy_native(
        "mean_reversion", filter_class_names, synthetic_data,
        timeframe="5m", market_symbol="NQ",
        hold_bars=24, stop_distance_atr=1.0,
    )
    rebuilt_pnl = _run_strategy_via_rebuild(
        "mean_reversion", filter_class_names, synthetic_data,
        timeframe="5m", market_symbol="NQ",
        hold_bars=24, stop_distance_atr=1.0,
        tmp_path=tmp_path,
    )
    # Expect zero-tolerance parity: same engine, same params, same direction.
    assert rebuilt_pnl == pytest.approx(native_pnl, rel=1e-6, abs=0.01), (
        f"Long MR rebuild mismatch: native=${native_pnl:,.2f} vs rebuilt=${rebuilt_pnl:,.2f}"
    )


def test_rebuild_parity_short_mean_reversion(synthetic_data, tmp_path):
    """Regression: ShortMR with direction='short' must rebuild with parity.

    Before the fix, rebuild constructed EngineConfig without `direction=`, so
    ShortMR was being rebuilt as long. This test fails on unfixed code.
    """
    filter_class_names = ["AboveFastSMAFilter", "DistanceAboveSMAFilter", "UpCloseShortFilter"]
    native_pnl = _run_strategy_native(
        "short_mean_reversion", filter_class_names, synthetic_data,
        timeframe="5m", market_symbol="NQ",
        hold_bars=24, stop_distance_atr=1.0,
    )
    rebuilt_pnl = _run_strategy_via_rebuild(
        "short_mean_reversion", filter_class_names, synthetic_data,
        timeframe="5m", market_symbol="NQ",
        hold_bars=24, stop_distance_atr=1.0,
        tmp_path=tmp_path,
    )
    assert rebuilt_pnl == pytest.approx(native_pnl, rel=1e-6, abs=0.01), (
        f"Short MR rebuild mismatch: native=${native_pnl:,.2f} vs rebuilt=${rebuilt_pnl:,.2f}"
    )


def test_rebuild_parity_short_trend(synthetic_data, tmp_path):
    """Regression: ShortTrend rebuild parity."""
    filter_class_names = ["LowerHighFilter", "DownCloseShortFilter", "LowerLowFilter"]
    native_pnl = _run_strategy_native(
        "short_trend", filter_class_names, synthetic_data,
        timeframe="5m", market_symbol="NQ",
        hold_bars=36, stop_distance_atr=0.75,
    )
    rebuilt_pnl = _run_strategy_via_rebuild(
        "short_trend", filter_class_names, synthetic_data,
        timeframe="5m", market_symbol="NQ",
        hold_bars=36, stop_distance_atr=0.75,
        tmp_path=tmp_path,
    )
    assert rebuilt_pnl == pytest.approx(native_pnl, rel=1e-6, abs=0.01), (
        f"Short Trend rebuild mismatch: native=${native_pnl:,.2f} vs rebuilt=${rebuilt_pnl:,.2f}"
    )


def test_rebuild_parity_short_breakout(synthetic_data, tmp_path):
    """Regression: ShortBreakout rebuild parity."""
    filter_class_names = ["TightRangeFilter", "BreakoutCloseStrengthFilter", "LowerLowFilter"]
    native_pnl = _run_strategy_native(
        "short_breakout", filter_class_names, synthetic_data,
        timeframe="5m", market_symbol="NQ",
        hold_bars=120, stop_distance_atr=0.5,
    )
    rebuilt_pnl = _run_strategy_via_rebuild(
        "short_breakout", filter_class_names, synthetic_data,
        timeframe="5m", market_symbol="NQ",
        hold_bars=120, stop_distance_atr=0.5,
        tmp_path=tmp_path,
    )
    assert rebuilt_pnl == pytest.approx(native_pnl, rel=1e-6, abs=0.01), (
        f"Short Breakout rebuild mismatch: native=${native_pnl:,.2f} vs rebuilt=${rebuilt_pnl:,.2f}"
    )


def test_rebuild_parity_short_mr_signal_exit_fast_sma(synthetic_data, tmp_path):
    """Regression: ShortMR with exit_type=signal_exit/fast_sma must rebuild
    identically to the sweep path.

    Bug #2 (Session 97): rebuild called engine.run() (Python loop) regardless
    of cfg.use_vectorized_trades. The Python-loop signal_exit logic is
    long-only (close >= fast_sma), which never fires for shorts → silent
    fallback to time_stop. Sweep dispatches engine.run_vectorized() which
    correctly handles direction (close <= fast_sma for shorts).
    """
    filter_class_names = ["AboveFastSMAFilter", "DistanceAboveSMAFilter", "UpCloseShortFilter"]
    native_pnl = _run_strategy_native(
        "short_mean_reversion", filter_class_names, synthetic_data,
        timeframe="5m", market_symbol="NQ",
        hold_bars=24, stop_distance_atr=0.4,
        exit_type="signal_exit", signal_exit_reference="fast_sma",
    )
    rebuilt_pnl = _run_strategy_via_rebuild(
        "short_mean_reversion", filter_class_names, synthetic_data,
        timeframe="5m", market_symbol="NQ",
        hold_bars=24, stop_distance_atr=0.4,
        tmp_path=tmp_path,
        exit_type="signal_exit", signal_exit_reference="fast_sma",
    )
    assert rebuilt_pnl == pytest.approx(native_pnl, rel=1e-6, abs=0.01), (
        f"Short MR signal_exit rebuild mismatch: native=${native_pnl:,.2f} vs rebuilt=${rebuilt_pnl:,.2f}"
    )


def test_rebuild_uses_best_refined_filters_when_leader_is_refined(synthetic_data, tmp_path):
    """Bug #3 (Session 97): when the refined winner came from a different
    promoted candidate than `best_combo_*`, rebuild must use
    `best_refined_filter_class_names` (the actual winning combo) — not
    `best_combo_filter_class_names` (which is the best raw-sweep combo).

    Setup: native run uses filter combo X. Build a leaderboard row with
    `best_combo_filter_class_names = Y` (different combo) but
    `best_refined_filter_class_names = X`, leader_source='refined'. Rebuild
    must produce the X result (matching native), not the Y result.
    """
    filter_x = ["DistanceBelowSMAFilter", "DownCloseFilter", "TwoBarDownFilter"]
    filter_y = ["DistanceBelowSMAFilter", "ReversalUpBarFilter", "InsideBarFilter"]

    # Native run with combo X
    native_pnl_x = _run_strategy_native(
        "mean_reversion", filter_x, synthetic_data,
        timeframe="5m", market_symbol="NQ",
        hold_bars=24, stop_distance_atr=1.0,
    )

    # Build a leaderboard row that says best_combo=Y but best_refined=X (leader=refined).
    row = pd.Series({
        "strategy_type": "mean_reversion",
        "leader_source": "refined",
        "leader_strategy_name": "TestRefined",
        "best_combo_strategy_name": "ComboY",
        "best_combo_filter_class_names": ",".join(filter_y),
        "best_refined_filter_class_names": ",".join(filter_x),
        "leader_hold_bars": 24,
        "leader_stop_distance_atr": 1.0,
        "leader_min_avg_range": 0.0,
        "leader_momentum_lookback": 0,
        "leader_exit_type": "time_stop",
        "leader_trailing_stop_atr": float("nan"),
        "leader_profit_target_atr": float("nan"),
        "leader_signal_exit_reference": float("nan"),
        "leader_net_pnl": 0.0,
    })

    trades_df, _, _ = _rebuild_strategy_from_leaderboard_row(
        row=row, data=synthetic_data, outputs_dir=tmp_path,
        market_symbol="NQ", timeframe="5m",
    )
    trades_df = _normalize_trade_columns(trades_df)
    rebuilt_pnl = float(pd.to_numeric(trades_df["net_pnl"], errors="coerce").fillna(0.0).sum()) if not trades_df.empty else 0.0

    assert rebuilt_pnl == pytest.approx(native_pnl_x, rel=1e-6, abs=0.01), (
        f"Rebuild used wrong filter combo. Expected combo X result "
        f"(native=${native_pnl_x:,.2f}) but got ${rebuilt_pnl:,.2f}. "
        f"Likely fell back to best_combo (Y) instead of best_refined (X)."
    )


def test_rebuild_parity_long_mr_signal_exit_fast_sma(synthetic_data, tmp_path):
    """Sanity: long MR with signal_exit/fast_sma also rebuilds with parity."""
    filter_class_names = ["DistanceBelowSMAFilter", "DownCloseFilter", "TwoBarDownFilter"]
    native_pnl = _run_strategy_native(
        "mean_reversion", filter_class_names, synthetic_data,
        timeframe="5m", market_symbol="NQ",
        hold_bars=24, stop_distance_atr=0.4,
        exit_type="signal_exit", signal_exit_reference="fast_sma",
    )
    rebuilt_pnl = _run_strategy_via_rebuild(
        "mean_reversion", filter_class_names, synthetic_data,
        timeframe="5m", market_symbol="NQ",
        hold_bars=24, stop_distance_atr=0.4,
        tmp_path=tmp_path,
        exit_type="signal_exit", signal_exit_reference="fast_sma",
    )
    assert rebuilt_pnl == pytest.approx(native_pnl, rel=1e-6, abs=0.01), (
        f"Long MR signal_exit rebuild mismatch: native=${native_pnl:,.2f} vs rebuilt=${rebuilt_pnl:,.2f}"
    )
