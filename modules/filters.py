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
