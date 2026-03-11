from __future__ import annotations

from modules.strategy_types.base_strategy_type import BaseStrategyType
from modules.strategy_types.breakout_strategy_type import BreakoutStrategyType
from modules.strategy_types.trend_strategy_type import TrendStrategyType


def get_strategy_type(name: str) -> BaseStrategyType:
    """
    Factory function returning a strategy type instance by name.

    Current supported strategy types:
    - trend
    - breakout

    Future:
    - mean_reversion
    - volatility_expansion
    """

    normalized = name.strip().lower()

    if normalized == "trend":
        return TrendStrategyType()

    if normalized == "breakout":
        return BreakoutStrategyType()

    raise ValueError(
        f"Unknown strategy type: '{name}'. "
        f"Supported types: ['trend', 'breakout']"
    )


def list_strategy_types() -> list[str]:
    """
    Returns the currently available strategy type names.
    """
    return ["trend", "breakout"]