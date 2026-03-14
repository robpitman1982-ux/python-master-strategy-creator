from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


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


class MomentumFilter(BaseFilter):
    name = "MomentumFilter"

    def __init__(self, lookback: int = 10):
        self.lookback = lookback

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback:
            return False
        return bool(data.iloc[i]["close"] > data.iloc[i - self.lookback]["close"])


class UpCloseFilter(BaseFilter):
    name = "UpCloseFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1:
            return False
        return bool(data.iloc[i]["close"] > data.iloc[i - 1]["close"])


class TwoBarUpFilter(BaseFilter):
    name = "TwoBarUpFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 2:
            return False
        return bool(
            data.iloc[i]["close"] > data.iloc[i - 1]["close"]
            and data.iloc[i - 1]["close"] > data.iloc[i - 2]["close"]
        )


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


class HigherLowFilter(BaseFilter):
    name = "HigherLowFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 2:
            return False
        return bool(data.iloc[i]["low"] > data.iloc[i - 1]["low"])


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


class RangeBreakoutFilter(BaseFilter):
    name = "RangeBreakoutFilter"

    def __init__(self, lookback: int = 20):
        self.lookback = lookback

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback:
            return False

        prior_high = data.iloc[i - self.lookback : i]["high"].max()
        return bool(data.iloc[i]["close"] > prior_high)


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


class DownCloseFilter(BaseFilter):
    name = "DownCloseFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1:
            return False
        return bool(data.iloc[i]["close"] < data.iloc[i - 1]["close"])


class TwoBarDownFilter(BaseFilter):
    name = "TwoBarDownFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 2:
            return False
        return bool(
            data.iloc[i]["close"] < data.iloc[i - 1]["close"]
            and data.iloc[i - 1]["close"] < data.iloc[i - 2]["close"]
        )


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
        if i < self.lookback * 2:
            return False

        atr_col = f"atr_{self.lookback}"
        current_atr = data.iloc[i][atr_col] if atr_col in data.columns else 10.0
        long_term_atr = data["true_range"].iloc[i - (self.lookback * 2) : i].mean()

        return bool(current_atr <= (long_term_atr * self.max_atr_mult))


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