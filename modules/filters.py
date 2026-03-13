from __future__ import annotations

from abc import ABC, abstractmethod
import pandas as pd
import numpy as np

class BaseFilter(ABC):
    name: str = "BaseFilter"
    @abstractmethod
    def passes(self, data: pd.DataFrame, i: int) -> bool:
        raise NotImplementedError

# ============================================================
# Trend-family filters
# ============================================================

class TrendDirectionFilter(BaseFilter):
    name = "TrendDirectionFilter"
    def __init__(self, fast_length: int = 50, slow_length: int = 200):
        self.fast_length = fast_length
        self.slow_length = slow_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < max(self.fast_length, self.slow_length): return False
        fast_col, slow_col = f"sma_{self.fast_length}", f"sma_{self.slow_length}"
        fast_sma = data.iloc[i][fast_col] if fast_col in data.columns else data["close"].iloc[i - self.fast_length + 1 : i + 1].mean()
        slow_sma = data.iloc[i][slow_col] if slow_col in data.columns else data["close"].iloc[i - self.slow_length + 1 : i + 1].mean()
        return bool(fast_sma > slow_sma)

class PullbackFilter(BaseFilter):
    name = "PullbackFilter"
    def __init__(self, fast_length: int = 50):
        self.fast_length = fast_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length: return False
        fast_col = f"sma_{self.fast_length}"
        prev_fast_sma = data.iloc[i - 1][fast_col] if fast_col in data.columns else data["close"].iloc[i - self.fast_length : i].mean()
        return bool(data.iloc[i]["prev_close"] <= prev_fast_sma)

class RecoveryTriggerFilter(BaseFilter):
    name = "RecoveryTriggerFilter"
    def __init__(self, fast_length: int = 50):
        self.fast_length = fast_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length: return False
        fast_col = f"sma_{self.fast_length}"
        fast_sma = data.iloc[i][fast_col] if fast_col in data.columns else data["close"].iloc[i - self.fast_length + 1 : i + 1].mean()
        return bool(data.iloc[i]["close"] > fast_sma)

class VolatilityFilter(BaseFilter):
    name = "VolatilityFilter"
    def __init__(self, lookback: int = 20, min_avg_range: float = 10.0): # Bumped default to 10
        self.lookback = lookback
        self.min_avg_range = min_avg_range

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback: return False
        avg_range_col = f"avg_range_{self.lookback}"
        avg_range = data.iloc[i][avg_range_col] if avg_range_col in data.columns else (data.iloc[i - self.lookback + 1 : i + 1]["high"] - data.iloc[i - self.lookback + 1 : i + 1]["low"]).mean()
        return bool(avg_range >= self.min_avg_range)

class MomentumFilter(BaseFilter):
    name = "MomentumFilter"
    def __init__(self, lookback: int = 10):
        self.lookback = lookback

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback: return False
        return bool(data.iloc[i]["close"] > data.iloc[i - self.lookback]["close"])

class UpCloseFilter(BaseFilter):
    name = "UpCloseFilter"
    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1: return False
        return bool(data.iloc[i]["close"] > data.iloc[i - 1]["close"])

class TwoBarUpFilter(BaseFilter):
    name = "TwoBarUpFilter"
    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 2: return False
        return bool(data.iloc[i]["close"] > data.iloc[i - 1]["close"] and data.iloc[i - 1]["close"] > data.iloc[i - 2]["close"])

# ============================================================
# Breakout-family filters
# ============================================================

class CompressionFilter(BaseFilter):
    name = "CompressionFilter"
    def __init__(self, lookback: int = 20, max_avg_range: float = 15.0): # Bumped to 15.0 for modern ES
        self.lookback = lookback
        self.max_avg_range = max_avg_range

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback: return False
        avg_range_col = f"avg_range_{self.lookback}"
        avg_range = data.iloc[i][avg_range_col] if avg_range_col in data.columns else (data.iloc[i - self.lookback + 1 : i + 1]["high"] - data.iloc[i - self.lookback + 1 : i + 1]["low"]).mean()
        return bool(avg_range <= self.max_avg_range)

class RangeBreakoutFilter(BaseFilter):
    name = "RangeBreakoutFilter"
    def __init__(self, lookback: int = 20):
        self.lookback = lookback

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback: return False
        prior_high = data.iloc[i - self.lookback : i]["high"].max()
        return bool(data.iloc[i]["close"] > prior_high)

class ExpansionBarFilter(BaseFilter):
    name = "ExpansionBarFilter"
    def __init__(self, lookback: int = 20, expansion_multiplier: float = 1.25): # Relaxed slightly
        self.lookback = lookback
        self.expansion_multiplier = expansion_multiplier

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback: return False
        current_bar_range = data.iloc[i]["high"] - data.iloc[i]["low"]
        avg_range_col = f"avg_range_{self.lookback}"
        avg_range = data.iloc[i][avg_range_col] if avg_range_col in data.columns else (data.iloc[i - self.lookback + 1 : i + 1]["high"] - data.iloc[i - self.lookback + 1 : i + 1]["low"]).mean()
        return bool(current_bar_range >= avg_range * self.expansion_multiplier)

class BreakoutRetestFilter(BaseFilter):
    name = "BreakoutRetestFilter"
    def __init__(self, lookback: int = 20, breakout_buffer_points: float = 0.0):
        self.lookback = lookback
        self.breakout_buffer_points = breakout_buffer_points

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback: return False
        prior_high = data.iloc[i - self.lookback : i]["high"].max()
        return bool(data.iloc[i]["close"] > prior_high + self.breakout_buffer_points)

class BreakoutTrendFilter(BaseFilter):
    name = "BreakoutTrendFilter"
    def __init__(self, fast_length: int = 50, slow_length: int = 200):
        self.fast_length = fast_length
        self.slow_length = slow_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < max(self.fast_length, self.slow_length): return False
        fast_col, slow_col = f"sma_{self.fast_length}", f"sma_{self.slow_length}"
        fast_sma = data.iloc[i][fast_col] if fast_col in data.columns else data["close"].iloc[i - self.fast_length + 1 : i + 1].mean()
        slow_sma = data.iloc[i][slow_col] if slow_col in data.columns else data["close"].iloc[i - self.slow_length + 1 : i + 1].mean()
        return bool(fast_sma > slow_sma)

class BreakoutCloseStrengthFilter(BaseFilter):
    name = "BreakoutCloseStrengthFilter"
    def __init__(self, close_position_threshold: float = 0.60): # Relaxed to top 40% of bar
        self.close_position_threshold = close_position_threshold

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        current_high, current_low, current_close = data.iloc[i]["high"], data.iloc[i]["low"], data.iloc[i]["close"]
        bar_range = current_high - current_low
        if bar_range <= 0: return False
        return bool(((current_close - current_low) / bar_range) >= self.close_position_threshold)

class PriorRangePositionFilter(BaseFilter):
    name = "PriorRangePositionFilter"
    def __init__(self, lookback: int = 20, min_position_in_range: float = 0.50): # Relaxed to top half
        self.lookback = lookback
        self.min_position_in_range = min_position_in_range

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback or i < 1: return False
        prior_window = data.iloc[i - self.lookback : i]
        range_low, range_high = prior_window["low"].min(), prior_window["high"].max()
        prior_close = data.iloc[i - 1]["close"]
        full_range = range_high - range_low
        if full_range <= 0: return False
        return bool(((prior_close - range_low) / full_range) >= self.min_position_in_range)

# ============================================================
# Mean-reversion-family filters
# ============================================================

class BelowFastSMAFilter(BaseFilter):
    name = "BelowFastSMAFilter"
    def __init__(self, fast_length: int = 20):
        self.fast_length = fast_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length: return False
        fast_col = f"sma_{self.fast_length}"
        fast_sma = data.iloc[i][fast_col] if fast_col in data.columns else data["close"].iloc[i - self.fast_length + 1 : i + 1].mean()
        return bool(data.iloc[i]["close"] < fast_sma)

class DistanceBelowSMAFilter(BaseFilter):
    name = "DistanceBelowSMAFilter"
    def __init__(self, fast_length: int = 20, min_distance_points: float = 6.0): # Default up to 6.0
        self.fast_length = fast_length
        self.min_distance_points = min_distance_points

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length: return False
        fast_col = f"sma_{self.fast_length}"
        fast_sma = data.iloc[i][fast_col] if fast_col in data.columns else data["close"].iloc[i - self.fast_length + 1 : i + 1].mean()
        return bool((fast_sma - data.iloc[i]["close"]) >= self.min_distance_points)

class DownCloseFilter(BaseFilter):
    name = "DownCloseFilter"
    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1: return False
        return bool(data.iloc[i]["close"] < data.iloc[i - 1]["close"])

class TwoBarDownFilter(BaseFilter):
    name = "TwoBarDownFilter"
    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 2: return False
        return bool(data.iloc[i]["close"] < data.iloc[i - 1]["close"] and data.iloc[i - 1]["close"] < data.iloc[i - 2]["close"])

class ReversalUpBarFilter(BaseFilter):
    name = "ReversalUpBarFilter"
    def passes(self, data: pd.DataFrame, i: int) -> bool:
        return bool(data.iloc[i]["close"] > data.iloc[i]["open"])

class LowVolatilityRegimeFilter(BaseFilter):
    name = "LowVolatilityRegimeFilter"
    def __init__(self, lookback: int = 20, max_avg_range: float = 15.0): # Bumped to 15.0
        self.lookback = lookback
        self.max_avg_range = max_avg_range

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback: return False
        avg_range_col = f"avg_range_{self.lookback}"
        avg_range = data.iloc[i][avg_range_col] if avg_range_col in data.columns else (data.iloc[i - self.lookback + 1 : i + 1]["high"] - data.iloc[i - self.lookback + 1 : i + 1]["low"]).mean()
        return bool(avg_range <= self.max_avg_range)

class AboveLongTermSMAFilter(BaseFilter):
    name = "AboveLongTermSMAFilter"
    def __init__(self, slow_length: int = 200):
        self.slow_length = slow_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.slow_length: return False
        slow_col = f"sma_{self.slow_length}"
        slow_sma = data.iloc[i][slow_col] if slow_col in data.columns else data["close"].iloc[i - self.slow_length + 1 : i + 1].mean()
        return bool(data.iloc[i]["close"] > slow_sma)