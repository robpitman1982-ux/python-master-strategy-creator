from __future__ import annotations

from modules.filters import (
    BreakoutCloseStrengthFilter,
    BreakoutRetestFilter,
    BreakoutTrendFilter,
    CompressionFilter,
    ExpansionBarFilter,
    PriorRangePositionFilter,
    RangeBreakoutFilter,
    RisingBaseFilter,
    TightRangeFilter,
)
from modules.strategy_types.breakout_strategy_type import BreakoutStrategyType


class BreakoutCompressionSqueezeStrategyType(BreakoutStrategyType):
    """Breakout subtype: Tight compression before breakout — the 'spring loaded' setup."""

    name = "breakout_compression_squeeze"

    def get_filter_classes(self) -> list:
        return [
            CompressionFilter,
            TightRangeFilter,
            PriorRangePositionFilter,
            BreakoutTrendFilter,
            RangeBreakoutFilter,
            BreakoutCloseStrengthFilter,
        ]

    min_filters_per_combo = 3
    max_filters_per_combo = 5


class BreakoutRangeExpansionStrategyType(BreakoutStrategyType):
    """Breakout subtype: Expansion bar breaks out of prior range structure."""

    name = "breakout_range_expansion"

    def get_filter_classes(self) -> list:
        return [
            RangeBreakoutFilter,
            ExpansionBarFilter,
            BreakoutCloseStrengthFilter,
            PriorRangePositionFilter,
            BreakoutRetestFilter,
            TightRangeFilter,
        ]

    min_filters_per_combo = 3
    max_filters_per_combo = 5


class BreakoutHigherLowStructureStrategyType(BreakoutStrategyType):
    """Breakout subtype: Higher low structure forming before breakout — structural confirmation."""

    name = "breakout_higher_low_structure"

    def get_filter_classes(self) -> list:
        return [
            RisingBaseFilter,
            CompressionFilter,
            BreakoutTrendFilter,
            PriorRangePositionFilter,
            BreakoutCloseStrengthFilter,
            TightRangeFilter,
        ]

    min_filters_per_combo = 3
    max_filters_per_combo = 5
