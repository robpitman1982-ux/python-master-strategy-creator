from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd


class BaseFilter(ABC):
    name: str = "BaseFilter"

    @abstractmethod
    def passes(self, data: pd.DataFrame, i: int) -> bool:
        raise NotImplementedError

    def mask(self, data: pd.DataFrame) -> pd.Series:
        """
        Default fallback: call passes() bar-by-bar.
        Subclasses override with a vectorized implementation.
        """
        return pd.Series(
            [self.passes(data, i) for i in range(len(data))],
            index=data.index,
            dtype=bool,
        )


# ============================================================
# Trend-family filters
# ============================================================

class TrendDirectionFilter(BaseFilter):
    name = "TrendDirectionFilter"

    def __init__(self, fast_length: int = 50, slow_length: int = 200):
        self.fast_length = fast_length
        self.slow_length = slow_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < max(self.fast_length, self.slow_length):
            return False

        fast_col = f"sma_{self.fast_length}"
        slow_col = f"sma_{self.slow_length}"

        fast_sma = (
            data.iloc[i][fast_col]
            if fast_col in data.columns
            else data["close"].iloc[i - self.fast_length + 1 : i + 1].mean()
        )
        slow_sma = (
            data.iloc[i][slow_col]
            if slow_col in data.columns
            else data["close"].iloc[i - self.slow_length + 1 : i + 1].mean()
        )
        return bool(fast_sma > slow_sma)

    def mask(self, data: pd.DataFrame) -> pd.Series:
        fast_col = f"sma_{self.fast_length}"
        slow_col = f"sma_{self.slow_length}"
        warmup = max(self.fast_length, self.slow_length)

        fast = data[fast_col] if fast_col in data.columns else data["close"].rolling(self.fast_length).mean()
        slow = data[slow_col] if slow_col in data.columns else data["close"].rolling(self.slow_length).mean()

        result = (fast > slow).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


class PullbackFilter(BaseFilter):
    name = "PullbackFilter"

    def __init__(self, fast_length: int = 50):
        self.fast_length = fast_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length:
            return False

        fast_col = f"sma_{self.fast_length}"
        prev_fast_sma = (
            data.iloc[i - 1][fast_col]
            if fast_col in data.columns
            else data["close"].iloc[i - self.fast_length : i].mean()
        )
        return bool(data.iloc[i]["prev_close"] <= prev_fast_sma)

    def mask(self, data: pd.DataFrame) -> pd.Series:
        fast_col = f"sma_{self.fast_length}"
        warmup = self.fast_length

        prev_close = data["prev_close"] if "prev_close" in data.columns else data["close"].shift(1)

        if fast_col in data.columns:
            prev_fast_sma = data[fast_col].shift(1)
        else:
            prev_fast_sma = data["close"].rolling(self.fast_length).mean().shift(1)

        result = (prev_close <= prev_fast_sma).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


class RecoveryTriggerFilter(BaseFilter):
    name = "RecoveryTriggerFilter"

    def __init__(self, fast_length: int = 50):
        self.fast_length = fast_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length:
            return False

        fast_col = f"sma_{self.fast_length}"
        fast_sma = (
            data.iloc[i][fast_col]
            if fast_col in data.columns
            else data["close"].iloc[i - self.fast_length + 1 : i + 1].mean()
        )
        return bool(data.iloc[i]["close"] > fast_sma)

    def mask(self, data: pd.DataFrame) -> pd.Series:
        fast_col = f"sma_{self.fast_length}"
        warmup = self.fast_length

        fast = data[fast_col] if fast_col in data.columns else data["close"].rolling(self.fast_length).mean()

        result = (data["close"] > fast).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


class VolatilityFilter(BaseFilter):
    name = "VolatilityFilter"

    def __init__(self, lookback: int = 20, min_atr_mult: float = 1.0):
        self.lookback = lookback
        self.min_atr_mult = min_atr_mult

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback * 2:
            return False

        atr_col = f"atr_{self.lookback}"
        current_atr = data.iloc[i][atr_col] if atr_col in data.columns else 10.0
        long_term_atr = data["true_range"].iloc[i - (self.lookback * 2) : i].mean()

        return bool(current_atr >= (long_term_atr * self.min_atr_mult))

    def mask(self, data: pd.DataFrame) -> pd.Series:
        atr_col = f"atr_{self.lookback}"
        warmup = self.lookback * 2

        current_atr = data[atr_col] if atr_col in data.columns else pd.Series(10.0, index=data.index)
        # Window of 2*lookback bars ending at i-1 (shifted by 1)
        long_term_atr = data["true_range"].rolling(self.lookback * 2).mean().shift(1)

        result = (current_atr >= (long_term_atr * self.min_atr_mult)).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


class MomentumFilter(BaseFilter):
    name = "MomentumFilter"

    def __init__(self, lookback: int = 10):
        self.lookback = lookback

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback:
            return False
        return bool(data.iloc[i]["close"] > data.iloc[i - self.lookback]["close"])

    def mask(self, data: pd.DataFrame) -> pd.Series:
        warmup = self.lookback

        result = (data["close"] > data["close"].shift(self.lookback)).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


class UpCloseFilter(BaseFilter):
    name = "UpCloseFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1:
            return False
        return bool(data.iloc[i]["close"] > data.iloc[i - 1]["close"])

    def mask(self, data: pd.DataFrame) -> pd.Series:
        result = (data["close"] > data["close"].shift(1)).copy()
        result.iloc[:1] = False
        return result.fillna(False)


class TwoBarUpFilter(BaseFilter):
    name = "TwoBarUpFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 2:
            return False
        return bool(
            data.iloc[i]["close"] > data.iloc[i - 1]["close"]
            and data.iloc[i - 1]["close"] > data.iloc[i - 2]["close"]
        )

    def mask(self, data: pd.DataFrame) -> pd.Series:
        c0 = data["close"]
        c1 = data["close"].shift(1)
        c2 = data["close"].shift(2)
        result = ((c0 > c1) & (c1 > c2)).copy()
        result.iloc[:2] = False
        return result.fillna(False)


class TrendSlopeFilter(BaseFilter):
    name = "TrendSlopeFilter"

    def __init__(self, fast_length: int = 50, slope_bars: int = 5):
        self.fast_length = fast_length
        self.slope_bars = slope_bars

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        min_bars = max(self.fast_length, self.slope_bars + self.fast_length)
        if i < min_bars:
            return False

        fast_col = f"sma_{self.fast_length}"
        if fast_col in data.columns:
            current_fast = data.iloc[i][fast_col]
            past_fast = data.iloc[i - self.slope_bars][fast_col]
        else:
            current_fast = data["close"].iloc[i - self.fast_length + 1 : i + 1].mean()
            past_fast = data["close"].iloc[
                i - self.slope_bars - self.fast_length + 1 : i - self.slope_bars + 1
            ].mean()

        return bool(current_fast > past_fast)

    def mask(self, data: pd.DataFrame) -> pd.Series:
        fast_col = f"sma_{self.fast_length}"
        min_bars = max(self.fast_length, self.slope_bars + self.fast_length)

        fast = data[fast_col] if fast_col in data.columns else data["close"].rolling(self.fast_length).mean()
        past_fast = fast.shift(self.slope_bars)

        result = (fast > past_fast).copy()
        result.iloc[:min_bars] = False
        return result.fillna(False)


class CloseAboveFastSMAFilter(BaseFilter):
    name = "CloseAboveFastSMAFilter"

    def __init__(self, fast_length: int = 50):
        self.fast_length = fast_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length:
            return False

        fast_col = f"sma_{self.fast_length}"
        fast_sma = (
            data.iloc[i][fast_col]
            if fast_col in data.columns
            else data["close"].iloc[i - self.fast_length + 1 : i + 1].mean()
        )
        return bool(data.iloc[i]["close"] > fast_sma)

    def mask(self, data: pd.DataFrame) -> pd.Series:
        fast_col = f"sma_{self.fast_length}"
        warmup = self.fast_length

        fast = data[fast_col] if fast_col in data.columns else data["close"].rolling(self.fast_length).mean()

        result = (data["close"] > fast).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


class HigherLowFilter(BaseFilter):
    name = "HigherLowFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 2:
            return False
        return bool(data.iloc[i]["low"] > data.iloc[i - 1]["low"])

    def mask(self, data: pd.DataFrame) -> pd.Series:
        result = (data["low"] > data["low"].shift(1)).copy()
        result.iloc[:2] = False
        return result.fillna(False)


# ============================================================
# Breakout-family filters
# ============================================================

class CompressionFilter(BaseFilter):
    name = "CompressionFilter"

    def __init__(self, lookback: int = 20, max_atr_mult: float = 0.75):
        self.lookback = lookback
        self.max_atr_mult = max_atr_mult

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback * 2:
            return False

        atr_col = f"atr_{self.lookback}"
        current_atr = data.iloc[i][atr_col] if atr_col in data.columns else 10.0
        long_term_atr = data["true_range"].iloc[i - (self.lookback * 2) : i].mean()

        return bool(current_atr <= (long_term_atr * self.max_atr_mult))

    def mask(self, data: pd.DataFrame) -> pd.Series:
        atr_col = f"atr_{self.lookback}"
        warmup = self.lookback * 2

        current_atr = data[atr_col] if atr_col in data.columns else pd.Series(10.0, index=data.index)
        long_term_atr = data["true_range"].rolling(self.lookback * 2).mean().shift(1)

        result = (current_atr <= (long_term_atr * self.max_atr_mult)).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


class RangeBreakoutFilter(BaseFilter):
    name = "RangeBreakoutFilter"

    def __init__(self, lookback: int = 20):
        self.lookback = lookback

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback:
            return False

        prior_high = data.iloc[i - self.lookback : i]["high"].max()
        return bool(data.iloc[i]["close"] > prior_high)

    def mask(self, data: pd.DataFrame) -> pd.Series:
        warmup = self.lookback
        # prior_high: max of lookback bars ending at i-1
        prior_high = data["high"].rolling(self.lookback).max().shift(1)

        result = (data["close"] > prior_high).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


class ExpansionBarFilter(BaseFilter):
    name = "ExpansionBarFilter"

    def __init__(self, lookback: int = 20, expansion_multiplier: float = 1.50):
        self.lookback = lookback
        self.expansion_multiplier = expansion_multiplier

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback:
            return False

        current_tr = (
            data.iloc[i]["true_range"]
            if "true_range" in data.columns
            else (data.iloc[i]["high"] - data.iloc[i]["low"])
        )
        atr_col = f"atr_{self.lookback}"
        current_atr = data.iloc[i][atr_col] if atr_col in data.columns else 10.0

        return bool(current_tr >= (current_atr * self.expansion_multiplier))

    def mask(self, data: pd.DataFrame) -> pd.Series:
        atr_col = f"atr_{self.lookback}"
        warmup = self.lookback

        current_tr = data["true_range"] if "true_range" in data.columns else (data["high"] - data["low"])
        current_atr = data[atr_col] if atr_col in data.columns else pd.Series(10.0, index=data.index)

        result = (current_tr >= (current_atr * self.expansion_multiplier)).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


class BreakoutRetestFilter(BaseFilter):
    name = "BreakoutRetestFilter"

    def __init__(self, lookback: int = 20, atr_buffer_mult: float = 0.0):
        self.lookback = lookback
        self.atr_buffer_mult = atr_buffer_mult

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback:
            return False

        prior_high = data.iloc[i - self.lookback : i]["high"].max()
        current_atr = (
            data.iloc[i][f"atr_{self.lookback}"]
            if f"atr_{self.lookback}" in data.columns
            else 10.0
        )

        return bool(data.iloc[i]["close"] > prior_high + (current_atr * self.atr_buffer_mult))

    def mask(self, data: pd.DataFrame) -> pd.Series:
        atr_col = f"atr_{self.lookback}"
        warmup = self.lookback

        prior_high = data["high"].rolling(self.lookback).max().shift(1)
        current_atr = data[atr_col] if atr_col in data.columns else pd.Series(10.0, index=data.index)

        result = (data["close"] > prior_high + (current_atr * self.atr_buffer_mult)).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


class BreakoutTrendFilter(BaseFilter):
    name = "BreakoutTrendFilter"

    def __init__(self, fast_length: int = 50, slow_length: int = 200):
        self.fast_length = fast_length
        self.slow_length = slow_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < max(self.fast_length, self.slow_length):
            return False

        fast_col = f"sma_{self.fast_length}"
        slow_col = f"sma_{self.slow_length}"

        fast_sma = (
            data.iloc[i][fast_col]
            if fast_col in data.columns
            else data["close"].iloc[i - self.fast_length + 1 : i + 1].mean()
        )
        slow_sma = (
            data.iloc[i][slow_col]
            if slow_col in data.columns
            else data["close"].iloc[i - self.slow_length + 1 : i + 1].mean()
        )

        return bool(fast_sma > slow_sma)

    def mask(self, data: pd.DataFrame) -> pd.Series:
        fast_col = f"sma_{self.fast_length}"
        slow_col = f"sma_{self.slow_length}"
        warmup = max(self.fast_length, self.slow_length)

        fast = data[fast_col] if fast_col in data.columns else data["close"].rolling(self.fast_length).mean()
        slow = data[slow_col] if slow_col in data.columns else data["close"].rolling(self.slow_length).mean()

        result = (fast > slow).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


class BreakoutCloseStrengthFilter(BaseFilter):
    name = "BreakoutCloseStrengthFilter"

    def __init__(self, close_position_threshold: float = 0.60):
        self.close_position_threshold = close_position_threshold

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        c_high = data.iloc[i]["high"]
        c_low = data.iloc[i]["low"]
        c_close = data.iloc[i]["close"]

        bar_range = c_high - c_low
        if bar_range <= 0:
            return False

        return bool(((c_close - c_low) / bar_range) >= self.close_position_threshold)

    def mask(self, data: pd.DataFrame) -> pd.Series:
        bar_range = data["high"] - data["low"]
        valid = bar_range > 0
        close_position = (data["close"] - data["low"]) / bar_range.where(valid, other=1.0)
        result = valid & (close_position >= self.close_position_threshold)
        return result.fillna(False)


class PriorRangePositionFilter(BaseFilter):
    name = "PriorRangePositionFilter"

    def __init__(self, lookback: int = 20, min_position_in_range: float = 0.50):
        self.lookback = lookback
        self.min_position_in_range = min_position_in_range

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback or i < 1:
            return False

        prior_window = data.iloc[i - self.lookback : i]
        r_low = prior_window["low"].min()
        r_high = prior_window["high"].max()
        full_range = r_high - r_low

        if full_range <= 0:
            return False

        return bool(((data.iloc[i - 1]["close"] - r_low) / full_range) >= self.min_position_in_range)

    def mask(self, data: pd.DataFrame) -> pd.Series:
        warmup = self.lookback

        # Rolling min/max over lookback bars ending at i-1 (shifted by 1)
        r_low = data["low"].rolling(self.lookback).min().shift(1)
        r_high = data["high"].rolling(self.lookback).max().shift(1)
        full_range = r_high - r_low

        prev_close = data["prev_close"] if "prev_close" in data.columns else data["close"].shift(1)

        valid = full_range > 0
        position = (prev_close - r_low) / full_range.where(valid, other=1.0)
        result = (valid & (position >= self.min_position_in_range)).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


class BreakoutDistanceFilter(BaseFilter):
    name = "BreakoutDistanceFilter"

    def __init__(self, lookback: int = 20, min_breakout_atr: float = 0.10):
        self.lookback = lookback
        self.min_breakout_atr = min_breakout_atr

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback:
            return False

        prior_high = data.iloc[i - self.lookback : i]["high"].max()
        current_atr = (
            data.iloc[i][f"atr_{self.lookback}"]
            if f"atr_{self.lookback}" in data.columns
            else 10.0
        )
        breakout_distance = data.iloc[i]["close"] - prior_high

        return bool(breakout_distance >= (current_atr * self.min_breakout_atr))

    def mask(self, data: pd.DataFrame) -> pd.Series:
        atr_col = f"atr_{self.lookback}"
        warmup = self.lookback

        prior_high = data["high"].rolling(self.lookback).max().shift(1)
        current_atr = data[atr_col] if atr_col in data.columns else pd.Series(10.0, index=data.index)
        breakout_distance = data["close"] - prior_high

        result = (breakout_distance >= (current_atr * self.min_breakout_atr)).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


class RisingBaseFilter(BaseFilter):
    name = "RisingBaseFilter"

    def __init__(self, lookback: int = 5):
        self.lookback = lookback

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback + 1:
            return False

        recent_lows = data.iloc[i - self.lookback : i]["low"]
        first_half = recent_lows.iloc[: max(1, len(recent_lows) // 2)]
        second_half = recent_lows.iloc[max(1, len(recent_lows) // 2) :]

        if first_half.empty or second_half.empty:
            return False

        return bool(second_half.min() >= first_half.min())

    def mask(self, data: pd.DataFrame) -> pd.Series:
        warmup = self.lookback + 1
        half = max(1, self.lookback // 2)
        second_half_len = self.lookback - half

        if second_half_len <= 0:
            return pd.Series(False, index=data.index, dtype=bool)

        # first_half: oldest `half` bars in the window [i-lookback, i-1]
        # = rolling(half).min() at position i - second_half_len - 1
        # = rolling(half).min().shift(second_half_len + 1)
        first_half_min = data["low"].rolling(half).min().shift(second_half_len + 1)

        # second_half: newest `second_half_len` bars in the window ending at i-1
        # = rolling(second_half_len).min() at position i-1
        # = rolling(second_half_len).min().shift(1)
        second_half_min = data["low"].rolling(second_half_len).min().shift(1)

        valid = first_half_min.notna() & second_half_min.notna()
        result = (valid & (second_half_min >= first_half_min)).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


class TightRangeFilter(BaseFilter):
    name = "TightRangeFilter"

    def __init__(self, lookback: int = 20, max_bar_range_mult: float = 0.85):
        self.lookback = lookback
        self.max_bar_range_mult = max_bar_range_mult

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback:
            return False

        avg_range_col = f"avg_range_{self.lookback}"
        avg_range = data.iloc[i][avg_range_col] if avg_range_col in data.columns else data["bar_range"].iloc[i - self.lookback : i].mean()
        current_range = data.iloc[i]["bar_range"] if "bar_range" in data.columns else (data.iloc[i]["high"] - data.iloc[i]["low"])

        return bool(current_range <= (avg_range * self.max_bar_range_mult))

    def mask(self, data: pd.DataFrame) -> pd.Series:
        avg_range_col = f"avg_range_{self.lookback}"
        warmup = self.lookback

        if avg_range_col in data.columns:
            avg_range = data[avg_range_col]
        else:
            bar_range_series = data["bar_range"] if "bar_range" in data.columns else (data["high"] - data["low"])
            avg_range = bar_range_series.rolling(self.lookback).mean()

        current_range = data["bar_range"] if "bar_range" in data.columns else (data["high"] - data["low"])

        result = (current_range <= (avg_range * self.max_bar_range_mult)).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


# ============================================================
# Mean-reversion-family filters
# ============================================================

class BelowFastSMAFilter(BaseFilter):
    name = "BelowFastSMAFilter"

    def __init__(self, fast_length: int = 20):
        self.fast_length = fast_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length:
            return False

        fast_col = f"sma_{self.fast_length}"
        fast_sma = (
            data.iloc[i][fast_col]
            if fast_col in data.columns
            else data["close"].iloc[i - self.fast_length + 1 : i + 1].mean()
        )
        return bool(data.iloc[i]["close"] < fast_sma)

    def mask(self, data: pd.DataFrame) -> pd.Series:
        fast_col = f"sma_{self.fast_length}"
        warmup = self.fast_length

        fast = data[fast_col] if fast_col in data.columns else data["close"].rolling(self.fast_length).mean()

        result = (data["close"] < fast).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


class DistanceBelowSMAFilter(BaseFilter):
    name = "DistanceBelowSMAFilter"

    def __init__(self, fast_length: int = 20, min_distance_atr: float = 0.3):
        self.fast_length = fast_length
        self.min_distance_atr = min_distance_atr

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length:
            return False

        fast_col = f"sma_{self.fast_length}"
        fast_sma = (
            data.iloc[i][fast_col]
            if fast_col in data.columns
            else data["close"].iloc[i - self.fast_length + 1 : i + 1].mean()
        )
        current_atr = data.iloc[i]["atr_20"] if "atr_20" in data.columns else 10.0

        return bool((fast_sma - data.iloc[i]["close"]) >= (current_atr * self.min_distance_atr))

    def mask(self, data: pd.DataFrame) -> pd.Series:
        fast_col = f"sma_{self.fast_length}"
        warmup = self.fast_length

        fast = data[fast_col] if fast_col in data.columns else data["close"].rolling(self.fast_length).mean()
        current_atr = data["atr_20"] if "atr_20" in data.columns else pd.Series(10.0, index=data.index)

        result = ((fast - data["close"]) >= (current_atr * self.min_distance_atr)).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


class DownCloseFilter(BaseFilter):
    name = "DownCloseFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1:
            return False
        return bool(data.iloc[i]["close"] < data.iloc[i - 1]["close"])

    def mask(self, data: pd.DataFrame) -> pd.Series:
        result = (data["close"] < data["close"].shift(1)).copy()
        result.iloc[:1] = False
        return result.fillna(False)


class TwoBarDownFilter(BaseFilter):
    name = "TwoBarDownFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 2:
            return False
        return bool(
            data.iloc[i]["close"] < data.iloc[i - 1]["close"]
            and data.iloc[i - 1]["close"] < data.iloc[i - 2]["close"]
        )

    def mask(self, data: pd.DataFrame) -> pd.Series:
        c0 = data["close"]
        c1 = data["close"].shift(1)
        c2 = data["close"].shift(2)
        result = ((c0 < c1) & (c1 < c2)).copy()
        result.iloc[:2] = False
        return result.fillna(False)


class ReversalUpBarFilter(BaseFilter):
    name = "ReversalUpBarFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        return bool(data.iloc[i]["close"] > data.iloc[i]["open"])

    def mask(self, data: pd.DataFrame) -> pd.Series:
        return (data["close"] > data["open"]).fillna(False)


class LowVolatilityRegimeFilter(BaseFilter):
    name = "LowVolatilityRegimeFilter"

    def __init__(self, lookback: int = 20, max_atr_mult: float = 1.0):
        self.lookback = lookback
        self.max_atr_mult = max_atr_mult

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback * 2:
            return False

        atr_col = f"atr_{self.lookback}"
        current_atr = data.iloc[i][atr_col] if atr_col in data.columns else 10.0
        long_term_atr = data["true_range"].iloc[i - (self.lookback * 2) : i].mean()

        return bool(current_atr <= (long_term_atr * self.max_atr_mult))

    def mask(self, data: pd.DataFrame) -> pd.Series:
        atr_col = f"atr_{self.lookback}"
        warmup = self.lookback * 2

        current_atr = data[atr_col] if atr_col in data.columns else pd.Series(10.0, index=data.index)
        long_term_atr = data["true_range"].rolling(self.lookback * 2).mean().shift(1)

        result = (current_atr <= (long_term_atr * self.max_atr_mult)).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


class AboveLongTermSMAFilter(BaseFilter):
    name = "AboveLongTermSMAFilter"

    def __init__(self, slow_length: int = 200):
        self.slow_length = slow_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.slow_length:
            return False

        slow_col = f"sma_{self.slow_length}"
        slow_sma = (
            data.iloc[i][slow_col]
            if slow_col in data.columns
            else data["close"].iloc[i - self.slow_length + 1 : i + 1].mean()
        )
        return bool(data.iloc[i]["close"] > slow_sma)

    def mask(self, data: pd.DataFrame) -> pd.Series:
        slow_col = f"sma_{self.slow_length}"
        warmup = self.slow_length

        slow = data[slow_col] if slow_col in data.columns else data["close"].rolling(self.slow_length).mean()

        result = (data["close"] > slow).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


class ThreeBarDownFilter(BaseFilter):
    name = "ThreeBarDownFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 3:
            return False

        return bool(
            data.iloc[i]["close"] < data.iloc[i - 1]["close"]
            and data.iloc[i - 1]["close"] < data.iloc[i - 2]["close"]
            and data.iloc[i - 2]["close"] < data.iloc[i - 3]["close"]
        )

    def mask(self, data: pd.DataFrame) -> pd.Series:
        c0 = data["close"]
        c1 = data["close"].shift(1)
        c2 = data["close"].shift(2)
        c3 = data["close"].shift(3)
        result = ((c0 < c1) & (c1 < c2) & (c2 < c3)).copy()
        result.iloc[:3] = False
        return result.fillna(False)


class CloseNearLowFilter(BaseFilter):
    name = "CloseNearLowFilter"

    def __init__(self, max_close_position: float = 0.35):
        self.max_close_position = max_close_position

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        high_ = data.iloc[i]["high"]
        low_ = data.iloc[i]["low"]
        close_ = data.iloc[i]["close"]

        bar_range = high_ - low_
        if bar_range <= 0:
            return False

        close_position = (close_ - low_) / bar_range
        return bool(close_position <= self.max_close_position)

    def mask(self, data: pd.DataFrame) -> pd.Series:
        bar_range = data["high"] - data["low"]
        valid = bar_range > 0
        close_position = (data["close"] - data["low"]) / bar_range.where(valid, other=1.0)
        result = valid & (close_position <= self.max_close_position)
        return result.fillna(False)


class StretchFromLongTermSMAFilter(BaseFilter):
    name = "StretchFromLongTermSMAFilter"

    def __init__(self, slow_length: int = 200, min_distance_atr: float = 0.5):
        self.slow_length = slow_length
        self.min_distance_atr = min_distance_atr

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.slow_length:
            return False

        slow_col = f"sma_{self.slow_length}"
        slow_sma = (
            data.iloc[i][slow_col]
            if slow_col in data.columns
            else data["close"].iloc[i - self.slow_length + 1 : i + 1].mean()
        )
        current_atr = data.iloc[i]["atr_20"] if "atr_20" in data.columns else 10.0
        distance = slow_sma - data.iloc[i]["close"]

        return bool(distance >= (current_atr * self.min_distance_atr))

    def mask(self, data: pd.DataFrame) -> pd.Series:
        slow_col = f"sma_{self.slow_length}"
        warmup = self.slow_length

        slow = data[slow_col] if slow_col in data.columns else data["close"].rolling(self.slow_length).mean()
        current_atr = data["atr_20"] if "atr_20" in data.columns else pd.Series(10.0, index=data.index)

        result = ((slow - data["close"]) >= (current_atr * self.min_distance_atr)).copy()
        result.iloc[:warmup] = False
        return result.fillna(False)


# ─── Short MR filters ────────────────────────────────────────────────────────


class AboveFastSMAFilter(BaseFilter):
    """Price above fast SMA — baseline overbought condition for short MR."""
    name = "AboveFastSMA"

    def __init__(self, fast_length: int = 20):
        self.fast_length = fast_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length:
            return False
        col = f"sma_{self.fast_length}"
        sma = data[col].iloc[i] if col in data.columns else data["close"].iloc[i - self.fast_length:i].mean()
        return data["close"].iloc[i] > sma

    def mask(self, data: pd.DataFrame) -> np.ndarray:
        col = f"sma_{self.fast_length}"
        if col in data.columns:
            return data["close"].values > data[col].values
        sma = data["close"].rolling(self.fast_length).mean().values
        return data["close"].values > sma


class DistanceAboveSMAFilter(BaseFilter):
    """Price is meaningfully above fast SMA — short MR stretch condition."""
    name = "DistanceAboveSMA"

    def __init__(self, fast_length: int = 20, min_distance_atr: float = 0.8):
        self.fast_length = fast_length
        self.min_distance_atr = min_distance_atr

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length:
            return False
        col = f"sma_{self.fast_length}"
        atr_col = f"atr_{self.fast_length}"
        sma = data[col].iloc[i] if col in data.columns else data["close"].iloc[i - self.fast_length:i].mean()
        atr = data[atr_col].iloc[i] if atr_col in data.columns else 1.0
        return (data["close"].iloc[i] - sma) >= atr * self.min_distance_atr

    def mask(self, data: pd.DataFrame) -> np.ndarray:
        col = f"sma_{self.fast_length}"
        atr_col = f"atr_{self.fast_length}"
        close = data["close"].values
        sma = data[col].values if col in data.columns else pd.Series(close).rolling(self.fast_length).mean().values
        atr = data[atr_col].values if atr_col in data.columns else np.ones(len(close))
        return (close - sma) >= atr * self.min_distance_atr


class UpCloseShortFilter(BaseFilter):
    """Current close above previous close — short-side selling pressure confirmation."""
    name = "UpCloseShort"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1:
            return False
        return data["close"].iloc[i] > data["close"].iloc[i - 1]

    def mask(self, data: pd.DataFrame) -> np.ndarray:
        close = data["close"].values
        result = np.zeros(len(close), dtype=bool)
        result[1:] = close[1:] > close[:-1]
        return result


class TwoBarUpShortFilter(BaseFilter):
    """Two consecutive up closes — short exhaustion pattern."""
    name = "TwoBarUpShort"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 2:
            return False
        return (data["close"].iloc[i] > data["close"].iloc[i - 1] and
                data["close"].iloc[i - 1] > data["close"].iloc[i - 2])

    def mask(self, data: pd.DataFrame) -> np.ndarray:
        close = data["close"].values
        result = np.zeros(len(close), dtype=bool)
        result[2:] = (close[2:] > close[1:-1]) & (close[1:-1] > close[:-2])
        return result


class ReversalDownBarFilter(BaseFilter):
    """Current close below current open — short-side reversal trigger."""
    name = "ReversalDownBar"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        return data["close"].iloc[i] < data["open"].iloc[i]

    def mask(self, data: pd.DataFrame) -> np.ndarray:
        return data["close"].values < data["open"].values


class HighVolatilityRegimeFilter(BaseFilter):
    """ATR above regime threshold — short MR in elevated vol (mirror of LowVolatilityRegime)."""
    name = "HighVolatilityRegime"

    def __init__(self, lookback: int = 20, min_atr_mult: float = 1.1):
        self.lookback = lookback
        self.min_atr_mult = min_atr_mult

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback * 2:
            return False
        atr_col = f"atr_{self.lookback}"
        current_atr = data[atr_col].iloc[i] if atr_col in data.columns else 1.0
        long_term_atr = data[atr_col].iloc[i - self.lookback:i].mean()
        return current_atr >= long_term_atr * self.min_atr_mult

    def mask(self, data: pd.DataFrame) -> np.ndarray:
        atr_col = f"atr_{self.lookback}"
        if atr_col not in data.columns:
            return np.zeros(len(data), dtype=bool)
        atr = data[atr_col].values
        long_term = pd.Series(atr).rolling(self.lookback).mean().values
        return atr >= long_term * self.min_atr_mult


class StretchAboveLongTermSMAFilter(BaseFilter):
    """Price meaningfully above 200 SMA — short MR long-term stretch."""
    name = "StretchAboveLongTermSMA"

    def __init__(self, slow_length: int = 200, min_distance_atr: float = 0.5):
        self.slow_length = slow_length
        self.min_distance_atr = min_distance_atr

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.slow_length:
            return False
        col = f"sma_{self.slow_length}"
        atr_col = "atr_20"
        sma = data[col].iloc[i] if col in data.columns else data["close"].iloc[i - self.slow_length:i].mean()
        atr = data[atr_col].iloc[i] if atr_col in data.columns else 1.0
        return (data["close"].iloc[i] - sma) >= atr * self.min_distance_atr

    def mask(self, data: pd.DataFrame) -> np.ndarray:
        col = f"sma_{self.slow_length}"
        atr_col = "atr_20"
        if col not in data.columns:
            return np.zeros(len(data), dtype=bool)
        close = data["close"].values
        sma = data[col].values
        atr = data[atr_col].values if atr_col in data.columns else np.ones(len(close))
        return (close - sma) >= atr * self.min_distance_atr


# ─── Short Trend filters ────────────────────────────────────────────────────


class DowntrendDirectionFilter(BaseFilter):
    """Fast SMA below slow SMA — confirms downtrend regime."""
    name = "DowntrendDirection"

    def __init__(self, fast_length: int = 50, slow_length: int = 200):
        self.fast_length = fast_length
        self.slow_length = slow_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.slow_length:
            return False
        fast_col = f"sma_{self.fast_length}"
        slow_col = f"sma_{self.slow_length}"
        fast = data[fast_col].iloc[i] if fast_col in data.columns else data["close"].iloc[i - self.fast_length:i].mean()
        slow = data[slow_col].iloc[i] if slow_col in data.columns else data["close"].iloc[i - self.slow_length:i].mean()
        return fast < slow

    def mask(self, data: pd.DataFrame) -> np.ndarray:
        fast_col = f"sma_{self.fast_length}"
        slow_col = f"sma_{self.slow_length}"
        if fast_col not in data.columns or slow_col not in data.columns:
            return np.zeros(len(data), dtype=bool)
        return data[fast_col].values < data[slow_col].values


class RallyInDowntrendFilter(BaseFilter):
    """Previous close at or above fast SMA — rally within downtrend (short entry setup)."""
    name = "RallyInDowntrend"

    def __init__(self, fast_length: int = 50):
        self.fast_length = fast_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1:
            return False
        col = f"sma_{self.fast_length}"
        sma = data[col].iloc[i - 1] if col in data.columns else data["close"].iloc[i - 1 - self.fast_length:i - 1].mean()
        return data["close"].iloc[i - 1] >= sma

    def mask(self, data: pd.DataFrame) -> np.ndarray:
        col = f"sma_{self.fast_length}"
        if col not in data.columns:
            return np.zeros(len(data), dtype=bool)
        prev_close = np.roll(data["close"].values, 1)
        prev_sma = np.roll(data[col].values, 1)
        result = prev_close >= prev_sma
        result[0] = False
        return result


class FailureToHoldFilter(BaseFilter):
    """Current close back below fast SMA — rally failed, short trigger."""
    name = "FailureToHold"

    def __init__(self, fast_length: int = 50):
        self.fast_length = fast_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length:
            return False
        col = f"sma_{self.fast_length}"
        sma = data[col].iloc[i] if col in data.columns else data["close"].iloc[i - self.fast_length:i].mean()
        return data["close"].iloc[i] < sma

    def mask(self, data: pd.DataFrame) -> np.ndarray:
        col = f"sma_{self.fast_length}"
        if col not in data.columns:
            return np.zeros(len(data), dtype=bool)
        return data["close"].values < data[col].values


class LowerHighFilter(BaseFilter):
    """Current high below previous high — structural downtrend continuation."""
    name = "LowerHigh"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1:
            return False
        return data["high"].iloc[i] < data["high"].iloc[i - 1]

    def mask(self, data: pd.DataFrame) -> np.ndarray:
        high = data["high"].values
        result = np.zeros(len(high), dtype=bool)
        result[1:] = high[1:] < high[:-1]
        return result


class DownCloseShortFilter(BaseFilter):
    """Current close below previous close — simple bearish confirmation."""
    name = "DownCloseShort"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1:
            return False
        return data["close"].iloc[i] < data["close"].iloc[i - 1]

    def mask(self, data: pd.DataFrame) -> np.ndarray:
        close = data["close"].values
        result = np.zeros(len(close), dtype=bool)
        result[1:] = close[1:] < close[:-1]
        return result


class DowntrendSlopeFilter(BaseFilter):
    """Fast SMA falling — confirms trend is worsening not just negative."""
    name = "DowntrendSlope"

    def __init__(self, fast_length: int = 50, slope_bars: int = 5):
        self.fast_length = fast_length
        self.slope_bars = slope_bars

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length + self.slope_bars:
            return False
        col = f"sma_{self.fast_length}"
        if col not in data.columns:
            return False
        return data[col].iloc[i] < data[col].iloc[i - self.slope_bars]

    def mask(self, data: pd.DataFrame) -> np.ndarray:
        col = f"sma_{self.fast_length}"
        if col not in data.columns:
            return np.zeros(len(data), dtype=bool)
        sma = data[col].values
        result = np.zeros(len(sma), dtype=bool)
        result[self.slope_bars:] = sma[self.slope_bars:] < sma[:-self.slope_bars]
        return result


# ─── Short Breakout filters ────────────────────────────────────────────────


class DownsideBreakoutFilter(BaseFilter):
    """Close below prior N-bar low — downside range breakout."""
    name = "DownsideBreakout"

    def __init__(self, lookback: int = 20):
        self.lookback = lookback

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback:
            return False
        prior_low = data["low"].iloc[i - self.lookback:i].min()
        return data["close"].iloc[i] < prior_low

    def mask(self, data: pd.DataFrame) -> np.ndarray:
        prior_low = data["low"].rolling(self.lookback).min().shift(1).values
        return data["close"].values < prior_low


class WeakCloseFilter(BaseFilter):
    """Close near bar low — weak close confirming selling pressure."""
    name = "WeakClose"

    def __init__(self, max_close_position: float = 0.35):
        self.max_close_position = max_close_position

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        bar_range = data["high"].iloc[i] - data["low"].iloc[i]
        if bar_range < 0.001:
            return False
        pos = (data["close"].iloc[i] - data["low"].iloc[i]) / bar_range
        return pos <= self.max_close_position

    def mask(self, data: pd.DataFrame) -> np.ndarray:
        high = data["high"].values
        low = data["low"].values
        close = data["close"].values
        bar_range = high - low
        pos = np.where(bar_range > 0.001, (close - low) / bar_range, 0.5)
        return pos <= self.max_close_position


# ============================================================
# Universal / market-agnostic filters
# ============================================================

class InsideBarFilter(BaseFilter):
    """Current bar's range entirely within previous bar's range (compression)."""
    name = "InsideBarFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1:
            return False
        return bool(
            data.iloc[i]["high"] <= data.iloc[i - 1]["high"]
            and data.iloc[i]["low"] >= data.iloc[i - 1]["low"]
        )

    def mask(self, data: pd.DataFrame) -> pd.Series:
        inside = (data["high"] <= data["high"].shift(1)) & (data["low"] >= data["low"].shift(1))
        result = inside.copy()
        result.iloc[0] = False
        return result.fillna(False)


class OutsideBarFilter(BaseFilter):
    """Current bar's range engulfs the previous bar entirely (expansion)."""
    name = "OutsideBarFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1:
            return False
        return bool(
            data.iloc[i]["high"] > data.iloc[i - 1]["high"]
            and data.iloc[i]["low"] < data.iloc[i - 1]["low"]
        )

    def mask(self, data: pd.DataFrame) -> pd.Series:
        outside = (data["high"] > data["high"].shift(1)) & (data["low"] < data["low"].shift(1))
        result = outside.copy()
        result.iloc[0] = False
        return result.fillna(False)


class GapUpFilter(BaseFilter):
    """Current bar opens above previous bar's high."""
    name = "GapUpFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1:
            return False
        return bool(data.iloc[i]["open"] > data.iloc[i - 1]["high"])

    def mask(self, data: pd.DataFrame) -> pd.Series:
        gap_up = data["open"] > data["high"].shift(1)
        result = gap_up.copy()
        result.iloc[0] = False
        return result.fillna(False)


class GapDownFilter(BaseFilter):
    """Current bar opens below previous bar's low."""
    name = "GapDownFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1:
            return False
        return bool(data.iloc[i]["open"] < data.iloc[i - 1]["low"])

    def mask(self, data: pd.DataFrame) -> pd.Series:
        gap_down = data["open"] < data["low"].shift(1)
        result = gap_down.copy()
        result.iloc[0] = False
        return result.fillna(False)


class ATRPercentileFilter(BaseFilter):
    """Checks whether current ATR is in a specific percentile range of its own history."""
    name = "ATRPercentileFilter"

    def __init__(self, lookback: int = 100, min_percentile: float = 0.0, max_percentile: float = 0.5):
        self.lookback = lookback
        self.min_percentile = min_percentile
        self.max_percentile = max_percentile

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback:
            return False
        atr_col = f"atr_{min(self.lookback, 20)}"
        if atr_col in data.columns:
            current_atr = data.iloc[i][atr_col]
        else:
            current_atr = data["true_range"].iloc[max(0, i - 19):i + 1].mean()
        window = data["true_range"].iloc[i - self.lookback + 1:i + 1]
        rank = (window < current_atr).sum() / len(window)
        return bool(self.min_percentile <= rank <= self.max_percentile)

    def mask(self, data: pd.DataFrame) -> pd.Series:
        tr = data["true_range"] if "true_range" in data.columns else (data["high"] - data["low"])
        atr_col = f"atr_{min(self.lookback, 20)}"
        if atr_col in data.columns:
            current_atr = data[atr_col]
        else:
            current_atr = tr.rolling(20).mean()
        rolling_rank = tr.rolling(self.lookback).apply(
            lambda w: (w < w.iloc[-1]).sum() / len(w),
            raw=False,
        )
        # passes() compares window against current_atr, not window's own last value
        # Recompute using current_atr as the reference
        ranks = pd.Series(np.nan, index=data.index)
        tr_vals = tr.values
        atr_vals = current_atr.values
        for i in range(self.lookback, len(data)):
            window = tr_vals[i - self.lookback + 1:i + 1]
            ranks.iloc[i] = (window < atr_vals[i]).sum() / len(window)
        result = (ranks >= self.min_percentile) & (ranks <= self.max_percentile)
        result.iloc[:self.lookback] = False
        return result.fillna(False)


class HigherHighFilter(BaseFilter):
    """Current high > previous high (trend continuation structure)."""
    name = "HigherHighFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1:
            return False
        return bool(data.iloc[i]["high"] > data.iloc[i - 1]["high"])

    def mask(self, data: pd.DataFrame) -> pd.Series:
        result = (data["high"] > data["high"].shift(1)).copy()
        result.iloc[0] = False
        return result.fillna(False)


class CumulativeDeclineFilter(BaseFilter):
    """Measures total price decline over N bars in ATR units, regardless of
    individual bar direction. Catches exhaustion moves that consecutive-bar
    filters miss (e.g., down-up-down-down that drops 2 ATR total).
    direction='long': decline = Close[lookback ago] - Close (positive = fell).
    direction='short': advance = Close - Close[lookback ago] (positive = rose).
    """
    name = "CumulativeDeclineFilter"

    def __init__(self, lookback: int = 4, atr_period: int = 20,
                 min_decline_atr: float = 1.5, direction: str = "long"):
        self.lookback = lookback
        self.atr_period = atr_period
        self.min_decline_atr = min_decline_atr
        self.direction = direction

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < max(self.lookback, self.atr_period):
            return False
        atr_col = f"atr_{self.atr_period}"
        atr = data[atr_col].iloc[i] if atr_col in data.columns else data["bar_range"].iloc[max(0, i - self.atr_period + 1):i + 1].mean()
        if pd.isna(atr) or atr <= 0:
            return False
        if self.direction == "long":
            move = data["close"].iloc[i - self.lookback] - data["close"].iloc[i]
        else:
            move = data["close"].iloc[i] - data["close"].iloc[i - self.lookback]
        return bool(move / atr >= self.min_decline_atr)

    def mask(self, data: pd.DataFrame) -> pd.Series:
        atr_col = f"atr_{self.atr_period}"
        atr = data[atr_col] if atr_col in data.columns else data["bar_range"].rolling(self.atr_period).mean()
        if self.direction == "long":
            move = data["close"].shift(self.lookback) - data["close"]
        else:
            move = data["close"] - data["close"].shift(self.lookback)
        ratio = move / atr.replace(0, np.nan)
        result = (ratio >= self.min_decline_atr).copy()
        warmup = max(self.lookback, self.atr_period)
        result.iloc[:warmup] = False
        return result.fillna(False)


class WickRejectionFilter(BaseFilter):
    """Pin bar / wick rejection filter.
    Long: large lower wick + close near high → buying rejection of lows.
    Short: large upper wick + close near low → selling rejection of highs.
    """
    name = "WickRejectionFilter"

    def __init__(self, wick_ratio: float = 0.5, close_position: float = 0.70,
                 min_range_mult: float = 1.0, direction: str = "long"):
        self.wick_ratio = wick_ratio
        self.close_position = close_position
        self.min_range_mult = min_range_mult
        self.direction = direction

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 20:
            return False
        bar = data.iloc[i]
        full_range = bar["high"] - bar["low"]
        if full_range <= 0:
            return False
        atr_col = "atr_20"
        atr = data[atr_col].iloc[i] if atr_col in data.columns else full_range
        if pd.isna(atr) or atr <= 0:
            return False
        if full_range < atr * self.min_range_mult:
            return False
        if self.direction == "long":
            lower_wick = min(bar["open"], bar["close"]) - bar["low"]
            wick_ok = (lower_wick / full_range) >= self.wick_ratio
            close_ok = (bar["close"] - bar["low"]) / full_range >= self.close_position
        else:
            upper_wick = bar["high"] - max(bar["open"], bar["close"])
            wick_ok = (upper_wick / full_range) >= self.wick_ratio
            close_ok = (bar["high"] - bar["close"]) / full_range >= self.close_position
        return bool(wick_ok and close_ok)

    def mask(self, data: pd.DataFrame) -> pd.Series:
        full_range = data["high"] - data["low"]
        atr_col = "atr_20"
        atr = data[atr_col] if atr_col in data.columns else full_range
        range_ok = full_range >= atr * self.min_range_mult
        safe_range = full_range.replace(0, np.nan)
        if self.direction == "long":
            lower_wick = np.minimum(data["open"], data["close"]) - data["low"]
            wick_ok = (lower_wick / safe_range) >= self.wick_ratio
            close_ok = (data["close"] - data["low"]) / safe_range >= self.close_position
        else:
            upper_wick = data["high"] - np.maximum(data["open"], data["close"])
            wick_ok = (upper_wick / safe_range) >= self.wick_ratio
            close_ok = (data["high"] - data["close"]) / safe_range >= self.close_position
        result = (wick_ok & close_ok & range_ok).copy()
        result.iloc[:20] = False
        return result.fillna(False)


class ATRExpansionRatioFilter(BaseFilter):
    """ATR(short) / ATR(long) measures volatility transition.
    mode='expanding': passes when ratio >= threshold (vol expanding — breakout/trend).
    mode='contracting': passes when ratio <= threshold (vol contracting — MR).
    """
    name = "ATRExpansionRatioFilter"

    def __init__(self, short_period: int = 10, long_period: int = 50,
                 threshold: float = 1.10, mode: str = "expanding"):
        self.short_period = short_period
        self.long_period = long_period
        self.threshold = threshold
        self.mode = mode

    def _get_atr(self, data: pd.DataFrame, period: int) -> pd.Series:
        col = f"atr_{period}"
        if col in data.columns:
            return data[col]
        tr = data["true_range"] if "true_range" in data.columns else (data["high"] - data["low"])
        return tr.rolling(period).mean()

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.long_period:
            return False
        short_atr = self._get_atr(data, self.short_period).iloc[i]
        long_atr = self._get_atr(data, self.long_period).iloc[i]
        if pd.isna(short_atr) or pd.isna(long_atr) or long_atr == 0:
            return False
        ratio = short_atr / long_atr
        if self.mode == "expanding":
            return bool(ratio >= self.threshold)
        return bool(ratio <= self.threshold)

    def mask(self, data: pd.DataFrame) -> pd.Series:
        short_atr = self._get_atr(data, self.short_period)
        long_atr = self._get_atr(data, self.long_period)
        ratio = short_atr / long_atr.replace(0, np.nan)
        if self.mode == "expanding":
            result = (ratio >= self.threshold).copy()
        else:
            result = (ratio <= self.threshold).copy()
        warmup = self.long_period
        result.iloc[:warmup] = False
        return result.fillna(False)


class EfficiencyRatioFilter(BaseFilter):
    """Kaufman Efficiency Ratio: abs(Close-Close[N]) / Sum(abs(Close[i]-Close[i-1]), i=1..N).
    mode='above': passes when ratio >= min_ratio (trend/breakout — clean directional move).
    mode='below': passes when ratio <= min_ratio (MR — choppy/ranging).
    """
    name = "EfficiencyRatioFilter"

    def __init__(self, lookback: int = 14, min_ratio: float = 0.45, mode: str = "above"):
        self.lookback = lookback
        self.min_ratio = min_ratio
        self.mode = mode

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback:
            return False
        closes = data["close"].iloc[i - self.lookback : i + 1].values
        direction = abs(closes[-1] - closes[0])
        volatility = np.sum(np.abs(np.diff(closes)))
        ratio = direction / volatility if volatility > 0 else 0.0
        if self.mode == "above":
            return bool(ratio >= self.min_ratio)
        return bool(ratio <= self.min_ratio)

    def mask(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"].values
        n = len(close)
        ratios = np.full(n, np.nan)
        abs_diff = np.abs(np.diff(close))
        for i in range(self.lookback, n):
            direction = abs(close[i] - close[i - self.lookback])
            volatility = abs_diff[i - self.lookback : i].sum()
            ratios[i] = direction / volatility if volatility > 0 else 0.0
        if self.mode == "above":
            result = pd.Series(ratios >= self.min_ratio, index=data.index)
        else:
            result = pd.Series(ratios <= self.min_ratio, index=data.index)
        result.iloc[: self.lookback] = False
        return result.fillna(False)


class LowerLowFilter(BaseFilter):
    """Current low < previous low (breakdown structure)."""
    name = "LowerLowFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1:
            return False
        return bool(data.iloc[i]["low"] < data.iloc[i - 1]["low"])

    def mask(self, data: pd.DataFrame) -> pd.Series:
        result = (data["low"] < data["low"].shift(1)).copy()
        result.iloc[0] = False
        return result.fillna(False)
