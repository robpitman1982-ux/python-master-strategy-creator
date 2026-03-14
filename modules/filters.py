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
    def __init__(self, lookback: int = 20, min_atr_mult: float = 1.0): 
        self.lookback = lookback
        self.min_atr_mult = min_atr_mult

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback * 2: return False
        atr_col = f"atr_{self.lookback}"
        current_atr = data.iloc[i][atr_col] if atr_col in data.columns else 10.0
        long_term_atr = data["true_range"].iloc[i - (self.lookback * 2) : i].mean()
        return bool(current_atr >= (long_term_atr * self.min_atr_mult))

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
    def __init__(self, lookback: int = 20, max_atr_mult: float = 0.75): 
        self.lookback = lookback
        self.max_atr_mult = max_atr_mult

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback * 2: return False
        atr_col = f"atr_{self.lookback}"
        current_atr = data.iloc[i][atr_col] if atr_col in data.columns else 10.0
        long_term_atr = data["true_range"].iloc[i - (self.lookback * 2) : i].mean()
        return bool(current_atr <= (long_term_atr * self.max_atr_mult))

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
    def __init__(self, lookback: int = 20, expansion_multiplier: float = 1.50):
        self.lookback = lookback
        self.expansion_multiplier = expansion_multiplier

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback: return False
        current_tr = data.iloc[i]["true_range"] if "true_range" in data.columns else (data.iloc[i]["high"] - data.iloc[i]["low"])
        atr_col = f"atr_{self.lookback}"
        current_atr = data.iloc[i][atr_col] if atr_col in data.columns else 10.0
        return bool(current_tr >= (current_atr * self.expansion_multiplier))

class BreakoutRetestFilter(BaseFilter):
    name = "BreakoutRetestFilter"
    def __init__(self, lookback: int = 20, atr_buffer_mult: float = 0.0):
        self.lookback = lookback
        self.atr_buffer_mult = atr_buffer_mult

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback: return False
        prior_high = data.iloc[i - self.lookback : i]["high"].max()
        current_atr = data.iloc[i][f"atr_{self.lookback}"] if f"atr_{self.lookback}" in data.columns else 10.0
        return bool(data.iloc[i]["close"] > prior_high + (current_atr * self.atr_buffer_mult))

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
    def __init__(self, close_position_threshold: float = 0.60):
        self.close_position_threshold = close_position_threshold

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        c_high, c_low, c_close = data.iloc[i]["high"], data.iloc[i]["low"], data.iloc[i]["close"]
        bar_range = c_high - c_low
        if bar_range <= 0: return False
        return bool(((c_close - c_low) / bar_range) >= self.close_position_threshold)

class PriorRangePositionFilter(BaseFilter):
    name = "PriorRangePositionFilter"
    def __init__(self, lookback: int = 20, min_position_in_range: float = 0.50):
        self.lookback = lookback
        self.min_position_in_range = min_position_in_range

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback or i < 1: return False
        prior_window = data.iloc[i - self.lookback : i]
        r_low, r_high = prior_window["low"].min(), prior_window["high"].max()
        full_range = r_high - r_low
        if full_range <= 0: return False
        return bool(((data.iloc[i - 1]["close"] - r_low) / full_range) >= self.min_position_in_range)

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
    def __init__(self, fast_length: int = 20, min_distance_atr: float = 0.3): 
        self.fast_length = fast_length
        self.min_distance_atr = min_distance_atr

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length: return False
        fast_col = f"sma_{self.fast_length}"
        fast_sma = data.iloc[i][fast_col] if fast_col in data.columns else data["close"].iloc[i - self.fast_length + 1 : i + 1].mean()
        current_atr = data.iloc[i]["atr_20"] if "atr_20" in data.columns else 10.0
        return bool((fast_sma - data.iloc[i]["close"]) >= (current_atr * self.min_distance_atr))

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
    def __init__(self, lookback: int = 20, max_atr_mult: float = 1.0): 
        self.lookback = lookback
        self.max_atr_mult = max_atr_mult

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback * 2: return False
        atr_col = f"atr_{self.lookback}"
        current_atr = data.iloc[i][atr_col] if atr_col in data.columns else 10.0
        long_term_atr = data["true_range"].iloc[i - (self.lookback*2) : i].mean()
        return bool(current_atr <= (long_term_atr * self.max_atr_mult))

class AboveLongTermSMAFilter(BaseFilter):
    name = "AboveLongTermSMAFilter"
    def __init__(self, slow_length: int = 200):
        self.slow_length = slow_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.slow_length: return False
        slow_col = f"sma_{self.slow_length}"
        slow_sma = data.iloc[i][slow_col] if slow_col in data.columns else data["close"].iloc[i - self.slow_length + 1 : i + 1].mean()
        return bool(data.iloc[i]["close"] > slow_sma)