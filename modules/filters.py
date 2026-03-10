from __future__ import annotations

from abc import ABC, abstractmethod
import pandas as pd


class BaseFilter(ABC):
    """
    Base class for reusable strategy filters.
    """

    name: str = "BaseFilter"

    @abstractmethod
    def passes(self, data: pd.DataFrame, i: int) -> bool:
        raise NotImplementedError


class TrendDirectionFilter(BaseFilter):
    """
    Bull trend when fast SMA > slow SMA.
    """

    name = "TrendDirectionFilter"

    def __init__(self, fast_length: int = 50, slow_length: int = 200):
        self.fast_length = fast_length
        self.slow_length = slow_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        required_bars = max(self.fast_length, self.slow_length)
        if i < required_bars:
            return False

        fast_col = f"sma_{self.fast_length}"
        slow_col = f"sma_{self.slow_length}"

        if fast_col in data.columns and slow_col in data.columns:
            fast_sma = data.iloc[i][fast_col]
            slow_sma = data.iloc[i][slow_col]
        else:
            close_series = data["close"]
            fast_sma = close_series.iloc[i - self.fast_length + 1 : i + 1].mean()
            slow_sma = close_series.iloc[i - self.slow_length + 1 : i + 1].mean()

        if pd.isna(fast_sma) or pd.isna(slow_sma):
            return False

        return fast_sma > slow_sma


class PullbackFilter(BaseFilter):
    """
    Previous close is at or below the fast SMA.
    """

    name = "PullbackFilter"

    def __init__(self, fast_length: int = 50):
        self.fast_length = fast_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length:
            return False

        fast_col = f"sma_{self.fast_length}"

        if fast_col in data.columns and "prev_close" in data.columns:
            prev_fast_sma = data.iloc[i - 1][fast_col]
            previous_close = data.iloc[i]["prev_close"]
        else:
            close_series = data["close"]
            prev_fast_sma = close_series.iloc[i - self.fast_length : i].mean()
            previous_close = close_series.iloc[i - 1]

        if pd.isna(prev_fast_sma) or pd.isna(previous_close):
            return False

        return previous_close <= prev_fast_sma


class RecoveryTriggerFilter(BaseFilter):
    """
    Current close is back above the fast SMA.
    """

    name = "RecoveryTriggerFilter"

    def __init__(self, fast_length: int = 50):
        self.fast_length = fast_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length:
            return False

        fast_col = f"sma_{self.fast_length}"

        if fast_col in data.columns:
            fast_sma = data.iloc[i][fast_col]
            current_close = data.iloc[i]["close"]
        else:
            close_series = data["close"]
            fast_sma = close_series.iloc[i - self.fast_length + 1 : i + 1].mean()
            current_close = close_series.iloc[i]

        if pd.isna(fast_sma) or pd.isna(current_close):
            return False

        return current_close > fast_sma


class VolatilityFilter(BaseFilter):
    """
    Average bar range over lookback must exceed a minimum threshold.
    """

    name = "VolatilityFilter"

    def __init__(self, lookback: int = 20, min_avg_range: float = 8.0):
        self.lookback = lookback
        self.min_avg_range = min_avg_range

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback:
            return False

        avg_range_col = f"avg_range_{self.lookback}"

        if avg_range_col in data.columns:
            avg_range = data.iloc[i][avg_range_col]
        else:
            window = data.iloc[i - self.lookback + 1 : i + 1]
            avg_range = (window["high"] - window["low"]).mean()

        if pd.isna(avg_range):
            return False

        return avg_range >= self.min_avg_range


class MomentumFilter(BaseFilter):
    """
    Current close must be above close N bars ago.
    """

    name = "MomentumFilter"

    def __init__(self, lookback: int = 10):
        self.lookback = lookback

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback:
            return False

        diff_col = f"mom_diff_{self.lookback}"

        if diff_col in data.columns:
            mom_value = data.iloc[i][diff_col]
            if pd.isna(mom_value):
                return False
            return mom_value > 0

        close_series = data["close"]
        current_close = close_series.iloc[i]
        past_close = close_series.iloc[i - self.lookback]

        return current_close > past_close