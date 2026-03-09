from __future__ import annotations

from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):
    """
    Base class for all strategies.
    """

    name: str = "BaseStrategy"
    direction: str = "LONG_ONLY"
    hold_bars: int = 3
    stop_distance_points: float = 10.0

    @abstractmethod
    def generate_signal(self, data: pd.DataFrame, i: int) -> int:
        """
        Return:
            1 = enter long
            0 = no action
        """
        raise NotImplementedError


class TestStrategy(BaseStrategy):
    """
    Very simple placeholder strategy:
    enter long when current close > previous close.
    """

    name = "TestStrategy"
    direction = "LONG_ONLY"
    hold_bars = 3
    stop_distance_points = 10.0

    def generate_signal(self, data: pd.DataFrame, i: int) -> int:
        if i < 1:
            return 0

        current_close = data["close"].iloc[i]
        previous_close = data["close"].iloc[i - 1]

        if current_close > previous_close:
            return 1

        return 0