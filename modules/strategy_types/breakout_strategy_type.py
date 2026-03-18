from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd

from modules.config_loader import get_timeframe_multiplier, scale_lookbacks
from modules.engine import EngineConfig, MasterStrategyEngine
from modules.filter_combinator import build_filter_combo_name, generate_filter_combinations
from modules.filters import (
    BaseFilter,
    BreakoutCloseStrengthFilter,
    BreakoutDistanceFilter,
    BreakoutRetestFilter,
    BreakoutTrendFilter,
    CompressionFilter,
    ExpansionBarFilter,
    PriorRangePositionFilter,
    RangeBreakoutFilter,
    RisingBaseFilter,
    TightRangeFilter,
)
from modules.refiner import StrategyParameterRefiner
from modules.strategy_types.base_strategy_type import BaseStrategyType


class _InlineBreakoutStrategy:
    direction = "LONG_ONLY"

    def __init__(
        self,
        filters: list[BaseFilter],
        hold_bars: int = 4,
        stop_distance_atr: float = 1.25,
        name: str | None = None,
    ):
        self.filters = filters
        self.hold_bars = hold_bars
        self.stop_distance_atr = stop_distance_atr
        self.name = name or f"ComboBreakout_{build_filter_combo_name(filters)}"

    def generate_signal(self, data: pd.DataFrame, i: int) -> int:
        for f in self.filters:
            if not f.passes(data, i):
                return 0
        return 1


def _run_breakout_combo_case(task: tuple[pd.DataFrame, EngineConfig, list[type]]) -> dict[str, Any]:
    data, cfg, combo_classes = task
    strat_type = BreakoutStrategyType()

    filter_objects = strat_type.build_filter_objects_from_classes(combo_classes, timeframe=cfg.timeframe)
    strategy = strat_type.build_combinable_strategy(
        filters=filter_objects,
        hold_bars=strat_type.default_hold_bars,
        stop_distance_points=strat_type.default_stop_distance_points,
    )

    engine = MasterStrategyEngine(data=data, config=cfg)
    engine.run(strategy=strategy)
    summary = engine.results()

    total_trades = int(str(summary.get("Total Trades", 0)).replace(",", ""))
    years_in_sample = (data.index.max() - data.index.min()).days / 365.25
    trades_per_year = total_trades / years_in_sample if years_in_sample > 0 else 0.0

    thresholds = strat_type.get_trade_filter_thresholds()
    passes = (
        total_trades >= thresholds["min_trades"]
        and trades_per_year >= thresholds["min_trades_per_year"]
    )

    def _pf(val: Any) -> float:
        return float(str(val).replace("$", "").replace(",", "").replace("%", "").strip() or 0.0)

    return {
        "strategy_name": str(summary.get("Strategy", "UnknownStrategy")),
        "filter_count": len(filter_objects),
        "filters": ",".join([f.name for f in filter_objects]),
        "filter_class_names": ",".join([c.__name__ for c in combo_classes]),
        "total_trades": total_trades,
        "trades_per_year": round(trades_per_year, 2),
        "passes_trade_filter": passes,
        "net_pnl": _pf(summary.get("Net PnL", 0.0)),
        "profit_factor": _pf(summary.get("Profit Factor", 0.0)),
        "average_trade": _pf(summary.get("Average Trade", 0.0)),
        "is_trades": int(summary.get("IS Trades", 0)),
        "oos_trades": int(summary.get("OOS Trades", 0)),
        "is_pf": _pf(summary.get("IS PF", 0.0)),
        "oos_pf": _pf(summary.get("OOS PF", 0.0)),
        "recent_12m_trades": int(summary.get("Recent 12m Trades", 0)),
        "recent_12m_pf": _pf(summary.get("Recent 12m PF", 0.0)),
        "quality_flag": str(summary.get("Quality Flag", "UNKNOWN")),
        "quality_score": _pf(summary.get("Quality Score", 0.0)),
        "pct_profitable_years": _pf(summary.get("Pct Profitable Years", 0.0)),
        "max_consecutive_losing_years": int(summary.get("Max Consecutive Losing Years", 0)),
        "consistency_flag": str(summary.get("Consistency Flag", "INSUFFICIENT_DATA")),
    }


class _BreakoutRefinementFactory:
    def __init__(self, strat_inst, combo_classes: list[type], timeframe: str = "60m"):
        self.strat_inst = strat_inst
        self.combo_classes = combo_classes
        self.timeframe = timeframe

    def __call__(
        self,
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
    ):
        return self.strat_inst.build_candidate_specific_strategy(
            self.combo_classes,
            hold_bars,
            stop_distance_points,
            min_avg_range,
            momentum_lookback,
            timeframe=self.timeframe,
        )


class BreakoutStrategyType(BaseStrategyType):
    name = "breakout"
    min_filters_per_combo = 3
    max_filters_per_combo = 5

    default_hold_bars = 4
    default_stop_distance_points = 1.25

    def get_required_sma_lengths(self, timeframe: str = "60m") -> list[int]:
        mult = get_timeframe_multiplier(timeframe)
        return scale_lookbacks([50, 200], mult, min_val=5)

    def get_required_avg_range_lookbacks(self, timeframe: str = "60m") -> list[int]:
        mult = get_timeframe_multiplier(timeframe)
        return scale_lookbacks([20], mult, min_val=5)

    def get_required_momentum_lookbacks(self, timeframe: str = "60m") -> list[int]:
        return []

    def build_default_sanity_filters(self) -> list[BaseFilter]:
        return [
            CompressionFilter(lookback=20, max_atr_mult=0.90),
            RangeBreakoutFilter(lookback=20),
            ExpansionBarFilter(lookback=20, expansion_multiplier=1.15),
            BreakoutTrendFilter(fast_length=50, slow_length=200),
            BreakoutCloseStrengthFilter(close_position_threshold=0.60),
        ]

    def build_default_strategy(self) -> _InlineBreakoutStrategy:
        return _InlineBreakoutStrategy(
            filters=self.build_default_sanity_filters(),
            hold_bars=self.default_hold_bars,
            stop_distance_atr=self.default_stop_distance_points,
            name="FilterBasedBreakoutStrategy",
        )

    def build_sanity_check_strategy(self) -> _InlineBreakoutStrategy:
        return self.build_default_strategy()

    def get_filter_classes(self) -> list[type]:
        return [
            CompressionFilter,
            RangeBreakoutFilter,
            ExpansionBarFilter,
            BreakoutRetestFilter,
            BreakoutTrendFilter,
            BreakoutCloseStrengthFilter,
            PriorRangePositionFilter,
            BreakoutDistanceFilter,
            RisingBaseFilter,
            TightRangeFilter,
        ]

    def build_filter_objects_from_classes(self, combo_classes: list[type], timeframe: str = "60m") -> list[BaseFilter]:
        mult = get_timeframe_multiplier(timeframe)
        fast_sma = max(10, round(50 * mult))
        slow_sma = max(20, round(200 * mult))
        lookback = max(5, round(20 * mult))

        filters: list[BaseFilter] = []

        for cls in combo_classes:
            if cls is CompressionFilter:
                filters.append(CompressionFilter(lookback=lookback, max_atr_mult=0.90))
            elif cls is RangeBreakoutFilter:
                filters.append(RangeBreakoutFilter(lookback=lookback))
            elif cls is ExpansionBarFilter:
                filters.append(ExpansionBarFilter(lookback=lookback, expansion_multiplier=1.15))
            elif cls is BreakoutRetestFilter:
                filters.append(BreakoutRetestFilter(lookback=lookback, atr_buffer_mult=0.00))
            elif cls is BreakoutTrendFilter:
                filters.append(BreakoutTrendFilter(fast_length=fast_sma, slow_length=slow_sma))
            elif cls is BreakoutCloseStrengthFilter:
                filters.append(BreakoutCloseStrengthFilter(close_position_threshold=0.60))
            elif cls is PriorRangePositionFilter:
                filters.append(PriorRangePositionFilter(lookback=lookback, min_position_in_range=0.55))
            elif cls is BreakoutDistanceFilter:
                filters.append(BreakoutDistanceFilter(lookback=lookback, min_breakout_atr=0.05))
            elif cls is RisingBaseFilter:
                filters.append(RisingBaseFilter(lookback=max(3, round(5 * mult))))
            elif cls is TightRangeFilter:
                filters.append(TightRangeFilter(lookback=lookback, max_bar_range_mult=0.90))
            else:
                filters.append(cls())

        return filters

    def build_combinable_strategy(
        self,
        filters: list[BaseFilter],
        hold_bars: int,
        stop_distance_points: float,
    ) -> _InlineBreakoutStrategy:
        return _InlineBreakoutStrategy(
            filters=filters,
            hold_bars=hold_bars,
            stop_distance_atr=stop_distance_points,
        )

    def build_candidate_specific_strategy(
        self,
        classes: list[type],
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
        timeframe: str = "60m",
    ) -> _InlineBreakoutStrategy:
        mult = get_timeframe_multiplier(timeframe)
        fast_sma = max(10, round(50 * mult))
        slow_sma = max(20, round(200 * mult))
        lookback = max(5, round(20 * mult))

        filters: list[BaseFilter] = []

        for cls in classes:
            if cls is CompressionFilter:
                filters.append(CompressionFilter(lookback=lookback, max_atr_mult=min_avg_range if min_avg_range > 0 else 0.90))
            elif cls is RangeBreakoutFilter:
                filters.append(RangeBreakoutFilter(lookback=lookback))
            elif cls is ExpansionBarFilter:
                filters.append(ExpansionBarFilter(lookback=lookback, expansion_multiplier=1.15))
            elif cls is BreakoutRetestFilter:
                filters.append(BreakoutRetestFilter(lookback=lookback, atr_buffer_mult=0.00))
            elif cls is BreakoutTrendFilter:
                filters.append(BreakoutTrendFilter(fast_length=fast_sma, slow_length=slow_sma))
            elif cls is BreakoutCloseStrengthFilter:
                filters.append(BreakoutCloseStrengthFilter(close_position_threshold=0.60))
            elif cls is PriorRangePositionFilter:
                filters.append(PriorRangePositionFilter(lookback=lookback, min_position_in_range=0.55))
            elif cls is BreakoutDistanceFilter:
                filters.append(BreakoutDistanceFilter(lookback=lookback, min_breakout_atr=0.05))
            elif cls is RisingBaseFilter:
                filters.append(RisingBaseFilter(lookback=max(3, round(5 * mult))))
            elif cls is TightRangeFilter:
                filters.append(TightRangeFilter(lookback=lookback, max_bar_range_mult=0.90))
            else:
                filters.append(cls())

        return _InlineBreakoutStrategy(
            filters=filters,
            hold_bars=hold_bars,
            stop_distance_atr=stop_distance_points,
            name=f"RefinedBreakout_HB{hold_bars}_ATR{stop_distance_points}_COMP{min_avg_range}_MOM{momentum_lookback}",
        )

    def get_promotion_thresholds(self) -> dict[str, float | bool]:
        return {
            "min_profit_factor": 0.70,
            "min_average_trade": 0.0,
            "require_positive_net_pnl": False,
            "min_trades": 60,
            "min_trades_per_year": 3.0,
            "max_promoted_candidates": 20,
        }

    def get_promotion_gate_config(self) -> dict[str, float | bool]:
        return self.get_promotion_thresholds()

    def get_trade_filter_thresholds(self) -> dict[str, float]:
        return {
            "min_trades": 60,
            "min_trades_per_year": 3.0,
        }

    def get_trade_filter_config(self) -> dict[str, float]:
        return self.get_trade_filter_thresholds()

    def get_active_refinement_grid_for_combo(
        self, classes: list[type], timeframe: str = "60m"
    ) -> dict[str, list]:
        base_hold_bars = [2, 3, 4, 5, 6, 8, 10]
        mult = get_timeframe_multiplier(timeframe)

        if mult != 1.0:
            scaled = sorted(set(max(1, round(h * mult)) for h in base_hold_bars))
            if len(scaled) < 4:
                scaled = sorted(set(scaled + [1, 2, 3, 5]))
        else:
            scaled = base_hold_bars

        grid = {
            "hold_bars": scaled,
            # stop_distance_points are ATR-based, unscaled
            "stop_distance_points": [0.5, 0.75, 1.0, 1.25, 1.5, 2.0],
        }

        grid["min_avg_range"] = [0.60, 0.70, 0.80, 0.90, 1.00] if any(cls is CompressionFilter for cls in classes) else [0.0]
        grid["momentum_lookback"] = [0]

        return grid

    def get_refinement_grid_for_candidate(self, row: dict[str, Any]) -> dict[str, list]:
        return self.get_active_refinement_grid_for_combo(
            row.get("filter_classes", []), row.get("timeframe", "60m")
        )

    def run_family_filter_combination_sweep(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        max_workers: int = 10,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> pd.DataFrame:
        combinations = generate_filter_combinations(
            self.get_filter_classes(),
            self.min_filters_per_combo,
            self.max_filters_per_combo,
        )

        tasks = [(data, cfg, combo_classes) for combo_classes in combinations]
        results: list[dict[str, Any]] = []

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            for idx, res in enumerate(executor.map(_run_breakout_combo_case, tasks), start=1):
                print(
                    f"  Combo {idx}/{len(combinations)} | {res['strategy_name']} | "
                    f"PF={res['profit_factor']:.2f} | Net={res['net_pnl']:.2f} | "
                    f"trades={res['total_trades']}"
                )
                res["filter_classes"] = combinations[idx - 1]
                results.append(res)
                if progress_callback is not None:
                    progress_callback(idx, len(combinations))

        if not results:
            return pd.DataFrame()

        return (
            pd.DataFrame(results)
            .sort_values(by=["net_pnl", "profit_factor", "average_trade"], ascending=[False, False, False])
            .reset_index(drop=True)
        )

    def run_top_combo_refinement(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        candidate_row: dict[str, Any],
        output_dir: str | Path = "Outputs",
        max_workers: int = 10,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> pd.DataFrame:
        classes = candidate_row.get("filter_classes", [])
        timeframe = cfg.timeframe
        grid = self.get_active_refinement_grid_for_combo(classes, timeframe=timeframe)
        thresholds = self.get_trade_filter_thresholds()

        refiner = StrategyParameterRefiner(
            MasterStrategyEngine,
            data,
            _BreakoutRefinementFactory(self, classes, timeframe=timeframe),
            cfg,
        )

        refinement_df = refiner.run_refinement(
            hold_bars=grid["hold_bars"],
            stop_distance_points=grid["stop_distance_points"],
            min_avg_range=grid["min_avg_range"],
            momentum_lookback=grid["momentum_lookback"],
            min_trades=thresholds["min_trades"],
            min_trades_per_year=thresholds["min_trades_per_year"],
            parallel=True,
            max_workers=max_workers,
            progress_callback=progress_callback,
        )

        if not refinement_df.empty:
            refinement_df["strategy_type"] = self.name
            refinement_df["combo_filters"] = candidate_row.get("filters", "")
            refinement_df["combo_filter_class_names"] = candidate_row.get("filter_class_names", "")
            refinement_df.to_csv(
                Path(output_dir) / f"{self.name}_top_combo_refinement_results_narrow.csv",
                index=False,
            )

        return refinement_df