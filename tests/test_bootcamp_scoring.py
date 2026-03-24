from __future__ import annotations

import pandas as pd

from modules.bootcamp_scoring import add_bootcamp_scores


def _score(row: dict) -> pd.Series:
    df = add_bootcamp_scores(pd.DataFrame([row]))
    return df.iloc[0]


def test_robust_strategy_scores_higher():
    robust = _score(
        {
            "leader_pf": 1.7,
            "leader_net_pnl": 90000.0,
            "leader_max_drawdown": 18000.0,
            "leader_trades": 220,
            "leader_trades_per_year": 16.0,
            "is_pf": 1.3,
            "oos_pf": 1.6,
            "recent_12m_pf": 1.5,
            "quality_flag": "ROBUST",
            "leader_quality_score": 0.85,
            "leader_pct_profitable_years": 0.8,
            "leader_max_consecutive_losing_years": 1,
            "leader_consistency_flag": "CONSISTENT",
        }
    )
    fragile = _score(
        {
            "leader_pf": 1.9,
            "leader_net_pnl": 40000.0,
            "leader_max_drawdown": 32000.0,
            "leader_trades": 28,
            "leader_trades_per_year": 2.5,
            "is_pf": 1.8,
            "oos_pf": 0.9,
            "recent_12m_pf": 0.85,
            "quality_flag": "BROKEN_IN_OOS",
            "leader_quality_score": 0.35,
            "leader_pct_profitable_years": 0.4,
            "leader_max_consecutive_losing_years": 3,
            "leader_consistency_flag": "INCONSISTENT",
        }
    )
    assert robust["bootcamp_score"] > fragile["bootcamp_score"]


def test_high_drawdown_is_penalized():
    base = {
        "leader_pf": 1.4,
        "leader_net_pnl": 50000.0,
        "leader_trades": 160,
        "leader_trades_per_year": 12.0,
        "is_pf": 1.2,
        "oos_pf": 1.3,
        "recent_12m_pf": 1.2,
        "quality_flag": "STABLE",
        "leader_quality_score": 0.75,
        "leader_pct_profitable_years": 0.7,
        "leader_max_consecutive_losing_years": 1,
        "leader_consistency_flag": "CONSISTENT",
    }
    shallow_dd = _score({**base, "leader_max_drawdown": 10000.0})
    deep_dd = _score({**base, "leader_max_drawdown": 45000.0})

    assert shallow_dd["bootcamp_drawdown_score"] > deep_dd["bootcamp_drawdown_score"]
    assert shallow_dd["bootcamp_score"] > deep_dd["bootcamp_score"]


def test_weak_oos_is_penalized():
    base = {
        "leader_pf": 1.5,
        "leader_net_pnl": 60000.0,
        "leader_max_drawdown": 15000.0,
        "leader_trades": 180,
        "leader_trades_per_year": 14.0,
        "is_pf": 1.3,
        "recent_12m_pf": 1.3,
        "quality_flag": "STABLE",
        "leader_quality_score": 0.8,
        "leader_pct_profitable_years": 0.75,
        "leader_max_consecutive_losing_years": 1,
        "leader_consistency_flag": "CONSISTENT",
    }
    strong_oos = _score({**base, "oos_pf": 1.5})
    weak_oos = _score({**base, "oos_pf": 0.85})

    assert strong_oos["bootcamp_oos_score"] > weak_oos["bootcamp_oos_score"]
    assert strong_oos["bootcamp_score"] > weak_oos["bootcamp_score"]


def test_low_trade_count_is_penalized():
    base = {
        "leader_pf": 1.35,
        "leader_net_pnl": 45000.0,
        "leader_max_drawdown": 12000.0,
        "is_pf": 1.15,
        "oos_pf": 1.25,
        "recent_12m_pf": 1.2,
        "quality_flag": "STABLE",
        "leader_quality_score": 0.72,
        "leader_pct_profitable_years": 0.68,
        "leader_max_consecutive_losing_years": 1,
        "leader_consistency_flag": "MIXED",
    }
    active = _score({**base, "leader_trades": 150, "leader_trades_per_year": 10.0})
    thin = _score({**base, "leader_trades": 18, "leader_trades_per_year": 1.5})

    assert active["bootcamp_trade_count_score"] > thin["bootcamp_trade_count_score"]
    assert active["bootcamp_score"] > thin["bootcamp_score"]
