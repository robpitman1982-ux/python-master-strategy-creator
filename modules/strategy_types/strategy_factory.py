from __future__ import annotations

from modules.strategy_types.base_strategy_type import BaseStrategyType
from modules.strategy_types.breakout_strategy_type import BreakoutStrategyType
from modules.strategy_types.breakout_subtypes import (
    BreakoutCompressionSqueezeStrategyType,
    BreakoutHigherLowStructureStrategyType,
    BreakoutRangeExpansionStrategyType,
)
from modules.strategy_types.mean_reversion_strategy_type import MeanReversionStrategyType
from modules.strategy_types.mean_reversion_subtypes import (
    MeanReversionMomExhaustionStrategyType,
    MeanReversionTrendPullbackStrategyType,
    MeanReversionVolDipStrategyType,
)
from modules.strategy_types.trend_strategy_type import TrendStrategyType
from modules.strategy_types.trend_subtypes import (
    TrendMomentumBreakoutStrategyType,
    TrendPullbackContinuationStrategyType,
    TrendSlopeRecoveryStrategyType,
)
from modules.strategy_types.short_strategy_types import (
    ShortMeanReversionStrategyType,
    ShortTrendStrategyType,
    ShortBreakoutStrategyType,
)

_STRATEGY_TYPES: dict[str, type[BaseStrategyType]] = {
    # Original families (kept for backward compat and single-family runs)
    "mean_reversion": MeanReversionStrategyType,
    "trend": TrendStrategyType,
    "breakout": BreakoutStrategyType,
    # MR subtypes
    "mean_reversion_vol_dip": MeanReversionVolDipStrategyType,
    "mean_reversion_mom_exhaustion": MeanReversionMomExhaustionStrategyType,
    "mean_reversion_trend_pullback": MeanReversionTrendPullbackStrategyType,
    # Trend subtypes
    "trend_pullback_continuation": TrendPullbackContinuationStrategyType,
    "trend_momentum_breakout": TrendMomentumBreakoutStrategyType,
    "trend_slope_recovery": TrendSlopeRecoveryStrategyType,
    # Breakout subtypes
    "breakout_compression_squeeze": BreakoutCompressionSqueezeStrategyType,
    "breakout_range_expansion": BreakoutRangeExpansionStrategyType,
    "breakout_higher_low_structure": BreakoutHigherLowStructureStrategyType,
    # Short-side families
    "short_mean_reversion": ShortMeanReversionStrategyType,
    "short_trend": ShortTrendStrategyType,
    "short_breakout": ShortBreakoutStrategyType,
}


def get_strategy_type(name: str) -> BaseStrategyType:
    """
    Factory function returning a strategy type instance by name.

    Supported strategy types:
    - Original families: trend, breakout, mean_reversion
    - MR subtypes: mean_reversion_vol_dip, mean_reversion_mom_exhaustion, mean_reversion_trend_pullback
    - Trend subtypes: trend_pullback_continuation, trend_momentum_breakout, trend_slope_recovery
    - Breakout subtypes: breakout_compression_squeeze, breakout_range_expansion, breakout_higher_low_structure
    - Short families: short_mean_reversion, short_trend, short_breakout
    """
    normalized = name.strip().lower()
    cls = _STRATEGY_TYPES.get(normalized)
    if cls is None:
        raise ValueError(
            f"Unknown strategy type: '{name}'. "
            f"Supported types: {list(_STRATEGY_TYPES.keys())}"
        )
    return cls()


def list_strategy_types() -> list[str]:
    """Returns all available strategy type names (originals + subtypes)."""
    return list(_STRATEGY_TYPES.keys())
