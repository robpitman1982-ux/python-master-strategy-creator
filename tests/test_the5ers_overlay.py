"""Sprint 87: The5ers MT5 cost overlay tests.

Verifies that when `use_the5ers_overlay` is enabled, the selector's
cost-aware MC reads asymmetric long/short swaps, custom triple-day rules,
and round-trip commission from `configs/the5ers_mt5_specs.yaml`.
"""
from __future__ import annotations

import pytest

import modules.portfolio_selector as ps


@pytest.fixture(autouse=True)
def _reset_caches_and_flag():
    """Reset module-level caches and overlay flag between tests."""
    ps._CFD_MARKET_CONFIG_CACHE = None
    ps._THE5ERS_SPECS_CACHE = None
    ps._THE5ERS_FIRM_META_CACHE = None
    ps._THE5ERS_EXCLUDED_CACHE = None
    ps._set_active_firm("none")
    ps._set_the5ers_overlay_enabled(False)
    ps._set_active_firm("none")
    yield
    ps._set_active_firm("none")


def test_overlay_loader_loads_canonical_markets():
    specs = ps._load_the5ers_specs()
    # Spot-check markets we know are in the file
    assert "ES" in specs
    assert "NQ" in specs
    assert "CL" in specs
    assert "BTC" in specs
    assert "GC" in specs
    # Excluded list populated
    excluded = ps._the5ers_excluded_markets()
    assert "RTY" in excluded
    assert "NG" in excluded


def test_overlay_loader_caches_after_first_call():
    first = ps._load_the5ers_specs()
    second = ps._load_the5ers_specs()
    assert first is second  # same object, cache hit


def test_overlay_off_falls_back_to_cfd_markets():
    ps._set_the5ers_overlay_enabled(False)
    ctx = ps._get_market_cost_context("ES")
    # cfd_markets path: source field set, symmetric swap
    assert ctx["source"] == "cfd_markets"
    assert ctx["swap_long_per_micro_per_night"] == ctx["swap_short_per_micro_per_night"]
    assert ctx["commission_pct"] == 0.0
    assert ctx["triple_day"] == "friday"


def test_overlay_on_uses_the5ers_data():
    ps._set_the5ers_overlay_enabled(True)
    ctx = ps._get_market_cost_context("CL")
    # CL has asymmetric swap (-0.70 long vs -0.40 short, stored as positive cost)
    assert ctx["source"] == "the5ers_overlay"
    assert ctx["swap_long_per_micro_per_night"] == pytest.approx(0.70)
    assert ctx["swap_short_per_micro_per_night"] == pytest.approx(0.40)
    # CL's Friday triple is 10x (not 3x)
    assert ctx["weekend_multiplier"] == pytest.approx(10.0)
    assert ctx["triple_day"] == "friday"
    # CL has 0.03% commission
    assert ctx["commission_pct"] == pytest.approx(0.03)


def test_overlay_btc_uses_daily_no_triple():
    ps._set_the5ers_overlay_enabled(True)
    ctx = ps._get_market_cost_context("BTC")
    assert ctx["triple_day"] == "none"
    # BTC has asymmetric swap
    assert ctx["swap_long_per_micro_per_night"] == pytest.approx(1.25)
    assert ctx["swap_short_per_micro_per_night"] == pytest.approx(0.90)


def test_overlay_unknown_market_falls_back():
    ps._set_the5ers_overlay_enabled(True)
    ctx = ps._get_market_cost_context("ZZZ")
    # ZZZ not in either yaml, falls back to cfd_markets path with zero costs
    assert ctx["source"] == "cfd_markets"


def test_swap_units_friday_triple_default():
    # Tue 2024-04-30 -> Sun 2024-05-05 (5 nights: Tue, Wed, Thu, Fri-triple, Sat skipped, Sun skipped — but Sat/Sun gap means we walk to but not past Sun)
    # Actually: walk Tue, Wed, Thu, Fri, Sat — Sat is current<exit so we continue
    # Easier to test a clean Mon-Fri close
    units, weekend = ps._estimate_swap_charge_units(
        "2024-04-29",  # Mon
        "2024-05-04",  # Sat
        weekend_multiplier=3.0,
        triple_day="friday",
    )
    # Mon=1, Tue=1, Wed=1, Thu=1, Fri=3 = 7 units, weekend touched
    assert units == pytest.approx(7.0)
    assert weekend is True


def test_swap_units_cl_friday_10x():
    # Same window as above but with 10x triple multiplier
    units, weekend = ps._estimate_swap_charge_units(
        "2024-04-29",  # Mon
        "2024-05-04",  # Sat
        weekend_multiplier=10.0,
        triple_day="friday",
    )
    # Mon=1, Tue=1, Wed=1, Thu=1, Fri=10 = 14 units
    assert units == pytest.approx(14.0)
    assert weekend is True


def test_swap_units_btc_daily_all_week():
    # BTC: charge every calendar day, no triple
    units, weekend = ps._estimate_swap_charge_units(
        "2024-04-29",  # Mon
        "2024-05-06",  # next Mon (7 nights)
        triple_day="none",
    )
    # Mon, Tue, Wed, Thu, Fri, Sat, Sun = 7 units (each = 1, no triple)
    assert units == pytest.approx(7.0)
    assert weekend is True  # weekend was touched


def test_swap_units_no_overnight():
    # Same-day exit: zero swap units
    units, weekend = ps._estimate_swap_charge_units(
        "2024-04-29 09:30",
        "2024-04-29 15:00",
    )
    assert units == 0.0
    assert weekend is False


def test_cost_adjustment_short_uses_short_swap():
    ps._set_the5ers_overlay_enabled(True)
    trade = {
        "entry_time": "2024-04-29",  # Mon
        "exit_time": "2024-04-30",   # Tue (1 swap night)
        "direction": "short",
        "net_pnl": 100.0,
    }
    costs = ps._compute_trade_cost_adjustment(trade, market="CL", timeframe="60m", weight=0.1)
    # weight=0.1 -> 1 micro. swap_units=1 (Mon->Tue). short rate = 0.40
    assert costs["swap_cost"] == pytest.approx(0.40)
    assert costs["swap_units"] == 1.0


def test_cost_adjustment_long_uses_long_swap():
    ps._set_the5ers_overlay_enabled(True)
    trade = {
        "entry_time": "2024-04-29",
        "exit_time": "2024-04-30",
        "direction": "long",
        "net_pnl": 100.0,
    }
    costs = ps._compute_trade_cost_adjustment(trade, market="CL", timeframe="60m", weight=0.1)
    # CL long = 0.70 per micro per night
    assert costs["swap_cost"] == pytest.approx(0.70)


def test_cost_adjustment_unknown_direction_uses_max():
    ps._set_the5ers_overlay_enabled(True)
    trade = {
        "entry_time": "2024-04-29",
        "exit_time": "2024-04-30",
        # No direction
        "net_pnl": 100.0,
    }
    costs = ps._compute_trade_cost_adjustment(trade, market="CL", timeframe="60m", weight=0.1)
    # Conservative: max(long=0.70, short=0.40) = 0.70
    assert costs["swap_cost"] == pytest.approx(0.70)


def test_cost_adjustment_includes_commission():
    ps._set_the5ers_overlay_enabled(True)
    trade = {
        "entry_time": "2024-04-29",
        "exit_time": "2024-04-29 15:00",  # same day, no swap
        "direction": "long",
        "entry_price": 80.0,  # CL at $80/barrel
        "net_pnl": 100.0,
    }
    costs = ps._compute_trade_cost_adjustment(trade, market="CL", timeframe="60m", weight=0.1)
    # CL: cfd_dollars_per_point=100, commission_pct=0.03 (= 0.0003 decimal)
    # notional_per_micro = 80 * 100 * 0.1 = 800
    # round-trip commission = 2 * 0.0003 * 800 * micro_count(1.0) = 0.48
    assert costs["commission_cost"] == pytest.approx(0.48)
    assert costs["swap_cost"] == 0.0  # same day


def test_cost_adjustment_es_no_commission():
    ps._set_the5ers_overlay_enabled(True)
    trade = {
        "entry_time": "2024-04-29",
        "exit_time": "2024-04-29 15:00",
        "direction": "long",
        "entry_price": 5000.0,
        "net_pnl": 100.0,
    }
    costs = ps._compute_trade_cost_adjustment(trade, market="ES", timeframe="60m", weight=0.1)
    # ES has commission_pct=0
    assert costs["commission_cost"] == 0.0


def test_cost_adjustment_overlay_off_no_commission():
    ps._set_the5ers_overlay_enabled(False)
    trade = {
        "entry_time": "2024-04-29",
        "exit_time": "2024-04-29 15:00",
        "direction": "long",
        "entry_price": 80.0,
        "net_pnl": 100.0,
    }
    costs = ps._compute_trade_cost_adjustment(trade, market="CL", timeframe="60m", weight=0.1)
    # Overlay disabled -> commission_pct from cfd_markets.yaml = 0
    assert costs["commission_cost"] == 0.0


def test_overlay_excluded_markets_in_loader():
    excluded = ps._the5ers_excluded_markets()
    # Markets unsupported on The5ers MT5
    assert set(excluded) >= {"W", "NG", "US", "TY", "RTY", "HG"}
