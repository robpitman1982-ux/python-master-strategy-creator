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


# ============================================================
# Trend-family filters
# ============================================================

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

        return bool(fast_sma > slow_sma)


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

        return bool(previous_close <= prev_fast_sma)


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

        return bool(current_close > fast_sma)


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

        return bool(avg_range >= self.min_avg_range)


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
            return bool(mom_value > 0)

        close_series = data["close"]
        current_close = close_series.iloc[i]
        past_close = close_series.iloc[i - self.lookback]

        return bool(current_close > past_close)


# ============================================================
# Breakout-family filters
# ============================================================

class CompressionFilter(BaseFilter):
    """
    Recent average range must be below a defined compression threshold.
    """

    name = "CompressionFilter"

    def __init__(self, lookback: int = 20, max_avg_range: float = 6.0):
        self.lookback = lookback
        self.max_avg_range = max_avg_range

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

        return bool(avg_range <= self.max_avg_range)


class RangeBreakoutFilter(BaseFilter):
    """
    Current close must break above the highest high of the prior N bars.
    """

    name = "RangeBreakoutFilter"

    def __init__(self, lookback: int = 20):
        self.lookback = lookback

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback:
            return False

        prior_window = data.iloc[i - self.lookback : i]
        if prior_window.empty:
            return False

        prior_high = prior_window["high"].max()
        current_close = data.iloc[i]["close"]

        if pd.isna(prior_high) or pd.isna(current_close):
            return False

        return bool(current_close > prior_high)


class ExpansionBarFilter(BaseFilter):
    """
    Current bar range must exceed recent average range by a multiplier.
    """

    name = "ExpansionBarFilter"

    def __init__(self, lookback: int = 20, expansion_multiplier: float = 1.5):
        self.lookback = lookback
        self.expansion_multiplier = expansion_multiplier

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback:
            return False

        current_bar_range = data.iloc[i]["high"] - data.iloc[i]["low"]
        avg_range_col = f"avg_range_{self.lookback}"

        if avg_range_col in data.columns:
            avg_range = data.iloc[i][avg_range_col]
        else:
            window = data.iloc[i - self.lookback + 1 : i + 1]
            avg_range = (window["high"] - window["low"]).mean()

        if pd.isna(current_bar_range) or pd.isna(avg_range) or avg_range <= 0:
            return False

        return bool(current_bar_range >= avg_range * self.expansion_multiplier)


class BreakoutRetestFilter(BaseFilter):
    """
    Current close must be above the prior breakout level by at least a buffer.
    """

    name = "BreakoutRetestFilter"

    def __init__(self, lookback: int = 20, breakout_buffer_points: float = 0.0):
        self.lookback = lookback
        self.breakout_buffer_points = breakout_buffer_points

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback:
            return False

        prior_window = data.iloc[i - self.lookback : i]
        if prior_window.empty:
            return False

        prior_high = prior_window["high"].max()
        current_close = data.iloc[i]["close"]

        if pd.isna(prior_high) or pd.isna(current_close):
            return False

        breakout_level = prior_high + self.breakout_buffer_points
        return bool(current_close > breakout_level)


class BreakoutTrendFilter(BaseFilter):
    """
    Optional trend-alignment filter for breakout systems.
    """

    name = "BreakoutTrendFilter"

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

        return bool(fast_sma > slow_sma)


class BreakoutCloseStrengthFilter(BaseFilter):
    """
    Require the close to finish near the high of the breakout bar.
    """

    name = "BreakoutCloseStrengthFilter"

    def __init__(self, close_position_threshold: float = 0.70):
        self.close_position_threshold = close_position_threshold

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        current_high = data.iloc[i]["high"]
        current_low = data.iloc[i]["low"]
        current_close = data.iloc[i]["close"]

        if pd.isna(current_high) or pd.isna(current_low) or pd.isna(current_close):
            return False

        bar_range = current_high - current_low
        if bar_range <= 0:
            return False

        close_position = (current_close - current_low) / bar_range
        return bool(close_position >= self.close_position_threshold)


class PriorRangePositionFilter(BaseFilter):
    """
    Require the prior close to already be positioned near the top of the
    recent range before the breakout.
    """

    name = "PriorRangePositionFilter"

    def __init__(self, lookback: int = 20, min_position_in_range: float = 0.65):
        self.lookback = lookback
        self.min_position_in_range = min_position_in_range

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback or i < 1:
            return False

        prior_window = data.iloc[i - self.lookback : i]
        if prior_window.empty:
            return False

        range_low = prior_window["low"].min()
        range_high = prior_window["high"].max()
        prior_close = data.iloc[i - 1]["close"]

        if pd.isna(range_low) or pd.isna(range_high) or pd.isna(prior_close):
            return False

        full_range = range_high - range_low
        if full_range <= 0:
            return False

        position_in_range = (prior_close - range_low) / full_range
        return bool(position_in_range >= self.min_position_in_range)


class MinimumBreakDistanceFilter(BaseFilter):
    """
    Require the breakout to clear the prior high by a minimum distance.
    """

    name = "MinimumBreakDistanceFilter"

    def __init__(self, lookback: int = 20, min_break_distance_points: float = 1.0):
        self.lookback = lookback
        self.min_break_distance_points = min_break_distance_points

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback:
            return False

        prior_window = data.iloc[i - self.lookback : i]
        if prior_window.empty:
            return False

        prior_high = prior_window["high"].max()
        current_close = data.iloc[i]["close"]

        if pd.isna(prior_high) or pd.isna(current_close):
            return False

        break_distance = current_close - prior_high
        return bool(break_distance >= self.min_break_distance_points)


# ============================================================
# Mean-reversion-family filters
# ============================================================

class BelowFastSMAFilter(BaseFilter):
    """
    Current close must be below the fast SMA.

    Used as a simple 'price stretched below mean' condition for long-only
    mean reversion research.
    """

    name = "BelowFastSMAFilter"

    def __init__(self, fast_length: int = 20):
        self.fast_length = fast_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length:
            return False

        fast_col = f"sma_{self.fast_length}"

        if fast_col in data.columns:
            fast_sma = data.iloc[i][fast_col]
        else:
            close_series = data["close"]
            fast_sma = close_series.iloc[i - self.fast_length + 1 : i + 1].mean()

        current_close = data.iloc[i]["close"]

        if pd.isna(fast_sma) or pd.isna(current_close):
            return False

        return bool(current_close < fast_sma)


class DistanceBelowSMAFilter(BaseFilter):
    """
    Current close must be below the fast SMA by at least a minimum distance
    measured in points.

    This helps require a meaningful stretch rather than a tiny dip.
    """

    name = "DistanceBelowSMAFilter"

    def __init__(self, fast_length: int = 20, min_distance_points: float = 4.0):
        self.fast_length = fast_length
        self.min_distance_points = min_distance_points

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length:
            return False

        fast_col = f"sma_{self.fast_length}"

        if fast_col in data.columns:
            fast_sma = data.iloc[i][fast_col]
        else:
            close_series = data["close"]
            fast_sma = close_series.iloc[i - self.fast_length + 1 : i + 1].mean()

        current_close = data.iloc[i]["close"]

        if pd.isna(fast_sma) or pd.isna(current_close):
            return False

        distance_below = fast_sma - current_close
        return bool(distance_below >= self.min_distance_points)


class DownCloseFilter(BaseFilter):
    """
    Current close must be below previous close.

    This helps identify short-term downward pressure / weakness before
    mean reversion attempts.
    """

    name = "DownCloseFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1:
            return False

        current_close = data.iloc[i]["close"]
        previous_close = data.iloc[i - 1]["close"]

        if pd.isna(current_close) or pd.isna(previous_close):
            return False

        return bool(current_close < previous_close)


class TwoBarDownFilter(BaseFilter):
    """
    Require two consecutive down closes.

    This is a slightly stronger short-term exhaustion / weakness filter.
    """

    name = "TwoBarDownFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 2:
            return False

        close_0 = data.iloc[i]["close"]
        close_1 = data.iloc[i - 1]["close"]
        close_2 = data.iloc[i - 2]["close"]

        if pd.isna(close_0) or pd.isna(close_1) or pd.isna(close_2):
            return False

        return bool(close_0 < close_1 and close_1 < close_2)


class ReversalUpBarFilter(BaseFilter):
    """
    Current close must be above the current open.

    Used as a simple reversal / snapback trigger for long-only
    mean reversion research.
    """

    name = "ReversalUpBarFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        current_open = data.iloc[i]["open"]
        current_close = data.iloc[i]["close"]

        if pd.isna(current_open) or pd.isna(current_close):
            return False

        return bool(current_close > current_open)


class LowVolatilityRegimeFilter(BaseFilter):
    """
    Average bar range must be below a maximum threshold.

    This can help identify calmer / more mean-reverting environments
    instead of high-volatility expansion environments.
    """

    name = "LowVolatilityRegimeFilter"

    def __init__(self, lookback: int = 20, max_avg_range: float = 12.0):
        self.lookback = lookback
        self.max_avg_range = max_avg_range

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

        return bool(avg_range <= self.max_avg_range)


class AboveLongTermSMAFilter(BaseFilter):
    """
    Current close must still be above a longer-term SMA.

    This is useful for 'buy the dip in broader uptrend' mean reversion,
    rather than catching falling knives in structural downtrends.
    """

    name = "AboveLongTermSMAFilter"

    def __init__(self, slow_length: int = 200):
        self.slow_length = slow_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.slow_length:
            return False

        slow_col = f"sma_{self.slow_length}"

        if slow_col in data.columns:
            slow_sma = data.iloc[i][slow_col]
        else:
            close_series = data["close"]
            slow_sma = close_series.iloc[i - self.slow_length + 1 : i + 1].mean()

        current_close = data.iloc[i]["close"]

        if pd.isna(slow_sma) or pd.isna(current_close):
            return False

        return bool(current_close > slow_sma)