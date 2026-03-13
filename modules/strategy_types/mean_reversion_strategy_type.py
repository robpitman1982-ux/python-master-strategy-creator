from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any
import pandas as pd

from modules.engine import EngineConfig, MasterStrategyEngine
from modules.filter_combinator import build_filter_combo_name, generate_filter_combinations
from modules.filters import (
    BaseFilter, BelowFastSMAFilter, DistanceBelowSMAFilter, DownCloseFilter,
    TwoBarDownFilter, ReversalUpBarFilter, LowVolatilityRegimeFilter, AboveLongTermSMAFilter
)
from modules.plateau_analyzer import PlateauAnalyzer
from modules.refiner import StrategyParameterRefiner
from modules.strategy_types.base_strategy_type import BaseStrategyType

class _InlineMeanReversionStrategy:
    direction = "LONG_ONLY"
    def __init__(self, filters: list[BaseFilter], hold_bars: int = 4, stop_distance_points: float = 8.0, name: str | None = None):
        self.filters = filters
        self.hold_bars = hold_bars
        self.stop_distance_points = stop_distance_points
        self.name = name or f"ComboMR_{build_filter_combo_name(filters)}"

    def generate_signal(self, data: pd.DataFrame, i: int) -> int:
        for filter_obj in self.filters:
            if not filter_obj.passes(data, i): return 0
        return 1

def _run_mr_combo_case(task: tuple[pd.DataFrame, EngineConfig, list[type]]) -> dict[str, Any]:
    data, cfg, combo_classes = task
    strategy_type = MeanReversionStrategyType()
    filter_objects = strategy_type.build_filter_objects_from_classes(combo_classes)
    strategy = strategy_type.build_combinable_strategy(filter_objects, strategy_type.default_hold_bars, strategy_type.default_stop_distance_points)
    engine = MasterStrategyEngine(data=data, config=cfg)
    engine.run(strategy=strategy)
    summary = engine.results()
    total_trades = int(str(summary.get("Total Trades", 0)).replace(",", ""))
    years_in_sample = (data.index.max() - data.index.min()).days / 365.25
    trades_per_year = total_trades / years_in_sample if years_in_sample > 0 else 0.0
    thresholds = strategy_type.get_trade_filter_thresholds()
    passes_trade_filter = (total_trades >= thresholds["min_trades"] and trades_per_year >= thresholds["min_trades_per_year"])

    def _parse_float(val: Any) -> float:
        return float(str(val).replace("$", "").replace(",", "").replace("%", "").strip() or 0.0)

    return {
        "strategy_name": str(summary.get("Strategy", "UnknownStrategy")),
        "filter_count": len(filter_objects),
        "filters": ",".join([f.name for f in filter_objects]),
        "filter_class_names": ",".join([cls.__name__ for cls in combo_classes]),
        "total_trades": total_trades,
        "trades_per_year": round(trades_per_year, 2),
        "passes_trade_filter": passes_trade_filter,
        "net_pnl": _parse_float(summary.get("Net PnL", 0.0)),
        "profit_factor": _parse_float(summary.get("Profit Factor", 0.0)),
        "average_trade": _parse_float(summary.get("Average Trade", 0.0)),
    }

class _MRRefinementFactory:
    def __init__(self, strategy_type_instance, promoted_combo_classes: list[type]):
        self.strategy_type_instance = strategy_type_instance
        self.promoted_combo_classes = promoted_combo_classes

    def __call__(self, hold_bars: int, stop_distance_points: float, min_avg_range: float, momentum_lookback: int):
        return self.strategy_type_instance.build_candidate_specific_strategy(
            self.promoted_combo_classes, hold_bars, stop_distance_points, min_avg_range, momentum_lookback
        )

class MeanReversionStrategyType(BaseStrategyType):
    name = "mean_reversion"
    min_filters_per_combo = 3
    max_filters_per_combo = 7
    default_hold_bars = 4
    default_stop_distance_points = 10.0

    def get_required_sma_lengths(self) -> list[int]: return [20, 200]
    def get_required_avg_range_lookbacks(self) -> list[int]: return [20]
    def get_required_momentum_lookbacks(self) -> list[int]: return []

    def build_default_sanity_filters(self) -> list[BaseFilter]:
        return [BelowFastSMAFilter(), DownCloseFilter(), ReversalUpBarFilter(), AboveLongTermSMAFilter()]

    def build_default_strategy(self) -> _InlineMeanReversionStrategy:
        return _InlineMeanReversionStrategy(self.build_default_sanity_filters(), self.default_hold_bars, self.default_stop_distance_points, "FilterBasedMRStrategy")

    def build_sanity_check_strategy(self) -> _InlineMeanReversionStrategy: return self.build_default_strategy()

    def get_filter_classes(self) -> list[type]:
        return [BelowFastSMAFilter, DistanceBelowSMAFilter, DownCloseFilter, TwoBarDownFilter, ReversalUpBarFilter, LowVolatilityRegimeFilter, AboveLongTermSMAFilter]

    def build_filter_objects_from_classes(self, combo_classes: list[type]) -> list[BaseFilter]:
        return [cls() for cls in combo_classes]

    def build_combinable_strategy(self, filters: list[BaseFilter], hold_bars: int, stop_distance_points: float) -> _InlineMeanReversionStrategy:
        return _InlineMeanReversionStrategy(filters, hold_bars, stop_distance_points)

    def build_candidate_specific_strategy(self, promoted_combo_classes: list[type], hold_bars: int, stop_distance_points: float, min_avg_range: float, momentum_lookback: int) -> _InlineMeanReversionStrategy:
        filters: list[BaseFilter] = []
        for cls in promoted_combo_classes:
            if cls is DistanceBelowSMAFilter: filters.append(DistanceBelowSMAFilter(min_distance_points=min_avg_range if min_avg_range > 0 else 6.0))
            elif cls is LowVolatilityRegimeFilter: filters.append(LowVolatilityRegimeFilter(max_avg_range=min_avg_range if min_avg_range > 0 else 15.0))
            else: filters.append(cls())
        return _InlineMeanReversionStrategy(filters, hold_bars, stop_distance_points, name=f"RefinedMRStrategy_HB{hold_bars}_STOP{stop_distance_points}_RANGE{min_avg_range}_MOM{momentum_lookback}")

    def get_promotion_thresholds(self) -> dict[str, float | bool]:
        return {"min_profit_factor": 1.00, "min_average_trade": 0.0, "require_positive_net_pnl": False, "min_trades": 100, "min_trades_per_year": 5.0}

    def get_promotion_gate_config(self) -> dict[str, float | bool]: return self.get_promotion_thresholds()
    def get_trade_filter_thresholds(self) -> dict[str, float]: return {"min_trades": 100, "min_trades_per_year": 5.0}
    def get_trade_filter_config(self) -> dict[str, float]: return self.get_trade_filter_thresholds()

    def get_active_refinement_grid_for_combo(self, promoted_combo_classes: list[type]) -> dict[str, list]:
        grid: dict[str, list] = {"hold_bars": [2, 3, 4, 5, 6, 8], "stop_distance_points": [6.0, 8.0, 10.0, 15.0, 20.0]}
        
        # FIXED: Added 4.0 and 6.0 so we don't starve Candidate #2 of trades!
        grid["min_avg_range"] = [4.0, 6.0, 8.0, 10.0, 15.0] if any(cls in [DistanceBelowSMAFilter, LowVolatilityRegimeFilter] for cls in promoted_combo_classes) else [0.0]
        
        grid["momentum_lookback"] = [0]
        return grid

    def get_refinement_grid_for_candidate(self, candidate_row: dict[str, Any]) -> dict[str, list]:
        return self.get_active_refinement_grid_for_combo(candidate_row.get("filter_classes", []))

    def run_family_filter_combination_sweep(self, data: pd.DataFrame, cfg: EngineConfig, max_workers: int = 10) -> pd.DataFrame:
        combinations = generate_filter_combinations(self.get_filter_classes(), self.min_filters_per_combo, self.max_filters_per_combo)
        tasks = [(data, cfg, combo_classes) for combo_classes in combinations]
        results: list[dict[str, Any]] = []
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            for idx, result in enumerate(executor.map(_run_mr_combo_case, tasks)):
                print(f"  Combo {idx + 1}/{len(combinations)} | {result['strategy_name']}")
                result["filter_classes"] = combinations[idx]
                results.append(result)
        return pd.DataFrame(results).sort_values(by=["passes_trade_filter", "net_pnl"], ascending=[False, False]).reset_index(drop=True) if results else pd.DataFrame()

    def run_top_combo_refinement(self, data: pd.DataFrame, cfg: EngineConfig, candidate_row: dict[str, Any], output_dir: str | Path = "Outputs", max_workers: int = 10) -> pd.DataFrame:
        promoted_combo_classes = candidate_row.get("filter_classes", [])
        grid = self.get_active_refinement_grid_for_combo(promoted_combo_classes)
        trade_filters = self.get_trade_filter_thresholds()
        refiner = StrategyParameterRefiner(MasterStrategyEngine, data, _MRRefinementFactory(self, promoted_combo_classes), cfg)
        refinement_df = refiner.run_refinement(grid["hold_bars"], grid["stop_distance_points"], grid["min_avg_range"], grid["momentum_lookback"], trade_filters["min_trades"], trade_filters["min_trades_per_year"], True, max_workers)
        if not refinement_df.empty:
            refinement_df["strategy_type"] = self.name
            refinement_df["combo_filters"] = candidate_row.get("filters", "")
            refinement_df["combo_filter_class_names"] = candidate_row.get("filter_class_names", "")
            out_path = Path(output_dir) / f"{self.name}_top_combo_refinement_results_narrow.csv"
            refinement_df.to_csv(out_path, index=False)
        return refinement_df