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


class SmaTrendStrategy(BaseStrategy):
    """
    Simple trend-following pullback recovery strategy.

    Logic:
    - Bull trend when fast SMA > slow SMA
    - Enter long when price closes back above the fast SMA
      after being at/below it on the previous bar
    """

    name = "SmaTrendStrategy"
    direction = "LONG_ONLY"
    hold_bars = 6
    stop_distance_points = 12.0

    fast_length = 50
    slow_length = 200

    def generate_signal(self, data: pd.DataFrame, i: int) -> int:
        required_bars = max(self.fast_length, self.slow_length)

        if i < required_bars:
            return 0

        close_series = data["close"]

        fast_sma = close_series.iloc[i - self.fast_length + 1 : i + 1].mean()
        slow_sma = close_series.iloc[i - self.slow_length + 1 : i + 1].mean()

        prev_fast_sma = close_series.iloc[i - self.fast_length : i].mean()

        current_close = close_series.iloc[i]
        previous_close = close_series.iloc[i - 1]

        bull_trend = fast_sma > slow_sma
        recovery_above_fast = current_close > fast_sma and previous_close <= prev_fast_sma

        if bull_trend and recovery_above_fast:
            return 1

        return 0