from __future__ import annotations

from typing import Any

import pandas as pd


QUALITY_PRIORITY: dict[str, int] = {
    "ROBUST": 0,
    "ROBUST_BORDERLINE": 1,
    "STABLE": 2,
    "STABLE_BORDERLINE": 3,
    "MARGINAL": 4,
    "EDGE_DECAYED_OOS": 5,
    "REGIME_DEPENDENT": 6,
    "BROKEN_IN_OOS": 7,
    "LOW_IS_SAMPLE": 8,
    "OOS_HEAVY": 9,
    "NO_TRADES": 10,
}


def quality_priority(flag: Any) -> int:
    return QUALITY_PRIORITY.get(str(flag).upper().strip(), 99)


def _numeric(df: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce").fillna(default)


def sort_family_leaderboard(df: pd.DataFrame) -> pd.DataFrame:
    ranked = df.copy()
    ranked["_accepted"] = ranked.get("accepted_final", pd.Series(False, index=ranked.index)).astype(bool)
    ranked["_quality"] = ranked.get("quality_flag", pd.Series("", index=ranked.index)).apply(quality_priority)
    ranked["_oos_pf"] = _numeric(ranked, "oos_pf")
    ranked["_recent_pf"] = _numeric(ranked, "recent_12m_pf")
    ranked["_calmar"] = _numeric(ranked, "calmar_ratio")
    ranked["_leader_pf"] = _numeric(ranked, "leader_pf")
    ranked["_max_dd"] = _numeric(ranked, "leader_max_drawdown", default=float("inf")).abs()
    ranked["_net_pnl"] = _numeric(ranked, "leader_net_pnl")
    ranked["_tpy"] = _numeric(ranked, "leader_trades_per_year")
    ranked["_avg_trade"] = _numeric(ranked, "leader_avg_trade")

    ranked = ranked.sort_values(
        by=[
            "_accepted",
            "_quality",
            "_oos_pf",
            "_recent_pf",
            "_calmar",
            "_leader_pf",
            "_max_dd",
            "_net_pnl",
            "_tpy",
            "_avg_trade",
        ],
        ascending=[False, True, False, False, False, False, True, False, False, False],
    )
    return ranked.drop(columns=[c for c in ranked.columns if c.startswith("_")], errors="ignore").reset_index(drop=True)


def sort_aggregate_leaderboard(df: pd.DataFrame) -> pd.DataFrame:
    ranked = df.copy()
    if "accepted_final" in ranked.columns:
        ranked["_accepted"] = ranked["accepted_final"].astype(str).str.strip().str.lower().isin(["true", "1", "yes"])
    else:
        ranked["_accepted"] = True
    ranked["_quality"] = ranked.get("quality_flag", pd.Series("", index=ranked.index)).apply(quality_priority)
    ranked["_oos_pf"] = _numeric(ranked, "oos_pf")
    ranked["_recent_pf"] = _numeric(ranked, "recent_12m_pf")
    ranked["_calmar"] = _numeric(ranked, "calmar_ratio")
    ranked["_dsr"] = _numeric(ranked, "deflated_sharpe_ratio")
    ranked["_leader_pf"] = _numeric(ranked, "leader_pf")
    ranked["_max_dd"] = _numeric(ranked, "leader_max_drawdown", default=float("inf")).abs()
    ranked["_net_pnl"] = _numeric(ranked, "leader_net_pnl")
    ranked["_tpy"] = _numeric(ranked, "leader_trades_per_year")

    ranked = ranked.sort_values(
        by=[
            "_accepted",
            "_quality",
            "_oos_pf",
            "_recent_pf",
            "_calmar",
            "_dsr",
            "_leader_pf",
            "_max_dd",
            "_net_pnl",
            "_tpy",
        ],
        ascending=[False, True, False, False, False, False, False, True, False, False],
    )
    return ranked.drop(columns=[c for c in ranked.columns if c.startswith("_")], errors="ignore").reset_index(drop=True)
