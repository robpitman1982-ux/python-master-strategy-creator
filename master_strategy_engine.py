"""
Master Strategy Engine
Project: Python Master Strategy Creator
"""

from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from modules.data_loader import load_tradestation_csv
from modules.engine import EngineConfig, MasterStrategyEngine
from modules.feature_builder import add_precomputed_features
from modules.filter_combinator import generate_filter_combinations
from modules.filters import (
    MomentumFilter,
    PullbackFilter,
    RecoveryTriggerFilter,
    TrendDirectionFilter,
    VolatilityFilter,
)
from modules.plateau_analyzer import PlateauAnalyzer
from modules.refiner import StrategyParameterRefiner
from modules.strategies import (
    CombinableFilterTrendStrategy,
    RefinedFiveFilterTrendStrategy,
)


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


def _build_filter_objects_from_classes(combo_classes: list[type]) -> list:
    filter_objects = []

    for cls in combo_classes:
        if cls is TrendDirectionFilter:
            filter_objects.append(cls(fast_length=50, slow_length=200))
        elif cls is PullbackFilter:
            filter_objects.append(cls(fast_length=50))
        elif cls is RecoveryTriggerFilter:
            filter_objects.append(cls(fast_length=50))
        elif cls is VolatilityFilter:
            filter_objects.append(cls(lookback=20, min_avg_range=8.0))
        elif cls is MomentumFilter:
            filter_objects.append(cls(lookback=10))
        else:
            filter_objects.append(cls())

    return filter_objects


def _run_combo_case(task: tuple[pd.DataFrame, EngineConfig, list[type]]) -> dict:
    data, cfg, combo_classes = task

    filter_objects = _build_filter_objects_from_classes(combo_classes)

    strategy = CombinableFilterTrendStrategy(
        filters=filter_objects,
        hold_bars=8,
        stop_distance_points=12.0,
    )

    engine = MasterStrategyEngine(data=data, config=cfg)
    engine.run(strategy=strategy)
    summary = engine.results()

    total_trades = int(summary["Total Trades"])
    years_in_sample = (data.index.max() - data.index.min()).days / 365.25
    trades_per_year = total_trades / years_in_sample if years_in_sample > 0 else 0.0
    passes_filter = total_trades >= 150 and trades_per_year >= 8.0

    return {
        "strategy_name": summary["Strategy"],
        "filter_count": len(filter_objects),
        "filters": ",".join([f.name for f in filter_objects]),
        "total_trades": total_trades,
        "trades_per_year": round(trades_per_year, 2),
        "passes_trade_filter": passes_filter,
        "net_pnl": float(str(summary["Net PnL"]).replace("$", "").replace(",", "")),
        "gross_profit": float(str(summary["Gross Profit"]).replace("$", "").replace(",", "")),
        "gross_loss": float(str(summary["Gross Loss"]).replace("$", "").replace(",", "")),
        "average_trade": float(str(summary["Average Trade"]).replace("$", "").replace(",", "")),
        "profit_factor": float(summary["Profit Factor"]),
        "max_drawdown": float(str(summary["Max Drawdown"]).replace("$", "").replace(",", "")),
        "win_rate": float(str(summary["Win Rate"]).replace("%", "")),
        "avg_mae_pts": float(summary["Average MAE (pts)"]),
        "avg_mfe_pts": float(summary["Average MFE (pts)"]),
    }


def run_single_strategy_test(
    data: pd.DataFrame,
    cfg: EngineConfig,
) -> None:
    filters = [
        TrendDirectionFilter(fast_length=50, slow_length=200),
        PullbackFilter(fast_length=50),
        RecoveryTriggerFilter(fast_length=50),
        VolatilityFilter(lookback=20, min_avg_range=8.0),
        MomentumFilter(lookback=10),
    ]

    strategy = CombinableFilterTrendStrategy(
        filters=filters,
        hold_bars=8,
        stop_distance_points=12.0,
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
    max_workers: int = 10,
) -> pd.DataFrame:
    filter_classes = [
        TrendDirectionFilter,
        PullbackFilter,
        RecoveryTriggerFilter,
        VolatilityFilter,
        MomentumFilter,
    ]

    combinations = generate_filter_combinations(
        filter_classes=filter_classes,
        min_filters=3,
        max_filters=5,
    )

    print("\n🧪 Running filter combination sweep...")
    print(f"Total filter combinations: {len(combinations)}")
    print(f"Parallel mode: ON | max_workers={max_workers}")

    tasks = [(data, cfg, combo_classes) for combo_classes in combinations]
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


def run_top_combo_refinement(
    data: pd.DataFrame,
    cfg: EngineConfig,
) -> pd.DataFrame:
    refiner = StrategyParameterRefiner(
        engine_class=MasterStrategyEngine,
        data=data,
        strategy_factory=RefinedFiveFilterTrendStrategy,
        config=cfg,
    )

    refinement_df = refiner.run_refinement(
        hold_bars=[6, 8, 10],
        stop_distance_points=[10.0, 12.0, 14.0],
        min_avg_range=[7.0, 8.0, 9.0],
        momentum_lookback=[8, 12],
        min_trades=150,
        min_trades_per_year=8.0,
        parallel=True,
        max_workers=10,
    )

    if not refinement_df.empty:
        print("\n🎯 Top Refinement Results:")
        print(refiner.top_results(10))
        refiner.print_summary_report(top_n=10)

        plateau = PlateauAnalyzer(refinement_df)
        plateau.print_report(top_n=10)

        output_path = Path("Outputs") / "top_combo_refinement_results.csv"
        saved_path = refiner.save_results_csv(output_path)
        print(f"\n💾 Top-combo refinement saved to: {saved_path}")
    else:
        print("\nNo refinement results met the trade filters.")

    return refinement_df


if __name__ == "__main__":
    total_start = time.perf_counter()

    CSV_PATH = Path("Data") / "ES_60m_2008_2026_tradestation.csv"
    OUTPUTS_DIR = Path("Outputs")
    COMBO_SWEEP_CSV_PATH = OUTPUTS_DIR / "filter_combination_sweep_results.csv"

    print("Loading data from:", CSV_PATH)
    data = load_tradestation_csv(CSV_PATH, debug=True)
    print("Data loaded successfully.")

    print("\n⚙ Adding precomputed feature columns...")
    data = add_precomputed_features(
        data,
        sma_lengths=[50, 200],
        avg_range_lookbacks=[20],
        momentum_lookbacks=[8, 10, 12],
    )
    print("Precomputed features added.")

    print_data_summary(data, name="ES Data (2008+)")

    cfg = EngineConfig(
        initial_capital=250_000.0,
        risk_per_trade=0.01,
        symbol="ES",
    )

    # ---------------------------------
    # Single sanity-check run
    # ---------------------------------
    run_single_strategy_test(data=data, cfg=cfg)

    # ---------------------------------
    # Filter combination sweep
    # ---------------------------------
    combo_start = time.perf_counter()
    combo_results_df = run_filter_combination_sweep(
        data=data,
        cfg=cfg,
        max_workers=10,
    )
    combo_elapsed = time.perf_counter() - combo_start

    if not combo_results_df.empty:
        print("\n📊 Top Filter Combination Results:")
        print(combo_results_df.head(10))

        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        combo_results_df.to_csv(COMBO_SWEEP_CSV_PATH, index=False)
        print(f"\n💾 Filter combination sweep saved to: {COMBO_SWEEP_CSV_PATH}")
    else:
        print("\nNo filter combination results generated.")

    print(f"\n⏱ Filter combination sweep runtime: {combo_elapsed:.2f} seconds")

    # ---------------------------------
    # Top-combo refinement
    # ---------------------------------
    run_top_combo_refinement(data=data, cfg=cfg)

    total_elapsed = time.perf_counter() - total_start
    print(f"\n🏁 Total script runtime: {total_elapsed:.2f} seconds")