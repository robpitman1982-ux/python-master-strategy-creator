"""
Short-side strategy types.

Each mirrors a long family but uses overbought/downtrend filters.
The engine direction is set to 'short' via get_engine_direction().
"""
from __future__ import annotations

from modules.strategy_types.mean_reversion_strategy_type import MeanReversionStrategyType
from modules.strategy_types.trend_strategy_type import TrendStrategyType
from modules.strategy_types.breakout_strategy_type import BreakoutStrategyType
from modules.filters import (
    AboveFastSMAFilter,
    BreakoutCloseStrengthFilter,
    CompressionFilter,
    DistanceAboveSMAFilter,
    DownCloseShortFilter,
    DownsideBreakoutFilter,
    DowntrendDirectionFilter,
    DowntrendSlopeFilter,
    FailureToHoldFilter,
    GapDownFilter,
    GapUpFilter,
    HighVolatilityRegimeFilter,
    InsideBarFilter,
    LowerHighFilter,
    LowerLowFilter,
    OutsideBarFilter,
    RallyInDowntrendFilter,
    ReversalDownBarFilter,
    StretchAboveLongTermSMAFilter,
    TightRangeFilter,
    TwoBarUpShortFilter,
    UpCloseShortFilter,
    WeakCloseFilter,
)


class ShortMeanReversionStrategyType(MeanReversionStrategyType):
    name = "short_mean_reversion"

    def get_filter_classes(self) -> list[type]:
        return [
            AboveFastSMAFilter,
            DistanceAboveSMAFilter,
            UpCloseShortFilter,
            TwoBarUpShortFilter,
            ReversalDownBarFilter,
            HighVolatilityRegimeFilter,
            StretchAboveLongTermSMAFilter,
            InsideBarFilter,
            GapUpFilter,
        ]

    def get_engine_direction(self) -> str:
        return "short"

    min_filters_per_combo = 3
    max_filters_per_combo = 5


class ShortTrendStrategyType(TrendStrategyType):
    name = "short_trend"

    def get_filter_classes(self) -> list[type]:
        return [
            DowntrendDirectionFilter,
            RallyInDowntrendFilter,
            FailureToHoldFilter,
            LowerHighFilter,
            DownCloseShortFilter,
            DowntrendSlopeFilter,
            LowerLowFilter,
            OutsideBarFilter,
        ]

    def get_engine_direction(self) -> str:
        return "short"

    min_filters_per_combo = 3
    max_filters_per_combo = 5


class ShortBreakoutStrategyType(BreakoutStrategyType):
    name = "short_breakout"

    def get_filter_classes(self) -> list[type]:
        return [
            DownsideBreakoutFilter,
            WeakCloseFilter,
            CompressionFilter,
            TightRangeFilter,
            BreakoutCloseStrengthFilter,
            DowntrendDirectionFilter,
            InsideBarFilter,
            GapDownFilter,
            LowerLowFilter,
        ]

    def get_engine_direction(self) -> str:
        return "short"

    min_filters_per_combo = 3
    max_filters_per_combo = 5
