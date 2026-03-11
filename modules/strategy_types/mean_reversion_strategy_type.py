from __future__ import annotations

from typing import Any

from modules.filters import (
    AboveLongTermSMAFilter,
    BaseFilter,
    BelowFastSMAFilter,
    DistanceBelowSMAFilter,
    DownCloseFilter,
    LowVolatilityRegimeFilter,
    ReversalUpBarFilter,
    TwoBarDownFilter,
)
from modules.strategies import CombinableFilterTrendStrategy, RefinedFiveFilterTrendStrategy
from modules.strategy_types.base_strategy_type import BaseStrategyType


class MeanReversionStrategyType(BaseStrategyType):
    """
    Mean reversion strategy family (v1).

    Core hypothesis:
    A tradable long-only snapback may occur when:
    - price is below a short-term moving average
    - the pullback is meaningful, not tiny
    - short-term weakness / exhaustion is present
    - the broader regime is not structurally broken
    - a reversal bar appears
    - volatility regime remains more 'calm' than explosive

    This is designed as the first mean-reversion family for the Master
    Strategy Creator and uses logical combinations of mean-reversion filters.
    """

    name = "mean_reversion"

    def get_feature_requirements(self) -> dict[str, list[int]]:
        return {
            "sma_lengths": [20, 200],
            "avg_range_lookbacks": [20],
            "momentum_lookbacks": [],
        }

    def get_filter_classes(self) -> list[type[BaseFilter]]:
        return [
            BelowFastSMAFilter,
            DistanceBelowSMAFilter,
            DownCloseFilter,
            TwoBarDownFilter,
            ReversalUpBarFilter,
            LowVolatilityRegimeFilter,
            AboveLongTermSMAFilter,
        ]

    def build_filter_objects_from_classes(
        self,
        combo_classes: list[type[BaseFilter]],
    ) -> list[BaseFilter]:
        filter_objects: list[BaseFilter] = []

        for cls in combo_classes:
            if cls is BelowFastSMAFilter:
                filter_objects.append(cls(fast_length=20))
            elif cls is DistanceBelowSMAFilter:
                filter_objects.append(cls(fast_length=20, min_distance_points=4.0))
            elif cls is DownCloseFilter:
                filter_objects.append(cls())
            elif cls is TwoBarDownFilter:
                filter_objects.append(cls())
            elif cls is ReversalUpBarFilter:
                filter_objects.append(cls())
            elif cls is LowVolatilityRegimeFilter:
                filter_objects.append(cls(lookback=20, max_avg_range=12.0))
            elif cls is AboveLongTermSMAFilter:
                filter_objects.append(cls(slow_length=200))
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

        strategy.name = f"ComboMeanReversion_{'_'.join([f.name.replace('Filter', '') for f in filter_objects])}"
        return strategy

    def create_refinement_strategy(
        self,
        hold_bars: int,
        stop_distance_points: float,
        **kwargs: Any,
    ) -> RefinedFiveFilterTrendStrategy:
        """
        Reuses the existing generic refinable wrapper for now while overriding
        the filter stack with mean-reversion logic.

        Parameter mapping for mean-reversion refinement:
        - min_avg_range -> max average range allowed for calmer regime
        - momentum_lookback -> reused here as stretch distance proxy tuning slot

        For v1, we map:
        - min_avg_range -> max_avg_range for LowVolatilityRegimeFilter
        - momentum_lookback -> min_distance_points for DistanceBelowSMAFilter
          using a simple float conversion
        """

        max_avg_range_allowed = float(kwargs.get("min_avg_range", 12.0))
        stretch_distance_points = float(kwargs.get("momentum_lookback", 4.0))

        strategy = RefinedFiveFilterTrendStrategy(
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
            fast_length=20,
            slow_length=200,
            volatility_lookback=20,
            min_avg_range=max_avg_range_allowed,
            momentum_lookback=int(stretch_distance_points),
        )

        strategy.filters = [
            BelowFastSMAFilter(fast_length=20),
            DistanceBelowSMAFilter(fast_length=20, min_distance_points=stretch_distance_points),
            TwoBarDownFilter(),
            ReversalUpBarFilter(),
            LowVolatilityRegimeFilter(lookback=20, max_avg_range=max_avg_range_allowed),
            AboveLongTermSMAFilter(slow_length=200),
        ]

        strategy.name = (
            "RefinedMeanReversionStrategy"
            f"_HB{hold_bars}"
            f"_STOP{stop_distance_points}"
            f"_MAXRANGE{max_avg_range_allowed}"
            f"_DIST{stretch_distance_points}"
        )

        return strategy

    def get_refinement_grid(self) -> dict[str, list[Any]]:
        return {
            "hold_bars": [2, 3, 4, 5, 6],
            "stop_distance_points": [6.0, 8.0, 10.0, 12.0],
            "min_avg_range": [8.0, 10.0, 12.0, 14.0],
            "momentum_lookback": [2, 4, 6, 8],
        }

    def get_trade_filter_thresholds(self) -> dict[str, float]:
        return {
            "min_trades": 150,
            "min_trades_per_year": 8.0,
        }

    def get_combo_sweep_defaults(self) -> dict[str, float]:
        return {
            "hold_bars": 4,
            "stop_distance_points": 8.0,
        }