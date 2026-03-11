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
from modules.strategies import CombinableFilterTrendStrategy, RefinedFiveFilterTrendStrategy
from modules.strategy_types.base_strategy_type import BaseStrategyType


class BreakoutStrategyType(BaseStrategyType):
    """
    Breakout / volatility-expansion strategy family (v2).

    Core hypothesis:
    Better breakout trades occur when:
    - the market has recently compressed
    - price is already positioned near the top of the recent range
    - price breaks above the prior range by a meaningful margin
    - the breakout bar expands
    - the breakout bar closes strongly near its high
    - optional broader trend alignment is present

    This version is more selective than breakout v1 and is intended to
    reject weak, marginal, mid-range fakeouts.
    """

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
    ) -> RefinedFiveFilterTrendStrategy:
        """
        Reuses the existing generic refinable wrapper for now, while overriding
        the filter stack with breakout-specific logic.

        Parameter mapping for breakout refinement:
        - min_avg_range -> compression max average range
        - momentum_lookback -> breakout lookback window
        """

        compression_max_avg_range = float(kwargs.get("min_avg_range", 8.0))
        breakout_lookback = int(kwargs.get("momentum_lookback", 20))

        strategy = RefinedFiveFilterTrendStrategy(
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
            fast_length=50,
            slow_length=200,
            volatility_lookback=20,
            min_avg_range=compression_max_avg_range,
            momentum_lookback=breakout_lookback,
        )

        strategy.filters = [
            CompressionFilter(lookback=20, max_avg_range=compression_max_avg_range),
            PriorRangePositionFilter(lookback=breakout_lookback, min_position_in_range=0.65),
            RangeBreakoutFilter(lookback=breakout_lookback),
            MinimumBreakDistanceFilter(lookback=breakout_lookback, min_break_distance_points=1.0),
            ExpansionBarFilter(lookback=20, expansion_multiplier=1.30),
            BreakoutCloseStrengthFilter(close_position_threshold=0.70),
            BreakoutTrendFilter(fast_length=50, slow_length=200),
        ]

        strategy.name = (
            "RefinedBreakoutStrategy"
            f"_HB{hold_bars}"
            f"_STOP{stop_distance_points}"
            f"_COMP{compression_max_avg_range}"
            f"_BRKLB{breakout_lookback}"
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