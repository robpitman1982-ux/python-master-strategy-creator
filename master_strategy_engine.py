"""
Master Strategy Engine
Project: Python Master Strategy Creator
"""

from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
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


def _parse_money(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).replace("$", "").replace(",", "").strip())


def _parse_percent(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).replace("%", "").strip())


def _build_filter_objects_from_classes(strategy_type, combo_classes: list[type]) -> list:
    return strategy_type.build_filter_objects_from_classes(combo_classes)


def _run_combo_case(task: tuple[pd.DataFrame, EngineConfig, Any, list[type]]) -> dict:
    data, cfg, strategy_type, combo_classes = task

    filter_objects = _build_filter_objects_from_classes(strategy_type, combo_classes)

    strategy = strategy_type.build_combinable_strategy(
        filters=filter_objects,
        hold_bars=strategy_type.default_hold_bars,
        stop_distance_points=strategy_type.default_stop_distance_points,
    )

    engine = MasterStrategyEngine(data=data, config=cfg)
    engine.run(strategy=strategy)
    summary = engine.results()

    total_trades = int(summary["Total Trades"])
    years_in_sample = (data.index.max() - data.index.min()).days / 365.25
    trades_per_year = total_trades / years_in_sample if years_in_sample > 0 else 0.0

    trade_thresholds = strategy_type.get_trade_filter_thresholds()
    passes_filter = (
        total_trades >= int(trade_thresholds["min_trades"])
        and trades_per_year >= float(trade_thresholds["min_trades_per_year"])
    )

    return {
        "strategy_name": str(summary["Strategy"]),
        "filter_count": len(filter_objects),
        "filters": ",".join([f.name for f in filter_objects]),
        "total_trades": total_trades,
        "trades_per_year": round(trades_per_year, 2),
        "passes_trade_filter": passes_filter,
        "net_pnl": _parse_money(summary["Net PnL"]),
        "gross_profit": _parse_money(summary["Gross Profit"]),
        "gross_loss": _parse_money(summary["Gross Loss"]),
        "average_trade": _parse_money(summary["Average Trade"]),
        "profit_factor": float(summary["Profit Factor"]),
        "max_drawdown": _parse_money(summary["Max Drawdown"]),
        "win_rate": _parse_percent(summary["Win Rate"]),
        "avg_mae_pts": float(summary["Average MAE (pts)"]),
        "avg_mfe_pts": float(summary["Average MFE (pts)"]),
    }


def run_single_strategy_test(
    data: pd.DataFrame,
    cfg: EngineConfig,
    strategy_type,
) -> None:
    filter_objects = strategy_type.build_default_sanity_filters()

    strategy = strategy_type.build_combinable_strategy(
        filters=filter_objects,
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


def run_filter_combination_sweep(
    data: pd.DataFrame,
    cfg: EngineConfig,
    strategy_type,
    max_workers: int = 10,
) -> pd.DataFrame:
    filter_classes = strategy_type.get_filter_classes()

    combinations = generate_filter_combinations(
        filter_classes=filter_classes,
        min_filters=strategy_type.min_filters_per_combo,
        max_filters=strategy_type.max_filters_per_combo,
    )

    print(f"\n🧪 Running {strategy_type.name} filter combination sweep...")
    print(f"Total filter combinations: {len(combinations)}")
    print(f"Parallel mode: ON | max_workers={max_workers}")

    tasks = [(data, cfg, strategy_type, combo_classes) for combo_classes in combinations]
    results: list[dict] = []

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        for idx, result in enumerate(executor.map(_run_combo_case, tasks), start=1):
            print(f"  Combo {idx}/{len(combinations)} | {result['strategy_name']}")
            results.append(result)

    results_df = pd.DataFrame(results)

    if not results_df.empty:
        results_df = results_df.sort_values(
            by=["passes_trade_filter", "profit_factor", "average_trade", "net_pnl"],
            ascending=[False, False, False, False],
        ).reset_index(drop=True)

    return results_df


def run_promotion_gate(
    combo_results_df: pd.DataFrame,
    strategy_type,
) -> pd.DataFrame:
    if combo_results_df.empty:
        print("\nNo combo results available for promotion gate.")
        return pd.DataFrame()

    thresholds = strategy_type.get_promotion_thresholds()

    promoted_df = combo_results_df.copy()

    promoted_df = promoted_df[promoted_df["passes_trade_filter"] == True]
    promoted_df = promoted_df[promoted_df["profit_factor"] >= float(thresholds["min_profit_factor"])]
    promoted_df = promoted_df[promoted_df["average_trade"] >= float(thresholds["min_average_trade"])]

    if thresholds.get("require_positive_net_pnl", False):
        promoted_df = promoted_df[promoted_df["net_pnl"] > 0]

    promoted_df = promoted_df.sort_values(
        by=["profit_factor", "average_trade", "net_pnl"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    print(f"\n🚦 Promotion Gate Results for strategy type: {strategy_type.name}")
    print(f"Minimum PF required: {thresholds['min_profit_factor']:.2f}")
    print(f"Minimum average trade required: {thresholds['min_average_trade']:.2f}")
    print(f"Require positive net PnL: {thresholds.get('require_positive_net_pnl', False)}")
    print(f"Promoted candidates: {len(promoted_df)}")

    if promoted_df.empty:
        print("\n❌ No candidates passed the promotion gate.")
        return promoted_df

    display_cols = [
        "strategy_name",
        "filters",
        "profit_factor",
        "average_trade",
        "net_pnl",
        "max_drawdown",
        "trades_per_year",
    ]
    display_cols = [c for c in display_cols if c in promoted_df.columns]

    print("\n✅ Promoted Candidates:")
    print(promoted_df[display_cols].head(10))

    output_path = Path("Outputs") / "promoted_candidates.csv"
    promoted_df.to_csv(output_path, index=False)
    print(f"\n💾 Promoted candidates saved to: {output_path}")

    return promoted_df


def map_promoted_row_to_combo_classes(strategy_type, promoted_row: pd.Series) -> list[type]:
    filter_name_text = str(promoted_row["filters"])
    selected_names = [name.strip() for name in filter_name_text.split(",") if name.strip()]

    combo_classes: list[type] = []
    for cls in strategy_type.get_filter_classes():
        cls_name = getattr(cls, "name", cls.__name__)
        if cls_name in selected_names:
            combo_classes.append(cls)

    return combo_classes


def normalize_active_refinement_grid(active_grid: dict[str, list]) -> dict[str, list]:
    normalized = {
        "hold_bars": [0],
        "stop_distance_points": [0.0],
        "min_avg_range": [0.0],
        "momentum_lookback": [0],
    }
    normalized.update(active_grid)
    return normalized


class CandidateSpecificStrategyFactory:
    def __init__(self, strategy_type, promoted_combo_classes: list[type]):
        self.strategy_type = strategy_type
        self.promoted_combo_classes = promoted_combo_classes

    def __call__(
        self,
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
    ):
        return self.strategy_type.build_candidate_specific_strategy(
            promoted_combo_classes=self.promoted_combo_classes,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
            min_avg_range=min_avg_range,
            momentum_lookback=momentum_lookback,
        )


def run_top_combo_refinement(
    data: pd.DataFrame,
    cfg: EngineConfig,
    strategy_type,
    promoted_candidates_df: pd.DataFrame,
    max_workers: int = 10,
    top_n: int = 3,
) -> pd.DataFrame:
    if promoted_candidates_df.empty:
        print(f"\n⛔ Skipping {strategy_type.name} refinement because no candidates were promoted.")
        return pd.DataFrame()

    print(f"\n🏆 Refining top {top_n} promoted candidates...")

    final_candidates: list[dict[str, Any]] = []

    for rank_idx, (_, row) in enumerate(promoted_candidates_df.head(top_n).iterrows(), start=1):
        print("\n---------------------------------------------")
        print(f"Refining Candidate #{rank_idx}")
        print(f"Strategy: {row['strategy_name']}")
        print(f"Filters: {row['filters']}")
        print(f"PF: {row['profit_factor']:.2f}")
        print(f"Avg Trade: {row['average_trade']:.2f}")
        print(f"Net PnL: {row['net_pnl']:.2f}")

        promoted_combo_classes = map_promoted_row_to_combo_classes(
            strategy_type=strategy_type,
            promoted_row=row,
        )

        active_grid = strategy_type.get_active_refinement_grid_for_combo(promoted_combo_classes)
        normalized_grid = normalize_active_refinement_grid(active_grid)

        print("\n🧩 Active refinement dimensions:")
        for k, v in active_grid.items():
            print(f"  {k}: {v}")

        candidate_strategy_factory = CandidateSpecificStrategyFactory(
            strategy_type=strategy_type,
            promoted_combo_classes=promoted_combo_classes,
        )

        refiner = StrategyParameterRefiner(
            engine_class=MasterStrategyEngine,
            data=data,
            strategy_factory=candidate_strategy_factory,
            config=cfg,
        )

        thresholds = strategy_type.get_trade_filter_thresholds()

        refinement_df = refiner.run_refinement(
            hold_bars=normalized_grid["hold_bars"],
            stop_distance_points=normalized_grid["stop_distance_points"],
            min_avg_range=normalized_grid["min_avg_range"],
            momentum_lookback=normalized_grid["momentum_lookback"],
            min_trades=int(thresholds["min_trades"]),
            min_trades_per_year=float(thresholds["min_trades_per_year"]),
            parallel=True,
            max_workers=max_workers,
        )

        if refinement_df.empty:
            print("\nNo refinement results met the trade filters for this candidate.")
            continue

        print(f"\n🎯 Top {strategy_type.name} Refinement Results:")
        print(refiner.top_results(10))

        refiner.print_summary_report(top_n=10)

        plateau = PlateauAnalyzer(refinement_df)
        plateau.print_report(top_n=10)

        candidate_output_path = Path("Outputs") / f"{strategy_type.name}_candidate_{rank_idx}_refinement_results.csv"
        saved_path = refiner.save_results_csv(candidate_output_path)
        print(f"\n💾 Candidate refinement saved to: {saved_path}")

        best = refiner.top_results(1).iloc[0]

        final_candidates.append(
            {
                "candidate_rank": rank_idx,
                "strategy_name": row["strategy_name"],
                "filters": row["filters"],
                "hold_bars": best["hold_bars"],
                "stop_distance_points": best["stop_distance_points"],
                "profit_factor": best["profit_factor"],
                "average_trade": best["average_trade"],
                "net_pnl": best["net_pnl"],
                "max_drawdown": best["max_drawdown"],
                "total_trades": best["total_trades"],
            }
        )

    if not final_candidates:
        print("\nNo refined candidates produced usable results.")
        return pd.DataFrame()

    final_df = pd.DataFrame(final_candidates)

    final_df = final_df.sort_values(
        by=["profit_factor", "average_trade", "net_pnl"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    print("\n🏆 FINAL RANKED STRATEGIES")
    print(final_df)

    output_path = Path("Outputs") / f"{strategy_type.name}_final_strategy_ranking.csv"
    final_df.to_csv(output_path, index=False)

    print(f"\n💾 Final strategy ranking saved to: {output_path}")

    return final_df


if __name__ == "__main__":
    total_start = time.perf_counter()

    STRATEGY_TYPE_NAME = "mean_reversion"
    MAX_WORKERS = 10
    TOP_N_PROMOTED_FOR_REFINEMENT = 3

    print(f"Selected strategy type: {STRATEGY_TYPE_NAME}")
    print(f"Available strategy types: {list_strategy_types()}")

    strategy_type = get_strategy_type(STRATEGY_TYPE_NAME)

    CSV_PATH = Path("Data") / "ES_60m_2008_2026_tradestation.csv"
    OUTPUTS_DIR = Path("Outputs")
    COMBO_SWEEP_CSV_PATH = OUTPUTS_DIR / "filter_combination_sweep_results.csv"

    print("\nLoading data from:", CSV_PATH)
    data = load_tradestation_csv(CSV_PATH, debug=True)
    print("Data loaded successfully.")

    cfg = EngineConfig(
        initial_capital=250_000.0,
        risk_per_trade=0.01,
        symbol="ES",
    )

    print(f"\n⚙ Adding precomputed feature columns for strategy type: {strategy_type.name}")
    data = add_precomputed_features(
        data,
        sma_lengths=strategy_type.get_required_sma_lengths(),
        avg_range_lookbacks=strategy_type.get_required_avg_range_lookbacks(),
        momentum_lookbacks=strategy_type.get_required_momentum_lookbacks(),
    )
    print("Precomputed features added.")

    print_data_summary(data, name="ES Data (2008+)")

    run_single_strategy_test(data=data, cfg=cfg, strategy_type=strategy_type)

    combo_start = time.perf_counter()
    combo_results_df = run_filter_combination_sweep(
        data=data,
        cfg=cfg,
        strategy_type=strategy_type,
        max_workers=MAX_WORKERS,
    )
    combo_elapsed = time.perf_counter() - combo_start

    if not combo_results_df.empty:
        print(f"\n📊 Top {strategy_type.name} Filter Combination Results:")
        print(combo_results_df.head(10))

        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        combo_results_df.to_csv(COMBO_SWEEP_CSV_PATH, index=False)
        print(f"\n💾 Filter combination sweep saved to: {COMBO_SWEEP_CSV_PATH}")
    else:
        print("\nNo filter combination results generated.")

    print(f"\n⏱ Filter combination sweep runtime: {combo_elapsed:.2f} seconds")

    promoted_candidates_df = run_promotion_gate(
        combo_results_df=combo_results_df,
        strategy_type=strategy_type,
    )

    run_top_combo_refinement(
        data=data,
        cfg=cfg,
        strategy_type=strategy_type,
        promoted_candidates_df=promoted_candidates_df,
        max_workers=MAX_WORKERS,
        top_n=TOP_N_PROMOTED_FOR_REFINEMENT,
    )

    total_elapsed = time.perf_counter() - total_start
    print(f"\n🏁 Total script runtime: {total_elapsed:.2f} seconds")