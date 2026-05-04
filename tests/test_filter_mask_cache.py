"""Tests for modules/filter_mask_cache.py - Sprint 94."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from modules import filter_mask_cache
from modules.filters import (
    BaseFilter,
    DistanceBelowSMAFilter,
    DownCloseFilter,
    MomentumFilter,
)
from modules.vectorized_signals import compute_combined_signal_mask


@pytest.fixture(autouse=True)
def _isolate_cache():
    """Each test gets a clean process-level cache + counters."""
    filter_mask_cache.clear_cache()
    # Force cache OFF unless test explicitly toggles it
    os.environ.pop("PSC_FILTER_MASK_CACHE", None)
    yield
    filter_mask_cache.clear_cache()
    os.environ.pop("PSC_FILTER_MASK_CACHE", None)


def _make_data(n: int = 200) -> pd.DataFrame:
    """Synthetic OHLC + precomputed columns sufficient for the filters used here."""
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    df = pd.DataFrame({
        "open": close + rng.normal(0, 0.2, n),
        "high": close + np.abs(rng.normal(0.5, 0.2, n)),
        "low": close - np.abs(rng.normal(0.5, 0.2, n)),
        "close": close,
        "volume": rng.integers(100, 1000, n),
    })
    # Precomputed features the filters expect
    for length in (5, 8, 20, 31, 50):
        df[f"sma_{length}"] = df["close"].rolling(length, min_periods=1).mean()
    df["true_range"] = (df["high"] - df["low"]).clip(lower=0.001)
    for lb in (5, 8, 20):
        df[f"atr_{lb}"] = df["true_range"].rolling(lb, min_periods=1).mean()
    return df


# ---------------------------------------------------------------------------
# is_enabled() flag handling
# ---------------------------------------------------------------------------

def test_is_enabled_env_var_truthy():
    os.environ["PSC_FILTER_MASK_CACHE"] = "1"
    assert filter_mask_cache.is_enabled() is True
    os.environ["PSC_FILTER_MASK_CACHE"] = "true"
    assert filter_mask_cache.is_enabled() is True


def test_is_enabled_env_var_falsy():
    os.environ["PSC_FILTER_MASK_CACHE"] = "0"
    assert filter_mask_cache.is_enabled() is False
    os.environ["PSC_FILTER_MASK_CACHE"] = "off"
    assert filter_mask_cache.is_enabled() is False


def test_is_enabled_default_off_when_no_env():
    """With no env var and default config (cache disabled), returns False."""
    assert filter_mask_cache.is_enabled() is False


# ---------------------------------------------------------------------------
# Cache hit / miss / params discrimination
# ---------------------------------------------------------------------------

def test_first_call_miss_second_call_hit():
    df = _make_data()
    f = DownCloseFilter()
    m1 = filter_mask_cache.get_or_compute_mask(f, df)
    m2 = filter_mask_cache.get_or_compute_mask(f, df)
    assert filter_mask_cache.stats()["cache_hits"] == 1
    assert filter_mask_cache.stats()["cache_misses"] == 1
    np.testing.assert_array_equal(m1, m2)


def test_different_params_miss_separately():
    df = _make_data()
    f1 = MomentumFilter(lookback=5)
    f2 = MomentumFilter(lookback=8)
    filter_mask_cache.get_or_compute_mask(f1, df)
    filter_mask_cache.get_or_compute_mask(f2, df)
    assert filter_mask_cache.stats()["cache_misses"] == 2
    assert filter_mask_cache.stats()["cache_hits"] == 0
    assert filter_mask_cache.stats()["unique_filters_cached"] == 2


def test_different_class_same_attrs_miss_separately():
    df = _make_data()
    a = DistanceBelowSMAFilter()
    b = DownCloseFilter()
    filter_mask_cache.get_or_compute_mask(a, df)
    filter_mask_cache.get_or_compute_mask(b, df)
    assert filter_mask_cache.stats()["unique_filters_cached"] == 2


def test_different_data_object_miss_separately():
    df1 = _make_data(150)
    df2 = _make_data(150)  # different object identity
    f = DownCloseFilter()
    filter_mask_cache.get_or_compute_mask(f, df1)
    filter_mask_cache.get_or_compute_mask(f, df2)
    # Different id(data) → different keys → both misses
    assert filter_mask_cache.stats()["cache_misses"] == 2


def test_cached_mask_is_bool_numpy_array():
    df = _make_data()
    f = DownCloseFilter()
    m = filter_mask_cache.get_or_compute_mask(f, df)
    assert isinstance(m, np.ndarray)
    assert m.dtype == bool
    assert len(m) == len(df)


def test_clear_cache_resets_state():
    df = _make_data()
    filter_mask_cache.get_or_compute_mask(DownCloseFilter(), df)
    final = filter_mask_cache.clear_cache()
    assert final["cache_misses"] == 1
    assert filter_mask_cache.stats()["cache_misses"] == 0
    assert filter_mask_cache.stats()["unique_filters_cached"] == 0


def test_reset_counters_keeps_cache():
    df = _make_data()
    filter_mask_cache.get_or_compute_mask(DownCloseFilter(), df)
    filter_mask_cache.reset_counters()
    assert filter_mask_cache.stats()["cache_misses"] == 0
    assert filter_mask_cache.stats()["unique_filters_cached"] == 1


# ---------------------------------------------------------------------------
# compute_combined_signal_mask integration - parity with cache off vs on
# ---------------------------------------------------------------------------

def _representative_filter_combos() -> list[list[BaseFilter]]:
    """Combos that exercise different filter-set sizes and overlap patterns."""
    return [
        [DownCloseFilter()],
        [DownCloseFilter(), MomentumFilter(lookback=5)],
        [DownCloseFilter(), MomentumFilter(lookback=5), DistanceBelowSMAFilter()],
        [MomentumFilter(lookback=5), MomentumFilter(lookback=8)],
        [],  # empty filter list
    ]


def test_compute_combined_signal_mask_parity_off_vs_on():
    """Cache OFF and cache ON must produce element-wise identical masks."""
    df = _make_data(300)
    combos = _representative_filter_combos()

    os.environ["PSC_FILTER_MASK_CACHE"] = "0"
    filter_mask_cache.clear_cache()
    off_results = [compute_combined_signal_mask(c, df) for c in combos]

    os.environ["PSC_FILTER_MASK_CACHE"] = "1"
    filter_mask_cache.clear_cache()
    on_results = [compute_combined_signal_mask(c, df) for c in combos]

    for off, on, combo in zip(off_results, on_results, combos):
        np.testing.assert_array_equal(
            off, on,
            err_msg=f"Mask mismatch for combo {[type(f).__name__ for f in combo]}",
        )


def test_compute_combined_signal_mask_uses_cache_on_repeat_combos():
    """Running the same combos twice with cache ON should produce hits."""
    df = _make_data(200)
    os.environ["PSC_FILTER_MASK_CACHE"] = "1"
    filter_mask_cache.clear_cache()

    combos = _representative_filter_combos()
    # First pass: every filter is a miss
    for c in combos:
        compute_combined_signal_mask(c, df)
    misses_after_first = filter_mask_cache.stats()["cache_misses"]
    hits_after_first = filter_mask_cache.stats()["cache_hits"]

    # Second pass on the SAME data with FRESH filter instances of the same
    # classes+params - these should cache-key-equal the first pass and HIT.
    fresh_combos = _representative_filter_combos()
    for c in fresh_combos:
        compute_combined_signal_mask(c, df)
    misses_after_second = filter_mask_cache.stats()["cache_misses"]
    hits_after_second = filter_mask_cache.stats()["cache_hits"]

    assert misses_after_second == misses_after_first, (
        "second pass should produce no new misses (same filter+params)"
    )
    assert hits_after_second > hits_after_first, "second pass should be all hits"


def test_compute_combined_signal_mask_empty_filters_returns_zeros():
    df = _make_data(50)
    out = compute_combined_signal_mask([], df)
    assert isinstance(out, np.ndarray)
    assert out.dtype == bool
    assert len(out) == 50
    assert not out.any()


def test_compute_combined_signal_mask_single_filter_off_vs_on_match():
    df = _make_data(150)
    f1 = DownCloseFilter()
    os.environ["PSC_FILTER_MASK_CACHE"] = "0"
    off = compute_combined_signal_mask([f1], df)
    os.environ["PSC_FILTER_MASK_CACHE"] = "1"
    filter_mask_cache.clear_cache()
    on = compute_combined_signal_mask([f1], df)
    np.testing.assert_array_equal(off, on)
