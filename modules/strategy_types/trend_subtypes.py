from __future__ import annotations

from modules.filters import (
    CloseAboveFastSMAFilter,
    HigherLowFilter,
    MomentumFilter,
    PullbackFilter,
    RecoveryTriggerFilter,
    TrendDirectionFilter,
    TrendSlopeFilter,
    TwoBarUpFilter,
    UpCloseFilter,
    VolatilityFilter,
)
from modules.strategy_types.trend_strategy_type import TrendStrategyType


class TrendPullbackContinuationStrategyType(TrendStrategyType):
    """Trend subtype: Established trend, pullback, recovery trigger."""

    name = "trend_pullback_continuation"

    def get_filter_classes(self) -> list:
        return [
            TrendDirectionFilter,
            PullbackFilter,
            RecoveryTriggerFilter,
            HigherLowFilter,
            UpCloseFilter,
            MomentumFilter,
        ]

    min_filters_per_combo = 3
    max_filters_per_combo = 5


class TrendMomentumBreakoutStrategyType(TrendStrategyType):
    """Trend subtype: Momentum + slope confirm trend direction, upclose closes the bar strong."""

    name = "trend_momentum_breakout"

    def get_filter_classes(self) -> list:
        return [
            MomentumFilter,
            TrendSlopeFilter,
            UpCloseFilter,
            TwoBarUpFilter,
            VolatilityFilter,
            TrendDirectionFilter,
        ]

    min_filters_per_combo = 3
    max_filters_per_combo = 5


class TrendSlopeRecoveryStrategyType(TrendStrategyType):
    """Trend subtype: Slope + fast SMA + recovery pattern — trend resuming after consolidation."""

    name = "trend_slope_recovery"

    def get_filter_classes(self) -> list:
        return [
            TrendSlopeFilter,
            CloseAboveFastSMAFilter,
            RecoveryTriggerFilter,
            HigherLowFilter,
            TwoBarUpFilter,
            PullbackFilter,
        ]

    min_filters_per_combo = 3
    max_filters_per_combo = 5
