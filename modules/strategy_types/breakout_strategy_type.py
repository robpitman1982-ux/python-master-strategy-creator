from __future__ import annotations

from typing import Any

from modules.filters import (
    BaseFilter,
    BreakoutCloseStrengthFilter,
    BreakoutTrendFilter,
    CompressionFilter,
    ExpansionBarFilter,
    MinimumBreakDistanceFilter,
    PriorRangePositionFilter,
    RangeBreakoutFilter,
)
from modules.strategies import CombinableFilterTrendStrategy
from modules.strategy_types.base_strategy_type import BaseStrategyType


class BreakoutStrategyType(BaseStrategyType):
    name = "breakout"

    def get_feature_requirements(self) -> dict[str, list[int]]:
        return {
            "sma_lengths": [50, 200],
            "avg_range_lookbacks": [20],
            "momentum_lookbacks": [],
        }

    def get_filter_classes(self) -> list[type[BaseFilter]]:
        return [
            CompressionFilter,
            PriorRangePositionFilter,
            RangeBreakoutFilter,
            MinimumBreakDistanceFilter,
            ExpansionBarFilter,
            BreakoutCloseStrengthFilter,
            BreakoutTrendFilter,
        ]

    def build_filter_objects_from_classes(
        self,
        combo_classes: list[type[BaseFilter]],
    ) -> list[BaseFilter]:
        filter_objects: list[BaseFilter] = []

        for cls in combo_classes:
            if cls is CompressionFilter:
                filter_objects.append(cls(lookback=20, max_avg_range=8.0))
            elif cls is PriorRangePositionFilter:
                filter_objects.append(cls(lookback=20, min_position_in_range=0.65))
            elif cls is RangeBreakoutFilter:
                filter_objects.append(cls(lookback=20))
            elif cls is MinimumBreakDistanceFilter:
                filter_objects.append(cls(lookback=20, min_break_distance_points=1.0))
            elif cls is ExpansionBarFilter:
                filter_objects.append(cls(lookback=20, expansion_multiplier=1.30))
            elif cls is BreakoutCloseStrengthFilter:
                filter_objects.append(cls(close_position_threshold=0.70))
            elif cls is BreakoutTrendFilter:
                filter_objects.append(cls(fast_length=50, slow_length=200))
            else:
                filter_objects.append(cls())

        return filter_objects

    def create_combo_strategy(
        self,
        combo_classes: list[type[BaseFilter]],
        hold_bars: int,
        stop_distance_points: float,
    ) -> CombinableFilterTrendStrategy:
        filter_objects = self.build_filter_objects_from_classes(combo_classes)
        strategy = CombinableFilterTrendStrategy(
            filters=filter_objects,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
        )
        strategy.name = f"ComboBreakout_{'_'.join([f.name.replace('Filter', '') for f in filter_objects])}"
        return strategy

    def create_refinement_strategy(
        self,
        hold_bars: int,
        stop_distance_points: float,
        **kwargs: Any,
    ) -> CombinableFilterTrendStrategy:
        compression_max_avg_range = float(kwargs.get("min_avg_range", 8.0))
        breakout_lookback = int(kwargs.get("momentum_lookback", 20))

        filter_objects = [
            CompressionFilter(lookback=20, max_avg_range=compression_max_avg_range),
            PriorRangePositionFilter(lookback=breakout_lookback, min_position_in_range=0.65),
            RangeBreakoutFilter(lookback=breakout_lookback),
            MinimumBreakDistanceFilter(lookback=breakout_lookback, min_break_distance_points=1.0),
            ExpansionBarFilter(lookback=20, expansion_multiplier=1.30),
            BreakoutCloseStrengthFilter(close_position_threshold=0.70),
            BreakoutTrendFilter(fast_length=50, slow_length=200),
        ]

        strategy = CombinableFilterTrendStrategy(
            filters=filter_objects,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
        )
        strategy.name = (
            "RefinedBreakoutStrategy"
            f"_HB{hold_bars}"
            f"_STOP{stop_distance_points}"
            f"_COMP{compression_max_avg_range}"
            f"_BRKLB{breakout_lookback}"
        )
        return strategy

    def create_refinement_strategy_from_combo(
        self,
        combo_classes: list[type[BaseFilter]],
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
    ) -> CombinableFilterTrendStrategy:
        filter_objects: list[BaseFilter] = []

        for cls in combo_classes:
            if cls is CompressionFilter:
                filter_objects.append(cls(lookback=20, max_avg_range=float(min_avg_range)))
            elif cls is PriorRangePositionFilter:
                filter_objects.append(cls(lookback=int(momentum_lookback), min_position_in_range=0.65))
            elif cls is RangeBreakoutFilter:
                filter_objects.append(cls(lookback=int(momentum_lookback)))
            elif cls is MinimumBreakDistanceFilter:
                filter_objects.append(cls(lookback=int(momentum_lookback), min_break_distance_points=1.0))
            elif cls is ExpansionBarFilter:
                filter_objects.append(cls(lookback=20, expansion_multiplier=1.30))
            elif cls is BreakoutCloseStrengthFilter:
                filter_objects.append(cls(close_position_threshold=0.70))
            elif cls is BreakoutTrendFilter:
                filter_objects.append(cls(fast_length=50, slow_length=200))
            else:
                filter_objects.append(cls())

        strategy = CombinableFilterTrendStrategy(
            filters=filter_objects,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
        )
        strategy.name = (
            "RefinedBreakoutCombo"
            f"_{'_'.join([f.name.replace('Filter', '') for f in filter_objects])}"
            f"_HB{hold_bars}"
            f"_STOP{stop_distance_points}"
            f"_COMP{float(min_avg_range)}"
            f"_LB{int(momentum_lookback)}"
        )
        return strategy

    def get_refinement_grid(self) -> dict[str, list[Any]]:
        return {
            "hold_bars": [4, 6, 8, 10],
            "stop_distance_points": [10.0, 12.0, 14.0, 16.0],
            "min_avg_range": [6.0, 7.0, 8.0, 9.0],
            "momentum_lookback": [10, 15, 20, 25],
        }

    def get_trade_filter_thresholds(self) -> dict[str, float]:
        return {
            "min_trades": 150,
            "min_trades_per_year": 8.0,
        }

    def get_combo_sweep_defaults(self) -> dict[str, float]:
        return {
            "hold_bars": 8,
            "stop_distance_points": 12.0,
        }

    def get_active_refinement_grid_for_combo(
        self,
        combo_classes: list[type],
    ) -> dict[str, list[Any]]:
        base_grid = self.get_refinement_grid()

        active_grid = {
            "hold_bars": base_grid["hold_bars"],
            "stop_distance_points": base_grid["stop_distance_points"],
        }

        if CompressionFilter in combo_classes:
            active_grid["min_avg_range"] = base_grid["min_avg_range"]

        if (
            PriorRangePositionFilter in combo_classes
            or RangeBreakoutFilter in combo_classes
            or MinimumBreakDistanceFilter in combo_classes
        ):
            active_grid["momentum_lookback"] = base_grid["momentum_lookback"]

        return active_grid