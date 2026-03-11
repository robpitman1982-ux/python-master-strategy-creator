"""
Master Strategy Engine
Project: Python Master Strategy Creator
"""

from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Callable

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

    text = str(value).replace("$", "").replace(",", "").strip()
    return float(text)


def _parse_percent(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).replace("%", "").strip()
    return float(text)


def _run_combo_case(task: tuple[pd.DataFrame, EngineConfig, object, list[type]]) -> dict[str, Any]:
    data, cfg, strategy_type, combo_classes = task

    combo_defaults = strategy_type.get_combo_sweep_defaults()

    strategy = strategy_type.create_combo_strategy(
        combo_classes=combo_classes,
        hold_bars=int(combo_defaults["hold_bars"]),
        stop_distance_points=float(combo_defaults["stop_distance_points"]),
    )

    engine = MasterStrategyEngine(data=data, config=cfg)
    engine.run(strategy=strategy)
    summary = engine.results()

    total_trades = int(summary["Total Trades"])
    years_in_sample = (data.index.max() - data.index.min()).days / 365.25
    trades_per_year = total_trades / years_in_sample if years_in_sample > 0 else 0.0

    thresholds = strategy_type.get_trade_filter_thresholds()
    passes_trade_filter = (
        total_trades >= thresholds["min_trades"]
        and trades_per_year >= thresholds["min_trades_per_year"]
    )

    filter_objects = strategy_type.build_filter_objects_from_classes(combo_classes)

    return {
        "strategy_name": str(summary["Strategy"]),
        "strategy_type": strategy_type.name,
        "filter_count": len(filter_objects),
        "filters": ",".join([f.name for f in filter_objects]),
        "total_trades": total_trades,
        "trades_per_year": round(trades_per_year, 2),
        "passes_trade_filter": passes_trade_filter,
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
    combo_classes = strategy_type.get_filter_classes()
    combo_defaults = strategy_type.get_combo_sweep_defaults()

    strategy = strategy_type.create_combo_strategy(
        combo_classes=combo_classes,
        hold_bars=int(combo_defaults["hold_bars"]),
        stop_distance_points=float(combo_defaults["stop_distance_points"]),
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
        min_filters=3,
        max_filters=5,
    )

    print(f"\n🧪 Running {strategy_type.name} filter combination sweep...")
    print(f"Total filter combinations: {len(combinations)}")
    print(f"Parallel mode: ON | max_workers={max_workers}")

    tasks = [(data, cfg, strategy_type, combo_classes) for combo_classes in combinations]
    results: list[dict[str, Any]] = []

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


def apply_promotion_gate(
    combo_results_df: pd.DataFrame,
    strategy_type_name: str,
    min_profit_factor: float = 1.00,
    min_average_trade: float = 0.0,
    require_positive_net_pnl: bool = False,
    top_n: int = 5,
) -> pd.DataFrame:
    if combo_results_df.empty:
        return pd.DataFrame()

    promoted = combo_results_df.copy()

    promoted = promoted[promoted["passes_trade_filter"] == True]
    promoted = promoted[promoted["profit_factor"] >= min_profit_factor]
    promoted = promoted[promoted["average_trade"] > min_average_trade]

    if require_positive_net_pnl:
        promoted = promoted[promoted["net_pnl"] > 0]

    promoted = promoted.sort_values(
        by=["profit_factor", "average_trade", "net_pnl"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    if top_n > 0:
        promoted = promoted.head(top_n).copy()

    print(f"\n🚦 Promotion Gate Results for strategy type: {strategy_type_name}")
    print(f"Minimum PF required: {min_profit_factor:.2f}")
    print(f"Minimum average trade required: {min_average_trade:.2f}")
    print(f"Require positive net PnL: {require_positive_net_pnl}")
    print(f"Promoted candidates: {len(promoted)}")

    if not promoted.empty:
        display_cols = [
            "strategy_name",
            "filters",
            "profit_factor",
            "average_trade",
            "net_pnl",
            "total_trades",
            "trades_per_year",
        ]
        available_cols = [c for c in display_cols if c in promoted.columns]

        print("\n✅ Promoted Candidates:")
        print(promoted[available_cols])
    else:
        print("\n❌ No candidates passed the promotion gate.")

    return promoted


def map_promoted_row_to_combo_classes(strategy_type, promoted_row: pd.Series) -> list[type]:
    """
    Rebuild the exact promoted filter combo from the saved filter names.
    """
    filter_name_list = str(promoted_row["filters"]).split(",")
    available_filter_classes = strategy_type.get_filter_classes()

    combo_classes: list[type] = []

    for filter_name in filter_name_list:
        matched_class = None
        for cls in available_filter_classes:
            if getattr(cls, "name", cls.__name__) == filter_name:
                matched_class = cls
                break

        if matched_class is None:
            raise ValueError(
                f"Could not map promoted filter '{filter_name}' back to a filter class "
                f"for strategy type '{strategy_type.name}'."
            )

        combo_classes.append(matched_class)

    return combo_classes


def build_candidate_specific_refinement_factory(
    strategy_type,
    promoted_combo_classes: list[type],
) -> Callable[..., Any]:
    """
    Returns a strategy factory that always rebuilds the exact promoted combo,
    while allowing the refiner to vary hold/stop and family-specific tuning params.
    """

    def candidate_specific_strategy_factory(
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
    ):
        return strategy_type.create_refinement_strategy_from_combo(
            combo_classes=promoted_combo_classes,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
            min_avg_range=min_avg_range,
            momentum_lookback=momentum_lookback,
        )

    return candidate_specific_strategy_factory


def run_top_combo_refinement(
    data: pd.DataFrame,
    cfg: EngineConfig,
    strategy_type,
    promoted_candidates_df: pd.DataFrame,
    max_workers: int = 10,
) -> pd.DataFrame:
    if promoted_candidates_df.empty:
        print(f"\n⛔ Skipping {strategy_type.name} refinement because no candidates were promoted.")
        return pd.DataFrame()

    top_candidate = promoted_candidates_df.iloc[0]

    print(f"\n🏆 Selected top promoted candidate for refinement:")
    print(f"Strategy: {top_candidate['strategy_name']}")
    print(f"Filters: {top_candidate['filters']}")
    print(f"PF: {top_candidate['profit_factor']:.2f}")
    print(f"Average Trade: {top_candidate['average_trade']:.2f}")
    print(f"Net PnL: {top_candidate['net_pnl']:.2f}")

    promoted_combo_classes = map_promoted_row_to_combo_classes(
        strategy_type=strategy_type,
        promoted_row=top_candidate,
    )

    candidate_strategy_factory = build_candidate_specific_refinement_factory(
        strategy_type=strategy_type,
        promoted_combo_classes=promoted_combo_classes,
    )

    refiner = StrategyParameterRefiner(
        engine_class=MasterStrategyEngine,
        data=data,
        strategy_factory=candidate_strategy_factory,
        config=cfg,
    )

    grid = strategy_type.get_refinement_grid()
    thresholds = strategy_type.get_trade_filter_thresholds()

    refinement_df = refiner.run_refinement(
        hold_bars=grid["hold_bars"],
        stop_distance_points=grid["stop_distance_points"],
        min_avg_range=grid["min_avg_range"],
        momentum_lookback=grid["momentum_lookback"],
        min_trades=int(thresholds["min_trades"]),
        min_trades_per_year=float(thresholds["min_trades_per_year"]),
        parallel=True,
        max_workers=max_workers,
    )

    if not refinement_df.empty:
        print(f"\n🎯 Top {strategy_type.name} Refinement Results:")
        print(refiner.top_results(10))
        refiner.print_summary_report(top_n=10)

        plateau = PlateauAnalyzer(refinement_df)
        plateau.print_report(top_n=10)

        output_path = Path("Outputs") / f"{strategy_type.name}_top_combo_refinement_results_narrow.csv"
        saved_path = refiner.save_results_csv(output_path)
        print(f"\n💾 Narrow top-combo refinement saved to: {saved_path}")
    else:
        print("\nNo refinement results met the trade filters.")

    return refinement_df


def validate_strategy_type_name(strategy_type_name: str) -> str:
    available = list_strategy_types()
    normalized = strategy_type_name.strip().lower()

    if normalized not in available:
        raise ValueError(
            f"Unknown strategy type: '{strategy_type_name}'. "
            f"Available strategy types: {available}"
        )

    return normalized


if __name__ == "__main__":
    total_start = time.perf_counter()

    CSV_PATH = Path("Data") / "ES_60m_2008_2026_tradestation.csv"
    OUTPUTS_DIR = Path("Outputs")
    COMBO_SWEEP_CSV_PATH = OUTPUTS_DIR / "filter_combination_sweep_results.csv"
    PROMOTED_CANDIDATES_CSV_PATH = OUTPUTS_DIR / "promoted_candidates.csv"

    STRATEGY_TYPE_NAME = "mean_reversion"
    MAX_WORKERS = 10

    # Promotion gate settings
    PROMOTION_MIN_PROFIT_FACTOR = 1.00
    PROMOTION_MIN_AVERAGE_TRADE = 0.0
    PROMOTION_REQUIRE_POSITIVE_NET_PNL = False
    PROMOTION_TOP_N = 5

    strategy_type_name = validate_strategy_type_name(STRATEGY_TYPE_NAME)
    strategy_type = get_strategy_type(strategy_type_name)

    print(f"Selected strategy type: {strategy_type.name}")
    print(f"Available strategy types: {list_strategy_types()}")

    print("\nLoading data from:", CSV_PATH)
    data = load_tradestation_csv(CSV_PATH, debug=True)
    print("Data loaded successfully.")

    cfg = EngineConfig(
        initial_capital=250_000.0,
        risk_per_trade=0.01,
        symbol="ES",
    )

    print(f"\n⚙ Adding precomputed feature columns for strategy type: {strategy_type.name}")
    feature_requirements = strategy_type.get_feature_requirements()

    data = add_precomputed_features(
        data,
        sma_lengths=feature_requirements.get("sma_lengths", []),
        avg_range_lookbacks=feature_requirements.get("avg_range_lookbacks", []),
        momentum_lookbacks=feature_requirements.get("momentum_lookbacks", []),
    )
    print("Precomputed features added.")

    print_data_summary(data, name="ES Data (2008+)")

    # ---------------------------------
    # Single sanity-check run
    # ---------------------------------
    run_single_strategy_test(
        data=data,
        cfg=cfg,
        strategy_type=strategy_type,
    )

    # ---------------------------------
    # Filter combination sweep
    # ---------------------------------
    combo_start = time.perf_counter()
    combo_results_df = run_filter_combination_sweep(
        data=data,
        cfg=cfg,
        strategy_type=strategy_type,
        max_workers=MAX_WORKERS,
    )
    combo_elapsed = time.perf_counter() - combo_start

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    if not combo_results_df.empty:
        print(f"\n📊 Top {strategy_type.name} Filter Combination Results:")
        print(combo_results_df.head(10))

        combo_results_df.to_csv(COMBO_SWEEP_CSV_PATH, index=False)
        print(f"\n💾 Filter combination sweep saved to: {COMBO_SWEEP_CSV_PATH}")
    else:
        print("\nNo filter combination results generated.")

    print(f"\n⏱ Filter combination sweep runtime: {combo_elapsed:.2f} seconds")

    # ---------------------------------
    # Promotion gate
    # ---------------------------------
    promoted_candidates_df = apply_promotion_gate(
        combo_results_df=combo_results_df,
        strategy_type_name=strategy_type.name,
        min_profit_factor=PROMOTION_MIN_PROFIT_FACTOR,
        min_average_trade=PROMOTION_MIN_AVERAGE_TRADE,
        require_positive_net_pnl=PROMOTION_REQUIRE_POSITIVE_NET_PNL,
        top_n=PROMOTION_TOP_N,
    )

    if not promoted_candidates_df.empty:
        promoted_candidates_df.to_csv(PROMOTED_CANDIDATES_CSV_PATH, index=False)
        print(f"\n💾 Promoted candidates saved to: {PROMOTED_CANDIDATES_CSV_PATH}")

    # ---------------------------------
    # Top-candidate refinement
    # ---------------------------------
    run_top_combo_refinement(
        data=data,
        cfg=cfg,
        strategy_type=strategy_type,
        promoted_candidates_df=promoted_candidates_df,
        max_workers=MAX_WORKERS,
    )

    total_elapsed = time.perf_counter() - total_start
    print(f"\n🏁 Total script runtime: {total_elapsed:.2f} seconds")