"""
Vectorized trade simulation for the strategy discovery engine.

Produces IDENTICAL trades to engine.run() but uses numpy 2D array
operations instead of a per-bar Python loop.  The expensive parts
(stop / target / trailing-stop checking across all trade windows)
are fully vectorized; only overlap prevention and capital tracking
are sequential — and those are O(n_trades), not O(n_bars).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _empty_result(initial_capital: float) -> dict:
    """Return the result dict for a run with zero trades."""
    return {
        "trades": [],
        "Total Trades": 0,
        "Net PnL": 0.0,
        "current_capital": initial_capital,
    }


def vectorized_backtest(
    signal_mask: np.ndarray,
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    atr: np.ndarray,
    timestamps: np.ndarray | pd.DatetimeIndex,
    hold_bars: int,
    stop_distance_atr: float,
    exit_type: str = "time_stop",
    direction: str = "long",
    initial_capital: float = 250_000.0,
    risk_per_trade: float = 0.01,
    commission_per_contract: float = 2.0,
    slippage_ticks: int = 4,
    tick_value: float = 12.50,
    dollars_per_point: float = 50.0,
    oos_split_date: str = "2019-01-01",
    # Exit-type-specific parameters
    profit_target_atr: float | None = None,
    trailing_stop_atr: float | None = None,
    signal_exit_sma: np.ndarray | None = None,
    early_exit_bars: int | None = None,
    break_even_atr: float | None = None,
    break_even_lock_atr: float = 0.0,
) -> dict:
    """Vectorized backtest — same interface as engine.run(), same results.

    Currently implements: time_stop + protective stop.
    Other exit types will be added incrementally.
    """
    raise NotImplementedError(
        "vectorized_backtest is a stub — implementation follows in Task 2"
    )
