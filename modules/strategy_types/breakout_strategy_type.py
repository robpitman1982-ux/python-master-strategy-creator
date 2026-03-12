"""
Breakout Strategy Type
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd

from .base_strategy_type import BaseStrategyType
from modules.engine import EngineConfig, MasterStrategyEngine
from modules.filter_combinator import generate_filter_combinations
from modules.filters import (
    BreakoutCloseStrengthFilter,
    BreakoutTrendFilter,
    CompressionFilter,
    ExpansionBarFilter,
    MinimumBreakDistanceFilter,
    PriorRangePositionFilter,
    RangeBreakoutFilter,
)
from modules.plateau_analyzer import PlateauAnalyzer
from modules.refiner import StrategyParameterRefiner
from modules.strategies import (
    CombinableFilterBreakoutStrategy,
    FilterBasedBreakoutStrategy,
    RefinedBreakoutStrategy,
)


def _run_breakout_combo_case(task: tuple[pd.DataFrame, EngineConfig, list[type]]) -> dict[str, Any]:
    data, cfg, combo_classes = task

    filter_objects = []

    for cls in combo_classes:
        if cls is CompressionFilter:
            filter_objects.append(cls(lookback=20, max_avg_range=9.0))
        elif cls is PriorRangePositionFilter:
            filter_objects.append(cls(lookback=20, threshold=0.35))
        elif cls is RangeBreakoutFilter:
            filter_objects.append(cls(lookback=20))
        elif cls is MinimumBreakDistanceFilter:
            filter_objects.append(cls(min_break_distance=1.5))
        elif cls is ExpansionBarFilter:
            filter_objects.append(cls(lookback=20, expansion_multiplier=1.2))
        elif cls is BreakoutCloseStrengthFilter:
            filter_objects.append(cls(min_close_position=0.60))
        elif cls is BreakoutTrendFilter:
            filter_objects.append(cls(fast_length=50, slow_length=200))
        else:
            filter_objects.append(cls())

    strategy = CombinableFilterBreakoutStrategy(
        filters=filter_objects,
        hold_bars=6,
        stop_distance_points=12.0,
    )

    engine = MasterStrategyEngine(data=data, config=cfg)
    engine.run(strategy=strategy)
    summary = engine.results()

    total_trades = int(summary["Total Trades"])
    years_in_sample = (data.index.max() - data.index.min()).days / 365.25
    trades_per_year = total_trades / years_in_sample if years_in_sample > 0 else 0.0

    thresholds = {
        "min_trades": 150,
        "min_trades_per_year": 8.0,
    }

    passes_trade_filter = (
        total_trades >= thresholds["min_trades"]
        and trades_per_year >= thresholds["min_trades_per_year"]
    )

    return {
        "strategy_name": str(summary["Strategy"]),
        "filter_count": len(filter_objects),
        "filters": ",".join([f.name for f in filter_objects]),
        "total_trades": total_trades,
        "trades_per_year": round(trades_per_year, 2),
        "passes_trade_filter": passes_trade_filter,
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


class BreakoutStrategyType(BaseStrategyType):
    name = "breakout"

    def get_required_sma_lengths(self) -> list[int]:
        return [50, 200]

    def get_required_avg_range_lookbacks(self) -> list[int]:
        return [20]

    def get_required_momentum_lookbacks(self) -> list[int]:
        return []

    def get_filter_classes(self) -> list[type]:
        return [
            CompressionFilter,
            PriorRangePositionFilter,
            RangeBreakoutFilter,
            MinimumBreakDistanceFilter,
            ExpansionBarFilter,
            BreakoutCloseStrengthFilter,
            BreakoutTrendFilter,
        ]

    def build_filter_objects_from_classes(self, combo_classes: list[type]) -> list:
        filter_objects = []

        for cls in combo_classes:
            if cls is CompressionFilter:
                filter_objects.append(cls(lookback=20, max_avg_range=9.0))
            elif cls is PriorRangePositionFilter:
                filter_objects.append(cls(lookback=20, threshold=0.35))
            elif cls is RangeBreakoutFilter:
                filter_objects.append(cls(lookback=20))
            elif cls is MinimumBreakDistanceFilter:
                filter_objects.append(cls(min_break_distance=1.5))
            elif cls is ExpansionBarFilter:
                filter_objects.append(cls(lookback=20, expansion_multiplier=1.2))
            elif cls is BreakoutCloseStrengthFilter:
                filter_objects.append(cls(min_close_position=0.60))
            elif cls is BreakoutTrendFilter:
                filter_objects.append(cls(fast_length=50, slow_length=200))
            else:
                filter_objects.append(cls())

        return filter_objects

    def build_default_strategy(self):
        return FilterBasedBreakoutStrategy()

    def build_default_sanity_filters(self) -> dict[str, Any]:
        return {}

    def build_combinable_strategy(
        self,
        filters: list,
        hold_bars: int,
        stop_distance_points: float,
    ):
        return CombinableFilterBreakoutStrategy(
            filters=filters,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
        )

    def build_combination_strategy(self, filters: dict[str, Any]):
        return CombinableFilterBreakoutStrategy(
            filters=filters["filter_objects"],
            hold_bars=filters.get("hold_bars", 6),
            stop_distance_points=filters.get("stop_distance_points", 12.0),
        )

    def build_candidate_specific_strategy(self, candidate_row: dict[str, Any]):
        return RefinedBreakoutStrategy(
            hold_bars=int(candidate_row.get("hold_bars", 6)),
            stop_distance_points=float(candidate_row.get("stop_distance_points", 12.0)),
            min_avg_range=float(candidate_row.get("min_avg_range", 7.0)),
            momentum_lookback=int(candidate_row.get("momentum_lookback", 10)),
        )

    def build_candidate_specific_refinement_factory(self, candidate_row: dict[str, Any]):
        return RefinedBreakoutStrategy

    def get_trade_filter_thresholds(self) -> dict[str, Any]:
        return {
            "min_trades": 150,
            "min_trades_per_year": 8.0,
        }

    def get_trade_filter_config(self) -> dict[str, Any]:
        return self.get_trade_filter_thresholds()

    def get_promotion_thresholds(self) -> dict[str, Any]:
        return {
            "min_profit_factor": 1.00,
            "min_average_trade": 0.0,
            "require_positive_net_pnl": False,
        }

    def get_promotion_gate_config(self) -> dict[str, Any]:
        return self.get_promotion_thresholds()

    def get_active_refinement_grid_for_combo(self, candidate_row: dict[str, Any]) -> dict[str, list]:
        return {
            "hold_bars": [4, 6, 8, 10],
            "stop_distance_points": [10.0, 12.0, 14.0, 16.0],
            "min_avg_range": [6.0, 7.0, 8.0, 9.0],
            "momentum_lookback": [10, 15, 20, 25],
        }

    def get_refinement_grid_for_candidate(self, candidate_row: dict[str, Any]) -> dict[str, list]:
        return self.get_active_refinement_grid_for_combo(candidate_row)

    def run_family_filter_combination_sweep(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        max_workers: int = 10,
    ) -> pd.DataFrame:
        filter_classes = self.get_filter_classes()

        combinations = generate_filter_combinations(
            filter_classes=filter_classes,
            min_filters=3,
            max_filters=5,
        )

        print("\n🧪 Running breakout filter combination sweep...")
        print(f"Total filter combinations: {len(combinations)}")
        print(f"Parallel mode: ON | max_workers={max_workers}")

        tasks = [(data, cfg, combo_classes) for combo_classes in combinations]
        results: list[dict[str, Any]] = []

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            for idx, result in enumerate(executor.map(_run_breakout_combo_case, tasks), start=1):
                print(f"  Combo {idx}/{len(combinations)} | {result['strategy_name']}")
                results.append(result)

        results_df = pd.DataFrame(results)

        if not results_df.empty:
            results_df = results_df.sort_values(
                by=["passes_trade_filter", "profit_factor", "average_trade", "net_pnl"],
                ascending=[False, False, False, False],
            ).reset_index(drop=True)

        return results_df

    def run_refinement_for_candidate(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        candidate_row: dict[str, Any],
        output_dir: str | Path = "Outputs",
        max_workers: int = 10,
    ) -> pd.DataFrame:
        refiner = StrategyParameterRefiner(
            engine_class=MasterStrategyEngine,
            data=data,
            strategy_factory=RefinedBreakoutStrategy,
            config=cfg,
        )

        grid = self.get_refinement_grid_for_candidate(candidate_row)
        trade_filters = self.get_trade_filter_thresholds()

        refinement_df = refiner.run_refinement(
            hold_bars=grid["hold_bars"],
            stop_distance_points=grid["stop_distance_points"],
            min_avg_range=grid["min_avg_range"],
            momentum_lookback=grid["momentum_lookback"],
            min_trades=trade_filters["min_trades"],
            min_trades_per_year=trade_filters["min_trades_per_year"],
            parallel=True,
            max_workers=max_workers,
        )

        if not refinement_df.empty:
            print("\n🎯 Top breakout Refinement Results:")
            print(refiner.top_results(10))
            refiner.print_summary_report(top_n=10)

            plateau = PlateauAnalyzer(refinement_df)
            plateau.print_report(top_n=10)

            output_path = Path(output_dir) / "breakout_top_combo_refinement_results_narrow.csv"
            saved_path = refiner.save_results_csv(output_path)
            print(f"\n💾 Narrow top-combo refinement saved to: {saved_path}")
        else:
            print("\nNo refinement results met the trade filters.")

        return refinement_df

    def run_top_combo_refinement(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        candidate_row: dict[str, Any],
        output_dir: str | Path = "Outputs",
        max_workers: int = 10,
    ) -> pd.DataFrame:
        return self.run_refinement_for_candidate(
            data=data,
            cfg=cfg,
            candidate_row=candidate_row,
            output_dir=output_dir,
            max_workers=max_workers,
        )