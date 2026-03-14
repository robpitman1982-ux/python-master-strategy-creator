"""
Master Strategy Engine
Project: Python Master Strategy Creator
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pandas as pd

from modules.data_loader import load_tradestation_csv
from modules.engine import EngineConfig, MasterStrategyEngine
from modules.feature_builder import add_precomputed_features
from modules.portfolio_evaluator import evaluate_portfolio
from modules.strategy_types import get_strategy_type, list_strategy_types

CSV_PATH = Path("Data") / "ES_60m_2008_2026_tradestation.csv"
STRATEGY_TYPE_NAME = "all"
OUTPUTS_DIR = Path("Outputs")

MAX_WORKERS_SWEEP = 10
MAX_WORKERS_REFINEMENT = 10
MAX_CANDIDATES_TO_REFINE = 3


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


def get_required_sma_lengths(strategy_type: Any) -> list[int]:
    return call_first_available(strategy_type, ["get_required_sma_lengths"])


def get_required_avg_range_lookbacks(strategy_type: Any) -> list[int]:
    return call_first_available(strategy_type, ["get_required_avg_range_lookbacks"])


def get_required_momentum_lookbacks(strategy_type: Any) -> list[int]:
    return call_first_available(strategy_type, ["get_required_momentum_lookbacks"])


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
) -> pd.DataFrame:
    return call_first_available(
        strategy_type,
        ["run_filter_combination_sweep", "run_family_filter_combination_sweep"],
        data=data,
        cfg=cfg,
        max_workers=max_workers,
    )


def get_promotion_gate_config(strategy_type: Any) -> dict[str, Any]:
    return call_first_available(strategy_type, ["get_promotion_gate_config"])


def run_top_combo_refinement(
    strategy_type: Any,
    data: pd.DataFrame,
    cfg: EngineConfig,
    candidate_row: dict[str, Any],
    max_workers: int,
) -> pd.DataFrame:
    return call_first_available(
        strategy_type,
        ["run_top_combo_refinement", "run_refinement_for_candidate"],
        data=data,
        cfg=cfg,
        candidate_row=candidate_row,
        max_workers=max_workers,
    )


def apply_promotion_gate(combo_results_df: pd.DataFrame, promotion_gate: dict[str, Any]) -> pd.DataFrame:
    """
    Sweep promotion should be looser than refinement.

    Important design choice:
    - We do NOT require positive average_trade at sweep stage anymore.
    - We can still sort by average_trade later, but we do not kill candidates early for it.
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

    dedup_cols = [c for c in ["strategy_name"] if c in promoted.columns]
    if dedup_cols:
        promoted = promoted.drop_duplicates(subset=dedup_cols).reset_index(drop=True)

    return promoted


def print_promotion_gate_report(strategy_type_name: str, promotion_gate: dict[str, Any], promoted_df: pd.DataFrame) -> None:
    print(f"\n🚦 Promotion Gate Results for strategy type: {strategy_type_name}")
    print(f"Minimum PF required: {promotion_gate.get('min_profit_factor', 0.0):.2f}")

    if promoted_df.empty:
        print("\n❌ No candidates passed the promotion gate.")
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
    print(f"\n✅ Promoted Candidates ({len(promoted_df)} Distinct):")
    print(promoted_df[display_cols].head(10).to_string(index=False))


def save_csv_if_not_empty(df: pd.DataFrame, filepath: Path) -> None:
    if df is None or df.empty:
        return
    filepath.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(filepath, index=False)


def run_sanity_check(strategy_type: Any, data: pd.DataFrame, cfg: EngineConfig) -> dict[str, Any]:
    strategy = build_sanity_check_strategy(strategy_type)
    engine = MasterStrategyEngine(data=data, config=cfg)
    engine.run(strategy=strategy)

    results = engine.results()
    print("\n✅ Sanity Check run completed.")

    return {
        "strategy_name": str(results.get("Strategy", "UnknownStrategy")),
        "total_trades": parse_int(results.get("Total Trades", 0)),
        "profit_factor": float(results.get("Profit Factor", 0.0)),
        "average_trade": parse_money(results.get("Average Trade", 0.0)),
        "net_pnl": parse_money(results.get("Net PnL", 0.0)),
    }


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
        "best_combo_quality_flag": str(best_combo.get("quality_flag", "UNKNOWN")),

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
        "best_refined_quality_flag": str(_extract_best_refined_param(best_refined, "quality_flag", "UNKNOWN")),
    }


def print_family_summary(summary_row: dict[str, Any]) -> None:
    print("\n" + "=" * 72 + "\n🏁 FAMILY RUN SUMMARY\n" + "=" * 72)
    print(f"Strategy Type:            {summary_row['strategy_type']}")
    print(f"Dataset:                  {summary_row['dataset']}")
    print(f"Rows:                     {summary_row['rows']:,}")
    print(f"Start:                    {summary_row['start']}")
    print(f"End:                      {summary_row['end']}")
    print("\n--- Combination Sweep ---")
    print(f"Total Combinations:       {summary_row['total_combinations']}")
    print(f"Promoted Candidates:      {summary_row['promoted_candidates']}")
    print("\n--- Best Refined Candidate ---")
    print(f"Strategy:                 {summary_row['best_refined_strategy_name']}")
    print(f"Quality Flag:             {summary_row['best_refined_quality_flag']}")
    print(f"PF:                       {summary_row['best_refined_profit_factor']:.2f}")
    print(f"Net PnL:                  {summary_row['best_refined_net_pnl']:.2f}")
    print(f"Total Trades:             {summary_row['best_refined_total_trades']}")
    print("=" * 72)


def _choose_family_leader(row: pd.Series) -> dict[str, Any]:
    """
    Choose between combo and refined.

    Rule:
    - If no refinement ran, combo wins.
    - If refinement ran, refined only wins if it improves net_pnl.
    - If net_pnl is tied, require PF >= combo PF.
    Otherwise keep combo.
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
        "leader_hold_bars": 0,
        "leader_stop_distance_points": 0.0,
        "leader_min_avg_range": 0.0,
        "leader_momentum_lookback": 0,
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
        "leader_hold_bars": row.get("best_refined_hold_bars", 0),
        "leader_stop_distance_points": row.get("best_refined_stop_distance_points", 0.0),
        "leader_min_avg_range": row.get("best_refined_min_avg_range", 0.0),
        "leader_momentum_lookback": row.get("best_refined_momentum_lookback", 0),
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


def build_family_leaderboard(summary_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df.empty:
        return pd.DataFrame()

    leaderboard = summary_df.copy()

    leader_rows = leaderboard.apply(_choose_family_leader, axis=1, result_type="expand")
    leaderboard = pd.concat([leaderboard, leader_rows], axis=1)

    leaderboard = leaderboard.sort_values(
        by=["leader_net_pnl", "leader_pf", "leader_avg_trade"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    keep_cols = [
        "strategy_type",
        "dataset",
        "promotion_status",
        "promoted_candidates",
        "leader_source",
        "leader_strategy_name",
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
        "leader_hold_bars",
        "leader_stop_distance_points",
        "leader_min_avg_range",
        "leader_momentum_lookback",
        "best_combo_strategy_name",
        "best_combo_filters",
        "best_combo_filter_class_names",
        "best_refined_strategy_name",
    ]

    return leaderboard[[c for c in keep_cols if c in leaderboard.columns]].copy()


def run_single_family(
    strategy_type_name: str,
    dataset_path: Path,
    outputs_dir: Path,
    max_workers_sweep: int,
    max_workers_refinement: int,
    market_symbol: str,
) -> dict[str, Any]:
    family_start = time.perf_counter()
    strategy_type = get_strategy_type(strategy_type_name)

    print(f"\nSelected strategy type: {strategy_type_name}")
    print(f"Available strategy types: {list_strategy_types()}")
    print("\nLoading data from:", dataset_path)

    data = load_tradestation_csv(dataset_path, debug=True)

    cfg = EngineConfig(
        initial_capital=250_000.0,
        risk_per_trade=0.01,
        symbol=market_symbol,
    )

    print(f"\n⚙ Adding precomputed feature columns for strategy type: {strategy_type_name}")
    data = add_precomputed_features(
        data,
        sma_lengths=get_required_sma_lengths(strategy_type),
        avg_range_lookbacks=get_required_avg_range_lookbacks(strategy_type),
        momentum_lookbacks=get_required_momentum_lookbacks(strategy_type),
    )

    sanity_check = run_sanity_check(strategy_type=strategy_type, data=data, cfg=cfg)

    sweep_start = time.perf_counter()
    combo_results_df = run_family_filter_combination_sweep(
        strategy_type=strategy_type,
        data=data,
        cfg=cfg,
        max_workers=max_workers_sweep,
    )
    sweep_elapsed = time.perf_counter() - sweep_start

    combo_results_path = outputs_dir / f"{strategy_type_name}_filter_combination_sweep_results.csv"
    save_csv_if_not_empty(combo_results_df, combo_results_path)

    print(f"\n⏱ Filter combination sweep runtime: {sweep_elapsed:.2f} seconds")

    promotion_gate = get_promotion_gate_config(strategy_type)
    promoted_df = apply_promotion_gate(combo_results_df, promotion_gate)
    print_promotion_gate_report(strategy_type_name, promotion_gate, promoted_df)

    promoted_path = outputs_dir / f"{strategy_type_name}_promoted_candidates.csv"
    save_csv_if_not_empty(promoted_df, promoted_path)

    refinement_df: pd.DataFrame | None = None
    all_accepted_refinements: list[pd.DataFrame] = []

    if promoted_df is None or promoted_df.empty:
        print(f"\n⛔ Skipping {strategy_type_name} refinement because no candidates were promoted.")
    else:
        candidates_to_test = promoted_df.head(MAX_CANDIDATES_TO_REFINE).to_dict("records")

        for rank, candidate in enumerate(candidates_to_test, start=1):
            print(f"\n{'=' * 50}\n🏆 Attempting Refinement on Promoted Candidate #{rank}\n{'=' * 50}")
            print(f"Strategy: {candidate.get('strategy_name', 'UNKNOWN')}")
            print(f"Filters:  {candidate.get('filters', 'UNKNOWN')}")

            current_refinement_df = run_top_combo_refinement(
                strategy_type=strategy_type,
                data=data,
                cfg=cfg,
                candidate_row=candidate,
                max_workers=max_workers_refinement,
            )

            if current_refinement_df is not None and not current_refinement_df.empty:
                print(f"\n✅ Refinement successful for candidate #{rank}. Storing {len(current_refinement_df)} viable settings.")
                all_accepted_refinements.append(current_refinement_df)
            else:
                print(f"\n❌ Refinement yielded 0 accepted rows for candidate #{rank}.")

        if all_accepted_refinements:
            print(f"\n🧠 Pooling all refined results across {len(all_accepted_refinements)} candidates and sorting for the absolute best edge...")
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
    return family_summary_row


if __name__ == "__main__":
    total_start = time.perf_counter()
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    filename_parts = CSV_PATH.stem.split("_")
    market_symbol = filename_parts[0] if len(filename_parts) > 0 else "UNKNOWN"
    timeframe = filename_parts[1] if len(filename_parts) > 1 else "UNKNOWN"

    print(f"\n🎯 ENGINE CONFIGURATION AUTO-DETECTED:")
    print(f"   Market Symbol: {market_symbol}")
    print(f"   Timeframe:     {timeframe}\n")

    family_names = list_strategy_types() if STRATEGY_TYPE_NAME == "all" else [STRATEGY_TYPE_NAME]
    all_family_summaries: list[dict[str, Any]] = []

    for family_name in family_names:
        summary_row = run_single_family(
            strategy_type_name=family_name,
            dataset_path=CSV_PATH,
            outputs_dir=OUTPUTS_DIR,
            max_workers_sweep=MAX_WORKERS_SWEEP,
            max_workers_refinement=MAX_WORKERS_REFINEMENT,
            market_symbol=market_symbol,
        )
        all_family_summaries.append(summary_row)

    family_summary_df = pd.DataFrame(all_family_summaries)
    family_summary_path = OUTPUTS_DIR / "family_summary_results.csv"
    family_summary_df.to_csv(family_summary_path, index=False)

    leaderboard_df = build_family_leaderboard(family_summary_df)
    leaderboard_path = OUTPUTS_DIR / "family_leaderboard_results.csv"

    if not leaderboard_df.empty:
        leaderboard_df.to_csv(leaderboard_path, index=False)
        print("\n🏆 LEADERBOARD 3.0 (Saved to family_leaderboard_results.csv)")

        preview_cols = [
            "strategy_type",
            "leader_source",
            "leader_strategy_name",
            "quality_flag",
            "is_trades",
            "oos_trades",
            "is_pf",
            "oos_pf",
            "recent_12m_trades",
            "recent_12m_pf",
            "leader_pf",
            "leader_net_pnl",
        ]
        print(leaderboard_df[[c for c in preview_cols if c in leaderboard_df.columns]].to_string(index=False))

        print("\n" + "=" * 72 + "\n🔬 STARTING AUTOMATED PORTFOLIO EVALUATION\n" + "=" * 72)

        review_table, returns_df, corr_matrix, yearly_df = evaluate_portfolio(
            leaderboard_csv=leaderboard_path,
            data_csv=CSV_PATH,
            market_name=market_symbol,
            timeframe=timeframe,
        )

        if not review_table.empty:
            review_table.to_csv(OUTPUTS_DIR / "portfolio_review_table.csv", index=False)
            returns_df.to_csv(OUTPUTS_DIR / "strategy_returns.csv", index=True)
            corr_matrix.to_csv(OUTPUTS_DIR / "correlation_matrix.csv", index=True)
            if not yearly_df.empty:
                yearly_df.to_csv(OUTPUTS_DIR / "yearly_stats_breakdown.csv", index=False)

            print("\n✅ PORTFOLIO EVALUATION COMPLETE.")
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

    print(f"\n🏁 Total script runtime: {time.perf_counter() - total_start:.2f} seconds")