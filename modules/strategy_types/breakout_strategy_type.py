from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from modules.engine import EngineConfig, MasterStrategyEngine
from modules.feature_builder import add_precomputed_features
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
    BreakoutStrategy,
    CombinableBreakoutStrategy,
)
from modules.strategy_types.base_strategy_type import BaseStrategyType


class BreakoutStrategyType(BaseStrategyType):
    name = "breakout"

    def get_required_sma_lengths(self) -> list[int]:
        return [50, 200]

    def get_required_avg_range_lookbacks(self) -> list[int]:
        return [20]

    def get_required_momentum_lookbacks(self) -> list[int]:
        return []

    def add_features(self, data: pd.DataFrame) -> pd.DataFrame:
        return add_precomputed_features(
            data,
            sma_lengths=self.get_required_sma_lengths(),
            avg_range_lookbacks=self.get_required_avg_range_lookbacks(),
            momentum_lookbacks=self.get_required_momentum_lookbacks(),
        )

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

    def build_default_sanity_filters(self) -> list:
        return [
            CompressionFilter(lookback=20, max_avg_range=8.0),
            PriorRangePositionFilter(lookback=20, max_position=0.60),
            RangeBreakoutFilter(lookback=20),
            MinimumBreakDistanceFilter(min_break_distance=6.0),
            ExpansionBarFilter(min_expansion_multiple=1.2, lookback=20),
            BreakoutCloseStrengthFilter(min_close_position=0.60),
            BreakoutTrendFilter(fast_length=50, slow_length=200),
        ]

    def build_filter_objects_from_classes(self, combo_classes: list[type]) -> list:
        filter_objects = []

        for cls in combo_classes:
            if cls is CompressionFilter:
                filter_objects.append(cls(lookback=20, max_avg_range=8.0))
            elif cls is PriorRangePositionFilter:
                filter_objects.append(cls(lookback=20, max_position=0.60))
            elif cls is RangeBreakoutFilter:
                filter_objects.append(cls(lookback=20))
            elif cls is MinimumBreakDistanceFilter:
                filter_objects.append(cls(min_break_distance=6.0))
            elif cls is ExpansionBarFilter:
                filter_objects.append(cls(min_expansion_multiple=1.2, lookback=20))
            elif cls is BreakoutCloseStrengthFilter:
                filter_objects.append(cls(min_close_position=0.60))
            elif cls is BreakoutTrendFilter:
                filter_objects.append(cls(fast_length=50, slow_length=200))
            else:
                filter_objects.append(cls())

        return filter_objects

    def build_default_strategy(self):
        return BreakoutStrategy()

    def build_combinable_strategy(
        self,
        filters: list,
        hold_bars: int | None = None,
        stop_distance_points: float | None = None,
    ):
        return CombinableBreakoutStrategy(
            filters=filters,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
        )

    def build_candidate_specific_strategy(
        self,
        promoted_row: dict[str, Any],
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
    ):
        strategy_name = str(promoted_row.get("strategy_name", ""))
        filters = self._rebuild_filters_from_strategy_name(
            strategy_name=strategy_name,
            min_avg_range=min_avg_range,
            momentum_lookback=momentum_lookback,
        )

        return CombinableBreakoutStrategy(
            filters=filters,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
        )

    def _rebuild_filters_from_strategy_name(
        self,
        strategy_name: str,
        min_avg_range: float,
        momentum_lookback: int,
    ) -> list:
        filters: list = []

        if "Compression" in strategy_name:
            filters.append(
                CompressionFilter(
                    lookback=20,
                    max_avg_range=float(min_avg_range),
                )
            )

        if "PriorRangePosition" in strategy_name:
            filters.append(PriorRangePositionFilter(lookback=20, max_position=0.60))

        if "RangeBreakout" in strategy_name:
            filters.append(RangeBreakoutFilter(lookback=20))

        if "MinimumBreakDistance" in strategy_name:
            filters.append(
                MinimumBreakDistanceFilter(
                    min_break_distance=float(max(1.0, momentum_lookback))
                )
            )

        if "ExpansionBar" in strategy_name:
            filters.append(ExpansionBarFilter(min_expansion_multiple=1.2, lookback=20))

        if "BreakoutCloseStrength" in strategy_name:
            filters.append(BreakoutCloseStrengthFilter(min_close_position=0.60))

        if "BreakoutTrend" in strategy_name:
            filters.append(BreakoutTrendFilter(fast_length=50, slow_length=200))

        return filters

    def run_filter_combination_sweep(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        max_workers: int = 10,
    ) -> pd.DataFrame:
        from concurrent.futures import ProcessPoolExecutor

        filter_classes = self.get_filter_classes()
        combinations = generate_filter_combinations(
            filter_classes=filter_classes,
            min_filters=3,
            max_filters=len(filter_classes),
        )

        print(f"\n🧪 Running {self.name} filter combination sweep...")
        print(f"Total filter combinations: {len(combinations)}")
        print(f"Parallel mode: ON | max_workers={max_workers}")

        tasks = [(data, cfg, combo_classes) for combo_classes in combinations]
        results: list[dict[str, Any]] = []

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            for idx, result in enumerate(executor.map(self._run_combo_case, tasks), start=1):
                print(f"  Combo {idx}/{len(combinations)} | {result['strategy_name']}")
                results.append(result)

        results_df = pd.DataFrame(results)

        if not results_df.empty:
            results_df = results_df.sort_values(
                by=["passes_trade_filter", "profit_factor", "average_trade", "net_pnl"],
                ascending=[False, False, False, False],
            ).reset_index(drop=True)

        return results_df

    def _run_combo_case(
        self,
        task: tuple[pd.DataFrame, EngineConfig, list[type]],
    ) -> dict[str, Any]:
        data, cfg, combo_classes = task

        filter_objects = self.build_filter_objects_from_classes(combo_classes)

        strategy = CombinableBreakoutStrategy(
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

        min_trades, min_trades_per_year = self.get_trade_filter_thresholds()
        passes_filter = total_trades >= min_trades and trades_per_year >= min_trades_per_year

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

    def get_trade_filter_thresholds(self) -> tuple[int, float]:
        return 150, 8.0

    def get_promotion_gate_config(self) -> dict[str, Any]:
        return {
            "min_profit_factor": 1.00,
            "min_average_trade": 0.0,
            "require_positive_net_pnl": False,
            "max_candidates": 5,
        }

    def get_promotion_thresholds(self) -> dict[str, Any]:
        return self.get_promotion_gate_config()

    def get_active_refinement_grid_for_combo(self, promoted_row: dict[str, Any]) -> dict[str, list]:
        return {
            "hold_bars": [4, 6, 8, 10],
            "stop_distance_points": [10.0, 12.0, 14.0, 16.0],
            "min_avg_range": [6.0, 7.0, 8.0, 9.0],
            "momentum_lookback": [10, 15, 20, 25],
        }

    def run_refinement_for_candidate(
        self,
        promoted_row: dict[str, Any],
        data: pd.DataFrame,
        cfg: EngineConfig,
        max_workers: int = 10,
    ) -> pd.DataFrame:
        active_grid = self.get_active_refinement_grid_for_combo(promoted_row)

        def strategy_factory(
            hold_bars: int,
            stop_distance_points: float,
            min_avg_range: float,
            momentum_lookback: int,
        ):
            return self.build_candidate_specific_strategy(
                promoted_row=promoted_row,
                hold_bars=hold_bars,
                stop_distance_points=stop_distance_points,
                min_avg_range=min_avg_range,
                momentum_lookback=momentum_lookback,
            )

        refiner = StrategyParameterRefiner(
            engine_class=MasterStrategyEngine,
            data=data,
            strategy_factory=strategy_factory,
            config=cfg,
        )

        print("\n🎯 Running top-combo parameter refinement...")
        refinement_df = refiner.run_refinement(
            hold_bars=active_grid["hold_bars"],
            stop_distance_points=active_grid["stop_distance_points"],
            min_avg_range=active_grid["min_avg_range"],
            momentum_lookback=active_grid["momentum_lookback"],
            min_trades=self.get_trade_filter_thresholds()[0],
            min_trades_per_year=self.get_trade_filter_thresholds()[1],
            parallel=True,
            max_workers=max_workers,
        )

        if not refinement_df.empty:
            print(f"\n🎯 Top {self.name} Refinement Results:")
            print(refiner.top_results(10))
            refiner.print_summary_report(top_n=10)

            plateau = PlateauAnalyzer(refinement_df)
            plateau.print_report(top_n=10)

            output_path = Path("Outputs") / f"{self.name}_top_combo_refinement_results_narrow.csv"
            saved_path = refiner.save_results_csv(output_path)
            print(f"\n💾 Narrow top-combo refinement saved to: {saved_path}")
        else:
            print("\nNo refinement results met the trade filters.")

        return refinement_df

    def run_top_combo_refinement(
        self,
        promoted_row: dict[str, Any],
        data: pd.DataFrame,
        cfg: EngineConfig,
        max_workers: int = 10,
    ) -> pd.DataFrame:
        return self.run_refinement_for_candidate(
            promoted_row=promoted_row,
            data=data,
            cfg=cfg,
            max_workers=max_workers,
        )

    def get_refinement_parameter_labels(self) -> dict[str, str]:
        return {
            "hold_bars": "hold_bars",
            "stop_distance_points": "stop_distance_points",
            "min_avg_range": "min_avg_range",
            "momentum_lookback": "momentum_lookback",
        }

    def get_family_summary_notes(
        self,
        promoted_df: pd.DataFrame,
        refinement_df: pd.DataFrame,
    ) -> str:
        if promoted_df.empty:
            return "No candidates passed the promotion gate."

        if refinement_df.empty:
            return "At least one candidate passed promotion, but no refinement rows met the refinement trade filters."

        return "At least one candidate passed promotion and refinement was attempted."