"""
Master Strategy Engine
Project: Python Master Strategy Creator
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

import pandas as pd

from modules.config_loader import get_nested, load_config
from modules.bootcamp_scoring import add_bootcamp_scores
from modules.data_loader import load_tradestation_csv
from modules.engine import EngineConfig, MasterStrategyEngine
from modules.feature_builder import add_precomputed_features
from modules.portfolio_evaluator import evaluate_portfolio
from modules.progress import ProgressTracker
from modules.strategy_types import get_strategy_type, list_strategy_types

# =============================================================================
# CONFIGURATION
# =============================================================================

_cfg = load_config()

CSV_PATH = Path(get_nested(_cfg, "datasets", default=[{}])[0].get("path", "Data/ES_60m_2008_2026_tradestation.csv"))
STRATEGY_TYPE_NAME = get_nested(_cfg, "strategy_types", default="all")
OUTPUTS_DIR = Path(get_nested(_cfg, "output_dir", default="Outputs"))

MAX_WORKERS_SWEEP = get_nested(_cfg, "pipeline", "max_workers_sweep", default=10)
MAX_WORKERS_REFINEMENT = get_nested(_cfg, "pipeline", "max_workers_refinement", default=10)
MAX_CANDIDATES_TO_REFINE = get_nested(_cfg, "pipeline", "max_candidates_to_refine", default=3)

# Final leaderboard acceptance gate
FINAL_MIN_NET_PNL = get_nested(_cfg, "leaderboard", "min_net_pnl", default=0.0)
FINAL_MIN_PF = get_nested(_cfg, "leaderboard", "min_pf", default=1.00)
FINAL_MIN_OOS_PF = get_nested(_cfg, "leaderboard", "min_oos_pf", default=1.00)
FINAL_MIN_TOTAL_TRADES = get_nested(_cfg, "leaderboard", "min_total_trades", default=60)

# Bootcamp scoring contract
# -------------------------
# Session 30 adds a second, prop-firm-oriented ranking layer alongside the
# classic research leaderboard. The actual score calculation lives in
# modules/bootcamp_scoring.py, but we define the expected input and derived
# fields here so leaderboard rows stay explicit and inspectable.
#
# Intended formula shape:
# - reward profitability and survivability: PF, OOS PF, recent PF
# - penalize large drawdown relative to profit
# - penalize weak trade frequency
# - penalize weak or unstable quality flags
# - reward yearly consistency when available
#
# Each family leaderboard row should expose these raw inputs so the Bootcamp
# scorer can remain deterministic and explainable instead of reaching back into
# engine internals.
BOOTCAMP_INPUT_FIELDS = [
    "leader_pf",
    "leader_net_pnl",
    "leader_max_drawdown",
    "leader_trades",
    "leader_trades_per_year",
    "is_pf",
    "oos_pf",
    "recent_12m_pf",
    "quality_flag",
    "leader_quality_score",
    "leader_pct_profitable_years",
    "leader_max_consecutive_losing_years",
    "leader_consistency_flag",
]

BOOTCAMP_DERIVED_FIELDS = [
    "bootcamp_drawdown_to_profit_ratio",
    "bootcamp_trade_frequency_score",
    "bootcamp_oos_score",
    "bootcamp_consistency_score",
    "bootcamp_quality_penalty",
]


# =============================================================================
# GENERIC HELPERS
# =============================================================================

def parse_money(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("$", "").replace(",", "").strip()
    return float(text) if text else 0.0


def parse_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).replace(",", "").strip()
    return int(float(text)) if text else 0


def call_first_available(obj: Any, method_names: list[str], *args, **kwargs):
    for method_name in method_names:
        method = getattr(obj, method_name, None)
        if callable(method):
            return method(*args, **kwargs)
    raise AttributeError(f"{obj.__class__.__name__} does not implement any of: {method_names}")


def get_required_sma_lengths(strategy_type: Any, timeframe: str = "60m") -> list[int]:
    return call_first_available(strategy_type, ["get_required_sma_lengths"], timeframe=timeframe)


def get_required_avg_range_lookbacks(strategy_type: Any, timeframe: str = "60m") -> list[int]:
    return call_first_available(strategy_type, ["get_required_avg_range_lookbacks"], timeframe=timeframe)


def get_required_momentum_lookbacks(strategy_type: Any, timeframe: str = "60m") -> list[int]:
    return call_first_available(strategy_type, ["get_required_momentum_lookbacks"], timeframe=timeframe)


def build_sanity_check_strategy(strategy_type: Any):
    return call_first_available(
        strategy_type,
        ["build_sanity_check_strategy", "get_sanity_check_strategy", "build_default_strategy"],
    )


def run_family_filter_combination_sweep(
    strategy_type: Any,
    data: pd.DataFrame,
    cfg: EngineConfig,
    max_workers: int,
    progress_callback: Any = None,
) -> pd.DataFrame:
    return call_first_available(
        strategy_type,
        ["run_filter_combination_sweep", "run_family_filter_combination_sweep"],
        data=data,
        cfg=cfg,
        max_workers=max_workers,
        progress_callback=progress_callback,
    )


def estimate_compute_budget(
    stage: str,
    n_evaluations: int,
    avg_seconds_per_eval: float = 0.5,
) -> dict[str, float]:
    """Print and return a compute budget estimate before running a stage."""
    estimated_minutes = (n_evaluations * avg_seconds_per_eval) / 60.0
    print(f"\nCOMPUTE BUDGET - {stage}")
    print(f"   Evaluations:  {n_evaluations:,}")
    print(f"   Est. time:    {estimated_minutes:.1f} minutes (at {avg_seconds_per_eval:.2f}s/eval)")
    return {
        "stage": stage,
        "n_evaluations": n_evaluations,
        "estimated_minutes": round(estimated_minutes, 2),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Master Strategy Engine")
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to config YAML file (default: config.yaml)",
    )
    return parser.parse_args()


def get_promotion_gate_config(strategy_type: Any) -> dict[str, Any]:
    return call_first_available(strategy_type, ["get_promotion_gate_config"])


def run_top_combo_refinement(
    strategy_type: Any,
    data: pd.DataFrame,
    cfg: EngineConfig,
    candidate_row: dict[str, Any],
    max_workers: int,
    progress_callback: Any = None,
) -> pd.DataFrame:
    return call_first_available(
        strategy_type,
        ["run_top_combo_refinement", "run_refinement_for_candidate"],
        data=data,
        cfg=cfg,
        candidate_row=candidate_row,
        max_workers=max_workers,
        progress_callback=progress_callback,
    )


# =============================================================================
# PROMOTION GATE
# =============================================================================

def apply_promotion_gate(combo_results_df: pd.DataFrame, promotion_gate: dict[str, Any]) -> pd.DataFrame:
    """
    Sweep promotion is intentionally looser than final leaderboard acceptance.

    Sweep goal:
    - let promising candidates through
    - do not kill things too early just because avg trade is temporarily weak
    """
    if combo_results_df is None or combo_results_df.empty:
        return pd.DataFrame()

    min_pf = float(promotion_gate.get("min_profit_factor", 0.0))
    require_positive_net_pnl = bool(promotion_gate.get("require_positive_net_pnl", False))
    min_trades = int(promotion_gate.get("min_trades", 0))
    min_trades_per_year = float(promotion_gate.get("min_trades_per_year", 0.0))

    promoted = combo_results_df.copy()

    if "profit_factor" in promoted.columns:
        promoted = promoted[promoted["profit_factor"] >= min_pf]

    if require_positive_net_pnl and "net_pnl" in promoted.columns:
        promoted = promoted[promoted["net_pnl"] > 0]

    if "total_trades" in promoted.columns:
        promoted = promoted[promoted["total_trades"] >= min_trades]

    if "trades_per_year" in promoted.columns:
        promoted = promoted[promoted["trades_per_year"] >= min_trades_per_year]

    if promoted.empty:
        return promoted

    sort_cols = [c for c in ["net_pnl", "profit_factor", "average_trade", "total_trades"] if c in promoted.columns]
    if sort_cols:
        promoted = promoted.sort_values(by=sort_cols, ascending=[False] * len(sort_cols)).reset_index(drop=True)

    if "strategy_name" in promoted.columns:
        promoted = promoted.drop_duplicates(subset=["strategy_name"]).reset_index(drop=True)

    max_candidates = int(promotion_gate.get("max_promoted_candidates", 50))

    if len(promoted) > max_candidates:
        if "quality_score" in promoted.columns:
            qs = promoted["quality_score"].fillna(0.0)
            oos = promoted["oos_pf"].fillna(0.0) if "oos_pf" in promoted.columns else pd.Series(0.0, index=promoted.index)
            tpy = promoted["trades_per_year"].fillna(0.0) if "trades_per_year" in promoted.columns else pd.Series(0.0, index=promoted.index)

            def _normalize(s: pd.Series) -> pd.Series:
                r = s.max() - s.min()
                return (s - s.min()) / r if r > 0 else s * 0.0

            promoted = promoted.copy()
            promoted["_composite_rank"] = (
                _normalize(qs) * 0.4
                + _normalize(oos) * 0.3
                + _normalize(tpy) * 0.3
            )
            promoted = promoted.nlargest(max_candidates, "_composite_rank")
            promoted = promoted.drop(columns=["_composite_rank"])
        else:
            promoted = promoted.head(max_candidates)

        promoted = promoted.reset_index(drop=True)

    return promoted


def print_promotion_gate_report(strategy_type_name: str, promotion_gate: dict[str, Any], promoted_df: pd.DataFrame) -> None:
    print(f"\nPromotion Gate Results for strategy type: {strategy_type_name}")
    print(f"Minimum PF required: {promotion_gate.get('min_profit_factor', 0.0):.2f}")

    if promoted_df.empty:
        print("\nNo candidates passed the promotion gate.")
        return

    display_cols = [
        c for c in [
            "strategy_name",
            "profit_factor",
            "average_trade",
            "net_pnl",
            "total_trades",
            "trades_per_year",
            "filters",
        ]
        if c in promoted_df.columns
    ]

    max_candidates = int(promotion_gate.get("max_promoted_candidates", 50))
    cap_note = f" - capped at {max_candidates}" if len(promoted_df) == max_candidates else ""
    print(f"\nPromoted Candidates ({len(promoted_df)} Distinct{cap_note}):")
    print(promoted_df[display_cols].head(10).to_string(index=False))


def deduplicate_promoted_candidates(
    promoted_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Remove near-duplicate filter combos from promoted candidates.
    Two combos are duplicates if they have identical total_trades AND
    their net_pnl values are within 1% of each other.
    """
    if promoted_df is None or promoted_df.empty or len(promoted_df) <= 1:
        return promoted_df

    keep_mask = [True] * len(promoted_df)

    for i in range(len(promoted_df)):
        if not keep_mask[i]:
            continue
        for j in range(i + 1, len(promoted_df)):
            if not keep_mask[j]:
                continue

            trades_i = promoted_df.iloc[i].get("total_trades", 0)
            trades_j = promoted_df.iloc[j].get("total_trades", 0)
            pnl_i = promoted_df.iloc[i].get("net_pnl", 0.0)
            pnl_j = promoted_df.iloc[j].get("net_pnl", 0.0)

            if trades_i == trades_j and trades_i > 0:
                pnl_diff = abs(pnl_i - pnl_j) / max(abs(pnl_i), 1.0)
                if pnl_diff < 0.01:
                    score_i = promoted_df.iloc[i].get("quality_score", promoted_df.iloc[i].get("profit_factor", 0.0))
                    score_j = promoted_df.iloc[j].get("quality_score", promoted_df.iloc[j].get("profit_factor", 0.0))
                    if score_j > score_i:
                        keep_mask[i] = False
                        break
                    else:
                        keep_mask[j] = False

    original_count = len(promoted_df)
    result = promoted_df[keep_mask].reset_index(drop=True)
    removed = original_count - len(result)

    if removed > 0:
        print(f"\nDeduplication: {original_count} -> {len(result)} candidates (removed {removed} near-duplicates)")
    else:
        print(f"\nDeduplication: no near-duplicates found in {original_count} candidates")

    return result


def save_csv_if_not_empty(df: pd.DataFrame, filepath: Path) -> None:
    if df is None or df.empty:
        return
    filepath.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(filepath, index=False)


# =============================================================================
# SANITY CHECK
# =============================================================================

def run_sanity_check(strategy_type: Any, data: pd.DataFrame, cfg: EngineConfig) -> dict[str, Any]:
    strategy = build_sanity_check_strategy(strategy_type)
    engine = MasterStrategyEngine(data=data, config=cfg)
    engine.run(strategy=strategy)

    results = engine.results()
    print("\nSanity Check run completed.")

    return {
        "strategy_name": str(results.get("Strategy", "UnknownStrategy")),
        "total_trades": parse_int(results.get("Total Trades", 0)),
        "profit_factor": float(results.get("Profit Factor", 0.0)),
        "average_trade": parse_money(results.get("Average Trade", 0.0)),
        "net_pnl": parse_money(results.get("Net PnL", 0.0)),
    }


# =============================================================================
# FAMILY SUMMARY
# =============================================================================

def _extract_best_refined_param(best_refined: dict[str, Any], key: str, default: Any) -> Any:
    value = best_refined.get(key, default)
    return default if value is None or value == "" else value


def build_family_summary_row(
    strategy_type_name: str,
    dataset_path: Path,
    data: pd.DataFrame,
    sanity_check: dict[str, Any],
    combo_results_df: pd.DataFrame,
    promoted_df: pd.DataFrame,
    refinement_df: pd.DataFrame | None,
) -> dict[str, Any]:
    best_combo = combo_results_df.iloc[0].to_dict() if combo_results_df is not None and not combo_results_df.empty else {}
    best_refined = refinement_df.iloc[0].to_dict() if refinement_df is not None and not refinement_df.empty else {}
    promotion_status = "NO_PROMOTED_CANDIDATES" if promoted_df is None or promoted_df.empty else "PROMOTED"

    return {
        "strategy_type": strategy_type_name,
        "dataset": dataset_path.name,
        "rows": len(data),
        "start": str(data.index.min()),
        "end": str(data.index.max()),
        "sanity_strategy_name": sanity_check.get("strategy_name", "NONE"),
        "sanity_total_trades": sanity_check.get("total_trades", 0),
        "total_combinations": len(combo_results_df) if combo_results_df is not None else 0,
        "promoted_candidates": len(promoted_df) if promoted_df is not None else 0,
        "promotion_status": promotion_status,

        "best_combo_strategy_name": best_combo.get("strategy_name", "NONE"),
        "best_combo_profit_factor": float(best_combo.get("profit_factor", 0.0) or 0.0),
        "best_combo_average_trade": float(best_combo.get("average_trade", 0.0) or 0.0),
        "best_combo_net_pnl": float(best_combo.get("net_pnl", 0.0) or 0.0),
        "best_combo_total_trades": int(best_combo.get("total_trades", 0) or 0),
        "best_combo_filters": str(best_combo.get("filters", "")),
        "best_combo_filter_class_names": str(best_combo.get("filter_class_names", "")),
        "best_combo_is_trades": int(best_combo.get("is_trades", 0) or 0),
        "best_combo_oos_trades": int(best_combo.get("oos_trades", 0) or 0),
        "best_combo_is_pf": float(best_combo.get("is_pf", 0.0) or 0.0),
        "best_combo_oos_pf": float(best_combo.get("oos_pf", 0.0) or 0.0),
        "best_combo_recent_12m_trades": int(best_combo.get("recent_12m_trades", 0) or 0),
        "best_combo_recent_12m_pf": float(best_combo.get("recent_12m_pf", 0.0) or 0.0),
        "best_combo_trades_per_year": float(best_combo.get("trades_per_year", 0.0) or 0.0),
        "best_combo_max_drawdown": float(best_combo.get("max_drawdown", 0.0) or 0.0),
        "best_combo_quality_flag": str(best_combo.get("quality_flag", "UNKNOWN")),
        "best_combo_quality_score": float(best_combo.get("quality_score", 0.0) or 0.0),
        "best_combo_pct_profitable_years": float(best_combo.get("pct_profitable_years", 0.0) or 0.0),
        "best_combo_max_consecutive_losing_years": int(best_combo.get("max_consecutive_losing_years", 0) or 0),
        "best_combo_consistency_flag": str(best_combo.get("consistency_flag", "INSUFFICIENT_DATA")),
        "best_combo_exit_type": "time_stop",
        "best_combo_trailing_stop_atr": None,
        "best_combo_profit_target_atr": None,
        "best_combo_signal_exit_reference": None,

        "refinement_ran": refinement_df is not None and not refinement_df.empty,
        "accepted_refinement_rows": len(refinement_df) if refinement_df is not None else 0,

        "best_refined_strategy_name": best_refined.get("strategy_name", "NONE"),
        "best_refined_profit_factor": float(best_refined.get("profit_factor", 0.0) or 0.0),
        "best_refined_average_trade": float(best_refined.get("average_trade", 0.0) or 0.0),
        "best_refined_net_pnl": float(best_refined.get("net_pnl", 0.0) or 0.0),
        "best_refined_total_trades": int(best_refined.get("total_trades", 0) or 0),
        "best_refined_hold_bars": int(_extract_best_refined_param(best_refined, "hold_bars", 0) or 0),
        "best_refined_stop_distance_points": float(_extract_best_refined_param(best_refined, "stop_distance_points", 0.0) or 0.0),
        "best_refined_min_avg_range": float(_extract_best_refined_param(best_refined, "min_avg_range", 0.0) or 0.0),
        "best_refined_momentum_lookback": int(_extract_best_refined_param(best_refined, "momentum_lookback", 0) or 0),
        "best_refined_is_trades": int(_extract_best_refined_param(best_refined, "is_trades", 0)),
        "best_refined_oos_trades": int(_extract_best_refined_param(best_refined, "oos_trades", 0)),
        "best_refined_is_pf": float(_extract_best_refined_param(best_refined, "is_pf", 0.0)),
        "best_refined_oos_pf": float(_extract_best_refined_param(best_refined, "oos_pf", 0.0)),
        "best_refined_recent_12m_trades": int(_extract_best_refined_param(best_refined, "recent_12m_trades", 0)),
        "best_refined_recent_12m_pf": float(_extract_best_refined_param(best_refined, "recent_12m_pf", 0.0)),
        "best_refined_trades_per_year": float(_extract_best_refined_param(best_refined, "trades_per_year", 0.0)),
        "best_refined_max_drawdown": float(_extract_best_refined_param(best_refined, "max_drawdown", 0.0)),
        "best_refined_quality_flag": str(_extract_best_refined_param(best_refined, "quality_flag", "UNKNOWN")),
        "best_refined_quality_score": float(_extract_best_refined_param(best_refined, "quality_score", 0.0)),
        "best_refined_pct_profitable_years": float(_extract_best_refined_param(best_refined, "pct_profitable_years", 0.0)),
        "best_refined_max_consecutive_losing_years": int(_extract_best_refined_param(best_refined, "max_consecutive_losing_years", 0)),
        "best_refined_consistency_flag": str(_extract_best_refined_param(best_refined, "consistency_flag", "INSUFFICIENT_DATA")),
        "best_refined_exit_type": str(_extract_best_refined_param(best_refined, "exit_type", "time_stop")),
        "best_refined_trailing_stop_atr": _extract_best_refined_param(best_refined, "trailing_stop_atr", None),
        "best_refined_profit_target_atr": _extract_best_refined_param(best_refined, "profit_target_atr", None),
        "best_refined_signal_exit_reference": _extract_best_refined_param(best_refined, "signal_exit_reference", None),
    }


def print_family_summary(summary_row: dict[str, Any]) -> None:
    print("\n" + "=" * 72 + "\nFAMILY RUN SUMMARY\n" + "=" * 72)
    print(f"Strategy Type:            {summary_row['strategy_type']}")
    print(f"Dataset:                  {summary_row['dataset']}")
    print(f"Rows:                     {summary_row['rows']:,}")
    print(f"Start:                    {summary_row['start']}")
    print(f"End:                      {summary_row['end']}")

    print("\n--- Combination Sweep ---")
    print(f"Total Combinations:       {summary_row['total_combinations']}")
    print(f"Promoted Candidates:      {summary_row['promoted_candidates']}")

    print("\n--- Best Promoted Combo ---")
    print(f"Strategy:                 {summary_row['best_combo_strategy_name']}")
    print(f"PF:                       {summary_row['best_combo_profit_factor']:.2f}")
    print(f"Net PnL:                  {summary_row['best_combo_net_pnl']:.2f}")
    print(f"Total Trades:             {summary_row['best_combo_total_trades']}")

    print("\n--- Best Refined Candidate ---")
    print(f"Strategy:                 {summary_row['best_refined_strategy_name']}")
    print(f"Quality Flag:             {summary_row['best_refined_quality_flag']}")
    print(f"PF:                       {summary_row['best_refined_profit_factor']:.2f}")
    print(f"Net PnL:                  {summary_row['best_refined_net_pnl']:.2f}")
    print(f"Total Trades:             {summary_row['best_refined_total_trades']}")
    print("=" * 72)


# =============================================================================
# LEADERBOARD SELECTION
# =============================================================================

def _choose_family_leader(row: pd.Series) -> dict[str, Any]:
    """
    Rule:
    - if no refinement ran -> combo wins
    - if refinement ran -> refined wins only if net pnl improves
    - if tied on net pnl -> refined must have PF >= combo PF
    """
    combo = {
        "leader_source": "combo",
        "leader_strategy_name": row.get("best_combo_strategy_name", "NONE"),
        "leader_pf": row.get("best_combo_profit_factor", 0.0),
        "leader_avg_trade": row.get("best_combo_average_trade", 0.0),
        "leader_net_pnl": row.get("best_combo_net_pnl", 0.0),
        "leader_trades": row.get("best_combo_total_trades", 0),
        "quality_flag": row.get("best_combo_quality_flag", "UNKNOWN"),
        "is_trades": row.get("best_combo_is_trades", 0),
        "oos_trades": row.get("best_combo_oos_trades", 0),
        "is_pf": row.get("best_combo_is_pf", 0.0),
        "oos_pf": row.get("best_combo_oos_pf", 0.0),
        "recent_12m_trades": row.get("best_combo_recent_12m_trades", 0),
        "recent_12m_pf": row.get("best_combo_recent_12m_pf", 0.0),
        "leader_trades_per_year": row.get("best_combo_trades_per_year", 0.0),
        "leader_max_drawdown": row.get("best_combo_max_drawdown", 0.0),
        "leader_hold_bars": 0,
        "leader_stop_distance_points": 0.0,
        "leader_min_avg_range": 0.0,
        "leader_momentum_lookback": 0,
        "leader_quality_score": row.get("best_combo_quality_score", 0.0),
        "leader_pct_profitable_years": row.get("best_combo_pct_profitable_years", 0.0),
        "leader_max_consecutive_losing_years": row.get("best_combo_max_consecutive_losing_years", 0),
        "leader_consistency_flag": row.get("best_combo_consistency_flag", "INSUFFICIENT_DATA"),
        "leader_exit_type": row.get("best_combo_exit_type", "time_stop"),
        "leader_trailing_stop_atr": row.get("best_combo_trailing_stop_atr"),
        "leader_profit_target_atr": row.get("best_combo_profit_target_atr"),
        "leader_signal_exit_reference": row.get("best_combo_signal_exit_reference"),
    }

    if not bool(row.get("refinement_ran", False)):
        return combo

    refined = {
        "leader_source": "refined",
        "leader_strategy_name": row.get("best_refined_strategy_name", "NONE"),
        "leader_pf": row.get("best_refined_profit_factor", 0.0),
        "leader_avg_trade": row.get("best_refined_average_trade", 0.0),
        "leader_net_pnl": row.get("best_refined_net_pnl", 0.0),
        "leader_trades": row.get("best_refined_total_trades", 0),
        "quality_flag": row.get("best_refined_quality_flag", "UNKNOWN"),
        "is_trades": row.get("best_refined_is_trades", 0),
        "oos_trades": row.get("best_refined_oos_trades", 0),
        "is_pf": row.get("best_refined_is_pf", 0.0),
        "oos_pf": row.get("best_refined_oos_pf", 0.0),
        "recent_12m_trades": row.get("best_refined_recent_12m_trades", 0),
        "recent_12m_pf": row.get("best_refined_recent_12m_pf", 0.0),
        "leader_trades_per_year": row.get("best_refined_trades_per_year", 0.0),
        "leader_max_drawdown": row.get("best_refined_max_drawdown", 0.0),
        "leader_hold_bars": row.get("best_refined_hold_bars", 0),
        "leader_stop_distance_points": row.get("best_refined_stop_distance_points", 0.0),
        "leader_min_avg_range": row.get("best_refined_min_avg_range", 0.0),
        "leader_momentum_lookback": row.get("best_refined_momentum_lookback", 0),
        "leader_quality_score": row.get("best_refined_quality_score", 0.0),
        "leader_pct_profitable_years": row.get("best_refined_pct_profitable_years", 0.0),
        "leader_max_consecutive_losing_years": row.get("best_refined_max_consecutive_losing_years", 0),
        "leader_consistency_flag": row.get("best_refined_consistency_flag", "INSUFFICIENT_DATA"),
        "leader_exit_type": row.get("best_refined_exit_type", "time_stop"),
        "leader_trailing_stop_atr": row.get("best_refined_trailing_stop_atr"),
        "leader_profit_target_atr": row.get("best_refined_profit_target_atr"),
        "leader_signal_exit_reference": row.get("best_refined_signal_exit_reference"),
    }

    combo_net = float(combo["leader_net_pnl"] or 0.0)
    refined_net = float(refined["leader_net_pnl"] or 0.0)
    combo_pf = float(combo["leader_pf"] or 0.0)
    refined_pf = float(refined["leader_pf"] or 0.0)

    if refined_net > combo_net:
        return refined

    if refined_net == combo_net and refined_pf >= combo_pf:
        return refined

    return combo


def _passes_final_leaderboard_gate(row: pd.Series) -> bool:
    leader_net = float(row.get("leader_net_pnl", 0.0) or 0.0)
    leader_pf = float(row.get("leader_pf", 0.0) or 0.0)
    oos_pf = float(row.get("oos_pf", 0.0) or 0.0)
    leader_trades = int(row.get("leader_trades", 0) or 0)

    if leader_net <= FINAL_MIN_NET_PNL:
        return False
    if leader_pf < FINAL_MIN_PF:
        return False
    if oos_pf < FINAL_MIN_OOS_PF:
        return False
    if leader_trades < FINAL_MIN_TOTAL_TRADES:
        return False

    return True


def build_family_leaderboard(summary_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df.empty:
        return pd.DataFrame()

    leaderboard = summary_df.copy()
    leader_rows = leaderboard.apply(_choose_family_leader, axis=1, result_type="expand")
    leaderboard = pd.concat([leaderboard, leader_rows], axis=1)

    leaderboard["accepted_final"] = leaderboard.apply(_passes_final_leaderboard_gate, axis=1)
    leaderboard = add_bootcamp_scores(leaderboard)

    leaderboard = leaderboard.sort_values(
        by=["accepted_final", "leader_net_pnl", "leader_pf", "leader_avg_trade"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)

    keep_cols = [
        "strategy_type",
        "dataset",
        "promotion_status",
        "promoted_candidates",
        "leader_source",
        "leader_strategy_name",
        "accepted_final",
        "quality_flag",
        "is_trades",
        "oos_trades",
        "is_pf",
        "oos_pf",
        "recent_12m_trades",
        "recent_12m_pf",
        "leader_pf",
        "leader_avg_trade",
        "leader_net_pnl",
        "leader_trades",
        "leader_trades_per_year",
        "leader_max_drawdown",
        "leader_quality_score",
        "leader_pct_profitable_years",
        "leader_max_consecutive_losing_years",
        "leader_consistency_flag",
        "bootcamp_score",
        "bootcamp_profitability_score",
        "bootcamp_drawdown_score",
        "bootcamp_oos_score",
        "bootcamp_consistency_score",
        "bootcamp_trade_count_score",
        "bootcamp_quality_penalty",
        "bootcamp_drawdown_to_profit_ratio",
        "leader_hold_bars",
        "leader_stop_distance_points",
        "leader_min_avg_range",
        "leader_momentum_lookback",
        "leader_exit_type",
        "leader_trailing_stop_atr",
        "leader_profit_target_atr",
        "leader_signal_exit_reference",
        "best_combo_strategy_name",
        "best_combo_filters",
        "best_combo_filter_class_names",
        "best_refined_strategy_name",
        "best_combo_exit_type",
        "best_combo_trailing_stop_atr",
        "best_combo_profit_target_atr",
        "best_combo_signal_exit_reference",
        "best_refined_exit_type",
        "best_refined_trailing_stop_atr",
        "best_refined_profit_target_atr",
        "best_refined_signal_exit_reference",
    ]

    return leaderboard[[c for c in keep_cols if c in leaderboard.columns]].copy()


def build_family_bootcamp_leaderboard(summary_df: pd.DataFrame) -> pd.DataFrame:
    classic = build_family_leaderboard(summary_df)
    if classic.empty:
        return pd.DataFrame()

    sort_cols = [c for c in ["accepted_final", "bootcamp_score", "oos_pf", "leader_net_pnl"] if c in classic.columns]
    if not sort_cols:
        return classic.reset_index(drop=True)

    return classic.sort_values(
        by=sort_cols,
        ascending=[False] * len(sort_cols),
    ).reset_index(drop=True)


# =============================================================================
# FAMILY RUN
# =============================================================================

def run_single_family(
    strategy_type_name: str,
    dataset_path: Path,
    outputs_dir: Path,
    max_workers_sweep: int,
    max_workers_refinement: int,
    market_symbol: str,
    timeframe: str = "60m",
    tracker: ProgressTracker | None = None,
) -> dict[str, Any]:
    family_start = time.perf_counter()
    strategy_type = get_strategy_type(strategy_type_name)

    if tracker is not None:
        tracker.start_family(strategy_type_name)

    print(f"\nSelected strategy type: {strategy_type_name}")
    print(f"Available strategy types: {list_strategy_types()}")
    print("\nLoading data from:", dataset_path)

    data = load_tradestation_csv(dataset_path, debug=True)

    cfg = EngineConfig(
        initial_capital=get_nested(_cfg, "engine", "initial_capital", default=250_000.0),
        risk_per_trade=get_nested(_cfg, "engine", "risk_per_trade", default=0.01),
        symbol=market_symbol,
        commission_per_contract=get_nested(_cfg, "engine", "commission_per_contract", default=2.00),
        slippage_ticks=get_nested(_cfg, "engine", "slippage_ticks", default=4),
        tick_value=get_nested(_cfg, "engine", "tick_value", default=12.50),
        dollars_per_point=get_nested(_cfg, "engine", "dollars_per_point", default=50.0),
        oos_split_date=get_nested(_cfg, "pipeline", "oos_split_date", default="2019-01-01"),
        timeframe=timeframe,
    )

    # Memory estimation — warn if parallel copies of the dataframe may exceed RAM budget
    data_mb = data.memory_usage(deep=True).sum() / 1_048_576
    est_parallel_mb = data_mb * max_workers_sweep
    print(f"\nData: {len(data):,} bars, {data_mb:.1f} MB per copy")
    print(f"   Parallel estimate: {est_parallel_mb:.0f} MB for {max_workers_sweep} workers")
    max_memory_gb = get_nested(_cfg, "pipeline", "max_memory_gb", default=None)
    if max_memory_gb is not None and est_parallel_mb > float(max_memory_gb) * 1024:
        adjusted_workers = max(2, int(float(max_memory_gb) * 1024 / data_mb))
        print(f"   Auto-reducing sweep workers from {max_workers_sweep} to {adjusted_workers} to fit memory budget ({max_memory_gb} GB)")
        max_workers_sweep = adjusted_workers
    elif est_parallel_mb > 60_000:
        print(f"   WARNING: Estimated memory usage ({est_parallel_mb:.0f} MB) is high — consider reducing max_workers or adding max_memory_gb to config.")

    print(f"\n Adding precomputed feature columns for strategy type: {strategy_type_name} (timeframe={timeframe})")
    data = add_precomputed_features(
        data,
        sma_lengths=get_required_sma_lengths(strategy_type, timeframe=timeframe),
        avg_range_lookbacks=get_required_avg_range_lookbacks(strategy_type, timeframe=timeframe),
        momentum_lookbacks=get_required_momentum_lookbacks(strategy_type, timeframe=timeframe),
    )

    sanity_check = run_sanity_check(strategy_type=strategy_type, data=data, cfg=cfg)

    from itertools import combinations as _combs
    filter_classes = strategy_type.get_filter_classes()
    n_filter_combos = sum(
        len(list(_combs(filter_classes, r)))
        for r in range(strategy_type.min_filters_per_combo, len(filter_classes) + 1)
    )
    estimate_compute_budget(
        stage=f"{strategy_type_name} filter sweep",
        n_evaluations=n_filter_combos,
    )

    if tracker is not None:
        tracker.reset_stage_timer()
    sweep_start = time.perf_counter()
    combo_results_df = run_family_filter_combination_sweep(
        strategy_type=strategy_type,
        data=data,
        cfg=cfg,
        max_workers=max_workers_sweep,
        progress_callback=tracker.update_sweep if tracker is not None else None,
    )
    sweep_elapsed = time.perf_counter() - sweep_start

    combo_results_path = outputs_dir / f"{strategy_type_name}_filter_combination_sweep_results.csv"
    save_csv_if_not_empty(combo_results_df, combo_results_path)

    print(f"\nFilter combination sweep runtime: {sweep_elapsed:.2f} seconds")

    promotion_gate = get_promotion_gate_config(strategy_type)
    promoted_df = apply_promotion_gate(combo_results_df, promotion_gate)
    print_promotion_gate_report(strategy_type_name, promotion_gate, promoted_df)

    if tracker is not None:
        tracker.log_promotion(
            count=len(promoted_df) if promoted_df is not None else 0,
            cap=int(promotion_gate.get("max_promoted_candidates", 20)),
        )

    if promoted_df is not None and not promoted_df.empty:
        promoted_df = deduplicate_promoted_candidates(promoted_df)

    promoted_path = outputs_dir / f"{strategy_type_name}_promoted_candidates.csv"
    save_csv_if_not_empty(promoted_df, promoted_path)

    refinement_df: pd.DataFrame | None = None
    all_accepted_refinements: list[pd.DataFrame] = []

    if promoted_df is None or promoted_df.empty:
        print(f"\nSkipping {strategy_type_name} refinement because no candidates were promoted.")
    else:
        n_candidates = min(len(promoted_df), MAX_CANDIDATES_TO_REFINE)
        sample_candidate = {**promoted_df.iloc[0].to_dict(), "timeframe": cfg.timeframe}
        sample_grid = call_first_available(
            strategy_type,
            ["get_refinement_grid_for_candidate"],
            sample_candidate,
        )
        grid_size = 1
        for values in sample_grid.values():
            grid_size *= len(values)

        from modules.config_loader import get_timeframe_multiplier as _gtm
        _mult = _gtm(cfg.timeframe)
        _tf_note = f"{cfg.timeframe} timeframe, multiplier={_mult:.3g}x" if cfg.timeframe != "60m" else "60m timeframe"
        estimate_compute_budget(
            stage=f"{strategy_type_name} refinement ({n_candidates} candidates × {grid_size} grid points, {_tf_note})",
            n_evaluations=n_candidates * grid_size,
        )
        print(f"   hold_bars (scaled): {sample_grid.get('hold_bars', [])}")
        print(f"   stop_distance_points (ATR-based, unscaled): {sample_grid.get('stop_distance_points', [])}")

        candidates_to_test = promoted_df.head(MAX_CANDIDATES_TO_REFINE).to_dict("records")

        for rank, candidate in enumerate(candidates_to_test, start=1):
            candidate_name = candidate.get('strategy_name', candidate.get('filters', 'UNKNOWN'))
            if tracker is not None:
                tracker.log_refinement_candidate(rank, len(candidates_to_test), candidate_name)
                tracker.reset_stage_timer()
            print(f"\n{'=' * 50}\nAttempting Refinement on Promoted Candidate #{rank}\n{'=' * 50}")
            print(f"Strategy: {candidate.get('strategy_name', 'UNKNOWN')}")
            print(f"Filters:  {candidate.get('filters', 'UNKNOWN')}")

            current_refinement_df = run_top_combo_refinement(
                strategy_type=strategy_type,
                data=data,
                cfg=cfg,
                candidate_row=candidate,
                max_workers=max_workers_refinement,
                progress_callback=tracker.update_refinement if tracker is not None else None,
            )

            if current_refinement_df is not None and not current_refinement_df.empty:
                print(f"\nRefinement successful for candidate #{rank}. Storing {len(current_refinement_df)} viable settings.")
                all_accepted_refinements.append(current_refinement_df)
            else:
                print(f"\nRefinement yielded 0 accepted rows for candidate #{rank}.")

        if all_accepted_refinements:
            print(f"\nPooling all refined results across {len(all_accepted_refinements)} candidates and sorting for the absolute best edge...")
            combined_refinements = pd.concat(all_accepted_refinements, ignore_index=True)
            combined_refinements = combined_refinements.sort_values(
                by=["net_pnl", "profit_factor", "average_trade"],
                ascending=[False, False, False],
            ).reset_index(drop=True)
            refinement_df = combined_refinements

    family_summary_row = build_family_summary_row(
        strategy_type_name=strategy_type_name,
        dataset_path=dataset_path,
        data=data,
        sanity_check=sanity_check,
        combo_results_df=combo_results_df,
        promoted_df=promoted_df,
        refinement_df=refinement_df,
    )

    print_family_summary(family_summary_row)
    family_summary_row["family_runtime_seconds"] = round(time.perf_counter() - family_start, 2)

    if tracker is not None:
        tracker.end_family(strategy_type_name)

    return family_summary_row


# =============================================================================
# MAIN
# =============================================================================

def _run_dataset(
    ds_path: Path,
    ds_market: str,
    ds_timeframe: str,
    ds_output_dir: Path,
) -> None:
    """Run the full pipeline for a single dataset and save results to ds_output_dir."""
    ds_output_dir.mkdir(parents=True, exist_ok=True)

    family_names = list_strategy_types() if STRATEGY_TYPE_NAME == "all" else [STRATEGY_TYPE_NAME]
    dataset_summaries: list[dict[str, Any]] = []

    tracker = ProgressTracker(
        output_dir=ds_output_dir,
        dataset_label=f"{ds_market}_{ds_timeframe}",
    )
    tracker.set_families(family_names)

    for family_name in family_names:
        summary_row = run_single_family(
            strategy_type_name=family_name,
            dataset_path=ds_path,
            outputs_dir=ds_output_dir,
            max_workers_sweep=MAX_WORKERS_SWEEP,
            max_workers_refinement=MAX_WORKERS_REFINEMENT,
            market_symbol=ds_market,
            timeframe=ds_timeframe,
            tracker=tracker,
        )
        dataset_summaries.append(summary_row)

    family_summary_df = pd.DataFrame(dataset_summaries)
    family_summary_df.to_csv(ds_output_dir / "family_summary_results.csv", index=False)

    leaderboard_df = build_family_leaderboard(family_summary_df)
    bootcamp_leaderboard_df = build_family_bootcamp_leaderboard(family_summary_df)
    leaderboard_path = ds_output_dir / "family_leaderboard_results.csv"
    bootcamp_leaderboard_path = ds_output_dir / "family_leaderboard_bootcamp.csv"

    if not leaderboard_df.empty:
        leaderboard_df.to_csv(leaderboard_path, index=False)
        if not bootcamp_leaderboard_df.empty:
            bootcamp_leaderboard_df.to_csv(bootcamp_leaderboard_path, index=False)

        print(f"\nLEADERBOARD - {ds_market} {ds_timeframe} (Saved to {leaderboard_path})")
        preview_cols = [
            "strategy_type",
            "leader_source",
            "leader_strategy_name",
            "accepted_final",
            "quality_flag",
            "is_trades",
            "oos_trades",
            "is_pf",
            "oos_pf",
            "recent_12m_trades",
            "recent_12m_pf",
            "leader_pf",
            "leader_net_pnl",
            "bootcamp_score",
        ]
        print(leaderboard_df[[c for c in preview_cols if c in leaderboard_df.columns]].to_string(index=False))

        if not bootcamp_leaderboard_df.empty:
            print(f"\nBOOTCAMP LEADERBOARD - {ds_market} {ds_timeframe} (Saved to {bootcamp_leaderboard_path})")
            print(bootcamp_leaderboard_df[[c for c in preview_cols if c in bootcamp_leaderboard_df.columns]].to_string(index=False))

        print("\n" + "=" * 72 + "\nSTARTING AUTOMATED PORTFOLIO EVALUATION\n" + "=" * 72)

        n_accepted = int(leaderboard_df.get("accepted_final", pd.Series(dtype=bool)).sum()) if "accepted_final" in leaderboard_df.columns else len(leaderboard_df)
        tracker.log_portfolio(n_accepted)

        review_table, returns_df, corr_matrix, yearly_df = evaluate_portfolio(
            leaderboard_csv=leaderboard_path,
            data_csv=ds_path,
            market_name=ds_market,
            timeframe=ds_timeframe,
            oos_split_date=get_nested(_cfg, "pipeline", "oos_split_date", default="2019-01-01"),
        )

        if not review_table.empty:
            review_table.to_csv(ds_output_dir / "portfolio_review_table.csv", index=False)
            returns_df.to_csv(ds_output_dir / "strategy_returns.csv", index=True)
            corr_matrix.to_csv(ds_output_dir / "correlation_matrix.csv", index=True)
            if not yearly_df.empty:
                yearly_df.to_csv(ds_output_dir / "yearly_stats_breakdown.csv", index=False)

            print("\nPORTFOLIO EVALUATION COMPLETE.")
            preview_cols = [
                "strategy_family",
                "strategy_name",
                "is_trades",
                "oos_trades",
                "is_pf_pre_2019",
                "oos_pf_post_2019",
                "mc_max_dd_99",
                "shock_drop_10pct_pnl",
            ]
            print("\n[Final Strategy Review Table]")
            print(review_table[[c for c in preview_cols if c in review_table.columns]].to_string(index=False))
        else:
            print("\nNo strategies passed final leaderboard acceptance gate for evaluation.")

    tracker.log_done()


if __name__ == "__main__":
    args = parse_args()
    _cfg = load_config(args.config)

    # Re-derive all constants from the loaded config
    CSV_PATH = Path(get_nested(_cfg, "datasets", default=[{}])[0].get("path", "Data/ES_60m_2008_2026_tradestation.csv"))
    STRATEGY_TYPE_NAME = get_nested(_cfg, "strategy_types", default="all")
    OUTPUTS_DIR = Path(get_nested(_cfg, "output_dir", default="Outputs"))
    MAX_WORKERS_SWEEP = get_nested(_cfg, "pipeline", "max_workers_sweep", default=10)
    MAX_WORKERS_REFINEMENT = get_nested(_cfg, "pipeline", "max_workers_refinement", default=10)
    MAX_CANDIDATES_TO_REFINE = get_nested(_cfg, "pipeline", "max_candidates_to_refine", default=3)
    FINAL_MIN_NET_PNL = get_nested(_cfg, "leaderboard", "min_net_pnl", default=0.0)
    FINAL_MIN_PF = get_nested(_cfg, "leaderboard", "min_pf", default=1.00)
    FINAL_MIN_OOS_PF = get_nested(_cfg, "leaderboard", "min_oos_pf", default=1.00)
    FINAL_MIN_TOTAL_TRADES = get_nested(_cfg, "leaderboard", "min_total_trades", default=60)

    total_start = time.perf_counter()
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    datasets = get_nested(_cfg, "datasets", default=[])
    if not datasets:
        # Fallback: single dataset from CSV_PATH
        filename_parts = CSV_PATH.stem.split("_")
        datasets = [
            {
                "path": str(CSV_PATH),
                "market": filename_parts[0] if filename_parts else "UNKNOWN",
                "timeframe": filename_parts[1] if len(filename_parts) > 1 else "UNKNOWN",
            }
        ]

    all_run_summaries: list[dict[str, Any]] = []

    for ds_idx, ds in enumerate(datasets):
        ds_path = Path(ds.get("path", str(CSV_PATH)))
        ds_market = ds.get("market", "UNKNOWN")
        ds_timeframe = ds.get("timeframe", "UNKNOWN")

        print(f"\n{'=' * 72}")
        print(f"DATASET {ds_idx + 1}/{len(datasets)}: {ds_market} {ds_timeframe}")
        print(f"   Path: {ds_path}")
        print(f"{'=' * 72}")

        ds_output_dir = OUTPUTS_DIR / f"{ds_market}_{ds_timeframe}"

        _run_dataset(
            ds_path=ds_path,
            ds_market=ds_market,
            ds_timeframe=ds_timeframe,
            ds_output_dir=ds_output_dir,
        )

    if len(datasets) > 1:
        print(f"\n{'=' * 72}")
        print(f"All {len(datasets)} datasets complete.")

        from modules.master_leaderboard import write_master_leaderboards

        master_lb, bootcamp_master_lb = write_master_leaderboards(outputs_root=str(OUTPUTS_DIR))
        if not master_lb.empty:
            print(f"\n{'=' * 72}")
            print(f"MASTER LEADERBOARD — {len(master_lb)} accepted strategies across all datasets")
            print(f"{'=' * 72}")
            preview_cols = [
                "rank", "market", "timeframe", "strategy_type",
                "leader_strategy_name", "quality_flag", "leader_pf",
                "leader_net_pnl", "is_pf", "oos_pf", "recent_12m_pf",
            ]
            print(master_lb[[c for c in preview_cols if c in master_lb.columns]].to_string(index=False))

            print(f"\nSaved to {OUTPUTS_DIR / 'master_leaderboard.csv'}")
            if not bootcamp_master_lb.empty:
                print(f"\n{'=' * 72}")
                print(f"BOOTCAMP MASTER LEADERBOARD â€” {len(bootcamp_master_lb)} accepted strategies across all datasets")
                print(f"{'=' * 72}")
                print(bootcamp_master_lb[[c for c in preview_cols + ['bootcamp_score'] if c in bootcamp_master_lb.columns]].to_string(index=False))
                print(f"\nSaved to {OUTPUTS_DIR / 'master_leaderboard_bootcamp.csv'}")
        else:
            print("\nNo accepted strategies found across all datasets for master leaderboard.")

    print(f"\n Total script runtime: {time.perf_counter() - total_start:.2f} seconds")
