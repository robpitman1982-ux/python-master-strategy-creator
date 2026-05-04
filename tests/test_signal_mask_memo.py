"""Tests for modules/signal_mask_memo.py - Sprint 95."""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from modules import signal_mask_memo


@dataclass
class _StubCfg:
    commission_per_contract: float = 2.0
    slippage_ticks: int = 4
    tick_value: float = 12.5
    dollars_per_point: float = 50.0
    oos_split_date: str = "2019-01-01"
    direction: str = "long"
    timeframe: str = "60m"
    use_vectorized_trades: bool = True
    initial_capital: float = 250000.0
    risk_per_trade: float = 0.01


@pytest.fixture(autouse=True)
def _isolate_memo():
    signal_mask_memo.clear_cache()
    signal_mask_memo.reset_enabled_cache()  # Sprint 99-bis
    os.environ.pop("PSC_SIGNAL_MASK_MEMO", None)
    yield
    signal_mask_memo.clear_cache()
    signal_mask_memo.reset_enabled_cache()  # Sprint 99-bis
    os.environ.pop("PSC_SIGNAL_MASK_MEMO", None)


def _make_mask(n: int = 100, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.random(n) > 0.5


def _make_data(n: int = 100) -> pd.DataFrame:
    return pd.DataFrame({"x": np.arange(n)})


# ---------------------------------------------------------------------------
# Flag handling
# ---------------------------------------------------------------------------

def test_is_enabled_env_truthy():
    os.environ["PSC_SIGNAL_MASK_MEMO"] = "1"
    assert signal_mask_memo.is_enabled() is True


def test_is_enabled_env_falsy():
    os.environ["PSC_SIGNAL_MASK_MEMO"] = "0"
    assert signal_mask_memo.is_enabled() is False


def test_is_enabled_default_off():
    assert signal_mask_memo.is_enabled() is False


def test_disabled_passes_through():
    """When the cache is off, run_fn() is always called and result is uncached."""
    os.environ["PSC_SIGNAL_MASK_MEMO"] = "0"
    mask = _make_mask()
    data = _make_data()
    cfg = _StubCfg()
    calls = {"n": 0}

    def run_fn():
        calls["n"] += 1
        return {"x": calls["n"]}

    r1 = signal_mask_memo.get_or_compute_summary(mask, 1, 1.0, data, cfg, run_fn)
    r2 = signal_mask_memo.get_or_compute_summary(mask, 1, 1.0, data, cfg, run_fn)
    assert calls["n"] == 2
    assert r1 == {"x": 1} and r2 == {"x": 2}


# ---------------------------------------------------------------------------
# Cache hit / miss behaviour
# ---------------------------------------------------------------------------

def test_first_miss_second_hit_same_mask_and_params():
    os.environ["PSC_SIGNAL_MASK_MEMO"] = "1"
    mask = _make_mask()
    data = _make_data()
    cfg = _StubCfg()
    calls = {"n": 0}

    def run_fn():
        calls["n"] += 1
        return {"value": calls["n"]}

    r1 = signal_mask_memo.get_or_compute_summary(mask, 1, 1.0, data, cfg, run_fn)
    r2 = signal_mask_memo.get_or_compute_summary(mask, 1, 1.0, data, cfg, run_fn)
    assert calls["n"] == 1, "second call must be a cache hit"
    assert r1 == r2 == {"value": 1}


def test_different_masks_miss_separately():
    os.environ["PSC_SIGNAL_MASK_MEMO"] = "1"
    data = _make_data()
    cfg = _StubCfg()
    m1 = _make_mask(seed=1)
    m2 = _make_mask(seed=2)
    calls = {"n": 0}

    def run_fn():
        calls["n"] += 1
        return {"v": calls["n"]}

    signal_mask_memo.get_or_compute_summary(m1, 1, 1.0, data, cfg, run_fn)
    signal_mask_memo.get_or_compute_summary(m2, 1, 1.0, data, cfg, run_fn)
    assert calls["n"] == 2
    assert signal_mask_memo.stats()["unique_masks"] == 2


def test_same_mask_different_hold_bars_miss_separately():
    os.environ["PSC_SIGNAL_MASK_MEMO"] = "1"
    mask = _make_mask()
    data = _make_data()
    cfg = _StubCfg()
    calls = {"n": 0}

    def run_fn():
        calls["n"] += 1
        return {}

    signal_mask_memo.get_or_compute_summary(mask, 1, 1.0, data, cfg, run_fn)
    signal_mask_memo.get_or_compute_summary(mask, 2, 1.0, data, cfg, run_fn)
    assert calls["n"] == 2


def test_same_mask_different_cfg_direction_miss_separately():
    os.environ["PSC_SIGNAL_MASK_MEMO"] = "1"
    mask = _make_mask()
    data = _make_data()
    cfg_long = _StubCfg(direction="long")
    cfg_short = _StubCfg(direction="short")
    calls = {"n": 0}

    def run_fn():
        calls["n"] += 1
        return {}

    signal_mask_memo.get_or_compute_summary(mask, 1, 1.0, data, cfg_long, run_fn)
    signal_mask_memo.get_or_compute_summary(mask, 1, 1.0, data, cfg_short, run_fn)
    assert calls["n"] == 2


def test_hit_returns_shallow_copy_so_caller_mutation_does_not_poison_cache():
    os.environ["PSC_SIGNAL_MASK_MEMO"] = "1"
    mask = _make_mask()
    data = _make_data()
    cfg = _StubCfg()

    def run_fn():
        return {"a": 1, "b": 2}

    r1 = signal_mask_memo.get_or_compute_summary(mask, 1, 1.0, data, cfg, run_fn)
    r1["a"] = 999  # mutate caller's copy
    r2 = signal_mask_memo.get_or_compute_summary(mask, 1, 1.0, data, cfg, run_fn)
    assert r2["a"] == 1, "cache must not be poisoned by caller mutation"


def test_stats_tracking():
    os.environ["PSC_SIGNAL_MASK_MEMO"] = "1"
    mask = _make_mask()
    data = _make_data()
    cfg = _StubCfg()

    def run_fn():
        return {}

    signal_mask_memo.get_or_compute_summary(mask, 1, 1.0, data, cfg, run_fn)  # miss
    signal_mask_memo.get_or_compute_summary(mask, 1, 1.0, data, cfg, run_fn)  # hit
    signal_mask_memo.get_or_compute_summary(mask, 1, 1.0, data, cfg, run_fn)  # hit
    s = signal_mask_memo.stats()
    assert s["memo_hits"] == 2
    assert s["memo_misses"] == 1
    assert abs(s["hit_rate"] - 2 / 3) < 1e-9


def test_clear_cache_resets_counters_and_storage():
    os.environ["PSC_SIGNAL_MASK_MEMO"] = "1"
    mask = _make_mask()
    data = _make_data()
    cfg = _StubCfg()
    signal_mask_memo.get_or_compute_summary(mask, 1, 1.0, data, cfg, lambda: {})
    final = signal_mask_memo.clear_cache()
    assert final["unique_masks"] == 1
    assert signal_mask_memo.stats()["memo_misses"] == 0
    assert signal_mask_memo.stats()["unique_masks"] == 0


def test_reset_counters_keeps_cache_entries():
    os.environ["PSC_SIGNAL_MASK_MEMO"] = "1"
    mask = _make_mask()
    data = _make_data()
    cfg = _StubCfg()
    signal_mask_memo.get_or_compute_summary(mask, 1, 1.0, data, cfg, lambda: {})
    signal_mask_memo.reset_counters()
    assert signal_mask_memo.stats()["memo_misses"] == 0
    assert signal_mask_memo.stats()["unique_masks"] == 1


def test_pandas_series_mask_input_normalises():
    """Caller may pass a pandas Series; should still cache correctly."""
    os.environ["PSC_SIGNAL_MASK_MEMO"] = "1"
    mask_arr = _make_mask()
    mask_series = pd.Series(mask_arr)
    data = _make_data()
    cfg = _StubCfg()
    calls = {"n": 0}

    def run_fn():
        calls["n"] += 1
        return {}

    signal_mask_memo.get_or_compute_summary(mask_arr, 1, 1.0, data, cfg, run_fn)
    signal_mask_memo.get_or_compute_summary(mask_series, 1, 1.0, data, cfg, run_fn)
    # Same content via different containers -> same hash -> hit
    assert calls["n"] == 1


def test_none_stop_distance_is_acceptable():
    os.environ["PSC_SIGNAL_MASK_MEMO"] = "1"
    mask = _make_mask()
    data = _make_data()
    cfg = _StubCfg()

    def run_fn():
        return {"v": 1}

    r1 = signal_mask_memo.get_or_compute_summary(mask, 1, None, data, cfg, run_fn)
    r2 = signal_mask_memo.get_or_compute_summary(mask, 1, None, data, cfg, run_fn)
    assert r1 == r2
    assert signal_mask_memo.stats()["memo_hits"] == 1
