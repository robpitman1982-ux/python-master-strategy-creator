"""Sprint 88: account-aware sizing tests.

Verifies that with the The5ers overlay enabled, the selector flags portfolios
whose smallest weight scales below MT5 min_lot at the operator's actual
account balance. Default behaviour (overlay off) imposes no constraint.
"""
from __future__ import annotations

import pytest

import modules.portfolio_selector as ps
from modules.prop_firm_simulator import (
    The5ersBootcampConfig,
    The5ersHighStakesConfig,
    The5ersHyperGrowthConfig,
    The5ersProGrowthConfig,
)


@pytest.fixture(autouse=True)
def _reset_state():
    ps._CFD_MARKET_CONFIG_CACHE = None
    ps._THE5ERS_SPECS_CACHE = None
    ps._THE5ERS_FIRM_META_CACHE = None
    ps._THE5ERS_EXCLUDED_CACHE = None
    ps._set_the5ers_overlay_enabled(False)
    yield
    ps._set_the5ers_overlay_enabled(False)


def test_account_balance_bootcamp_uses_first_step():
    cfg = The5ersBootcampConfig(250_000)
    # Bootcamp 250K: step 1 = $100K (40%)
    assert ps._account_balance(cfg) == pytest.approx(100_000.0)


def test_account_balance_high_stakes_uses_first_step():
    cfg = The5ersHighStakesConfig(100_000)
    # High Stakes: both steps = $100K
    assert ps._account_balance(cfg) == pytest.approx(100_000.0)


def test_account_balance_pro_growth_uses_target():
    cfg = The5ersProGrowthConfig(5_000)
    # Pro Growth single step at $5K
    assert ps._account_balance(cfg) == pytest.approx(5_000.0)


def test_account_balance_hyper_growth_uses_target():
    cfg = The5ersHyperGrowthConfig(5_000)
    assert ps._account_balance(cfg) == pytest.approx(5_000.0)


def test_min_viable_weight_overlay_off_returns_zero():
    ps._set_the5ers_overlay_enabled(False)
    # Even with tiny account, no constraint when overlay disabled
    assert ps._compute_min_viable_weight("ES", 5_000.0) == 0.0


def test_min_viable_weight_es_at_5k():
    ps._set_the5ers_overlay_enabled(True)
    # ES: min_lot=0.01, futures_dpp=50, cfd_dpp=1, leverage_ratio=50
    # min_W = 0.01 * 250_000 / (5_000 * 50) = 0.01
    assert ps._compute_min_viable_weight("ES", 5_000.0) == pytest.approx(0.01)


def test_min_viable_weight_ym_at_5k_is_higher():
    ps._set_the5ers_overlay_enabled(True)
    # YM: min_lot=0.01, futures_dpp=5, cfd_dpp=1, leverage_ratio=5
    # min_W = 0.01 * 250_000 / (5_000 * 5) = 0.10
    assert ps._compute_min_viable_weight("YM", 5_000.0) == pytest.approx(0.10)


def test_min_viable_weight_btc_at_5k_higher_still():
    ps._set_the5ers_overlay_enabled(True)
    # BTC: min_lot=0.01, futures_dpp=5, cfd_dpp=1, leverage_ratio=5 (same as YM)
    # Same calc
    assert ps._compute_min_viable_weight("BTC", 5_000.0) == pytest.approx(0.10)


def test_min_viable_weight_at_250k_is_tiny():
    ps._set_the5ers_overlay_enabled(True)
    # YM at $250K: min_W = 0.01 * 250_000 / (250_000 * 5) = 0.002
    # Below any realistic optimizer weight; effectively no constraint
    assert ps._compute_min_viable_weight("YM", 250_000.0) == pytest.approx(0.002)


def test_min_viable_weight_fx_returns_zero():
    ps._set_the5ers_overlay_enabled(True)
    # EC has cfd_dollars_per_point: null (FX) -> no constraint
    assert ps._compute_min_viable_weight("EC", 5_000.0) == 0.0


def test_min_viable_weight_unknown_market_returns_zero():
    ps._set_the5ers_overlay_enabled(True)
    assert ps._compute_min_viable_weight("ZZZ", 5_000.0) == 0.0


def test_deployability_overlay_off_passes_all():
    ps._set_the5ers_overlay_enabled(False)
    weights = {"YM_60m_strat1": 0.001}  # tiny weight
    cand_by_label = {"YM_60m_strat1": {"market": "YM"}}
    cfg = The5ersHyperGrowthConfig(5_000)
    result = ps._check_portfolio_deployability(weights, cand_by_label, cfg)
    assert result["min_lot_check_passed"] is True
    assert result["infeasible_strategies"] == []


def test_deployability_ym_at_5k_rejects_low_weight():
    ps._set_the5ers_overlay_enabled(True)
    # weight 0.05 on YM at $5K: lots = 0.05 * 5 * (5000/250000) = 0.005 < min_lot 0.01
    weights = {"YM_60m_strat1": 0.05}
    cand_by_label = {"YM_60m_strat1": {"market": "YM"}}
    cfg = The5ersHyperGrowthConfig(5_000)
    result = ps._check_portfolio_deployability(weights, cand_by_label, cfg)
    assert result["min_lot_check_passed"] is False
    assert "YM_60m_strat1" in result["infeasible_strategies"]
    assert result["smallest_strategy_lots"] < 0.01
    assert any("YM_60m_strat1" in w for w in result["warnings"])


def test_deployability_ym_at_5k_passes_at_threshold():
    ps._set_the5ers_overlay_enabled(True)
    # weight 0.10 on YM at $5K: lots = 0.10 * 5 * 0.02 = 0.01 = min_lot
    weights = {"YM_60m_strat1": 0.10}
    cand_by_label = {"YM_60m_strat1": {"market": "YM"}}
    cfg = The5ersHyperGrowthConfig(5_000)
    result = ps._check_portfolio_deployability(weights, cand_by_label, cfg)
    assert result["min_lot_check_passed"] is True
    assert result["smallest_strategy_lots"] == pytest.approx(0.01)


def test_deployability_es_at_5k_passes_low_weight():
    ps._set_the5ers_overlay_enabled(True)
    # weight 0.02 on ES at $5K: lots = 0.02 * 50 * 0.02 = 0.02 > min_lot 0.01
    weights = {"ES_60m_strat1": 0.02}
    cand_by_label = {"ES_60m_strat1": {"market": "ES"}}
    cfg = The5ersHyperGrowthConfig(5_000)
    result = ps._check_portfolio_deployability(weights, cand_by_label, cfg)
    assert result["min_lot_check_passed"] is True
    assert result["smallest_strategy_lots"] == pytest.approx(0.02)


def test_deployability_at_250k_anything_works():
    ps._set_the5ers_overlay_enabled(True)
    # At $250K (Bootcamp's $100K step 1 actually, but use full 250K for stress)
    weights = {
        "YM_60m_a": 0.05,
        "BTC_60m_b": 0.05,
        "ES_60m_c": 0.05,
    }
    cand_by_label = {
        "YM_60m_a": {"market": "YM"},
        "BTC_60m_b": {"market": "BTC"},
        "ES_60m_c": {"market": "ES"},
    }

    class FakeCfg:
        step_balances = [250_000.0]
        target_balance = 250_000.0
        n_steps = 1
        max_drawdown_pct = 0.05

    result = ps._check_portfolio_deployability(weights, cand_by_label, FakeCfg())
    # All weights produce well-above-min_lot positions at full reference
    assert result["min_lot_check_passed"] is True


def test_deployability_mixed_portfolio_one_infeasible():
    ps._set_the5ers_overlay_enabled(True)
    weights = {
        "ES_60m_safe": 0.10,    # safe at $5K
        "YM_60m_unsafe": 0.05,  # below YM threshold at $5K
    }
    cand_by_label = {
        "ES_60m_safe": {"market": "ES"},
        "YM_60m_unsafe": {"market": "YM"},
    }
    cfg = The5ersProGrowthConfig(5_000)
    result = ps._check_portfolio_deployability(weights, cand_by_label, cfg)
    assert result["min_lot_check_passed"] is False
    assert "YM_60m_unsafe" in result["infeasible_strategies"]
    assert "ES_60m_safe" not in result["infeasible_strategies"]
