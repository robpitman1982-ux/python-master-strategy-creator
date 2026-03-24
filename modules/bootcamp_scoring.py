"""
Bootcamp scoring utilities.

This ranking layer is intentionally simple and explainable. It is designed to
favor strategies that are more likely to survive a prop-firm style evaluation:

- profitability still matters, but not by itself
- out-of-sample strength matters more than in-sample shine
- large drawdown relative to profit is penalized
- very low trade counts are penalized
- unstable quality flags are penalized
- yearly consistency is rewarded when available
"""
from __future__ import annotations

from typing import Any

import pandas as pd


_QUALITY_PENALTIES = {
    "ROBUST": 0.0,
    "STABLE": 0.0,
    "STABLE_BORDERLINE": 2.0,
    "REGIME_DEPENDENT": 5.0,
    "MARGINAL": 8.0,
    "EDGE_DECAYED_OOS": 10.0,
    "BROKEN_IN_OOS": 15.0,
    "LOW_IS_SAMPLE": 10.0,
    "NO_TRADES": 15.0,
    "UNKNOWN": 6.0,
    "INSUFFICIENT_DATA": 4.0,
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        text = str(value).replace("$", "").replace(",", "").strip()
        return float(text) if text else default
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        return int(float(value))
    except Exception:
        return default


def _clip(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _get_metric(row: pd.Series, *names: str, default: float = 0.0) -> float:
    for name in names:
        if name in row.index:
            return _as_float(row.get(name), default=default)
    return default


def _get_text(row: pd.Series, *names: str, default: str = "") -> str:
    for name in names:
        if name in row.index:
            value = row.get(name)
            if value is None or (isinstance(value, float) and pd.isna(value)):
                continue
            text = str(value).strip()
            if text:
                return text
    return default


def score_strategy_row(row: pd.Series) -> dict[str, float]:
    """
    Score a strategy row using a 0-100 Bootcamp scale.

    Component weights:
    - profitability: 30
    - OOS / recency stability: 25
    - drawdown control: 20
    - trade count / frequency: 15
    - yearly consistency: 10
    - quality penalty: subtract up to 15
    """
    pf = _get_metric(row, "leader_pf", "profit_factor", default=0.0)
    net_pnl = _get_metric(row, "leader_net_pnl", "net_pnl", default=0.0)
    max_drawdown = abs(_get_metric(row, "leader_max_drawdown", "max_drawdown", default=0.0))
    total_trades = _as_int(row.get("leader_trades", row.get("total_trades", 0)))
    trades_per_year = _get_metric(row, "leader_trades_per_year", "trades_per_year", default=0.0)
    is_pf = _get_metric(row, "is_pf", default=0.0)
    oos_pf = _get_metric(row, "oos_pf", default=0.0)
    recent_12m_pf = _get_metric(row, "recent_12m_pf", default=0.0)
    quality_flag = _get_text(row, "quality_flag", default="UNKNOWN").upper()
    quality_score = _get_metric(row, "leader_quality_score", "quality_score", default=0.0)
    pct_profitable_years = _get_metric(row, "leader_pct_profitable_years", "pct_profitable_years", default=0.0)
    max_consecutive_losing_years = _as_int(
        row.get("leader_max_consecutive_losing_years", row.get("max_consecutive_losing_years", 0))
    )
    consistency_flag = _get_text(row, "leader_consistency_flag", "consistency_flag", default="INSUFFICIENT_DATA").upper()

    # Profitability: require PF above 1.0 to score well.
    profitability_score = 30.0 * _clip((pf - 1.0) / 1.0)

    # OOS stability rewards OOS PF most, with smaller weight on IS/recent confirmation.
    oos_core = _clip((oos_pf - 1.0) / 0.8)
    recent_core = _clip((recent_12m_pf - 1.0) / 0.8)
    is_core = _clip((is_pf - 1.0) / 0.8)
    bootcamp_oos_score = 25.0 * (oos_core * 0.5 + recent_core * 0.3 + is_core * 0.2)

    # Drawdown control is based on pain relative to profit. Negative/flat systems get no credit.
    if net_pnl <= 0:
        drawdown_ratio = 9.99
        bootcamp_drawdown_score = 0.0
    elif max_drawdown <= 0:
        drawdown_ratio = 0.0
        bootcamp_drawdown_score = 20.0
    else:
        drawdown_ratio = max_drawdown / max(net_pnl, 1.0)
        bootcamp_drawdown_score = 20.0 * _clip(1.0 - (drawdown_ratio / 1.5))

    # Trade count uses both absolute count and yearly frequency so ultra-thin systems are penalized.
    trade_count_core = _clip(total_trades / 120.0)
    trade_frequency_core = _clip(trades_per_year / 12.0)
    bootcamp_trade_count_score = 15.0 * (trade_count_core * 0.5 + trade_frequency_core * 0.5)

    # Consistency favors a healthy share of profitable years and short losing streaks.
    profitable_years_core = _clip(pct_profitable_years)
    losing_streak_core = _clip(1.0 - (max_consecutive_losing_years / 4.0))
    consistency_bonus = {
        "CONSISTENT": 1.0,
        "MIXED": 0.6,
        "INCONSISTENT": 0.25,
        "INSUFFICIENT_DATA": 0.4,
    }.get(consistency_flag, 0.4)
    bootcamp_consistency_score = 10.0 * (
        profitable_years_core * 0.45
        + losing_streak_core * 0.25
        + _clip(quality_score) * 0.15
        + consistency_bonus * 0.15
    )

    bootcamp_quality_penalty = _QUALITY_PENALTIES.get(quality_flag, _QUALITY_PENALTIES["UNKNOWN"])

    bootcamp_score = (
        profitability_score
        + bootcamp_oos_score
        + bootcamp_drawdown_score
        + bootcamp_trade_count_score
        + bootcamp_consistency_score
        - bootcamp_quality_penalty
    )
    bootcamp_score = round(max(0.0, bootcamp_score), 2)

    return {
        "bootcamp_score": bootcamp_score,
        "bootcamp_profitability_score": round(profitability_score, 2),
        "bootcamp_drawdown_score": round(bootcamp_drawdown_score, 2),
        "bootcamp_oos_score": round(bootcamp_oos_score, 2),
        "bootcamp_consistency_score": round(bootcamp_consistency_score, 2),
        "bootcamp_trade_count_score": round(bootcamp_trade_count_score, 2),
        "bootcamp_quality_penalty": round(bootcamp_quality_penalty, 2),
        "bootcamp_drawdown_to_profit_ratio": round(drawdown_ratio, 4),
    }


def add_bootcamp_scores(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df.copy()

    scored = df.copy()
    score_rows = scored.apply(score_strategy_row, axis=1, result_type="expand")
    for column in score_rows.columns:
        scored[column] = score_rows[column]
    return scored
