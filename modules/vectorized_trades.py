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
    """Vectorized backtest — produces IDENTICAL trades to engine.run().

    All exit types supported: time_stop, profit_target, trailing_stop,
    signal_exit.  Optional modifiers: early_exit, break_even.
    """
    n_bars = len(close)
    is_long = direction == "long"
    slippage_pts = slippage_ticks * tick_value / dollars_per_point
    half_slip = slippage_pts / 2.0

    # Match engine's NaN handling: replace NaN ATR with 10.0
    atr_clean = np.where(np.isnan(atr), 10.0, atr)

    # ── All potential signal bars ──────────────────────────────
    signal_bars = np.flatnonzero(signal_mask)
    n_pot = len(signal_bars)
    if n_pot == 0:
        return _empty_result(initial_capital)

    # ── Entry prices & stop distances for every potential entry ─
    entry_atrs = atr_clean[signal_bars]
    stop_dists = stop_distance_atr * entry_atrs  # (n_pot,)

    if is_long:
        entry_prices = close[signal_bars] + half_slip
        stop_prices = entry_prices - stop_dists
    else:
        entry_prices = close[signal_bars] - half_slip
        stop_prices = entry_prices + stop_dists

    # ── 2-D price windows: (n_pot, hold_bars) ─────────────────
    offsets = np.arange(1, hold_bars + 1)                       # (hold_bars,)
    raw_idx = signal_bars[:, None] + offsets[None, :]           # (n_pot, hb)
    win_idx = np.clip(raw_idx, 0, n_bars - 1)
    in_bounds = raw_idx < n_bars                                # mask for valid data

    win_highs = high[win_idx]
    win_lows  = low[win_idx]
    win_closes = close[win_idx]

    # ── Break-even stop modifier ──────────────────────────────
    # Modifies the effective protective stop per bar in the window.
    # Must be computed BEFORE the protective-stop check.
    if break_even_atr is not None and break_even_atr > 0:
        # MFE at each bar in the window (cumulative from bar 1 onward,
        # starting from 0 — matching engine which inits mfe_points=0)
        if is_long:
            unrealised = win_highs - entry_prices[:, None]
        else:
            unrealised = entry_prices[:, None] - win_lows

        running_mfe = np.maximum(0.0, np.maximum.accumulate(unrealised, axis=1))

        be_threshold = break_even_atr * entry_atrs  # (n_pot,)
        be_triggered = running_mfe >= be_threshold[:, None]  # (n_pot, hb)
        any_be = be_triggered.any(axis=1)
        be_first_widx = np.argmax(be_triggered, axis=1)  # first True

        # Compute break-even stop level
        if is_long:
            be_stop_level = entry_prices + break_even_lock_atr * entry_atrs
        else:
            be_stop_level = entry_prices - break_even_lock_atr * entry_atrs

        # Build 2-D effective stop array
        bar_indices = np.arange(hold_bars)[None, :]
        be_active = any_be[:, None] & (bar_indices >= be_first_widx[:, None])

        stop_2d = np.broadcast_to(stop_prices[:, None],
                                  (n_pot, hold_bars)).copy()
        if is_long:
            be_new = np.maximum(stop_prices[:, None],
                                np.where(be_active, be_stop_level[:, None],
                                         stop_prices[:, None]))
            stop_2d = np.maximum(stop_2d, be_new)
        else:
            be_new = np.minimum(stop_prices[:, None],
                                np.where(be_active, be_stop_level[:, None],
                                         stop_prices[:, None]))
            stop_2d = np.minimum(stop_2d, be_new)

        # Protective-stop check with 2-D per-bar stop prices
        if is_long:
            prot_mask = (win_lows <= stop_2d) & in_bounds
        else:
            prot_mask = (win_highs >= stop_2d) & in_bounds

        any_prot = prot_mask.any(axis=1)
        prot_widx = np.where(any_prot, np.argmax(prot_mask, axis=1), hold_bars)

        # For stop exit price, use the stop level that was active on that bar
        prot_stop_exit_level = np.where(
            any_prot,
            stop_2d[np.arange(n_pot), np.clip(prot_widx, 0, hold_bars - 1)],
            stop_prices,
        )
    else:
        # ── Protective stop (constant stop price per trade) ───
        if is_long:
            prot_mask = (win_lows <= stop_prices[:, None]) & in_bounds
        else:
            prot_mask = (win_highs >= stop_prices[:, None]) & in_bounds

        any_prot = prot_mask.any(axis=1)
        prot_widx = np.where(any_prot, np.argmax(prot_mask, axis=1), hold_bars)
        prot_stop_exit_level = stop_prices

    prot_held = np.where(any_prot, prot_widx + 1, hold_bars + 1)

    # ── Initialise exit resolution: TIME / FINAL_BAR ──────────
    final_held = np.full(n_pot, hold_bars)
    final_reason = np.full(n_pot, "TIME", dtype="U20")
    final_use_close = np.ones(n_pot, dtype=bool)
    final_level = np.zeros(n_pot)

    # FINAL_BAR for trades that extend beyond data
    extends = (signal_bars + hold_bars) >= n_bars
    fb_held = np.maximum(0, n_bars - 1 - signal_bars)
    final_held = np.where(extends, fb_held, final_held)
    final_reason = np.where(extends, "FINAL_BAR", final_reason)

    # ── Early exit (lowest priority above TIME) ───────────────
    if early_exit_bars is not None:
        # Early exit fires on the FIRST bar where bars_held >= early_exit_bars
        # AND the trade is losing (unrealized PnL < 0).
        # The engine checks early exit on every bar after the threshold.
        early_base_widx = early_exit_bars - 1  # 0-indexed window offset

        if early_base_widx < hold_bars:
            if is_long:
                unreal_pnl = win_closes - entry_prices[:, None]
            else:
                unreal_pnl = entry_prices[:, None] - win_closes

            # Mask: eligible for early exit (bars_held >= early_exit_bars & losing)
            eligible = (offsets[None, :] >= early_exit_bars) & (unreal_pnl < 0) & in_bounds
            any_early = eligible.any(axis=1)
            early_widx = np.where(any_early, np.argmax(eligible, axis=1), hold_bars)
            early_held = np.where(any_early, early_widx + 1, hold_bars + 1)

            mask = any_early & (early_held <= final_held)
            final_held = np.where(mask, early_held, final_held)
            final_reason = np.where(mask, "EARLY_EXIT", final_reason)

    # ── Exit-type-specific exits (above EARLY_EXIT priority) ──

    if exit_type == "profit_target" and profit_target_atr is not None:
        if is_long:
            target_prices = entry_prices + profit_target_atr * entry_atrs
            pt_mask = (win_highs >= target_prices[:, None]) & in_bounds
        else:
            target_prices = entry_prices - profit_target_atr * entry_atrs
            pt_mask = (win_lows <= target_prices[:, None]) & in_bounds

        any_pt = pt_mask.any(axis=1)
        pt_widx = np.where(any_pt, np.argmax(pt_mask, axis=1), hold_bars)
        pt_held = np.where(any_pt, pt_widx + 1, hold_bars + 1)

        mask = any_pt & (pt_held <= final_held)
        final_held = np.where(mask, pt_held, final_held)
        final_reason = np.where(mask, "PROFIT_TARGET", final_reason)
        final_use_close = np.where(mask, False, final_use_close)
        final_level = np.where(mask, target_prices, final_level)

    elif exit_type == "trailing_stop" and trailing_stop_atr is not None:
        # Running high/low from the ENTRY bar onward
        # Entry bar's high/low used to initialise the tracker.
        entry_bar_high = high[signal_bars]  # (n_pot,)
        entry_bar_low = low[signal_bars]

        if is_long:
            # Prepend entry bar high, then window highs → cummax
            full_highs = np.concatenate(
                [entry_bar_high[:, None], win_highs], axis=1)  # (n_pot, 1+hb)
            running_high = np.maximum.accumulate(full_highs, axis=1)[:, 1:]  # drop entry col

            win_atrs = atr_clean[win_idx]
            raw_trail = running_high - trailing_stop_atr * win_atrs

            # Initial trailing stop = protective stop; ratchet upward
            trail_seq = np.empty((n_pot, hold_bars + 1))
            trail_seq[:, 0] = stop_prices
            trail_seq[:, 1:] = raw_trail
            trail_ratcheted = np.maximum.accumulate(trail_seq, axis=1)[:, 1:]

            trail_mask = (win_lows <= trail_ratcheted) & in_bounds
        else:
            full_lows = np.concatenate(
                [entry_bar_low[:, None], win_lows], axis=1)
            running_low = np.minimum.accumulate(full_lows, axis=1)[:, 1:]

            win_atrs = atr_clean[win_idx]
            raw_trail = running_low + trailing_stop_atr * win_atrs

            trail_seq = np.empty((n_pot, hold_bars + 1))
            trail_seq[:, 0] = stop_prices
            trail_seq[:, 1:] = raw_trail
            trail_ratcheted = np.minimum.accumulate(trail_seq, axis=1)[:, 1:]

            trail_mask = (win_highs >= trail_ratcheted) & in_bounds

        any_trail = trail_mask.any(axis=1)
        trail_widx = np.where(any_trail, np.argmax(trail_mask, axis=1), hold_bars)
        trail_held = np.where(any_trail, trail_widx + 1, hold_bars + 1)
        trail_exit_level = np.where(
            any_trail,
            trail_ratcheted[np.arange(n_pot), np.clip(trail_widx, 0, hold_bars - 1)],
            0.0,
        )

        mask = any_trail & (trail_held <= final_held)
        final_held = np.where(mask, trail_held, final_held)
        final_reason = np.where(mask, "TRAILING_STOP", final_reason)
        final_use_close = np.where(mask, False, final_use_close)
        final_level = np.where(mask, trail_exit_level, final_level)

    elif exit_type == "signal_exit" and signal_exit_sma is not None:
        win_sma = signal_exit_sma[win_idx]
        if is_long:
            sig_mask = (win_closes >= win_sma) & in_bounds
        else:
            sig_mask = (win_closes <= win_sma) & in_bounds

        any_sig = sig_mask.any(axis=1)
        sig_widx = np.where(any_sig, np.argmax(sig_mask, axis=1), hold_bars)
        sig_held = np.where(any_sig, sig_widx + 1, hold_bars + 1)

        mask = any_sig & (sig_held <= final_held)
        final_held = np.where(mask, sig_held, final_held)
        final_reason = np.where(mask, "SIGNAL_EXIT", final_reason)
        # signal exit uses close price — use_close stays True

    # ── Protective stop (highest priority — overrides everything) ─
    mask = any_prot & (prot_held <= final_held)
    final_held = np.where(mask, prot_held, final_held)
    final_reason = np.where(mask, "STOP", final_reason)
    final_use_close = np.where(mask, False, final_use_close)
    final_level = np.where(mask, prot_stop_exit_level, final_level)

    # ── Exit bars (absolute) ──────────────────────────────────
    exit_bars = np.clip(signal_bars + final_held, 0, n_bars - 1)

    # ── Overlap prevention (sequential, O(n_potential)) ───────
    valid_mask = np.zeros(n_pot, dtype=bool)
    next_allowed = 0
    for k in range(n_pot):
        if signal_bars[k] < next_allowed:
            continue
        if stop_dists[k] <= 0:
            continue
        valid_mask[k] = True
        next_allowed = int(exit_bars[k]) + 1

    vi = np.flatnonzero(valid_mask)
    n_trades = len(vi)
    if n_trades == 0:
        return _empty_result(initial_capital)

    # ── Slice to valid trades ─────────────────────────────────
    v_sig   = signal_bars[vi]
    v_entry = entry_prices[vi]
    v_held  = final_held[vi]
    v_exit_bar = exit_bars[vi]
    v_reason   = final_reason[vi]
    v_use_close = final_use_close[vi]
    v_level    = final_level[vi]
    v_stop_dist = stop_dists[vi]

    # ── Exit prices ───────────────────────────────────────────
    if is_long:
        close_exit = close[v_exit_bar] - half_slip
        level_exit = v_level - half_slip
    else:
        close_exit = close[v_exit_bar] + half_slip
        level_exit = v_level + half_slip

    v_exit_price = np.where(v_use_close, close_exit, level_exit)

    # ── Position sizing (vectorized — uses initial_capital) ───
    risk_amount = initial_capital * risk_per_trade
    contracts = np.maximum(
        1, np.floor(risk_amount / (v_stop_dist * dollars_per_point)).astype(int)
    )

    # ── PnL (vectorized) ─────────────────────────────────────
    if is_long:
        pnl_per_point = v_exit_price - v_entry
    else:
        pnl_per_point = v_entry - v_exit_price

    gross_pnl = pnl_per_point * dollars_per_point * contracts
    commission = 2.0 * commission_per_contract * contracts
    net_pnl = gross_pnl - commission

    # ── Build trade list ──────────────────────────────────────
    ts = pd.DatetimeIndex(timestamps) if not isinstance(timestamps, pd.DatetimeIndex) else timestamps
    dir_upper = direction.upper()

    trades: list[dict] = []
    for i in range(n_trades):
        trades.append({
            "entry_time": ts[v_sig[i]],
            "entry_price": float(v_entry[i]),
            "exit_time": ts[v_exit_bar[i]],
            "exit_price": float(v_exit_price[i]),
            "exit_reason": str(v_reason[i]),
            "pnl": float(net_pnl[i]),
            "bars_held": int(v_held[i]),
            "direction": dir_upper,
            "contracts": int(contracts[i]),
        })

    total_pnl = float(np.sum(net_pnl))
    return {
        "trades": trades,
        "Total Trades": n_trades,
        "Net PnL": total_pnl,
        "current_capital": initial_capital + total_pnl,
    }
