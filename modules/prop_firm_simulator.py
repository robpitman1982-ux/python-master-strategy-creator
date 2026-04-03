"""
Prop Firm Challenge Simulator
Simulates strategy trade lists against prop firm evaluation rules.

Supported firms:
    - The5ers Bootcamp ($20K / $100K / $250K)
    - The5ers High Stakes ($2.5K–$100K)
    - The5ers Hyper Growth ($5K–$20K)
    - The5ers Pro Growth ($5K–$10K)
    - Generic (any prop firm via PropFirmConfig)

Usage:
    from modules.prop_firm_simulator import (
        The5ersBootcampConfig,
        simulate_challenge,
        monte_carlo_pass_rate,
        rank_strategies_for_prop,
    )

    # Single strategy simulation
    result = simulate_challenge(trades, config=The5ersBootcampConfig())

    # Monte Carlo pass rate estimation
    stats = monte_carlo_pass_rate(trades, config=The5ersBootcampConfig(), n_sims=10000)

    # Score and rank multiple strategies
    rankings = rank_strategies_for_prop(strategy_trade_lists)
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

import numpy as np


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class PropFirmConfig:
    """Generic prop firm challenge configuration."""
    firm_name: str = "Generic"
    program_name: str = "Challenge"

    # --- Challenge structure ---
    n_steps: int = 1
    step_balances: list[float] = field(default_factory=lambda: [100_000.0])
    # Actual dollar balance at each step (NOT fractions)

    target_balance: float = 250_000.0  # Final funded account size

    # --- Per-step rules (can differ per step in advanced configs) ---
    profit_target_pct: float = 0.06         # 6% profit target per step
    max_drawdown_pct: float = 0.05          # 5% max drawdown (static)
    max_daily_drawdown_pct: float | None = None  # None = no daily DD limit
    drawdown_type: str = "static"           # "static" or "trailing"

    # --- Risk rules ---
    max_risk_per_trade_pct: float = 0.02    # 2% max SL risk per trade
    mandatory_stop_loss: bool = True
    max_violations: int = 5
    min_profitable_days: int | None = None  # None = no minimum

    # --- Time rules ---
    max_calendar_days: int | None = None    # None = unlimited
    max_inactivity_days: int = 30

    # --- Funded stage ---
    funded_profit_target_pct: float = 0.05
    funded_max_drawdown_pct: float = 0.04
    funded_daily_pause_pct: float = 0.03
    profit_split_start_pct: float = 0.50
    profit_split_max_pct: float = 1.00

    # --- Leverage ---
    leverage: float = 30.0

    # --- Cost ---
    entry_fee: float = 225.0
    funded_fee: float = 350.0

    # --- Per-step profit targets (overrides profit_target_pct per step) ---
    step_profit_targets: list[float] | None = None
    # If None, use profit_target_pct for all steps (backward compatible)
    # If set, use per-step targets: e.g. [0.08, 0.05] for High Stakes

    # --- Daily DD behaviour ---
    daily_dd_is_pause: bool = False       # True = skip rest of day, False = terminate step
    daily_dd_recalculates: bool = False   # True = recalc daily limit from day-start equity

    # --- Instrument settings (for PnL scaling) ---
    dollars_per_point: float = 50.0  # ES = $50/pt
    contracts_per_trade: int = 1


def The5ersBootcampConfig(target: float = 250_000.0) -> PropFirmConfig:
    """
    Factory for The5ers Bootcamp configuration.

    Supports $20K, $100K, and $250K tracks.
    Step balances scale proportionally with target.

    $250K track: $100K -> $150K -> $200K -> $250K funded
    $100K track: $40K -> $60K -> $80K -> $100K funded
    $20K track:  $8K -> $12K -> $16K -> $20K funded
    """
    # Step balances are 40%, 60%, 80% of target
    return PropFirmConfig(
        firm_name="The5ers",
        program_name="Bootcamp",
        n_steps=3,
        step_balances=[
            target * 0.40,  # Step 1: $100K for $250K track
            target * 0.60,  # Step 2: $150K for $250K track
            target * 0.80,  # Step 3: $200K for $250K track
        ],
        target_balance=target,
        profit_target_pct=0.06,
        max_drawdown_pct=0.05,
        drawdown_type="static",
        max_daily_drawdown_pct=None,  # No daily DD during evaluation
        max_risk_per_trade_pct=0.02,
        mandatory_stop_loss=True,
        max_violations=5,
        min_profitable_days=None,  # No minimum for Bootcamp
        max_calendar_days=None,
        max_inactivity_days=30,
        funded_profit_target_pct=0.05,
        funded_max_drawdown_pct=0.04,
        funded_daily_pause_pct=0.03,
        profit_split_start_pct=0.50,
        profit_split_max_pct=1.00,
        leverage=30.0,
        entry_fee=225.0 if target == 250_000 else 95.0 if target == 100_000 else 45.0,
        funded_fee=350.0 if target == 250_000 else 205.0 if target == 100_000 else 55.0,
        dollars_per_point=50.0,
        contracts_per_trade=1,
    )


def The5ersHighStakesConfig(target: float = 100_000.0) -> PropFirmConfig:
    """
    Factory for The5ers High Stakes (NEW program).

    $100K track: $100K Step 1 -> $100K Step 2 -> $100K Funded
    Also available: $2.5K, $5K, $10K, $25K, $50K tracks.
    Rules:
    - Step 1: 8% profit target, 10% max loss, 5% daily loss, 3 min profitable days
    - Step 2: 5% profit target, 10% max loss, 5% daily loss, 3 min profitable days
    - Funded: 80-100% profit split, refund of entry fee
    """
    return PropFirmConfig(
        firm_name="The5ers",
        program_name="HighStakes",
        n_steps=2,
        step_balances=[target, target],  # Same balance both steps
        target_balance=target,
        profit_target_pct=0.08,  # Default (Step 1), overridden by step_profit_targets
        step_profit_targets=[0.08, 0.05],  # Step 1 = 8%, Step 2 = 5%
        max_drawdown_pct=0.10,   # 10% max loss
        drawdown_type="static",
        max_daily_drawdown_pct=0.05,  # 5% daily loss limit
        max_risk_per_trade_pct=0.02,
        mandatory_stop_loss=True,
        max_violations=5,
        min_profitable_days=3,
        max_calendar_days=None,  # Unlimited
        max_inactivity_days=30,
        funded_profit_target_pct=0.10,
        funded_max_drawdown_pct=0.10,
        funded_daily_pause_pct=0.05,
        profit_split_start_pct=0.80,
        profit_split_max_pct=1.00,
        leverage=30.0,
        entry_fee=545.0 if target == 100_000 else 0.0,
        funded_fee=0.0,  # Refund
        dollars_per_point=50.0,
        contracts_per_trade=1,
    )


def The5ersHyperGrowthConfig(target: float = 5_000.0) -> PropFirmConfig:
    """
    Factory for The5ers Hyper Growth program.

    1 step, $5K/$10K/$20K accounts.
    10% profit target, 6% stop out, 3% daily pause.
    Unlimited time, up to 100% profit split.
    """
    fee_map = {5_000: 260.0, 10_000: 520.0, 20_000: 960.0}
    return PropFirmConfig(
        firm_name="The5ers",
        program_name="HyperGrowth",
        n_steps=1,
        step_balances=[target],
        target_balance=target,
        profit_target_pct=0.10,     # 10% target
        max_drawdown_pct=0.06,      # 6% stop out
        drawdown_type="static",
        max_daily_drawdown_pct=0.03, # 3% daily pause
        max_risk_per_trade_pct=0.02,
        mandatory_stop_loss=False,
        max_violations=5,
        min_profitable_days=None,
        max_calendar_days=None,
        max_inactivity_days=30,
        funded_profit_target_pct=0.10,
        funded_max_drawdown_pct=0.06,
        funded_daily_pause_pct=0.03,
        profit_split_start_pct=0.50,
        profit_split_max_pct=1.00,
        leverage=30.0,
        entry_fee=fee_map.get(target, 260.0),
        funded_fee=0.0,
        dollars_per_point=50.0,
        contracts_per_trade=1,
    )


def The5ersProGrowthConfig(target: float = 5_000.0) -> PropFirmConfig:
    """
    Factory for The5ers Pro Growth program.

    Same rules as Hyper Growth but lower entry fee.
    1 step, $5K/$10K accounts.
    10% profit target, 6% stop out, 3% daily pause.
    """
    return PropFirmConfig(
        firm_name="The5ers",
        program_name="ProGrowth",
        n_steps=1,
        step_balances=[target],
        target_balance=target,
        profit_target_pct=0.10,
        max_drawdown_pct=0.06,
        drawdown_type="static",
        max_daily_drawdown_pct=0.03,
        max_risk_per_trade_pct=0.02,
        mandatory_stop_loss=False,
        max_violations=5,
        min_profitable_days=None,
        max_calendar_days=None,
        max_inactivity_days=30,
        funded_profit_target_pct=0.10,
        funded_max_drawdown_pct=0.06,
        funded_daily_pause_pct=0.03,
        profit_split_start_pct=0.50,
        profit_split_max_pct=1.00,
        leverage=30.0,
        entry_fee=74.0 if target == 5_000 else 150.0,
        funded_fee=0.0,
        dollars_per_point=50.0,
        contracts_per_trade=1,
    )


# =============================================================================
# SIMULATION RESULTS
# =============================================================================

@dataclass
class StepResult:
    """Result of a single challenge step."""
    step_number: int
    starting_balance: float
    ending_balance: float
    profit_target: float
    max_drawdown_limit: float
    peak_balance: float
    trough_balance: float
    max_drawdown_dollars: float
    max_drawdown_pct: float
    trades_taken: int
    passed: bool
    failure_reason: str | None = None
    equity_curve: list[float] = field(default_factory=list)
    target_hit_trade_idx: int | None = None
    daily_dd_breach: bool = False


@dataclass
class ChallengeResult:
    """Result of a full multi-step challenge simulation."""
    config: PropFirmConfig
    passed_all_steps: bool
    steps: list[StepResult]
    total_trades_used: int
    worst_drawdown_pct: float
    avg_trades_per_step: float
    trades_consumed: int
    trades_available: int
    daily_dd_breaches: int = 0


# =============================================================================
# CORE SIMULATOR
# =============================================================================

def _scale_trade_pnl(
    trade_pnl: float,
    source_capital: float,
    step_balance: float,
) -> float:
    """
    Scale a trade's PnL from backtest context to challenge step context.

    Preserves the strategy's return profile by converting to percentage
    of source capital, then applying to step balance.
    """
    if source_capital <= 0:
        return 0.0
    trade_return_pct = trade_pnl / source_capital
    return trade_return_pct * step_balance


def simulate_single_step(
    trade_pnls: list[float],
    step_number: int,
    step_balance: float,
    config: PropFirmConfig,
    source_capital: float = 250_000.0,
    step_profit_target_pct: float | None = None,
    trades_per_day: float = 1.0,
) -> StepResult:
    """
    Simulate one step of a prop firm challenge.

    Args:
        trade_pnls: List of trade PnL values (dollars, from backtest)
        step_number: Which step (1, 2, 3)
        step_balance: Starting balance for this step
        config: Prop firm rules
        source_capital: Capital used in the backtest (for scaling)
        step_profit_target_pct: Override profit target for this step.
            If None, uses config.profit_target_pct.
        trades_per_day: Approximate trades per trading day, used for
            daily drawdown grouping. Default 1.0 (daily strategies).

    Returns:
        StepResult with pass/fail and equity curve
    """
    effective_target_pct = step_profit_target_pct if step_profit_target_pct is not None else config.profit_target_pct
    profit_target_dollars = step_balance * effective_target_pct
    target_balance = step_balance + profit_target_dollars
    drawdown_floor = step_balance * (1.0 - config.max_drawdown_pct)

    # Daily DD tracking
    daily_dd_limit = None
    if config.max_daily_drawdown_pct is not None:
        daily_dd_limit = step_balance * config.max_daily_drawdown_pct
    trades_per_day_group = max(1, math.ceil(trades_per_day))
    daily_pnl_accumulator = 0.0

    balance = step_balance
    peak = step_balance
    trough = step_balance
    max_dd_dollars = 0.0
    equity_curve = [balance]
    target_hit_idx = None

    for i, raw_pnl in enumerate(trade_pnls):
        scaled_pnl = _scale_trade_pnl(raw_pnl, source_capital, step_balance)
        balance += scaled_pnl
        equity_curve.append(balance)

        if balance > peak:
            peak = balance
        if balance < trough:
            trough = balance

        dd_from_peak = peak - balance
        if dd_from_peak > max_dd_dollars:
            max_dd_dollars = dd_from_peak

        # Daily drawdown check
        if daily_dd_limit is not None:
            daily_pnl_accumulator += scaled_pnl
            # Check if daily loss exceeds limit (negative PnL)
            if daily_pnl_accumulator <= -daily_dd_limit:
                return StepResult(
                    step_number=step_number,
                    starting_balance=step_balance,
                    ending_balance=balance,
                    profit_target=profit_target_dollars,
                    max_drawdown_limit=drawdown_floor,
                    peak_balance=peak,
                    trough_balance=trough,
                    max_drawdown_dollars=max_dd_dollars,
                    max_drawdown_pct=max_dd_dollars / step_balance if step_balance > 0 else 0,
                    trades_taken=i + 1,
                    passed=False,
                    failure_reason=f"Daily DD breach: ${daily_pnl_accumulator:,.0f} exceeds -{config.max_daily_drawdown_pct*100:.0f}% (${daily_dd_limit:,.0f})",
                    equity_curve=equity_curve,
                    target_hit_trade_idx=None,
                    daily_dd_breach=True,
                )
            # Reset accumulator at day boundary
            if (i + 1) % trades_per_day_group == 0:
                daily_pnl_accumulator = 0.0

        # Check drawdown breach
        if config.drawdown_type == "static":
            if balance <= drawdown_floor:
                return StepResult(
                    step_number=step_number,
                    starting_balance=step_balance,
                    ending_balance=balance,
                    profit_target=profit_target_dollars,
                    max_drawdown_limit=drawdown_floor,
                    peak_balance=peak,
                    trough_balance=trough,
                    max_drawdown_dollars=max_dd_dollars,
                    max_drawdown_pct=max_dd_dollars / step_balance if step_balance > 0 else 0,
                    trades_taken=i + 1,
                    passed=False,
                    failure_reason=f"Drawdown breach: balance ${balance:,.0f} <= floor ${drawdown_floor:,.0f}",
                    equity_curve=equity_curve,
                    target_hit_trade_idx=None,
                )
        elif config.drawdown_type == "trailing":
            trailing_floor = peak * (1.0 - config.max_drawdown_pct)
            if balance <= trailing_floor:
                return StepResult(
                    step_number=step_number,
                    starting_balance=step_balance,
                    ending_balance=balance,
                    profit_target=profit_target_dollars,
                    max_drawdown_limit=trailing_floor,
                    peak_balance=peak,
                    trough_balance=trough,
                    max_drawdown_dollars=max_dd_dollars,
                    max_drawdown_pct=max_dd_dollars / step_balance if step_balance > 0 else 0,
                    trades_taken=i + 1,
                    passed=False,
                    failure_reason=f"Trailing DD breach: balance ${balance:,.0f} <= floor ${trailing_floor:,.0f}",
                    equity_curve=equity_curve,
                    target_hit_trade_idx=None,
                )

        # Check profit target
        if balance >= target_balance:
            target_hit_idx = i
            return StepResult(
                step_number=step_number,
                starting_balance=step_balance,
                ending_balance=balance,
                profit_target=profit_target_dollars,
                max_drawdown_limit=drawdown_floor,
                peak_balance=peak,
                trough_balance=trough,
                max_drawdown_dollars=max_dd_dollars,
                max_drawdown_pct=max_dd_dollars / step_balance if step_balance > 0 else 0,
                trades_taken=i + 1,
                passed=True,
                failure_reason=None,
                equity_curve=equity_curve,
                target_hit_trade_idx=target_hit_idx,
            )

    # Ran out of trades
    return StepResult(
        step_number=step_number,
        starting_balance=step_balance,
        ending_balance=balance,
        profit_target=profit_target_dollars,
        max_drawdown_limit=drawdown_floor,
        peak_balance=peak,
        trough_balance=trough,
        max_drawdown_dollars=max_dd_dollars,
        max_drawdown_pct=max_dd_dollars / step_balance if step_balance > 0 else 0,
        trades_taken=len(trade_pnls),
        passed=False,
        failure_reason=f"Ran out of trades ({len(trade_pnls)}) without hitting +{effective_target_pct*100:.0f}% target",
        equity_curve=equity_curve,
        target_hit_trade_idx=None,
    )


def simulate_challenge(
    trade_pnls: list[float],
    config: PropFirmConfig | None = None,
    source_capital: float = 250_000.0,
    trades_per_day: float = 1.0,
) -> ChallengeResult:
    """
    Simulate a full multi-step prop firm challenge.

    Trades are consumed sequentially across steps. If step 1 uses 15 trades
    to hit target, step 2 starts from trade 16 with a fresh balance.
    """
    if config is None:
        config = The5ersBootcampConfig()

    steps: list[StepResult] = []
    trade_cursor = 0
    all_passed = True

    for step_idx in range(config.n_steps):
        step_number = step_idx + 1
        step_balance = config.step_balances[step_idx]

        # Use per-step target if available, else fall back to config default
        if config.step_profit_targets and step_idx < len(config.step_profit_targets):
            step_target_pct = config.step_profit_targets[step_idx]
        else:
            step_target_pct = config.profit_target_pct

        remaining_trades = trade_pnls[trade_cursor:]

        if not remaining_trades:
            steps.append(StepResult(
                step_number=step_number,
                starting_balance=step_balance,
                ending_balance=step_balance,
                profit_target=step_balance * step_target_pct,
                max_drawdown_limit=step_balance * (1 - config.max_drawdown_pct),
                peak_balance=step_balance,
                trough_balance=step_balance,
                max_drawdown_dollars=0,
                max_drawdown_pct=0,
                trades_taken=0,
                passed=False,
                failure_reason="No trades remaining",
            ))
            all_passed = False
            break

        step_result = simulate_single_step(
            trade_pnls=remaining_trades,
            step_number=step_number,
            step_balance=step_balance,
            config=config,
            source_capital=source_capital,
            step_profit_target_pct=step_target_pct,
            trades_per_day=trades_per_day,
        )
        steps.append(step_result)
        trade_cursor += step_result.trades_taken

        if not step_result.passed:
            all_passed = False
            break

    total_trades = sum(s.trades_taken for s in steps)
    worst_dd = max(s.max_drawdown_pct for s in steps) if steps else 0.0
    avg_trades = total_trades / len(steps) if steps else 0.0
    dd_breaches = sum(1 for s in steps if s.daily_dd_breach)

    return ChallengeResult(
        config=config,
        passed_all_steps=all_passed,
        steps=steps,
        total_trades_used=total_trades,
        worst_drawdown_pct=worst_dd,
        avg_trades_per_step=avg_trades,
        trades_consumed=trade_cursor,
        trades_available=len(trade_pnls),
        daily_dd_breaches=dd_breaches,
    )


# =============================================================================
# VECTORIZED BATCH CHALLENGE SIMULATOR
# =============================================================================


def simulate_challenge_batch(
    trade_matrix: np.ndarray,
    config: PropFirmConfig,
    source_capital: float = 250_000.0,
    trades_per_day: float = 1.0,
) -> dict:
    """Vectorized multi-step prop firm challenge for N simulations at once.

    Args:
        trade_matrix: (n_sims, n_trades) — pre-generated trade PnL sequences.
        config: Prop firm challenge configuration.
        source_capital: Capital used in backtest (for scaling).
        trades_per_day: Approximate trades per day (for daily DD grouping).

    Returns dict with:
      - pass_rate, per-step pass rates
      - DD percentiles (median, p95, p99)
      - trades_to_pass stats (median, p75)
      - risk metrics (rolling 20 DD, max losing streak, max recovery)
    """
    n_sims, n_trades = trade_matrix.shape
    n_steps = config.n_steps

    # Track which sims are still alive and where they are in the trade sequence
    alive = np.ones(n_sims, dtype=bool)
    trade_cursor = np.zeros(n_sims, dtype=int)
    step_pass_counts = np.zeros(n_steps, dtype=int)
    all_passed = np.ones(n_sims, dtype=bool)
    total_trades_used = np.zeros(n_sims, dtype=int)
    worst_dd_pct = np.zeros(n_sims)

    for step_idx in range(n_steps):
        step_balance = config.step_balances[step_idx]

        if config.step_profit_targets and step_idx < len(config.step_profit_targets):
            step_target_pct = config.step_profit_targets[step_idx]
        else:
            step_target_pct = config.profit_target_pct

        target_balance = step_balance * (1.0 + step_target_pct)
        scale_factor = step_balance / source_capital if source_capital > 0 else 0.0

        # For sims not alive, skip
        active = alive.copy()
        if not active.any():
            break

        # Get remaining trades for each sim from their cursor position
        # We need to handle variable start positions efficiently
        # Build a sub-matrix of remaining trades for active sims
        max_remaining = n_trades - int(trade_cursor[active].min()) if active.any() else 0
        if max_remaining <= 0:
            all_passed[active] = False
            alive[active] = False
            continue

        # Extract trades for active sims, pad with zeros where sim has fewer remaining
        active_indices = np.where(active)[0]
        n_active = len(active_indices)

        # Build scaled trade sub-matrix
        step_trades = np.zeros((n_active, max_remaining))
        for ai, sim_idx in enumerate(active_indices):
            cursor = int(trade_cursor[sim_idx])
            remaining = n_trades - cursor
            if remaining > 0:
                step_trades[ai, :remaining] = trade_matrix[sim_idx, cursor:cursor + remaining] * scale_factor

        # Cumulative equity: (n_active, max_remaining)
        equity = step_balance + np.cumsum(step_trades, axis=1)

        # Running peak for trailing DD
        peaks = np.maximum.accumulate(equity, axis=1)
        # Ensure peak starts at step_balance
        peaks = np.maximum(peaks, step_balance)

        # DD breach check
        if config.drawdown_type == "static":
            floor = step_balance * (1.0 - config.max_drawdown_pct)
            dd_breach = equity <= floor
        else:  # trailing
            floors = peaks * (1.0 - config.max_drawdown_pct)
            dd_breach = equity <= floors

        # Profit target hit
        target_hit = equity >= target_balance

        # Daily DD check
        daily_dd_breach_arr = np.zeros((n_active, max_remaining), dtype=bool)
        if config.max_daily_drawdown_pct is not None:
            daily_dd_limit = step_balance * config.max_daily_drawdown_pct
            trades_per_day_group = max(1, int(np.ceil(trades_per_day)))
            # Reshape into day groups and check daily PnL
            n_full_days = max_remaining // trades_per_day_group
            if n_full_days > 0:
                trunc_len = n_full_days * trades_per_day_group
                daily_shaped = step_trades[:, :trunc_len].reshape(n_active, n_full_days, trades_per_day_group)
                daily_pnl = daily_shaped.sum(axis=2)  # (n_active, n_full_days)
                # Cumulative within-day PnL for partial-day detection
                daily_cum = np.cumsum(daily_shaped, axis=2)  # (n_active, n_full_days, tpd)
                # Check if any within-day cumulative PnL breaches daily limit
                day_breach = (daily_cum <= -daily_dd_limit).any(axis=2)  # (n_active, n_full_days)
                # Expand back to trade-level
                for d in range(n_full_days):
                    if day_breach[:, d].any():
                        start_t = d * trades_per_day_group
                        # Find first breach trade within the day
                        for t in range(trades_per_day_group):
                            idx = start_t + t
                            breached_sims = daily_cum[:, d, t] <= -daily_dd_limit
                            daily_dd_breach_arr[:, idx] |= breached_sims

        # Combined breach: DD breach OR daily DD breach
        any_breach = dd_breach | daily_dd_breach_arr

        # For each sim: find first breach and first target hit
        # argmax on bool returns first True; returns 0 if no True
        breach_exists = any_breach.any(axis=1)
        breach_idx = np.argmax(any_breach, axis=1)
        target_exists = target_hit.any(axis=1)
        target_idx = np.argmax(target_hit, axis=1)

        # Step passes if target hit before breach (or no breach)
        passed = target_exists & (~breach_exists | (target_idx < breach_idx))

        # Compute trades used for this step
        step_trades_used = np.where(
            passed, target_idx + 1,
            np.where(breach_exists, breach_idx + 1, max_remaining)
        )

        # Compute max DD pct for this step
        dd_from_peak = (peaks - equity)
        max_dd_dollars = dd_from_peak.max(axis=1)
        step_dd_pct = max_dd_dollars / step_balance if step_balance > 0 else np.zeros(n_active)

        # Update globals
        for ai, sim_idx in enumerate(active_indices):
            total_trades_used[sim_idx] += int(step_trades_used[ai])
            trade_cursor[sim_idx] += int(step_trades_used[ai])
            worst_dd_pct[sim_idx] = max(worst_dd_pct[sim_idx], float(step_dd_pct[ai]))
            if passed[ai]:
                step_pass_counts[step_idx] += 1
            else:
                all_passed[sim_idx] = False
                alive[sim_idx] = False

    # Aggregate results
    pass_count = int(all_passed.sum())
    step_pass_rates = [int(c) / n_sims for c in step_pass_counts]

    # Trades-to-pass for passing sims
    passing_mask = all_passed
    trades_to_pass = total_trades_used[passing_mask]

    # Risk metrics on the full trade matrix (using raw trades scaled to first step)
    first_step_scale = config.step_balances[0] / source_capital if source_capital > 0 else 1.0
    scaled_all = trade_matrix * first_step_scale

    # Worst rolling 20-trade DD
    rolling_20_worst = np.zeros(n_sims)
    if n_trades >= 20:
        kernel = np.ones(20)
        for sim in range(n_sims):
            rolling_sum = np.convolve(scaled_all[sim], kernel, mode='valid')
            rolling_20_worst[sim] = float(rolling_sum.min())
    else:
        rolling_20_worst = scaled_all.sum(axis=1)

    # Max losing streak (vectorized per-sim)
    signs = (scaled_all < 0).astype(np.int8)
    max_streaks = np.zeros(n_sims, dtype=int)
    for sim in range(n_sims):
        s = signs[sim]
        if s.any():
            # Diff trick: find runs of 1s
            d = np.diff(np.concatenate([[0], s, [0]]))
            starts = np.where(d == 1)[0]
            ends = np.where(d == -1)[0]
            if len(starts) > 0 and len(ends) > 0:
                max_streaks[sim] = int((ends - starts).max())

    # Max recovery trades
    equity_full = np.cumsum(scaled_all, axis=1)
    peaks_full = np.maximum.accumulate(equity_full, axis=1)
    in_dd = equity_full < peaks_full
    max_recovery = np.zeros(n_sims, dtype=int)
    for sim in range(n_sims):
        dd_mask = in_dd[sim]
        if dd_mask.any():
            d = np.diff(np.concatenate([[False], dd_mask, [False]]).astype(int))
            starts = np.where(d == 1)[0]
            ends = np.where(d == -1)[0]
            if len(starts) > 0 and len(ends) > 0:
                max_recovery[sim] = int((ends - starts).max())

    # Build result dict
    mc_result: dict = {
        "pass_rate": pass_count / n_sims,
        "final_pass_rate": step_pass_rates[-1] if step_pass_rates else 0.0,
    }
    for si, rate in enumerate(step_pass_rates):
        mc_result[f"step{si + 1}_pass_rate"] = rate

    mc_result.update({
        "median_worst_dd_pct": float(np.median(worst_dd_pct)),
        "p95_worst_dd_pct": float(np.percentile(worst_dd_pct, 95)),
        "p99_worst_dd_pct": float(np.percentile(worst_dd_pct, 99)),
        "avg_trades_to_pass": float(np.mean(trades_to_pass)) if len(trades_to_pass) > 0 else 0.0,
        "median_trades_to_pass": float(np.median(trades_to_pass)) if len(trades_to_pass) > 0 else 0.0,
        "p75_trades_to_pass": float(np.percentile(trades_to_pass, 75)) if len(trades_to_pass) > 0 else 0.0,
        "step_median_trades": [],  # populated per-step below
        "worst_rolling_20_p95": float(np.percentile(rolling_20_worst, 95)),
        "max_losing_streak_p95": int(np.percentile(max_streaks, 95)),
        "max_recovery_trades_p95": int(np.percentile(max_recovery, 95)),
    })

    return mc_result


# =============================================================================
# MONTE CARLO PASS RATE
# =============================================================================

@dataclass
class MonteCarloStats:
    """Statistics from Monte Carlo challenge simulations."""
    n_simulations: int
    pass_count: int
    pass_rate: float
    avg_trades_to_pass: float
    median_trades_to_pass: float
    avg_worst_dd_pct: float
    p5_worst_dd_pct: float
    p50_worst_dd_pct: float
    p95_worst_dd_pct: float
    failure_reasons: dict[str, int]
    step_pass_rates: list[float]
    blowup_count: int
    insufficient_trades_count: int


def monte_carlo_pass_rate(
    trade_pnls: list[float],
    config: PropFirmConfig | None = None,
    source_capital: float = 250_000.0,
    n_sims: int = 10_000,
    seed: int | None = 42,
) -> MonteCarloStats:
    """
    Estimate challenge pass probability by shuffling trade order.

    Answers: "If this strategy's trades arrived in random order,
    how often would we pass the challenge?"
    """
    if config is None:
        config = The5ersBootcampConfig()

    rng = random.Random(seed)
    trades = list(trade_pnls)

    pass_count = 0
    trades_to_pass: list[int] = []
    worst_dds: list[float] = []
    failure_reasons: dict[str, int] = {}
    blowup_count = 0
    insufficient_count = 0
    step_pass_counts = [0] * config.n_steps

    for _ in range(n_sims):
        shuffled = trades.copy()
        rng.shuffle(shuffled)

        result = simulate_challenge(shuffled, config, source_capital)
        worst_dds.append(result.worst_drawdown_pct)

        for step in result.steps:
            if step.passed:
                step_pass_counts[step.step_number - 1] += 1

        if result.passed_all_steps:
            pass_count += 1
            trades_to_pass.append(result.total_trades_used)
        else:
            last_step = result.steps[-1] if result.steps else None
            reason = last_step.failure_reason if last_step else "Unknown"
            if reason and "Ran out of trades" in reason:
                insufficient_count += 1
                key = "Insufficient trades"
            elif reason and ("Drawdown breach" in reason or "Trailing DD" in reason):
                blowup_count += 1
                key = f"DD breach step {last_step.step_number}"
            else:
                key = reason or "Unknown"
            failure_reasons[key] = failure_reasons.get(key, 0) + 1

    worst_dd_arr = np.array(worst_dds)
    trades_arr = np.array(trades_to_pass) if trades_to_pass else np.array([0])

    step_pass_rates = [c / n_sims for c in step_pass_counts]

    return MonteCarloStats(
        n_simulations=n_sims,
        pass_count=pass_count,
        pass_rate=pass_count / n_sims,
        avg_trades_to_pass=float(np.mean(trades_arr)) if trades_to_pass else 0.0,
        median_trades_to_pass=float(np.median(trades_arr)) if trades_to_pass else 0.0,
        avg_worst_dd_pct=float(np.mean(worst_dd_arr)),
        p5_worst_dd_pct=float(np.percentile(worst_dd_arr, 5)),
        p50_worst_dd_pct=float(np.percentile(worst_dd_arr, 50)),
        p95_worst_dd_pct=float(np.percentile(worst_dd_arr, 95)),
        failure_reasons=failure_reasons,
        step_pass_rates=step_pass_rates,
        blowup_count=blowup_count,
        insufficient_trades_count=insufficient_count,
    )


# =============================================================================
# STRATEGY RANKING
# =============================================================================

@dataclass
class PropFirmScore:
    """Prop firm suitability score for a single strategy."""
    strategy_name: str
    pass_rate: float
    avg_trades_to_pass: float
    median_worst_dd_pct: float
    p95_worst_dd_pct: float
    challenge_score: float
    chrono_passed: bool
    chrono_trades_used: int
    chrono_worst_dd_pct: float


def compute_challenge_score(mc_stats: MonteCarloStats) -> float:
    """
    Composite "challenge score" from Monte Carlo results.

    Weights:
    - Pass rate: 0.50 (if you can't pass, nothing else matters)
    - Low drawdown: 0.25 (survival margin)
    - Speed: 0.15 (fewer trades to pass = faster completion)
    - Step consistency: 0.10 (all steps should pass evenly)

    Returns: float between 0.0 and 1.0
    """
    pass_component = mc_stats.pass_rate

    dd_score = max(0.0, 1.0 - (mc_stats.p95_worst_dd_pct / 0.05))
    dd_component = dd_score

    if mc_stats.avg_trades_to_pass > 0:
        speed_score = max(0.0, 1.0 - (mc_stats.avg_trades_to_pass - 10) / 190)
    else:
        speed_score = 0.0
    speed_component = speed_score

    if mc_stats.step_pass_rates:
        step_std = float(np.std(mc_stats.step_pass_rates))
        consistency_component = max(0.0, 1.0 - step_std * 5)
    else:
        consistency_component = 0.0

    score = (
        0.50 * pass_component
        + 0.25 * dd_component
        + 0.15 * speed_component
        + 0.10 * consistency_component
    )
    return round(min(1.0, max(0.0, score)), 4)


def rank_strategies_for_prop(
    strategy_trade_lists: dict[str, list[float]],
    config: PropFirmConfig | None = None,
    source_capital: float = 250_000.0,
    n_sims: int = 10_000,
    seed: int | None = 42,
) -> list[PropFirmScore]:
    """Score and rank multiple strategies for prop firm suitability."""
    if config is None:
        config = The5ersBootcampConfig()

    scores: list[PropFirmScore] = []

    for name, trades in strategy_trade_lists.items():
        chrono = simulate_challenge(trades, config, source_capital)
        mc = monte_carlo_pass_rate(trades, config, source_capital, n_sims, seed)
        challenge_score = compute_challenge_score(mc)

        scores.append(PropFirmScore(
            strategy_name=name,
            pass_rate=mc.pass_rate,
            avg_trades_to_pass=mc.avg_trades_to_pass,
            median_worst_dd_pct=mc.p50_worst_dd_pct,
            p95_worst_dd_pct=mc.p95_worst_dd_pct,
            challenge_score=challenge_score,
            chrono_passed=chrono.passed_all_steps,
            chrono_trades_used=chrono.total_trades_used,
            chrono_worst_dd_pct=chrono.worst_drawdown_pct,
        ))

    scores.sort(key=lambda s: s.challenge_score, reverse=True)
    return scores


# =============================================================================
# PRETTY PRINTING
# =============================================================================

def print_challenge_result(result: ChallengeResult) -> None:
    """Print human-readable challenge simulation result."""
    cfg = result.config
    print(f"\n{'='*60}")
    print(f"  {cfg.firm_name} {cfg.program_name} Challenge Simulation")
    print(f"  Target: ${cfg.target_balance:,.0f} | Steps: {cfg.n_steps}")
    print(f"  Rules: +{cfg.profit_target_pct*100:.0f}% target, "
          f"-{cfg.max_drawdown_pct*100:.0f}% max DD ({cfg.drawdown_type})")
    print(f"{'='*60}")

    for step in result.steps:
        status = "PASSED" if step.passed else "FAILED"
        print(f"\n  Step {step.step_number}: ${step.starting_balance:,.0f} -> {status}")
        print(f"    Target: +${step.profit_target:,.0f} | "
              f"Floor: ${step.max_drawdown_limit:,.0f}")
        print(f"    Ending balance: ${step.ending_balance:,.0f} | "
              f"Trades: {step.trades_taken}")
        print(f"    Peak: ${step.peak_balance:,.0f} | "
              f"Max DD: {step.max_drawdown_pct*100:.2f}%")
        if step.failure_reason:
            print(f"    Reason: {step.failure_reason}")

    overall = "CHALLENGE PASSED" if result.passed_all_steps else "CHALLENGE FAILED"
    print(f"\n  {'='*56}")
    print(f"  {overall}")
    print(f"  Total trades consumed: {result.trades_consumed} / {result.trades_available}")
    print(f"  Worst DD across steps: {result.worst_drawdown_pct*100:.2f}%")
    if result.passed_all_steps:
        total_cost = result.config.entry_fee + result.config.funded_fee
        print(f"  Challenge cost: ${total_cost:,.0f} "
              f"(${result.config.entry_fee:.0f} entry + ${result.config.funded_fee:.0f} funded)")
    print(f"{'='*60}\n")


def print_monte_carlo_stats(stats: MonteCarloStats, strategy_name: str = "") -> None:
    """Print Monte Carlo pass rate statistics."""
    label = f" -- {strategy_name}" if strategy_name else ""
    print(f"\n{'='*60}")
    print(f"  Monte Carlo Challenge Simulation{label}")
    print(f"  Simulations: {stats.n_simulations:,}")
    print(f"{'='*60}")
    print(f"  Pass rate:          {stats.pass_rate*100:.1f}% "
          f"({stats.pass_count:,} / {stats.n_simulations:,})")
    print(f"  Avg trades to pass: {stats.avg_trades_to_pass:.0f}")
    print(f"  Median trades:      {stats.median_trades_to_pass:.0f}")
    print(f"\n  Worst DD distribution:")
    print(f"    5th percentile:   {stats.p5_worst_dd_pct*100:.2f}%")
    print(f"    Median:           {stats.p50_worst_dd_pct*100:.2f}%")
    print(f"    95th percentile:  {stats.p95_worst_dd_pct*100:.2f}%")
    print(f"\n  Step pass rates:")
    for i, rate in enumerate(stats.step_pass_rates):
        print(f"    Step {i+1}: {rate*100:.1f}%")
    print(f"\n  Failure breakdown:")
    print(f"    DD blowups:       {stats.blowup_count:,}")
    print(f"    Ran out of trades:{stats.insufficient_trades_count:,}")
    for reason, count in sorted(stats.failure_reasons.items(), key=lambda x: -x[1]):
        print(f"    {reason}: {count:,}")
    print(f"{'='*60}\n")


def print_prop_rankings(scores: list[PropFirmScore]) -> None:
    """Print ranked strategy table for prop firm suitability."""
    print(f"\n{'='*90}")
    print(f"  PROP FIRM STRATEGY RANKINGS")
    print(f"{'='*90}")
    print(f"  {'Rank':<5} {'Strategy':<35} {'Score':<8} {'Pass%':<8} "
          f"{'AvgTrades':<10} {'p95 DD%':<9} {'Chrono':<8}")
    print(f"  {'-'*5} {'-'*35} {'-'*8} {'-'*8} {'-'*10} {'-'*9} {'-'*8}")

    for rank, s in enumerate(scores, 1):
        chrono = "PASS" if s.chrono_passed else "FAIL"
        print(f"  {rank:<5} {s.strategy_name:<35} {s.challenge_score:<8.4f} "
              f"{s.pass_rate*100:<8.1f} {s.avg_trades_to_pass:<10.0f} "
              f"{s.p95_worst_dd_pct*100:<9.2f} {chrono:<8}")

    print(f"{'='*90}\n")


# =============================================================================
# STANDALONE TEST
# =============================================================================

if __name__ == "__main__":
    print("Prop Firm Challenge Simulator -- Self-Test")
    print("-" * 40)

    # Synthetic trade list: decent MR-style strategy
    rng = random.Random(123)
    synthetic_trades = []
    for _ in range(200):
        if rng.random() < 0.45:
            pnl = rng.gauss(2000, 500)
        else:
            pnl = rng.gauss(-1200, 300)
        synthetic_trades.append(pnl)

    config = The5ersBootcampConfig()

    # 1. Chronological simulation
    print("\n1. CHRONOLOGICAL SIMULATION")
    result = simulate_challenge(synthetic_trades, config, source_capital=250_000.0)
    print_challenge_result(result)

    # 2. Monte Carlo pass rate
    print("\n2. MONTE CARLO PASS RATE")
    mc_stats = monte_carlo_pass_rate(
        synthetic_trades, config, source_capital=250_000.0, n_sims=5000
    )
    print_monte_carlo_stats(mc_stats, "SyntheticMR")

    # 3. Multi-strategy ranking
    print("\n3. STRATEGY RANKING")
    strategies = {
        "SyntheticMR_v1": synthetic_trades,
        "SyntheticMR_v2_tighter": [t * 0.7 for t in synthetic_trades],
        "SyntheticMR_v3_wider": [t * 1.3 for t in synthetic_trades],
    }
    rankings = rank_strategies_for_prop(
        strategies, config, source_capital=250_000.0, n_sims=2000
    )
    print_prop_rankings(rankings)

    # 4. Verify step balances
    print("\n4. CONFIG VERIFICATION")
    print(f"  Bootcamp $250K steps: {[f'${b:,.0f}' for b in config.step_balances]}")
    print(f"  Funded: ${config.target_balance:,.0f}")
    print(f"  Cost: ${config.entry_fee:.0f} + ${config.funded_fee:.0f} = ${config.entry_fee + config.funded_fee:.0f}")

    cfg100 = The5ersBootcampConfig(target=100_000.0)
    print(f"  Bootcamp $100K steps: {[f'${b:,.0f}' for b in cfg100.step_balances]}")

    hs = The5ersHighStakesConfig()
    print(f"  High Stakes $100K: {hs.program_name}, {hs.n_steps} steps, "
          f"targets={[f'{t*100:.0f}%' for t in hs.step_profit_targets]}, {hs.max_drawdown_pct*100:.0f}% DD")

    hg = The5ersHyperGrowthConfig()
    print(f"  Hyper Growth ${hg.target_balance:,.0f}: {hg.n_steps} step, "
          f"{hg.profit_target_pct*100:.0f}% target, {hg.max_drawdown_pct*100:.0f}% DD")

    pg = The5ersProGrowthConfig()
    print(f"  Pro Growth ${pg.target_balance:,.0f}: {pg.n_steps} step, "
          f"{pg.profit_target_pct*100:.0f}% target, entry ${pg.entry_fee:.0f}")

    print("\nSelf-test complete.")
