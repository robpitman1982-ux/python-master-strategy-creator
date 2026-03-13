from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd

from modules.engine import EngineConfig, MasterStrategyEngine
from modules.filter_combinator import build_filter_combo_name, generate_filter_combinations
from modules.filters import (
    BaseFilter, CompressionFilter, RangeBreakoutFilter, ExpansionBarFilter,
    BreakoutRetestFilter, BreakoutTrendFilter, BreakoutCloseStrengthFilter, PriorRangePositionFilter
)
from modules.plateau_analyzer import PlateauAnalyzer
from modules.refiner import StrategyParameterRefiner
from modules.strategy_types.base_strategy_type import BaseStrategyType

class _InlineBreakoutStrategy:
    direction = "LONG_ONLY"
    def __init__(
        self, filters: list[BaseFilter], hold_bars: int = 6, stop_distance_points: float = 2.0, name: str | None = None
    ):
        self.filters = filters
        self.hold_bars = hold_bars
        self.stop_distance_atr = stop_distance_points # Mapped to new ATR Engine Logic
        self.name = name or f"ComboBreakout_{build_filter_combo_name(filters)}"

    def generate_signal(self, data: pd.DataFrame, i: int) -> int:
        for f in self.filters:
            if not f.passes(data, i): return 0
        return 1

def _run_breakout_combo_case(task: tuple[pd.DataFrame, EngineConfig, list[type]]) -> dict[str, Any]:
    data, cfg, combo_classes = task
    strat_type = BreakoutStrategyType()
    f_objs = strat_type.build_filter_objects_from_classes(combo_classes)
    strategy = strat_type.build_combinable_strategy(f_objs, strat_type.default_hold_bars, strat_type.default_stop_distance_points)
    
    engine = MasterStrategyEngine(data=data, config=cfg)
    engine.run(strategy=strategy)
    summary = engine.results()
    
    total_trades = int(str(summary.get("Total Trades", 0)).replace(",", ""))
    yis = (data.index.max() - data.index.min()).days / 365.25
    tpy = total_trades / yis if yis > 0 else 0.0
    passes = (total_trades >= strat_type.get_trade_filter_thresholds()["min_trades"] and tpy >= strat_type.get_trade_filter_thresholds()["min_trades_per_year"])

    def _pf(val): return float(str(val).replace("$", "").replace(",", "").replace("%", "").strip() or 0.0)

    return {
        "strategy_name": str(summary.get("Strategy", "UnknownStrategy")),
        "filter_count": len(f_objs), 
        "filters": ",".join([f.name for f in f_objs]),
        "filter_class_names": ",".join([c.__name__ for c in combo_classes]),
        "total_trades": total_trades, 
        "trades_per_year": round(tpy, 2), 
        "passes_trade_filter": passes,
        "net_pnl": _pf(summary.get("Net PnL", 0.0)), 
        "profit_factor": _pf(summary.get("Profit Factor", 0.0)),
        "average_trade": _pf(summary.get("Average Trade", 0.0)),
    }

class _BreakoutRefinementFactory:
    def __init__(self, strat_inst, combo_classes: list[type]):
        self.strat_inst = strat_inst
        self.combo_classes = combo_classes

    def __call__(self, hold_bars: int, stop_distance_points: float, min_avg_range: float, momentum_lookback: int):
        return self.strat_inst.build_candidate_specific_strategy(self.combo_classes, hold_bars, stop_distance_points, min_avg_range, momentum_lookback)

class BreakoutStrategyType(BaseStrategyType):
    name = "breakout"
    min_filters_per_combo = 3
    max_filters_per_combo = 5 
    default_hold_bars = 6
    default_stop_distance_points = 2.0

    def get_required_sma_lengths(self) -> list[int]: return [50, 200]
    def get_required_avg_range_lookbacks(self) -> list[int]: return [20]
    def get_required_momentum_lookbacks(self) -> list[int]: return []

    def build_default_sanity_filters(self) -> list[BaseFilter]:
        return [CompressionFilter(), RangeBreakoutFilter(), ExpansionBarFilter(), BreakoutTrendFilter()]

    def build_default_strategy(self) -> _InlineBreakoutStrategy:
        return _InlineBreakoutStrategy(self.build_default_sanity_filters(), self.default_hold_bars, self.default_stop_distance_points, "FilterBasedBreakoutStrategy")

    def build_sanity_check_strategy(self) -> _InlineBreakoutStrategy: 
        return self.build_default_strategy()

    def get_filter_classes(self) -> list[type]:
        return [CompressionFilter, RangeBreakoutFilter, ExpansionBarFilter, BreakoutRetestFilter, BreakoutTrendFilter, BreakoutCloseStrengthFilter, PriorRangePositionFilter]

    def build_filter_objects_from_classes(self, combo_classes: list[type]) -> list[BaseFilter]:
        return [cls() for cls in combo_classes]

    def build_combinable_strategy(self, filters: list[BaseFilter], hold_bars: int, stop_distance_points: float) -> _InlineBreakoutStrategy:
        return _InlineBreakoutStrategy(filters, hold_bars, stop_distance_points)

    def build_candidate_specific_strategy(self, classes: list[type], hb: int, stop: float, rng: float, mom: int) -> _InlineBreakoutStrategy:
        filters = []
        for cls in classes:
            if cls is CompressionFilter: filters.append(CompressionFilter(max_atr_mult=rng if rng > 0 else 0.8))
            else: filters.append(cls())
        return _InlineBreakoutStrategy(filters, hb, stop, name=f"RefinedBreakout_HB{hb}_ATR{stop}_COMP{rng}_MOM{mom}")

    def get_promotion_thresholds(self) -> dict[str, float | bool]:
        return {"min_profit_factor": 1.00, "min_average_trade": 0.0, "require_positive_net_pnl": False, "min_trades": 75, "min_trades_per_year": 4.0}

    def get_promotion_gate_config(self) -> dict[str, float | bool]: 
        return self.get_promotion_thresholds()

    def get_trade_filter_thresholds(self) -> dict[str, float]: 
        return {"min_trades": 120, "min_trades_per_year": 6.0}

    def get_trade_filter_config(self) -> dict[str, float]: 
        return self.get_trade_filter_thresholds()

    def get_active_refinement_grid_for_combo(self, classes: list[type]) -> dict[str, list]:
        # Massive Overnight Grid (Values are ATR Multipliers)
        grid = {
            "hold_bars": [2, 4, 6, 8, 12], 
            "stop_distance_points": [1.0, 1.5, 2.0, 2.5, 3.0]
        }
        grid["min_avg_range"] = [0.5, 0.6, 0.7, 0.8] if any(cls is CompressionFilter for cls in classes) else [0.0]
        grid["momentum_lookback"] = [0]
        return grid

    def get_refinement_grid_for_candidate(self, row: dict[str, Any]) -> dict[str, list]:
        return self.get_active_refinement_grid_for_combo(row.get("filter_classes", []))

    def run_family_filter_combination_sweep(self, data: pd.DataFrame, cfg: EngineConfig, max_workers: int = 10) -> pd.DataFrame:
        combinations = generate_filter_combinations(self.get_filter_classes(), self.min_filters_per_combo, self.max_filters_per_combo)
        tasks = [(data, cfg, combo_classes) for combo_classes in combinations]
        results = []
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            for idx, res in enumerate(executor.map(_run_breakout_combo_case, tasks)):
                print(f"  Combo {idx + 1}/{len(combinations)} | {res['strategy_name']}")
                res["filter_classes"] = combinations[idx]
                results.append(res)
        return pd.DataFrame(results).sort_values(by=["passes_trade_filter", "net_pnl"], ascending=[False, False]).reset_index(drop=True) if results else pd.DataFrame()

    def run_top_combo_refinement(self, data: pd.DataFrame, cfg: EngineConfig, candidate_row: dict[str, Any], output_dir: str | Path = "Outputs", max_workers: int = 10) -> pd.DataFrame:
        classes = candidate_row.get("filter_classes", [])
        grid = self.get_active_refinement_grid_for_combo(classes)
        tf = self.get_trade_filter_thresholds()
        
        refiner = StrategyParameterRefiner(MasterStrategyEngine, data, _BreakoutRefinementFactory(self, classes), cfg)
        rdf = refiner.run_refinement(grid["hold_bars"], grid["stop_distance_points"], grid["min_avg_range"], grid["momentum_lookback"], tf["min_trades"], tf["min_trades_per_year"], True, max_workers)
        
        if not rdf.empty:
            rdf["strategy_type"] = self.name
            rdf["combo_filters"] = candidate_row.get("filters", "")
            rdf["combo_filter_class_names"] = candidate_row.get("filter_class_names", "")
            rdf.to_csv(Path(output_dir) / f"{self.name}_top_combo_refinement_results_narrow.csv", index=False)
        return rdf