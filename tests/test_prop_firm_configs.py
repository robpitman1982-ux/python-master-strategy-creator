"""Tests for prop firm config correctness and simulation behaviour."""
from __future__ import annotations

import pytest

from modules.prop_firm_simulator import (
    The5ersBootcampConfig,
    The5ersHighStakesConfig,
    The5ersHyperGrowthConfig,
    The5ersProGrowthConfig,
    simulate_challenge,
)


# ── Config verification ─────────────────────────────────────────────────────

def test_bootcamp_unchanged():
    cfg = The5ersBootcampConfig(250_000)
    assert cfg.max_daily_drawdown_pct is None
    assert cfg.n_steps == 3
    assert cfg.profit_target_pct == 0.06
    assert cfg.max_drawdown_pct == 0.05
    assert cfg.leverage == 30.0
    assert cfg.daily_dd_is_pause is False
    assert cfg.daily_dd_recalculates is False
    assert cfg.min_profitable_days is None


def test_high_stakes_config_correct():
    cfg = The5ersHighStakesConfig(100_000)
    assert cfg.n_steps == 2
    assert cfg.step_profit_targets == [0.08, 0.05]
    assert cfg.max_drawdown_pct == 0.10
    assert cfg.max_daily_drawdown_pct == 0.05
    assert cfg.leverage == 100.0
    assert cfg.daily_dd_recalculates is True
    assert cfg.daily_dd_is_pause is False
    assert cfg.min_profitable_days == 3


def test_pro_growth_config_correct():
    cfg = The5ersProGrowthConfig(5_000)
    assert cfg.n_steps == 1
    assert cfg.profit_target_pct == 0.10
    assert cfg.max_drawdown_pct == 0.06
    assert cfg.max_daily_drawdown_pct == 0.03
    assert cfg.daily_dd_is_pause is True
    assert cfg.min_profitable_days == 3
    assert cfg.leverage == 30.0
    assert cfg.entry_fee == 74.0


def test_hyper_growth_config_correct():
    cfg = The5ersHyperGrowthConfig(5_000)
    assert cfg.n_steps == 1
    assert cfg.profit_target_pct == 0.10
    assert cfg.max_drawdown_pct == 0.06
    assert cfg.max_daily_drawdown_pct == 0.03
    assert cfg.daily_dd_is_pause is True
    assert cfg.daily_dd_recalculates is False
    assert cfg.min_profitable_days is None
    assert cfg.leverage == 30.0


# ── Daily DD behaviour tests ────────────────────────────────────────────────

def test_daily_dd_pause_continues_trading():
    """Daily DD pause should skip rest of day, not fail the step."""
    cfg = The5ersProGrowthConfig(5_000)
    # source_capital = 5000 so scaling is 1:1
    # Day 1 (2 trades): -200 (daily DD limit is 3% of 5000 = 150, breached after trade 1)
    #   With pause: skip rest of day 1, continue day 2
    # Day 2 (2 trades): +300, +300
    # Total PnL = -200 + 300 + 300 = +400 (but trade 2 of day 1 skipped under pause)
    # Actually with pause: -200 (pause), then day 2: +300, +300 => balance 5000 - 200 + 300 + 300 = 5400
    # Target is 10% of 5000 = 500, so balance needs 5500. Not quite enough.
    # Let's use bigger wins:
    trades = [-200, 50, 300, 300, 200, 200]
    result = simulate_challenge(
        trades, cfg, source_capital=5_000, trades_per_day=2
    )
    # Key: should NOT fail on day 1's daily DD breach
    # The step may or may not pass depending on total PnL, but it should NOT
    # report daily_dd_breach as failure
    step = result.steps[0]
    assert step.daily_dd_breach is False, (
        f"Pro Growth should pause on daily DD, not terminate. Got: {step.failure_reason}"
    )


def test_daily_dd_terminate_fails_step():
    """High Stakes daily DD should terminate the step."""
    cfg = The5ersHighStakesConfig(100_000)
    # Daily DD limit = 5% of 100K = 5000. One trade losing 6000 breaches it.
    trades = [-6000]
    result = simulate_challenge(
        trades, cfg, source_capital=100_000, trades_per_day=1
    )
    assert not result.passed_all_steps
    assert result.steps[0].daily_dd_breach is True


def test_daily_dd_recalculates_with_profit():
    """High Stakes daily DD limit should increase as account grows."""
    cfg = The5ersHighStakesConfig(100_000)
    # Day 1: profit $8000. Day 2 start balance = $108000
    # Recalculated daily DD limit = 5% of max(108000, 100000) = 5400
    # Day 2 trade: lose $5200 — within recalculated limit but would breach original $5000
    trades = [8000, -5200]
    result = simulate_challenge(
        trades, cfg, source_capital=100_000, trades_per_day=1
    )
    step = result.steps[0]
    # Should NOT breach daily DD because recalculated limit is 5400 > 5200
    assert step.daily_dd_breach is False, (
        f"Recalculated daily DD should be 5400, loss of 5200 should not breach. Got: {step.failure_reason}"
    )


def test_min_profitable_days_enforced():
    """Step should not pass until min profitable days met."""
    cfg = The5ersHighStakesConfig(100_000)
    # Hit 8% profit target ($8000) in 1 trade on day 1 — only 1 profitable day
    # Needs 3 profitable days to qualify
    trades = [8000, 100, 100]  # day1: +8000, day2: +100, day3: +100
    result = simulate_challenge(
        trades, cfg, source_capital=100_000, trades_per_day=1
    )
    step = result.steps[0]
    # Should use all 3 trades (waiting for 3 profitable days), not exit after trade 1
    assert step.trades_taken >= 3, (
        f"Min profitable days should delay exit. Only took {step.trades_taken} trades."
    )
