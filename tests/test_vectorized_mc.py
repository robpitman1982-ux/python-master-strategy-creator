"""Tests for vectorized Monte Carlo challenge simulator.

Verifies that simulate_challenge_batch() produces results matching
sequential simulate_challenge() calls, and covers multi-step + daily DD.
"""
from __future__ import annotations

import random
import time

import numpy as np
import pytest

from modules.prop_firm_simulator import (
    PropFirmConfig,
    The5ersBootcampConfig,
    The5ersHighStakesConfig,
    The5ersHyperGrowthConfig,
    simulate_challenge,
    simulate_challenge_batch,
)


def _build_shuffled_matrix(trades: list[float], n_sims: int, seed: int) -> np.ndarray:
    """Build (n_sims, n_trades) matrix with independently shuffled trades."""
    rng = random.Random(seed)
    n_trades = len(trades)
    matrix = np.zeros((n_sims, n_trades))
    for i in range(n_sims):
        shuffled = trades.copy()
        rng.shuffle(shuffled)
        matrix[i] = shuffled
    return matrix


def _sequential_pass_rate(trades: list[float], config: PropFirmConfig,
                          source_capital: float, n_sims: int, seed: int) -> dict:
    """Run sequential simulate_challenge() for comparison."""
    rng = random.Random(seed)
    pass_count = 0
    step_pass_counts = [0] * config.n_steps
    worst_dds = []

    for _ in range(n_sims):
        shuffled = trades.copy()
        rng.shuffle(shuffled)
        result = simulate_challenge(shuffled, config, source_capital)
        worst_dds.append(result.worst_drawdown_pct)

        for step in result.steps:
            if step.passed:
                step_pass_counts[step.step_number - 1] += 1
            else:
                break

        if result.passed_all_steps:
            pass_count += 1

    return {
        "pass_rate": pass_count / n_sims,
        "step_pass_rates": [c / n_sims for c in step_pass_counts],
        "median_worst_dd_pct": float(np.median(worst_dds)),
    }


# --- Parity tests ---

def test_vectorized_matches_sequential_bootcamp():
    """Ensure vectorized MC produces same pass rate as sequential for Bootcamp."""
    trades = [100, -50, 200, -150, 75, -30, 180, -90, 60, -40,
              120, -80, 90, -60, 150, -100, 200, -70, 50, -20] * 5
    config = The5ersBootcampConfig(250_000)
    n_sims = 500
    seed = 42
    source_capital = 250_000.0

    # Sequential
    seq = _sequential_pass_rate(trades, config, source_capital, n_sims, seed)

    # Vectorized
    trade_matrix = _build_shuffled_matrix(trades, n_sims, seed)
    vec = simulate_challenge_batch(trade_matrix, config, source_capital)

    assert abs(vec["pass_rate"] - seq["pass_rate"]) < 0.05, \
        f"Pass rate mismatch: vec={vec['pass_rate']:.3f} vs seq={seq['pass_rate']:.3f}"

    # Step pass rates should be close
    for i, (vr, sr) in enumerate(zip(
        [vec.get(f"step{j+1}_pass_rate", 0) for j in range(config.n_steps)],
        seq["step_pass_rates"]
    )):
        assert abs(vr - sr) < 0.05, \
            f"Step {i+1} pass rate mismatch: vec={vr:.3f} vs seq={sr:.3f}"


def test_vectorized_matches_sequential_high_stakes():
    """High Stakes has 2 steps + daily DD — verify vectorized handles it."""
    config = The5ersHighStakesConfig(100_000)
    assert config.n_steps == 2
    assert config.max_daily_drawdown_pct is not None

    trades = [50, -30, 100, -80, 40, -20, 60, -50, 30, -10] * 10
    n_sims = 500
    seed = 123
    source_capital = 250_000.0

    seq = _sequential_pass_rate(trades, config, source_capital, n_sims, seed)
    trade_matrix = _build_shuffled_matrix(trades, n_sims, seed)
    vec = simulate_challenge_batch(trade_matrix, config, source_capital)

    assert abs(vec["pass_rate"] - seq["pass_rate"]) < 0.05, \
        f"High Stakes pass rate mismatch: vec={vec['pass_rate']:.3f} vs seq={seq['pass_rate']:.3f}"


def test_vectorized_zero_trades():
    """All-zero trades should produce 0% pass rate."""
    config = The5ersBootcampConfig(250_000)
    trade_matrix = np.zeros((100, 50))
    result = simulate_challenge_batch(trade_matrix, config, 250_000.0)
    assert result["pass_rate"] == 0.0


def test_vectorized_all_winners():
    """Strong positive trades should produce high pass rate."""
    config = The5ersBootcampConfig(250_000)
    # Large positive trades (6% of step balance each)
    trade_matrix = np.full((100, 200), 5000.0)
    result = simulate_challenge_batch(trade_matrix, config, 250_000.0)
    assert result["pass_rate"] > 0.9, f"Expected high pass rate, got {result['pass_rate']}"


def test_vectorized_all_losers():
    """All negative trades should produce 0% pass rate."""
    config = The5ersBootcampConfig(250_000)
    trade_matrix = np.full((100, 50), -1000.0)
    result = simulate_challenge_batch(trade_matrix, config, 250_000.0)
    assert result["pass_rate"] == 0.0


def test_vectorized_trailing_dd():
    """Test with trailing drawdown type (Pro Growth)."""
    config = The5ersHyperGrowthConfig(5_000)
    trades = [20, -10, 30, -25, 15, -8, 40, -30, 10, -5] * 10
    n_sims = 200
    seed = 77

    trade_matrix = _build_shuffled_matrix(trades, n_sims, seed)
    result = simulate_challenge_batch(trade_matrix, config, 250_000.0)

    # Should produce valid results (not crash)
    assert 0.0 <= result["pass_rate"] <= 1.0
    assert result["p95_worst_dd_pct"] >= 0.0


def test_vectorized_risk_metrics_populated():
    """Verify all risk metric fields are present in output."""
    config = The5ersBootcampConfig(250_000)
    trades = [100, -50, 200, -150, 75] * 20
    trade_matrix = _build_shuffled_matrix(trades, 100, 42)
    result = simulate_challenge_batch(trade_matrix, config, 250_000.0)

    required_keys = [
        "pass_rate", "final_pass_rate",
        "step1_pass_rate",
        "median_worst_dd_pct", "p95_worst_dd_pct", "p99_worst_dd_pct",
        "avg_trades_to_pass", "median_trades_to_pass", "p75_trades_to_pass",
        "worst_rolling_20_p95", "max_losing_streak_p95", "max_recovery_trades_p95",
    ]
    for key in required_keys:
        assert key in result, f"Missing key: {key}"


def test_vectorized_speedup():
    """Vectorized should complete 1000 sims in reasonable time."""
    config = The5ersBootcampConfig(250_000)
    trades = [100, -50, 200, -150, 75, -30, 180, -90, 60, -40] * 50
    n_sims = 2000

    # Vectorized timing — main value is enabling batch processing
    trade_matrix = _build_shuffled_matrix(trades, n_sims, 42)
    t0 = time.time()
    result = simulate_challenge_batch(trade_matrix, config, 250_000.0)
    vec_time = time.time() - t0

    # Should complete 2000 sims with 500 trades each in under 5 seconds
    assert vec_time < 5.0, f"Vectorized too slow: {vec_time:.1f}s for {n_sims} sims"
    assert 0.0 <= result["pass_rate"] <= 1.0
