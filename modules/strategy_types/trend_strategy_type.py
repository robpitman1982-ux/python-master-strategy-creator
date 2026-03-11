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
from modules.strategies import CombinableFilterTrendStrategy
from modules.strategy_types.base_strategy_type import BaseStrategyType


class TrendStrategyType(BaseStrategyType):
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
        strategy = CombinableFilterTrendStrategy(
            filters=filter_objects,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
        )
        strategy.name = f"ComboTrend_{'_'.join([f.name.replace('Filter', '') for f in filter_objects])}"
        return strategy

    def create_refinement_strategy(
        self,
        hold_bars: int,
        stop_distance_points: float,
        **kwargs: Any,
    ) -> CombinableFilterTrendStrategy:
        min_avg_range = float(kwargs.get("min_avg_range", 8.0))
        momentum_lookback = int(kwargs.get("momentum_lookback", 10))

        filter_objects = [
            TrendDirectionFilter(fast_length=50, slow_length=200),
            PullbackFilter(fast_length=50),
            RecoveryTriggerFilter(fast_length=50),
            VolatilityFilter(lookback=20, min_avg_range=min_avg_range),
            MomentumFilter(lookback=momentum_lookback),
        ]

        strategy = CombinableFilterTrendStrategy(
            filters=filter_objects,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
        )
        strategy.name = (
            "RefinedTrendStrategy"
            f"_HB{hold_bars}"
            f"_STOP{stop_distance_points}"
            f"_RANGE{min_avg_range}"
            f"_MOM{momentum_lookback}"
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
            if cls is TrendDirectionFilter:
                filter_objects.append(cls(fast_length=50, slow_length=200))
            elif cls is PullbackFilter:
                filter_objects.append(cls(fast_length=50))
            elif cls is RecoveryTriggerFilter:
                filter_objects.append(cls(fast_length=50))
            elif cls is VolatilityFilter:
                filter_objects.append(cls(lookback=20, min_avg_range=float(min_avg_range)))
            elif cls is MomentumFilter:
                filter_objects.append(cls(lookback=int(momentum_lookback)))
            else:
                filter_objects.append(cls())

        strategy = CombinableFilterTrendStrategy(
            filters=filter_objects,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
        )
        strategy.name = (
            "RefinedTrendCombo"
            f"_{'_'.join([f.name.replace('Filter', '') for f in filter_objects])}"
            f"_HB{hold_bars}"
            f"_STOP{stop_distance_points}"
            f"_RANGE{float(min_avg_range)}"
            f"_MOM{int(momentum_lookback)}"
        )
        return strategy

    def get_refinement_grid(self) -> dict[str, list[Any]]:
        return {
            "hold_bars": [8, 9, 10, 11, 12],
            "stop_distance_points": [9.0, 10.0, 11.0, 12.0],
            "min_avg_range": [8.0, 8.5, 9.0, 9.5],
            "momentum_lookback": [11, 12, 13, 14],
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

        if VolatilityFilter in combo_classes:
            active_grid["min_avg_range"] = base_grid["min_avg_range"]

        if MomentumFilter in combo_classes:
            active_grid["momentum_lookback"] = base_grid["momentum_lookback"]

        return active_grid