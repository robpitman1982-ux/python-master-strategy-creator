from __future__ import annotations

from typing import Any

from modules.filters import (
    BaseFilter,
    MomentumFilter,
    PullbackFilter,
    RecoveryTriggerFilter,
    TrendDirectionFilter,
    VolatilityFilter,
)
from modules.strategies import (
    CombinableFilterTrendStrategy,
    RefinedFiveFilterTrendStrategy,
)
from modules.strategy_types.base_strategy_type import BaseStrategyType


class TrendStrategyType(BaseStrategyType):
    """
    Current trend-continuation discovery family.

    This wraps the exact trend logic already working in the project:
    - bull trend
    - pullback
    - recovery trigger
    - volatility qualification
    - momentum confirmation
    """

    name = "trend"

    def get_feature_requirements(self) -> dict[str, list[int]]:
        return {
            "sma_lengths": [50, 200],
            "avg_range_lookbacks": [20],
            "momentum_lookbacks": [8, 10, 11, 12, 13, 14],
        }

    def get_filter_classes(self) -> list[type[BaseFilter]]:
        return [
            TrendDirectionFilter,
            PullbackFilter,
            RecoveryTriggerFilter,
            VolatilityFilter,
            MomentumFilter,
        ]

    def build_filter_objects_from_classes(
        self,
        combo_classes: list[type[BaseFilter]],
    ) -> list[BaseFilter]:
        filter_objects: list[BaseFilter] = []

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

    def create_combo_strategy(
        self,
        combo_classes: list[type[BaseFilter]],
        hold_bars: int,
        stop_distance_points: float,
    ) -> CombinableFilterTrendStrategy:
        filter_objects = self.build_filter_objects_from_classes(combo_classes)

        return CombinableFilterTrendStrategy(
            filters=filter_objects,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
        )

    def create_refinement_strategy(
        self,
        hold_bars: int,
        stop_distance_points: float,
        **kwargs: Any,
    ) -> RefinedFiveFilterTrendStrategy:
        return RefinedFiveFilterTrendStrategy(
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
            min_avg_range=float(kwargs.get("min_avg_range", 8.0)),
            momentum_lookback=int(kwargs.get("momentum_lookback", 10)),
        )

    def get_refinement_grid(self) -> dict[str, list[Any]]:
        return {
            "hold_bars": [8, 9, 10, 11, 12],
            "stop_distance_points": [9.0, 10.0, 11.0, 12.0],
            "min_avg_range": [8.0, 8.5, 9.0, 9.5],
            "momentum_lookback": [11, 12, 13, 14],
        }