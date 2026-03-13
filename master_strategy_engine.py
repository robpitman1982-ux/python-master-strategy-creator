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
from modules.strategy_types import get_strategy_type, list_strategy_types


# =============================================================================
# USER SETTINGS
# =============================================================================
CSV_PATH = Path("Data") / "ES_60m_2008_2026_tradestation.csv"

# Choose one:
# "trend"
# "breakout"
# "mean_reversion"
# "all"
STRATEGY_TYPE_NAME = "mean_reversion"

OUTPUTS_DIR = Path("Outputs")
MAX_WORKERS_SWEEP = 10
MAX_WORKERS_REFINEMENT = 10
MAX_FALLBACK_CANDIDATES = 10  # Increased to 10 to ensure we catch robust edges


# =============================================================================
# HELPERS
# =============================================================================
def print_data_summary(df: pd.DataFrame, name: str = "DATA") -> None:
    print(f"\n=== {name} SUMMARY ===")
    print(f"Rows: {len(df):,}")
    print(f"Start: {df.index.min()}")
    print(f"End:   {df.index.max()}")
    print("Columns:", list(df.columns))
    print("\nHead:")
    print(df.head(3))
    print("\nTail:")
    print(df.tail(3))


def parse_money(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("$", "").replace(",", "").strip()
    if text == "":
        return 0.0
    return float(text)


def parse_percent(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("%", "").strip()
    if text == "":
        return 0.0
    return float(text)


def parse_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).replace(",", "").strip()
    if text == "":
        return 0
    return int(float(text))


def safe_get(obj: Any, attr_name: str, default: Any = None) -> Any:
    return getattr(obj, attr_name, default)


def call_first_available(obj: Any, method_names: list[str], *args, **kwargs):
    for method_name in method_names:
        method = getattr(obj, method_name, None)
        if callable(method):
            return method(*args, **kwargs)

    raise AttributeError(
        f"{obj.__class__.__name__} does not implement any of: {method_names}"
    )


def get_required_sma_lengths(strategy_type: Any) -> list[int]:
    return call_first_available(strategy_type, ["get_required_sma_lengths"])


def get_required_avg_range_lookbacks(strategy_type: Any) -> list[int]:
    return call_first_available(strategy_type, ["get_required_avg_range_lookbacks"])


def get_required_momentum_lookbacks(strategy_type: Any) -> list[int]:
    return call_first_available(strategy_type, ["get_required_momentum_lookbacks"])


def build_sanity_check_strategy(strategy_type: Any):
    return call_first_available(
        strategy_type,
        [
            "build_sanity_check_strategy",
            "get_sanity_check_strategy",
            "build_default_strategy",
        ],
    )


def run_family_filter_combination_sweep(
    strategy_type: Any,
    data: pd.DataFrame,
    cfg: EngineConfig,
    max_workers: int,
) -> pd.DataFrame:
    return call_first_available(
        strategy_type,
        [
            "run_filter_combination_sweep",
            "run_family_filter_combination_sweep",
        ],
        data=data,
        cfg=cfg,
        max_workers=max_workers,
    )


def get_promotion_gate_config(strategy_type: Any) -> dict[str, Any]:
    return call_first_available(strategy_type, ["get_promotion_gate_config"])


def build_candidate_specific_refinement_factory(
    strategy_type: Any,
    candidate_row: dict[str, Any],
):
    return call_first_available(
        strategy_type,
        [
            "build_candidate_specific_refinement_factory",
            "build_refinement_factory_from_candidate",
        ],
        candidate_row,
    )


def get_refinement_grid_for_candidate(
    strategy_type: Any,
    candidate_row: dict[str, Any],
) -> dict[str, list[Any]]:
    return call_first_available(
        strategy_type,
        [
            "get_refinement_grid_for_candidate",
            "build_refinement_grid_for_candidate",
        ],
        candidate_row,
    )


def run_top_combo_refinement(
    strategy_type: Any,
    data: pd.DataFrame,
    cfg: EngineConfig,
    candidate_row: dict[str, Any],
    max_workers: int,
) -> pd.DataFrame:
    return call_first_available(
        strategy_type,
        [
            "run_top_combo_refinement",
            "run_refinement_for_candidate",
        ],
        data=data,
        cfg=cfg,
        candidate_row=candidate_row,
        max_workers=max_workers,
    )


def apply_promotion_gate(
    combo_results_df: pd.DataFrame,
    promotion_gate: dict[str, Any],
) -> pd.DataFrame:
    if combo_results_df is None or combo_results_df.empty:
        return pd.DataFrame()

    min_pf = float(promotion_gate.get("min_profit_factor", 0.0))
    min_avg_trade = float(promotion_gate.get("min_average_trade", float("-inf")))
    require_positive_net_pnl = bool(promotion_gate.get("require_positive_net_pnl", False))
    min_trades = int(promotion_gate.get("min_trades", 0))
    min_trades_per_year = float(promotion_gate.get("min_trades_per_year", 0.0))

    promoted = combo_results_df.copy()

    if "profit_factor" in promoted.columns:
        promoted = promoted[promoted["profit_factor"] >= min_pf]

    if "average_trade" in promoted.columns:
        promoted = promoted[promoted["average_trade"] >= min_avg_trade]

    if require_positive_net_pnl and "net_pnl" in promoted.columns:
        promoted = promoted[promoted["net_pnl"] > 0]

    if "total_trades" in promoted.columns:
        promoted = promoted[promoted["total_trades"] >= min_trades]

    if "trades_per_year" in promoted.columns:
        promoted = promoted[promoted["trades_per_year"] >= min_trades_per_year]

    if promoted.empty:
        return promoted

    sort_cols: list[str] = []
    ascending: list[bool] = []

    # Sort by absolute Net PnL first
    for col in ["net_pnl", "profit_factor", "total_trades"]:
        if col in promoted.columns:
            sort_cols.append(col)
            ascending.append(False)

    if sort_cols:
        promoted = promoted.sort_values(by=sort_cols, ascending=ascending).reset_index(drop=True)

    # -------------------------------------------------------------------------
    # 💥 THE CLONE KILLER: Drop rows that generate mathematically identical results
    # -------------------------------------------------------------------------
    dedup_cols = [c for c in ["total_trades", "net_pnl", "profit_factor"] if c in promoted.columns]
    if dedup_cols:
        original_count = len(promoted)
        promoted = promoted.drop_duplicates(subset=dedup_cols).reset_index(drop=True)
        dropped_count = original_count - len(promoted)
        if dropped_count > 0:
            print(f"\n🗡️ Clone Killer Active: Eliminated {dropped_count} redundant strategies.")

    return promoted


def print_promotion_gate_report(
    strategy_type_name: str,
    promotion_gate: dict[str, Any],
    promoted_df: pd.DataFrame,
) -> None:
    print(f"\n🚦 Promotion Gate Results for strategy type: {strategy_type_name}")
    print(f"Minimum PF required: {promotion_gate.get('min_profit_factor', 0.0):.2f}")
    print(f"Minimum average trade required: {promotion_gate.get('min_average_trade', 0.0):.2f}")
    print(f"Require positive net PnL: {promotion_gate.get('require_positive_net_pnl', False)}")
    print(f"Minimum trades required (Sweep): {promotion_gate.get('min_trades', 0)}")
    print(f"Unique mathematically distinct candidates promoted: {len(promoted_df)}")

    if promoted_df.empty:
        print("\n❌ No candidates passed the promotion gate.")
        return

    display_cols = [
        "strategy_name",
        "profit_factor",
        "average_trade",
        "net_pnl",
        "total_trades",
        "trades_per_year",
        "filters",
    ]
    display_cols = [c for c in display_cols if c in promoted_df.columns]

    print("\n✅ Promoted Candidates (Top 10 Distinct):")
    print(promoted_df[display_cols].head(10))


def save_csv_if_not_empty(df: pd.DataFrame, filepath: Path) -> None:
    if df is None or df.empty:
        return
    filepath.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(filepath, index=False)


def run_sanity_check(
    strategy_type: Any,
    data: pd.DataFrame,
    cfg: EngineConfig,
) -> dict[str, Any]:
    strategy = build_sanity_check_strategy(strategy_type)
    engine = MasterStrategyEngine(data=data, config=cfg)

    print("\n🚀 Master Strategy Engine Initialized.")
    print("Engine Results Snapshot (Before Run):", engine.results())

    engine.run(strategy=strategy)

    results = engine.results()

    print("\n✅ Backtest run completed.")
    print("Engine Results Snapshot (After Run):", results)

    trades_df = engine.trades_dataframe()
    if not trades_df.empty:
        print("\nFirst 5 Trades:")
        print(trades_df.head())
    else:
        print("\nNo trades generated.")

    return {
        "strategy_name": str(results.get("Strategy", "UnknownStrategy")),
        "total_trades": parse_int(results.get("Total Trades", 0)),
        "profit_factor": float(results.get("Profit Factor", 0.0)),
        "average_trade": parse_money(results.get("Average Trade", 0.0)),
        "net_pnl": parse_money(results.get("Net PnL", 0.0)),
    }


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

    if promoted_df is None or promoted_df.empty:
        promotion_status = "NO_PROMOTED_CANDIDATES"
    else:
        promotion_status = "PROMOTED"

    summary = {
        "strategy_type": strategy_type_name,
        "dataset": dataset_path.name,
        "rows": len(data),
        "start": str(data.index.min()),
        "end": str(data.index.max()),
        "sanity_strategy_name": sanity_check.get("strategy_name", "NONE"),
        "sanity_total_trades": sanity_check.get("total_trades", 0),
        "sanity_profit_factor": sanity_check.get("profit_factor", 0.0),
        "sanity_average_trade": sanity_check.get("average_trade", 0.0),
        "sanity_net_pnl": sanity_check.get("net_pnl", 0.0),
        "total_combinations": len(combo_results_df) if combo_results_df is not None else 0,
        "promoted_candidates": len(promoted_df) if promoted_df is not None else 0,
        "promotion_status": promotion_status,
        "best_combo_strategy_name": best_combo.get("strategy_name", "NONE"),
        "best_combo_profit_factor": float(best_combo.get("profit_factor", 0.0) or 0.0),
        "best_combo_average_trade": float(best_combo.get("average_trade", 0.0) or 0.0),
        "best_combo_net_pnl": float(best_combo.get("net_pnl", 0.0) or 0.0),
        "best_combo_total_trades": int(best_combo.get("total_trades", 0) or 0),
        "refinement_ran": refinement_df is not None and not refinement_df.empty,
        "accepted_refinement_rows": len(refinement_df) if refinement_df is not None else 0,
        "best_refined_strategy_name": best_refined.get("strategy_name", "NONE"),
        "best_refined_profit_factor": float(best_refined.get("profit_factor", 0.0) or 0.0),
        "best_refined_average_trade": float(best_refined.get("average_trade", 0.0) or 0.0),
        "best_refined_net_pnl": float(best_refined.get("net_pnl", 0.0) or 0.0),
        "best_refined_total_trades": int(best_refined.get("total_trades", 0) or 0),
    }

    return summary


def print_family_summary(summary_row: dict[str, Any]) -> None:
    print("\n" + "=" * 72)
    print("🏁 FAMILY RUN SUMMARY")
    print("=" * 72)
    print(f"Strategy Type:            {summary_row['strategy_type']}")
    print(f"Dataset:                  {summary_row['dataset']}")
    print(f"Rows:                     {summary_row['rows']:,}")
    print(f"Start:                    {summary_row['start']}")
    print(f"End:                      {summary_row['end']}")

    print("\n--- Sanity Check ---")
    print(f"Strategy:                 {summary_row['sanity_strategy_name']}")
    print(f"Trades:                   {summary_row['sanity_total_trades']}")
    print(f"PF:                       {summary_row['sanity_profit_factor']:.2f}")
    print(f"Average Trade:            {summary_row['sanity_average_trade']:.2f}")
    print(f"Net PnL:                  {summary_row['sanity_net_pnl']:.2f}")

    print("\n--- Combination Sweep ---")
    print(f"Total Combinations:       {summary_row['total_combinations']}")
    print(f"Promoted Candidates:      {summary_row['promoted_candidates']}")
    print(f"Promotion Status:         {summary_row['promotion_status']}")

    print("\n--- Best Combo Candidate ---")
    print(f"Strategy:                 {summary_row['best_combo_strategy_name']}")
    print(f"PF:                       {summary_row['best_combo_profit_factor']:.2f}")
    print(f"Average Trade:            {summary_row['best_combo_average_trade']:.2f}")
    print(f"Net PnL:                  {summary_row['best_combo_net_pnl']:.2f}")
    print(f"Trades:                   {summary_row['best_combo_total_trades']}")

    print("\n--- Best Refined Candidate ---")
    print(f"Refinement Ran:           {summary_row['refinement_ran']}")
    print(f"Accepted Refinement Rows: {summary_row['accepted_refinement_rows']}")
    print(f"Strategy:                 {summary_row['best_refined_strategy_name']}")
    print(f"PF:                       {summary_row['best_refined_profit_factor']:.2f}")
    print(f"Average Trade:            {summary_row['best_refined_average_trade']:.2f}")
    print(f"Net PnL:                  {summary_row['best_refined_net_pnl']:.2f}")
    print(f"Trades:                   {summary_row['best_refined_total_trades']}")

    print("\n--- Notes ---")
    if summary_row["promotion_status"] == "NO_PROMOTED_CANDIDATES":
        print("No candidates passed the promotion gate.")
    else:
        print("At least one candidate passed promotion and refinement was attempted.")
    print("=" * 72)


def build_family_leaderboard(summary_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df.empty:
        return pd.DataFrame()

    leaderboard = summary_df.copy()
    leaderboard["leader_pf"] = leaderboard.apply(
        lambda row: row["best_refined_profit_factor"]
        if row["refinement_ran"]
        else row["best_combo_profit_factor"],
        axis=1,
    )
    leaderboard["leader_avg_trade"] = leaderboard.apply(
        lambda row: row["best_refined_average_trade"]
        if row["refinement_ran"]
        else row["best_combo_average_trade"],
        axis=1,
    )
    leaderboard["leader_net_pnl"] = leaderboard.apply(
        lambda row: row["best_refined_net_pnl"]
        if row["refinement_ran"]
        else row["best_combo_net_pnl"],
        axis=1,
    )
    leaderboard["leader_trades"] = leaderboard.apply(
        lambda row: row["best_refined_total_trades"]
        if row["refinement_ran"]
        else row["best_combo_total_trades"],
        axis=1,
    )
    leaderboard["leader_source"] = leaderboard.apply(
        lambda row: "refined" if row["refinement_ran"] else "combo",
        axis=1,
    )

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
        "leader_pf",
        "leader_avg_trade",
        "leader_net_pnl",
        "leader_trades",
        "best_combo_strategy_name",
        "best_refined_strategy_name",
    ]
    keep_cols = [c for c in keep_cols if c in leaderboard.columns]

    return leaderboard[keep_cols].copy()


# =============================================================================
# FAMILY RUN
# =============================================================================
def run_single_family(
    strategy_type_name: str,
    dataset_path: Path,
    outputs_dir: Path,
    max_workers_sweep: int,
    max_workers_refinement: int,
) -> dict[str, Any]:
    family_start = time.perf_counter()

    strategy_type = get_strategy_type(strategy_type_name)

    print(f"\nSelected strategy type: {strategy_type_name}")
    print(f"Available strategy types: {list_strategy_types()}")

    print("\nLoading data from:", dataset_path)
    data = load_tradestation_csv(dataset_path, debug=True)
    print("Data loaded successfully.")

    cfg = EngineConfig(
        initial_capital=250_000.0,
        risk_per_trade=0.01,
        symbol="ES",
    )

    print(f"\n⚙ Adding precomputed feature columns for strategy type: {strategy_type_name}")
    data = add_precomputed_features(
        data,
        sma_lengths=get_required_sma_lengths(strategy_type),
        avg_range_lookbacks=get_required_avg_range_lookbacks(strategy_type),
        momentum_lookbacks=get_required_momentum_lookbacks(strategy_type),
    )
    print("Precomputed features added.")

    print_data_summary(data, name="ES Data (2008+)")

    # -------------------------------------------------------------------------
    # 1. Sanity check
    # -------------------------------------------------------------------------
    sanity_check = run_sanity_check(strategy_type=strategy_type, data=data, cfg=cfg)

    # -------------------------------------------------------------------------
    # 2. Combination sweep
    # -------------------------------------------------------------------------
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

    if combo_results_df is not None and not combo_results_df.empty:
        print(f"\n📊 Top {strategy_type_name} Filter Combination Results:")
        print(combo_results_df.head(10))
        print(f"\n💾 Filter combination sweep saved to: {combo_results_path}")
    else:
        print(f"\nNo {strategy_type_name} filter combination results generated.")

    print(f"\n⏱ Filter combination sweep runtime: {sweep_elapsed:.2f} seconds")

    # -------------------------------------------------------------------------
    # 3. Promotion gate
    # -------------------------------------------------------------------------
    promotion_gate = get_promotion_gate_config(strategy_type)
    promoted_df = apply_promotion_gate(combo_results_df, promotion_gate)

    print_promotion_gate_report(
        strategy_type_name=strategy_type_name,
        promotion_gate=promotion_gate,
        promoted_df=promoted_df,
    )

    promoted_path = outputs_dir / f"{strategy_type_name}_promoted_candidates.csv"
    save_csv_if_not_empty(promoted_df, promoted_path)
    if promoted_df is not None and not promoted_df.empty:
        print(f"\n💾 Promoted candidates saved to: {promoted_path}")

    # -------------------------------------------------------------------------
    # 4. Refinement (WITH FALLBACK LOOP)
    # -------------------------------------------------------------------------
    refinement_df: pd.DataFrame | None = None

    if promoted_df is None or promoted_df.empty:
        print(f"\n⛔ Skipping {strategy_type_name} refinement because no candidates were promoted.")
    else:
        candidates_to_test = promoted_df.head(MAX_FALLBACK_CANDIDATES).to_dict("records")
        
        for rank, candidate in enumerate(candidates_to_test, start=1):
            print(f"\n{'='*50}")
            print(f"🏆 Attempting Refinement on Promoted Candidate #{rank}")
            print(f"{'='*50}")
            print(f"Strategy: {candidate.get('strategy_name', 'UNKNOWN')}")
            print(f"Filters: {candidate.get('filters', 'UNKNOWN')}")
            print(f"PF: {float(candidate.get('profit_factor', 0.0)):.2f}")
            print(f"Average Trade: {float(candidate.get('average_trade', 0.0)):.2f}")
            print(f"Net PnL: {float(candidate.get('net_pnl', 0.0)):.2f}")

            refinement_grid = get_refinement_grid_for_candidate(strategy_type, candidate)
            print("\n🧩 Active refinement dimensions for promoted combo:")
            for key, values in refinement_grid.items():
                print(f"  {key}: {values}")

            current_refinement_df = run_top_combo_refinement(
                strategy_type=strategy_type,
                data=data,
                cfg=cfg,
                candidate_row=candidate,
                max_workers=max_workers_refinement,
            )

            if current_refinement_df is not None and not current_refinement_df.empty:
                print(f"\n✅ Refinement successful for candidate #{rank}. Stopping fallback loop!")
                refinement_df = current_refinement_df
                break
            else:
                print(f"\n❌ Refinement yielded 0 accepted rows for candidate #{rank}.")
                if rank < len(candidates_to_test):
                    print("Falling back to next computationally distinct candidate in the list...")
                else:
                    print("All fallback candidates exhausted. No refinement results passed the trade filters.")

    # -------------------------------------------------------------------------
    # 5. Family summary
    # -------------------------------------------------------------------------
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

    family_elapsed = time.perf_counter() - family_start
    family_summary_row["family_runtime_seconds"] = round(family_elapsed, 2)

    return family_summary_row


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    total_start = time.perf_counter()
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    available_strategy_types = list_strategy_types()
    print(f"Available strategy types: {available_strategy_types}")

    if STRATEGY_TYPE_NAME == "all":
        family_names = available_strategy_types
    else:
        if STRATEGY_TYPE_NAME not in available_strategy_types:
            raise ValueError(
                f"Unknown strategy type '{STRATEGY_TYPE_NAME}'. "
                f"Available: {available_strategy_types + ['all']}"
            )
        family_names = [STRATEGY_TYPE_NAME]

    all_family_summaries: list[dict[str, Any]] = []

    for family_name in family_names:
        summary_row = run_single_family(
            strategy_type_name=family_name,
            dataset_path=CSV_PATH,
            outputs_dir=OUTPUTS_DIR,
            max_workers_sweep=MAX_WORKERS_SWEEP,
            max_workers_refinement=MAX_WORKERS_REFINEMENT,
        )
        all_family_summaries.append(summary_row)

    family_summary_df = pd.DataFrame(all_family_summaries)
    family_summary_path = OUTPUTS_DIR / "family_summary_results.csv"
    family_summary_df.to_csv(family_summary_path, index=False)

    print(f"\n💾 Family summary saved to: {family_summary_path}")

    leaderboard_df = build_family_leaderboard(family_summary_df)
    leaderboard_path = OUTPUTS_DIR / "family_leaderboard_results.csv"
    if not leaderboard_df.empty:
        leaderboard_df.to_csv(leaderboard_path, index=False)

        print("\n🏆 FAMILY LEADERBOARD")
        print(leaderboard_df)
        print(f"\n💾 Family leaderboard saved to: {leaderboard_path}")

    total_elapsed = time.perf_counter() - total_start
    print(f"\n🏁 Total script runtime: {total_elapsed:.2f} seconds")