from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd

from modules.engine import EngineConfig, MasterStrategyEngine
from modules.filter_combinator import build_filter_combo_name, generate_filter_combinations
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
from modules.strategy_types.base_strategy_type import BaseStrategyType

# =============================================================================
# INLINE BREAKOUT STRATEGY
# =============================================================================
class _InlineBreakoutStrategy:
    direction = "LONG_ONLY"

    def __init__(
        self,
        filters: list[Any],
        hold_bars: int = 10,
        stop_distance_points: float = 14.0,
        name: str | None = None,
    ) -> None:
        self.filters = filters
        self.hold_bars = hold_bars
        self.stop_distance_points = stop_distance_points
        self.name = name or f"ComboBreakout_{build_filter_combo_name(filters)}"

    def generate_signal(self, data: pd.DataFrame, i: int) -> int:
        for filter_obj in self.filters:
            if not filter_obj.passes(data, i):
                return 0
        return 1

# =============================================================================
# RUNNER HELPER FOR SWEEP
# =============================================================================
def _run_breakout_combo_case(task: tuple[pd.DataFrame, EngineConfig, list[type]]) -> dict[str, Any]:
    data, cfg, combo_classes = task

    strategy_type = BreakoutStrategyType()
    filter_objects = strategy_type.build_filter_objects_from_classes(combo_classes)
    
    strategy = strategy_type.build_combinable_strategy(
        filters=filter_objects,
        hold_bars=strategy_type.default_hold_bars,
        stop_distance_points=strategy_type.default_stop_distance_points,
    )

    engine = MasterStrategyEngine(data=data, config=cfg)
    engine.run(strategy=strategy)
    summary = engine.results()

    total_trades = int(str(summary.get("Total Trades", 0)).replace(",", ""))
    years_in_sample = (data.index.max() - data.index.min()).days / 365.25
    trades_per_year = total_trades / years_in_sample if years_in_sample > 0 else 0.0

    thresholds = strategy_type.get_trade_filter_thresholds()
    passes_trade_filter = (
        total_trades >= thresholds["min_trades"]
        and trades_per_year >= thresholds["min_trades_per_year"]
    )

    def _parse_float(val: Any) -> float:
        return float(str(val).replace("$", "").replace(",", "").replace("%", "").strip() or 0.0)

    return {
        "strategy_name": str(summary.get("Strategy", "UnknownStrategy")),
        "filter_count": len(filter_objects),
        "filters": ",".join([f.name for f in filter_objects]),
        "total_trades": total_trades,
        "trades_per_year": round(trades_per_year, 2),
        "passes_trade_filter": passes_trade_filter,
        "net_pnl": _parse_float(summary.get("Net PnL", 0.0)),
        "gross_profit": _parse_float(summary.get("Gross Profit", 0.0)),
        "gross_loss": _parse_float(summary.get("Gross Loss", 0.0)),
        "average_trade": _parse_float(summary.get("Average Trade", 0.0)),
        "profit_factor": _parse_float(summary.get("Profit Factor", 0.0)),
        "max_drawdown": _parse_float(summary.get("Max Drawdown", 0.0)),
        "win_rate": _parse_float(summary.get("Win Rate", 0.0)),
        "avg_mae_pts": _parse_float(summary.get("Average MAE (pts)", 0.0)),
        "avg_mfe_pts": _parse_float(summary.get("Average MFE (pts)", 0.0)),
    }

# =============================================================================
# BREAKOUT STRATEGY TYPE
# =============================================================================
class BreakoutStrategyType(BaseStrategyType):
    name = "breakout"

    min_filters_per_combo = 3
    max_filters_per_combo = 7

    default_hold_bars = 10
    default_stop_distance_points = 14.0

    def get_required_sma_lengths(self) -> list[int]:
        return [50, 200]

    def get_required_avg_range_lookbacks(self) -> list[int]:
        return [20]

    def get_required_momentum_lookbacks(self) -> list[int]:
        return []

    def build_default_sanity_filters(self) -> list[Any]:
        return [
            CompressionFilter(lookback=20, max_avg_range=6.0),
            PriorRangePositionFilter(lookback=20, min_position_in_range=0.60),
            RangeBreakoutFilter(lookback=20),
            MinimumBreakDistanceFilter(lookback=20, min_break_distance_points=1.0),
            ExpansionBarFilter(lookback=20, expansion_multiplier=1.20),
            BreakoutCloseStrengthFilter(close_position_threshold=0.60),
            BreakoutTrendFilter(fast_length=50, slow_length=200),
        ]

    def build_default_strategy(self) -> _InlineBreakoutStrategy:
        return _InlineBreakoutStrategy(
            filters=self.build_default_sanity_filters(),
            hold_bars=self.default_hold_bars,
            stop_distance_points=self.default_stop_distance_points,
            name="FilterBasedBreakoutStrategy",
        )

    def build_sanity_check_strategy(self) -> _InlineBreakoutStrategy:
        return self.build_default_strategy()

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

    def build_filter_objects_from_classes(self, combo_classes: list[type]) -> list[Any]:
        filters: list[Any] = []
        for cls in combo_classes:
            if cls is CompressionFilter:
                filters.append(CompressionFilter(lookback=20, max_avg_range=6.0))
            elif cls is PriorRangePositionFilter:
                filters.append(PriorRangePositionFilter(lookback=20, min_position_in_range=0.60))
            elif cls is RangeBreakoutFilter:
                filters.append(RangeBreakoutFilter(lookback=20))
            elif cls is MinimumBreakDistanceFilter:
                filters.append(MinimumBreakDistanceFilter(lookback=20, min_break_distance_points=1.0))
            elif cls is ExpansionBarFilter:
                filters.append(ExpansionBarFilter(lookback=20, expansion_multiplier=1.20))
            elif cls is BreakoutCloseStrengthFilter:
                filters.append(BreakoutCloseStrengthFilter(close_position_threshold=0.60))
            elif cls is BreakoutTrendFilter:
                filters.append(BreakoutTrendFilter(fast_length=50, slow_length=200))
            else:
                raise ValueError(f"Unsupported breakout filter class: {cls}")
        return filters

    def build_combinable_strategy(
        self,
        filters: list[Any],
        hold_bars: int,
        stop_distance_points: float,
    ) -> _InlineBreakoutStrategy:
        return _InlineBreakoutStrategy(
            filters=filters,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
        )

    def build_candidate_specific_strategy(
        self,
        promoted_combo_classes: list[type],
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
    ) -> _InlineBreakoutStrategy:
        
        filters: list[Any] = []
        for cls in promoted_combo_classes:
            if cls is CompressionFilter:
                max_range_val = float(min_avg_range) if min_avg_range > 0 else 6.0
                filters.append(CompressionFilter(lookback=20, max_avg_range=max_range_val))
            elif cls is PriorRangePositionFilter:
                filters.append(PriorRangePositionFilter(lookback=20, min_position_in_range=0.60))
            elif cls is RangeBreakoutFilter:
                filters.append(RangeBreakoutFilter(lookback=20))
            elif cls is MinimumBreakDistanceFilter:
                filters.append(MinimumBreakDistanceFilter(lookback=20, min_break_distance_points=1.0))
            elif cls is ExpansionBarFilter:
                filters.append(ExpansionBarFilter(lookback=20, expansion_multiplier=1.20))
            elif cls is BreakoutCloseStrengthFilter:
                filters.append(BreakoutCloseStrengthFilter(close_position_threshold=0.60))
            elif cls is BreakoutTrendFilter:
                filters.append(BreakoutTrendFilter(fast_length=50, slow_length=200))
            else:
                filters.append(cls())

        return _InlineBreakoutStrategy(
            filters=filters,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
            name=(
                f"RefinedBreakoutStrategy_"
                f"HB{hold_bars}_STOP{stop_distance_points}_"
                f"RANGE{min_avg_range}_MOM{momentum_lookback}"
            ),
        )

    def get_promotion_thresholds(self) -> dict[str, float | bool]:
        return {
            "min_profit_factor": 1.00,
            "min_average_trade": 0.00,
            "require_positive_net_pnl": False,
        }

    def get_promotion_gate_config(self) -> dict[str, float | bool]:
        return self.get_promotion_thresholds()

    def get_trade_filter_thresholds(self) -> dict[str, float]:
        return {
            "min_trades": 150,
            "min_trades_per_year": 8.0,
        }

    def get_trade_filter_config(self) -> dict[str, float]:
        return self.get_trade_filter_thresholds()

    def get_active_refinement_grid_for_combo(
        self,
        promoted_combo_classes: list[type],
    ) -> dict[str, list[Any]]:
        return {
            "hold_bars": [4, 6, 8, 10],
            "stop_distance_points": [10.0, 12.0, 14.0, 16.0],
            "min_avg_range": [6.0, 7.0, 8.0, 9.0], 
            "momentum_lookback": [0], 
        }

    def get_refinement_grid_for_candidate(
        self, 
        candidate_row: dict[str, Any]
    ) -> dict[str, list[Any]]:
        promoted_combo_classes = candidate_row.get("filter_classes", [])
        return self.get_active_refinement_grid_for_combo(promoted_combo_classes)

    def run_family_filter_combination_sweep(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        max_workers: int = 10,
    ) -> pd.DataFrame:
        filter_classes = self.get_filter_classes()
        combinations = generate_filter_combinations(
            filter_classes=filter_classes,
            min_filters=self.min_filters_per_combo,
            max_filters=self.max_filters_per_combo,
        )

        print(f"\n Running {self.name} filter combination sweep...")
        print(f"Total filter combinations: {len(combinations)}")
        print(f"Parallel mode: ON | max_workers={max_workers}")

        tasks = [(data, cfg, combo_classes) for combo_classes in combinations]
        results: list[dict[str, Any]] = []

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            for idx, result in enumerate(executor.map(_run_breakout_combo_case, tasks), start=1):
                print(f"  Combo {idx}/{len(combinations)} | {result['strategy_name']}")
                result["filter_classes"] = combinations[idx - 1]
                results.append(result)

        results_df = pd.DataFrame(results)
        if not results_df.empty:
            results_df = results_df.sort_values(
                by=["passes_trade_filter", "profit_factor", "average_trade", "net_pnl"],
                ascending=[False, False, False, False],
            ).reset_index(drop=True)

        return results_df

    def run_top_combo_refinement(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        candidate_row: dict[str, Any],
        output_dir: str | Path = "Outputs",
        max_workers: int = 10,
    ) -> pd.DataFrame:
        promoted_combo_classes = candidate_row.get("filter_classes", [])
        grid = self.get_active_refinement_grid_for_combo(promoted_combo_classes)
        trade_filters = self.get_trade_filter_thresholds()

        def strategy_factory(
            hold_bars: int,
            stop_distance_points: float,
            min_avg_range: float,
            momentum_lookback: int,
        ):
            return self.build_candidate_specific_strategy(
                promoted_combo_classes=promoted_combo_classes,
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

        print("\n Running top-combo parameter refinement...")
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
            print(f"\n Top {self.name} Refinement Results:")
            print(refiner.top_results(10))
            refiner.print_summary_report(top_n=10)

            plateau = PlateauAnalyzer(refinement_df)
            plateau.print_report(top_n=10)

            output_path = Path(output_dir) / f"{self.name}_top_combo_refinement_results_narrow.csv"
            saved_path = refiner.save_results_csv(output_path)
            print(f"\n Narrow top-combo refinement saved to: {saved_path}")
        else:
            print("\nNo refinement results met the trade filters.")

        return refinement_df