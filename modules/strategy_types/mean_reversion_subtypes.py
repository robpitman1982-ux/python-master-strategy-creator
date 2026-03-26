from __future__ import annotations

from modules.filters import (
    AboveLongTermSMAFilter,
    BelowFastSMAFilter,
    DistanceBelowSMAFilter,
    DownCloseFilter,
    LowVolatilityRegimeFilter,
    ReversalUpBarFilter,
    StretchFromLongTermSMAFilter,
    ThreeBarDownFilter,
    TwoBarDownFilter,
    CloseNearLowFilter,
)
from modules.strategy_types.mean_reversion_strategy_type import MeanReversionStrategyType


class MeanReversionVolDipStrategyType(MeanReversionStrategyType):
    """MR subtype: Market has gone quiet (low vol), stretched below SMA, pattern reversal signal."""

    name = "mean_reversion_vol_dip"

    def get_filter_classes(self) -> list:
        return [
            LowVolatilityRegimeFilter,
            DistanceBelowSMAFilter,
            StretchFromLongTermSMAFilter,
            DownCloseFilter,
            TwoBarDownFilter,
            ReversalUpBarFilter,
        ]

    min_filters_per_combo = 3
    max_filters_per_combo = 5


class MeanReversionMomExhaustionStrategyType(MeanReversionStrategyType):
    """MR subtype: Momentum selling exhausted — multi-bar decline, below fast SMA, reversal pattern."""

    name = "mean_reversion_mom_exhaustion"

    def get_filter_classes(self) -> list:
        return [
            ThreeBarDownFilter,
            TwoBarDownFilter,
            BelowFastSMAFilter,
            DistanceBelowSMAFilter,
            ReversalUpBarFilter,
            CloseNearLowFilter,
        ]

    min_filters_per_combo = 3
    max_filters_per_combo = 5


class MeanReversionTrendPullbackStrategyType(MeanReversionStrategyType):
    """MR subtype: Pullback within an uptrend — above long-term SMA but below fast SMA, reversal signal."""

    name = "mean_reversion_trend_pullback"

    def get_filter_classes(self) -> list:
        return [
            AboveLongTermSMAFilter,
            BelowFastSMAFilter,
            DownCloseFilter,
            ReversalUpBarFilter,
            DistanceBelowSMAFilter,
            LowVolatilityRegimeFilter,
        ]

    min_filters_per_combo = 3
    max_filters_per_combo = 5
