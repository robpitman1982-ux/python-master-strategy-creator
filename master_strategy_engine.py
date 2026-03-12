"""
Master Strategy Engine
Project: Python Master Strategy Creator
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from modules.data_loader import load_tradestation_csv
from modules.engine import EngineConfig, MasterStrategyEngine
from modules.feature_builder import add_precomputed_features
from modules.filter_combinator import generate_filter_combinations
from modules.plateau_analyzer import PlateauAnalyzer
from modules.refiner import StrategyParameterRefiner
from modules.strategy_types import get_strategy_type, list_strategy_types


# ============================================================
# CONFIG
# ============================================================

STRATEGY_TYPE_NAME = "mean_reversion"   # "trend", "breakout", "mean_reversion"

CSV_PATH = Path("Data") / "ES_60m_2008_2026_tradestation.csv"
OUTPUTS_DIR = Path("Outputs")

COMBO_SWEEP_CSV_PATH = OUTPUTS_DIR / "filter_combination_sweep_results.csv"
PROMOTED_CANDIDATES_CSV_PATH = OUTPUTS_DIR / "promoted_candidates.csv"
FAMILY_SUMMARY_CSV_PATH = OUTPUTS_DIR / "family_summary_results.csv"


# ============================================================
# DATACLASSES
# ============================================================

@dataclass
class FamilyRunSummary:
    strategy_type: str
    dataset: str
    rows: int
    start: str
    end: str

    sanity_strategy_name: str
    sanity_total_trades: int
    sanity_profit_factor: float
    sanity_average_trade: float
    sanity_net_pnl: float

    total_filter_combinations: int
    promoted_candidates: int
    promotion_status: str

    best_combo_strategy_name: str
    best_combo_profit_factor: float
    best_combo_average_trade: float
    best_combo_net_pnl: float
    best_combo_total_trades: int

    refinement_ran: bool
    refinement_accepted_rows: int
    best_refined_strategy_name: str
    best_refined_profit_factor: float
    best_refined_average_trade: float
    best_refined_net_pnl: float
    best_refined_total_trades: int

    notes: str


@dataclass
class CandidateSpecificStrategyFactory:
    strategy_type_name: str
    promoted_combo_class_names: list[str]

    def __call__(
        self,
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
    ):
        strategy_type = get_strategy_type(self.strategy_type_name)

        all_classes = strategy_type.get_filter_classes()
        class_map = {cls.__name__: cls for cls in all_classes}

        promoted_combo_classes = [
            class_map[name]
            for name in self.promoted_combo_class_names
            if name in class_map
        ]

        return strategy_type.build_candidate_specific_strategy(
            promoted_combo_classes=promoted_combo_classes,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
            min_avg_range=min_avg_range,
            momentum_lookback=momentum_lookback,
        )


# ============================================================
# HELPERS
# ============================================================

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
    return float(str(value).replace("$", "").replace(",", "").strip())


def parse_percent(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).replace("%", "").strip())


def get_years_in_sample(data: pd.DataFrame) -> float:
    if data.empty:
        return 0.0

    start = data.index.min()
    end = data.index.max()
    total_days = (end - start).days

    if total_days <= 0:
        return 0.0

    return total_days / 365.25


def class_names_from_combo(combo_classes: list[type]) -> list[str]:
    return [cls.__name__ for cls in combo_classes]


def combo_classes_from_names(strategy_type_name: str, class_names: list[str]) -> list[type]:
    strategy_type = get_strategy_type(strategy_type_name)
    all_classes = strategy_type.get_filter_classes()
    class_map = {cls.__name__: cls for cls in all_classes}
    return [class_map[name] for name in class_names if name in class_map]


def ensure_outputs_dir() -> None:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# WORKERS
# ============================================================

def run_combo_case(task: tuple[str, pd.DataFrame, EngineConfig, list[str]]) -> dict[str, Any]:
    strategy_type_name, data, cfg, combo_class_names = task

    strategy_type = get_strategy_type(strategy_type_name)
    combo_classes = combo_classes_from_names(strategy_type_name, combo_class_names)
    filter_objects = strategy_type.build_filter_objects_from_classes(combo_classes)

    strategy = strategy_type.build_combinable_strategy(
        filters=filter_objects,
        hold_bars=strategy_type.default_hold_bars,
        stop_distance_points=strategy_type.default_stop_distance_points,
    )

    engine = MasterStrategyEngine(data=data, config=cfg)
    engine.run(strategy=strategy)
    summary = engine.results()

    years_in_sample = get_years_in_sample(data)
    total_trades = int(summary["Total Trades"])
    trades_per_year = total_trades / years_in_sample if years_in_sample > 0 else 0.0

    trade_thresholds = strategy_type.get_trade_filter_thresholds()
    min_trades = int(trade_thresholds["min_trades"])
    min_trades_per_year = float(trade_thresholds["min_trades_per_year"])

    passes_trade_filter = (
        total_trades >= min_trades
        and trades_per_year >= min_trades_per_year
    )

    return {
        "strategy_name": str(summary["Strategy"]),
        "filter_count": len(filter_objects),
        "filters": ",".join([f.name for f in filter_objects]),
        "combo_class_names": combo_class_names,
        "total_trades": total_trades,
        "trades_per_year": round(trades_per_year, 2),
        "passes_trade_filter": passes_trade_filter,
        "net_pnl": parse_money(summary["Net PnL"]),
        "gross_profit": parse_money(summary["Gross Profit"]),
        "gross_loss": parse_money(summary["Gross Loss"]),
        "average_trade": parse_money(summary["Average Trade"]),
        "profit_factor": float(summary["Profit Factor"]),
        "max_drawdown": parse_money(summary["Max Drawdown"]),
        "win_rate": parse_percent(summary["Win Rate"]),
        "avg_mae_pts": float(summary["Average MAE (pts)"]),
        "avg_mfe_pts": float(summary["Average MFE (pts)"]),
    }


# ============================================================
# CORE RUNNERS
# ============================================================

def run_single_strategy_test(
    data: pd.DataFrame,
    cfg: EngineConfig,
    strategy_type_name: str,
) -> dict[str, Any]:
    strategy_type = get_strategy_type(strategy_type_name)

    filters = strategy_type.build_default_sanity_filters()
    strategy = strategy_type.build_combinable_strategy(
        filters=filters,
        hold_bars=strategy_type.default_hold_bars,
        stop_distance_points=strategy_type.default_stop_distance_points,
    )

    engine = MasterStrategyEngine(data=data, config=cfg)

    print("\n🚀 Master Strategy Engine Initialized.")
    print("Engine Results Snapshot (Before Run):", engine.results())

    engine.run(strategy=strategy)

    print("\n✅ Backtest run completed.")
    print("Engine Results Snapshot (After Run):", engine.results())

    trades_df = engine.trades_dataframe()
    if not trades_df.empty:
        print("\nFirst 5 Trades:")
        print(trades_df.head())
    else:
        print("\nNo trades generated.")

    return engine.results()


def run_filter_combination_sweep(
    data: pd.DataFrame,
    cfg: EngineConfig,
    strategy_type_name: str,
    max_workers: int = 10,
) -> pd.DataFrame:
    strategy_type = get_strategy_type(strategy_type_name)

    filter_classes = strategy_type.get_filter_classes()
    combinations = generate_filter_combinations(
        filter_classes=filter_classes,
        min_filters=strategy_type.min_filters_per_combo,
        max_filters=strategy_type.max_filters_per_combo,
    )

    print(f"\n🧪 Running {strategy_type_name} filter combination sweep...")
    print(f"Total filter combinations: {len(combinations)}")
    print(f"Parallel mode: ON | max_workers={max_workers}")

    tasks = [
        (
            strategy_type_name,
            data,
            cfg,
            class_names_from_combo(combo_classes),
        )
        for combo_classes in combinations
    ]

    results: list[dict[str, Any]] = []

    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        for idx, result in enumerate(executor.map(run_combo_case, tasks), start=1):
            print(f"  Combo {idx}/{len(combinations)} | {result['strategy_name']}")
            results.append(result)

    results_df = pd.DataFrame(results)

    if not results_df.empty:
        results_df = results_df.sort_values(
            by=["passes_trade_filter", "profit_factor", "average_trade", "net_pnl"],
            ascending=[False, False, False, False],
        ).reset_index(drop=True)

    return results_df


def apply_promotion_gate(
    combo_results_df: pd.DataFrame,
    strategy_type_name: str,
) -> pd.DataFrame:
    if combo_results_df.empty:
        return pd.DataFrame()

    strategy_type = get_strategy_type(strategy_type_name)
    thresholds = strategy_type.get_promotion_thresholds()

    min_pf = float(thresholds["min_profit_factor"])
    min_avg_trade = float(thresholds["min_average_trade"])
    require_positive_net_pnl = bool(thresholds["require_positive_net_pnl"])

    promoted_df = combo_results_df.copy()
    promoted_df = promoted_df[promoted_df["passes_trade_filter"] == True]
    promoted_df = promoted_df[promoted_df["profit_factor"] >= min_pf]
    promoted_df = promoted_df[promoted_df["average_trade"] >= min_avg_trade]

    if require_positive_net_pnl:
        promoted_df = promoted_df[promoted_df["net_pnl"] > 0]

    promoted_df = promoted_df.sort_values(
        by=["profit_factor", "average_trade", "net_pnl"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    print(f"\n🚦 Promotion Gate Results for strategy type: {strategy_type_name}")
    print(f"Minimum PF required: {min_pf:.2f}")
    print(f"Minimum average trade required: {min_avg_trade:.2f}")
    print(f"Require positive net PnL: {require_positive_net_pnl}")
    print(f"Promoted candidates: {len(promoted_df)}")

    if not promoted_df.empty:
        print("\n✅ Promoted Candidates:")
        display_cols = [
            "strategy_name",
            "profit_factor",
            "average_trade",
            "net_pnl",
            "total_trades",
            "trades_per_year",
            "filters",
        ]
        existing_cols = [c for c in display_cols if c in promoted_df.columns]
        print(promoted_df[existing_cols].head(10))
    else:
        print("\n❌ No candidates passed the promotion gate.")

    return promoted_df


def run_top_combo_refinement(
    data: pd.DataFrame,
    cfg: EngineConfig,
    strategy_type_name: str,
    promoted_df: pd.DataFrame,
) -> pd.DataFrame:
    if promoted_df.empty:
        print(f"\n⛔ Skipping {strategy_type_name} refinement because no candidates were promoted.")
        return pd.DataFrame()

    best_row = promoted_df.iloc[0]

    promoted_combo_class_names = list(best_row["combo_class_names"])
    promoted_combo_classes = combo_classes_from_names(strategy_type_name, promoted_combo_class_names)

    print("\n🏆 Selected top promoted candidate for refinement:")
    print(f"Strategy: {best_row['strategy_name']}")
    print(f"Filters: {best_row['filters']}")
    print(f"PF: {best_row['profit_factor']:.2f}")
    print(f"Average Trade: {best_row['average_trade']:.2f}")
    print(f"Net PnL: {best_row['net_pnl']:.2f}")

    strategy_type = get_strategy_type(strategy_type_name)
    active_grid = strategy_type.get_active_refinement_grid_for_combo(promoted_combo_classes)

    print("\n🧩 Active refinement dimensions for promoted combo:")
    for key, value in active_grid.items():
        print(f"  {key}: {value}")

    hold_bars = active_grid.get("hold_bars", [strategy_type.default_hold_bars])
    stop_distance_points = active_grid.get(
        "stop_distance_points",
        [strategy_type.default_stop_distance_points],
    )

    # Only sweep active dimensions. Inactive dimensions get a single dummy placeholder.
    min_avg_range = active_grid.get("min_avg_range", [0.0])
    momentum_lookback = active_grid.get("momentum_lookback", [0])

    trade_thresholds = strategy_type.get_trade_filter_thresholds()

    strategy_factory = CandidateSpecificStrategyFactory(
        strategy_type_name=strategy_type_name,
        promoted_combo_class_names=promoted_combo_class_names,
    )

    refiner = StrategyParameterRefiner(
        engine_class=MasterStrategyEngine,
        data=data,
        strategy_factory=strategy_factory,
        config=cfg,
    )

    refinement_df = refiner.run_refinement(
        hold_bars=hold_bars,
        stop_distance_points=stop_distance_points,
        min_avg_range=min_avg_range,
        momentum_lookback=momentum_lookback,
        min_trades=int(trade_thresholds["min_trades"]),
        min_trades_per_year=float(trade_thresholds["min_trades_per_year"]),
        parallel=True,
        max_workers=10,
    )

    if not refinement_df.empty:
        print(f"\n🎯 Top {strategy_type_name} Refinement Results:")
        print(refiner.top_results(10))
        refiner.print_summary_report(top_n=10)

        plateau = PlateauAnalyzer(refinement_df)
        plateau.print_report(top_n=10)

        refinement_output_path = OUTPUTS_DIR / f"{strategy_type_name}_top_combo_refinement_results_narrow.csv"
        saved_path = refiner.save_results_csv(refinement_output_path)
        print(f"\n💾 Narrow top-combo refinement saved to: {saved_path}")
    else:
        print("\nNo refinement results met the trade filters.")

    return refinement_df


# ============================================================
# FAMILY SUMMARY
# ============================================================

def build_family_run_summary(
    strategy_type_name: str,
    dataset_path: Path,
    data: pd.DataFrame,
    sanity_results: dict[str, Any],
    combo_results_df: pd.DataFrame,
    promoted_df: pd.DataFrame,
    refinement_df: pd.DataFrame,
) -> FamilyRunSummary:
    if not combo_results_df.empty:
        best_combo = combo_results_df.iloc[0]
        best_combo_strategy_name = str(best_combo["strategy_name"])
        best_combo_profit_factor = float(best_combo["profit_factor"])
        best_combo_average_trade = float(best_combo["average_trade"])
        best_combo_net_pnl = float(best_combo["net_pnl"])
        best_combo_total_trades = int(best_combo["total_trades"])
    else:
        best_combo_strategy_name = "NONE"
        best_combo_profit_factor = 0.0
        best_combo_average_trade = 0.0
        best_combo_net_pnl = 0.0
        best_combo_total_trades = 0

    if not refinement_df.empty:
        best_refined = refinement_df.iloc[0]
        best_refined_strategy_name = str(best_refined["strategy_name"])
        best_refined_profit_factor = float(best_refined["profit_factor"])
        best_refined_average_trade = float(best_refined["average_trade"])
        best_refined_net_pnl = float(best_refined["net_pnl"])
        best_refined_total_trades = int(best_refined["total_trades"])
    else:
        best_refined_strategy_name = "NONE"
        best_refined_profit_factor = 0.0
        best_refined_average_trade = 0.0
        best_refined_net_pnl = 0.0
        best_refined_total_trades = 0

    if promoted_df.empty:
        promotion_status = "NO_PROMOTED_CANDIDATES"
        notes = "No candidates passed the promotion gate."
    elif refinement_df.empty:
        promotion_status = "PROMOTED_BUT_REFINEMENT_EMPTY"
        notes = "Promoted candidate existed, but refinement produced no accepted rows."
    else:
        promotion_status = "PROMOTED_AND_REFINED"
        notes = "Candidate promoted and refinement completed successfully."

    return FamilyRunSummary(
        strategy_type=strategy_type_name,
        dataset=dataset_path.name,
        rows=len(data),
        start=str(data.index.min()),
        end=str(data.index.max()),

        sanity_strategy_name=str(sanity_results["Strategy"]),
        sanity_total_trades=int(sanity_results["Total Trades"]),
        sanity_profit_factor=float(sanity_results["Profit Factor"]),
        sanity_average_trade=parse_money(sanity_results["Average Trade"]),
        sanity_net_pnl=parse_money(sanity_results["Net PnL"]),

        total_filter_combinations=len(combo_results_df),
        promoted_candidates=len(promoted_df),
        promotion_status=promotion_status,

        best_combo_strategy_name=best_combo_strategy_name,
        best_combo_profit_factor=best_combo_profit_factor,
        best_combo_average_trade=best_combo_average_trade,
        best_combo_net_pnl=best_combo_net_pnl,
        best_combo_total_trades=best_combo_total_trades,

        refinement_ran=not promoted_df.empty,
        refinement_accepted_rows=len(refinement_df),
        best_refined_strategy_name=best_refined_strategy_name,
        best_refined_profit_factor=best_refined_profit_factor,
        best_refined_average_trade=best_refined_average_trade,
        best_refined_net_pnl=best_refined_net_pnl,
        best_refined_total_trades=best_refined_total_trades,

        notes=notes,
    )


def print_family_run_summary(summary: FamilyRunSummary) -> None:
    print("\n" + "=" * 72)
    print("🏁 FAMILY RUN SUMMARY")
    print("=" * 72)

    print(f"Strategy Type:            {summary.strategy_type}")
    print(f"Dataset:                  {summary.dataset}")
    print(f"Rows:                     {summary.rows:,}")
    print(f"Start:                    {summary.start}")
    print(f"End:                      {summary.end}")

    print("\n--- Sanity Check ---")
    print(f"Strategy:                 {summary.sanity_strategy_name}")
    print(f"Trades:                   {summary.sanity_total_trades}")
    print(f"PF:                       {summary.sanity_profit_factor:.2f}")
    print(f"Average Trade:            {summary.sanity_average_trade:.2f}")
    print(f"Net PnL:                  {summary.sanity_net_pnl:.2f}")

    print("\n--- Combination Sweep ---")
    print(f"Total Combinations:       {summary.total_filter_combinations}")
    print(f"Promoted Candidates:      {summary.promoted_candidates}")
    print(f"Promotion Status:         {summary.promotion_status}")

    print("\n--- Best Combo Candidate ---")
    print(f"Strategy:                 {summary.best_combo_strategy_name}")
    print(f"PF:                       {summary.best_combo_profit_factor:.2f}")
    print(f"Average Trade:            {summary.best_combo_average_trade:.2f}")
    print(f"Net PnL:                  {summary.best_combo_net_pnl:.2f}")
    print(f"Trades:                   {summary.best_combo_total_trades}")

    print("\n--- Best Refined Candidate ---")
    print(f"Refinement Ran:           {summary.refinement_ran}")
    print(f"Accepted Refinement Rows: {summary.refinement_accepted_rows}")
    print(f"Strategy:                 {summary.best_refined_strategy_name}")
    print(f"PF:                       {summary.best_refined_profit_factor:.2f}")
    print(f"Average Trade:            {summary.best_refined_average_trade:.2f}")
    print(f"Net PnL:                  {summary.best_refined_net_pnl:.2f}")
    print(f"Trades:                   {summary.best_refined_total_trades}")

    print("\n--- Notes ---")
    print(summary.notes)
    print("=" * 72)


def save_family_run_summary(summary: FamilyRunSummary, filepath: Path) -> None:
    ensure_outputs_dir()
    df = pd.DataFrame([asdict(summary)])
    df.to_csv(filepath, index=False)
    print(f"\n💾 Family summary saved to: {filepath}")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    total_start = time.perf_counter()

    available_strategy_types = list_strategy_types()

    print(f"Selected strategy type: {STRATEGY_TYPE_NAME}")
    print(f"Available strategy types: {available_strategy_types}")

    if STRATEGY_TYPE_NAME not in available_strategy_types:
        raise ValueError(
            f"Unknown strategy type '{STRATEGY_TYPE_NAME}'. "
            f"Available: {available_strategy_types}"
        )

    strategy_type = get_strategy_type(STRATEGY_TYPE_NAME)

    print("\nLoading data from:", CSV_PATH)
    data = load_tradestation_csv(CSV_PATH, debug=True)
    print("Data loaded successfully.")

    cfg = EngineConfig(
        initial_capital=250_000.0,
        risk_per_trade=0.01,
        symbol="ES",
    )

    print(f"\n⚙ Adding precomputed feature columns for strategy type: {STRATEGY_TYPE_NAME}")
    data = add_precomputed_features(
        data,
        sma_lengths=strategy_type.get_required_sma_lengths(),
        avg_range_lookbacks=strategy_type.get_required_avg_range_lookbacks(),
        momentum_lookbacks=strategy_type.get_required_momentum_lookbacks(),
    )
    print("Precomputed features added.")

    print_data_summary(data, name="ES Data (2008+)")

    # ------------------------------------------------
    # 1. Sanity check
    # ------------------------------------------------
    sanity_results = run_single_strategy_test(
        data=data,
        cfg=cfg,
        strategy_type_name=STRATEGY_TYPE_NAME,
    )

    # ------------------------------------------------
    # 2. Filter combination sweep
    # ------------------------------------------------
    combo_start = time.perf_counter()
    combo_results_df = run_filter_combination_sweep(
        data=data,
        cfg=cfg,
        strategy_type_name=STRATEGY_TYPE_NAME,
        max_workers=10,
    )
    combo_elapsed = time.perf_counter() - combo_start

    if not combo_results_df.empty:
        print(f"\n📊 Top {STRATEGY_TYPE_NAME} Filter Combination Results:")
        print(combo_results_df.head(10))

        ensure_outputs_dir()

        combo_results_to_save = combo_results_df.copy()
        if "combo_class_names" in combo_results_to_save.columns:
            combo_results_to_save["combo_class_names"] = combo_results_to_save["combo_class_names"].apply(
                lambda x: "|".join(x) if isinstance(x, list) else str(x)
            )

        combo_results_to_save.to_csv(COMBO_SWEEP_CSV_PATH, index=False)
        print(f"\n💾 Filter combination sweep saved to: {COMBO_SWEEP_CSV_PATH}")
    else:
        print("\nNo filter combination results generated.")

    print(f"\n⏱ Filter combination sweep runtime: {combo_elapsed:.2f} seconds")

    # ------------------------------------------------
    # 3. Promotion gate
    # ------------------------------------------------
    promoted_df = apply_promotion_gate(
        combo_results_df=combo_results_df,
        strategy_type_name=STRATEGY_TYPE_NAME,
    )

    if not promoted_df.empty:
        promoted_to_save = promoted_df.copy()
        if "combo_class_names" in promoted_to_save.columns:
            promoted_to_save["combo_class_names"] = promoted_to_save["combo_class_names"].apply(
                lambda x: "|".join(x) if isinstance(x, list) else str(x)
            )
        promoted_to_save.to_csv(PROMOTED_CANDIDATES_CSV_PATH, index=False)
        print(f"\n💾 Promoted candidates saved to: {PROMOTED_CANDIDATES_CSV_PATH}")

    # ------------------------------------------------
    # 4. Refinement
    # ------------------------------------------------
    refinement_df = run_top_combo_refinement(
        data=data,
        cfg=cfg,
        strategy_type_name=STRATEGY_TYPE_NAME,
        promoted_df=promoted_df,
    )

    # ------------------------------------------------
    # 5. Family summary / scoreboard
    # ------------------------------------------------
    family_summary = build_family_run_summary(
        strategy_type_name=STRATEGY_TYPE_NAME,
        dataset_path=CSV_PATH,
        data=data,
        sanity_results=sanity_results,
        combo_results_df=combo_results_df,
        promoted_df=promoted_df,
        refinement_df=refinement_df,
    )

    print_family_run_summary(family_summary)
    save_family_run_summary(family_summary, FAMILY_SUMMARY_CSV_PATH)

    total_elapsed = time.perf_counter() - total_start
    print(f"\n🏁 Total script runtime: {total_elapsed:.2f} seconds")