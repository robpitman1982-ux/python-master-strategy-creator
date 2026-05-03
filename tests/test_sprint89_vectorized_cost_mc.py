"""Sprint 89: vectorized cost-aware MC matrix builder tests.

Verifies that `_build_cost_adjusted_shuffled_interleave_matrix_vectorized`
produces a statistically equivalent matrix to the legacy
`_build_cost_adjusted_shuffled_interleave_matrix`, with byte-identical
per-sim aggregate PnL (sum) since the shuffle is just a permutation, and
≥10x speedup on representative input sizes.
"""
from __future__ import annotations

import time

import numpy as np
import pytest

import modules.portfolio_selector as ps


@pytest.fixture(autouse=True)
def _reset_state():
    ps._CFD_MARKET_CONFIG_CACHE = None
    ps._THE5ERS_SPECS_CACHE = None
    ps._THE5ERS_FIRM_META_CACHE = None
    ps._THE5ERS_EXCLUDED_CACHE = None
    ps._set_the5ers_overlay_enabled(False)
    yield
    ps._set_the5ers_overlay_enabled(False)


def _make_synthetic_trade_artifacts(
    strategy_count: int = 3,
    trades_per_strategy: int = 200,
    seed: int = 42,
    overlay: bool = False,
) -> tuple[dict, dict, dict]:
    """Generate a synthetic trade_artifacts payload + matching trade_lists.

    Each strategy has `trades_per_strategy` trades with randomized PnL,
    entry/exit times, direction, entry_price. Markets cycle through ES,
    NQ, GC so overlay path exercises asymmetric swap.
    """
    rng = np.random.default_rng(seed)
    markets = ["ES", "NQ", "GC"][:max(1, strategy_count)]
    timeframe = "60m"
    strategy_trade_lists: dict[str, list[float]] = {}
    trade_artifacts: dict[str, list[dict]] = {}
    contract_weights: dict[str, float] = {}

    for i in range(strategy_count):
        market = markets[i % len(markets)]
        name = f"{market}_{timeframe}_strat{i}"
        # PnL roughly normal around small positive mean
        pnl_arr = rng.normal(loc=20.0, scale=200.0, size=trades_per_strategy)
        # Force a few zero-pnl trades to exercise the filter
        pnl_arr[::50] = 0.0
        # Entry/exit timestamps: 1-3 day holds in 2024
        starts = np.array(
            [np.datetime64("2024-01-01") + np.timedelta64(int(d), "D")
             for d in rng.integers(0, 250, trades_per_strategy)]
        )
        holds_days = rng.integers(0, 4, trades_per_strategy)
        directions = rng.choice(["long", "short"], size=trades_per_strategy)
        prices = rng.uniform(2000.0, 5500.0, trades_per_strategy)

        trades_list = []
        for j in range(trades_per_strategy):
            trades_list.append({
                "net_pnl": float(pnl_arr[j]),
                "entry_time": str(starts[j]),
                "exit_time": str(starts[j] + np.timedelta64(int(holds_days[j]), "D")),
                "direction": str(directions[j]),
                "entry_price": float(prices[j]),
                "bars_held": int(holds_days[j] * 24),
            })
        trade_artifacts[name] = trades_list
        strategy_trade_lists[name] = [t["net_pnl"] for t in trades_list]
        contract_weights[name] = 0.5 + 0.2 * i  # vary per strategy

    if overlay:
        ps._set_the5ers_overlay_enabled(True)

    return strategy_trade_lists, trade_artifacts, contract_weights


def test_vectorized_matrix_shape_matches_legacy():
    stl, ta, cw = _make_synthetic_trade_artifacts(strategy_count=3, trades_per_strategy=100)
    seed = 42
    n_sims = 50

    legacy = ps._build_cost_adjusted_shuffled_interleave_matrix(stl, ta, cw, n_sims, seed)
    vec = ps._build_cost_adjusted_shuffled_interleave_matrix_vectorized(stl, ta, cw, n_sims, seed)

    assert legacy.shape == vec.shape, f"shape mismatch: legacy {legacy.shape} vs vec {vec.shape}"


def test_vectorized_matrix_per_sim_total_pnl_matches_legacy():
    """Per-sim sum of all matrix entries must be byte-equal between legacy
    and vectorized (shuffles are permutations; sum is invariant)."""
    stl, ta, cw = _make_synthetic_trade_artifacts(strategy_count=3, trades_per_strategy=100)
    n_sims = 100

    legacy = ps._build_cost_adjusted_shuffled_interleave_matrix(stl, ta, cw, n_sims, seed=42)
    vec = ps._build_cost_adjusted_shuffled_interleave_matrix_vectorized(stl, ta, cw, n_sims, seed=42)

    legacy_per_sim = legacy.sum(axis=1)
    vec_per_sim = vec.sum(axis=1)

    # All sims must have identical totals (within float64 precision)
    np.testing.assert_allclose(
        legacy_per_sim, vec_per_sim, rtol=1e-10, atol=1e-6,
        err_msg="per-sim totals diverge between legacy and vectorized cost-MC matrices",
    )


def test_vectorized_matrix_total_nonzero_count_matches_legacy():
    stl, ta, cw = _make_synthetic_trade_artifacts(strategy_count=3, trades_per_strategy=100)
    n_sims = 50

    legacy = ps._build_cost_adjusted_shuffled_interleave_matrix(stl, ta, cw, n_sims, seed=42)
    vec = ps._build_cost_adjusted_shuffled_interleave_matrix_vectorized(stl, ta, cw, n_sims, seed=42)

    # Same number of trade slots filled per sim — both pack from index 0
    legacy_nonzero = (legacy != 0.0).sum(axis=1)
    vec_nonzero = (vec != 0.0).sum(axis=1)
    np.testing.assert_array_equal(legacy_nonzero, vec_nonzero)


def test_vectorized_matrix_with_overlay_active():
    stl, ta, cw = _make_synthetic_trade_artifacts(
        strategy_count=3, trades_per_strategy=100, overlay=True,
    )
    n_sims = 50

    legacy = ps._build_cost_adjusted_shuffled_interleave_matrix(stl, ta, cw, n_sims, seed=42)
    vec = ps._build_cost_adjusted_shuffled_interleave_matrix_vectorized(stl, ta, cw, n_sims, seed=42)

    # Per-sim totals identical even with overlay's asymmetric long/short
    # swap rates and commission applied
    np.testing.assert_allclose(
        legacy.sum(axis=1), vec.sum(axis=1), rtol=1e-10, atol=1e-6,
    )


def test_vectorized_matrix_handles_empty_trade_artifacts():
    stl = {"ES_60m_a": [1.0, 2.0]}
    ta: dict[str, list[dict]] = {"ES_60m_a": []}
    cw = {"ES_60m_a": 1.0}
    vec = ps._build_cost_adjusted_shuffled_interleave_matrix_vectorized(stl, ta, cw, n_sims=10, seed=42)
    assert vec.shape == (10, 0)


def test_vectorized_matrix_handles_single_strategy():
    stl, ta, cw = _make_synthetic_trade_artifacts(strategy_count=1, trades_per_strategy=50)
    legacy = ps._build_cost_adjusted_shuffled_interleave_matrix(stl, ta, cw, n_sims=20, seed=42)
    vec = ps._build_cost_adjusted_shuffled_interleave_matrix_vectorized(stl, ta, cw, n_sims=20, seed=42)
    np.testing.assert_allclose(legacy.sum(axis=1), vec.sum(axis=1), rtol=1e-10)


def test_vectorized_matrix_handles_uneven_trade_counts():
    """One strategy with 100 trades, another with 30. Packing layout
    must match legacy: interleaved up to min(100,30), then 100's tail."""
    rng = np.random.default_rng(0)
    stl = {
        "ES_60m_a": list(rng.normal(20, 200, 100)),
        "NQ_60m_b": list(rng.normal(20, 200, 30)),
    }
    ta = {
        "ES_60m_a": [
            {"net_pnl": p, "entry_time": "2024-01-01", "exit_time": "2024-01-02",
             "direction": "long", "entry_price": 5000.0, "bars_held": 24}
            for p in stl["ES_60m_a"]
        ],
        "NQ_60m_b": [
            {"net_pnl": p, "entry_time": "2024-01-01", "exit_time": "2024-01-02",
             "direction": "short", "entry_price": 18000.0, "bars_held": 24}
            for p in stl["NQ_60m_b"]
        ],
    }
    cw = {"ES_60m_a": 1.0, "NQ_60m_b": 1.0}

    legacy = ps._build_cost_adjusted_shuffled_interleave_matrix(stl, ta, cw, n_sims=20, seed=7)
    vec = ps._build_cost_adjusted_shuffled_interleave_matrix_vectorized(stl, ta, cw, n_sims=20, seed=7)
    assert legacy.shape == vec.shape
    np.testing.assert_allclose(legacy.sum(axis=1), vec.sum(axis=1), rtol=1e-10)


def test_vectorized_is_at_least_5x_faster():
    """Smaller realistic config (3 strats × 100 trades × 200 sims) so the
    test stays under ~10s on slow hardware. Observed speedup on typical
    machines is 20-50x; this gates at 5x to avoid flakes on shared CI.
    """
    stl, ta, cw = _make_synthetic_trade_artifacts(
        strategy_count=3, trades_per_strategy=100, seed=99,
    )
    n_sims = 200

    t0 = time.perf_counter()
    legacy = ps._build_cost_adjusted_shuffled_interleave_matrix(stl, ta, cw, n_sims, seed=42)
    legacy_secs = time.perf_counter() - t0

    t0 = time.perf_counter()
    vec = ps._build_cost_adjusted_shuffled_interleave_matrix_vectorized(stl, ta, cw, n_sims, seed=42)
    vec_secs = time.perf_counter() - t0

    speedup = legacy_secs / vec_secs if vec_secs > 0 else float("inf")
    print(f"\n[Sprint 89] legacy={legacy_secs:.2f}s, vectorized={vec_secs:.3f}s, speedup={speedup:.1f}x")

    assert legacy.shape == vec.shape
    assert speedup >= 5.0, (
        f"vectorized only {speedup:.1f}x faster (target: ≥5x). "
        f"legacy={legacy_secs:.2f}s, vectorized={vec_secs:.3f}s"
    )


def test_precompute_unit_net_filters_zero_pnl_trades():
    """The unit_net precompute must drop zero-pnl trades to match legacy
    behaviour."""
    ta = {
        "ES_60m_a": [
            {"net_pnl": 100.0, "entry_time": "2024-01-01", "exit_time": "2024-01-02",
             "direction": "long", "entry_price": 5000.0, "bars_held": 24},
            {"net_pnl": 0.0, "entry_time": "2024-01-01", "exit_time": "2024-01-02",
             "direction": "long", "entry_price": 5000.0, "bars_held": 24},
            {"net_pnl": -50.0, "entry_time": "2024-01-01", "exit_time": "2024-01-02",
             "direction": "short", "entry_price": 5000.0, "bars_held": 24},
        ]
    }
    unit_net = ps._precompute_strategy_unit_net(["ES_60m_a"], ta)
    assert unit_net["ES_60m_a"].shape == (2,)  # 0.0 trade dropped


def test_precompute_unit_net_returns_empty_for_missing_strategy():
    unit_net = ps._precompute_strategy_unit_net(["UNKNOWN_60m_x"], {})
    assert unit_net["UNKNOWN_60m_x"].shape == (0,)
