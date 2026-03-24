from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd

from modules.filter_combinator import build_filter_combo_name
from modules.filters import (
    BaseFilter,
    MomentumFilter,
    PullbackFilter,
    RecoveryTriggerFilter,
    TrendDirectionFilter,
    VolatilityFilter,
)


class ExitType(str, Enum):
    TIME_STOP = "time_stop"
    TRAILING_STOP = "trailing_stop"
    PROFIT_TARGET = "profit_target"
    SIGNAL_EXIT = "signal_exit"


@dataclass(frozen=True)
class ExitConfig:
    exit_type: ExitType = ExitType.TIME_STOP
    hold_bars: int = 3
    stop_distance_points: float = 10.0
    profit_target_atr: float | None = None
    trailing_stop_atr: float | None = None
    signal_exit_reference: str | None = None


def normalize_exit_type(value: ExitType | str | None) -> ExitType:
    if isinstance(value, ExitType):
        return value
    if value is None:
        return ExitType.TIME_STOP
    return ExitType(str(value).strip().lower())


def build_exit_config(
    *,
    exit_config: ExitConfig | None = None,
    exit_type: ExitType | str | None = None,
    hold_bars: int | None = None,
    stop_distance_points: float | None = None,
    profit_target_atr: float | None = None,
    trailing_stop_atr: float | None = None,
    signal_exit_reference: str | None = None,
    default_hold_bars: int = 3,
    default_stop_distance_points: float = 10.0,
) -> ExitConfig:
    if exit_config is not None:
        return ExitConfig(
            exit_type=normalize_exit_type(exit_config.exit_type),
            hold_bars=int(exit_config.hold_bars),
            stop_distance_points=float(exit_config.stop_distance_points),
            profit_target_atr=exit_config.profit_target_atr,
            trailing_stop_atr=exit_config.trailing_stop_atr,
            signal_exit_reference=exit_config.signal_exit_reference,
        )

    return ExitConfig(
        exit_type=normalize_exit_type(exit_type),
        hold_bars=int(default_hold_bars if hold_bars is None else hold_bars),
        stop_distance_points=float(
            default_stop_distance_points
            if stop_distance_points is None
            else stop_distance_points
        ),
        profit_target_atr=(
            None if profit_target_atr is None else float(profit_target_atr)
        ),
        trailing_stop_atr=(
            None if trailing_stop_atr is None else float(trailing_stop_atr)
        ),
        signal_exit_reference=signal_exit_reference,
    )


class BaseStrategy(ABC):
    """
    Base class for all strategies.
    """

    name: str = "BaseStrategy"
    direction: str = "LONG_ONLY"
    hold_bars: int = 3
    stop_distance_points: float = 10.0
    exit_config: ExitConfig = ExitConfig()

    def _apply_exit_config(
        self,
        *,
        exit_config: ExitConfig | None = None,
        exit_type: ExitType | str | None = None,
        hold_bars: int | None = None,
        stop_distance_points: float | None = None,
        profit_target_atr: float | None = None,
        trailing_stop_atr: float | None = None,
        signal_exit_reference: str | None = None,
    ) -> ExitConfig:
        resolved = build_exit_config(
            exit_config=exit_config,
            exit_type=exit_type,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
            profit_target_atr=profit_target_atr,
            trailing_stop_atr=trailing_stop_atr,
            signal_exit_reference=signal_exit_reference,
            default_hold_bars=int(getattr(self, "hold_bars", 3)),
            default_stop_distance_points=float(getattr(self, "stop_distance_points", 10.0)),
        )
        self.exit_config = resolved
        self.hold_bars = int(resolved.hold_bars)
        self.stop_distance_points = float(resolved.stop_distance_points)
        return resolved

    @abstractmethod
    def generate_signal(self, data: pd.DataFrame, i: int) -> int:
        raise NotImplementedError


class TestStrategy(BaseStrategy):
    name = "TestStrategy"
    direction = "LONG_ONLY"
    hold_bars = 3
    stop_distance_points = 10.0

    def __init__(self, exit_config: ExitConfig | None = None):
        self._apply_exit_config(exit_config=exit_config)

    def generate_signal(self, data: pd.DataFrame, i: int) -> int:
        if i < 1:
            return 0

        current_close = data["close"].iloc[i]
        previous_close = data["close"].iloc[i - 1]

        if current_close > previous_close:
            return 1

        return 0


class FilterBasedTrendStrategy(BaseStrategy):
    """
    Fixed 5-filter trend strategy baseline.
    """

    name = "FilterBasedTrendStrategy"
    direction = "LONG_ONLY"
    hold_bars = 8
    stop_distance_points = 12.0

    def __init__(self, exit_config: ExitConfig | None = None):
        self._apply_exit_config(exit_config=exit_config)
        self.filters = [
            TrendDirectionFilter(fast_length=50, slow_length=200),
            PullbackFilter(fast_length=50),
            RecoveryTriggerFilter(fast_length=50),
            VolatilityFilter(lookback=20, min_avg_range=8.0),
            MomentumFilter(lookback=10),
        ]

    def generate_signal(self, data: pd.DataFrame, i: int) -> int:
        for filter_obj in self.filters:
            if not filter_obj.passes(data, i):
                return 0
        return 1


class CombinableFilterTrendStrategy(BaseStrategy):
    """
    Trend strategy assembled from a chosen set of filters.
    """

    direction = "LONG_ONLY"
    hold_bars = 8
    stop_distance_points = 12.0

    def __init__(
        self,
        filters: list[BaseFilter],
        hold_bars: Optional[int] = None,
        stop_distance_points: Optional[float] = None,
        exit_config: ExitConfig | None = None,
    ):
        self.filters = filters
        self._apply_exit_config(
            exit_config=exit_config,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
        )
        self.name = f"ComboTrend_{build_filter_combo_name(filters)}"

    def generate_signal(self, data: pd.DataFrame, i: int) -> int:
        for filter_obj in self.filters:
            if not filter_obj.passes(data, i):
                return 0
        return 1


class RefinedFiveFilterTrendStrategy(BaseStrategy):
    """
    Parameter-refinable version of the current best 5-filter trend stack.
    """

    direction = "LONG_ONLY"

    def __init__(
        self,
        hold_bars: int = 8,
        stop_distance_points: float = 12.0,
        fast_length: int = 50,
        slow_length: int = 200,
        volatility_lookback: int = 20,
        min_avg_range: float = 8.0,
        momentum_lookback: int = 10,
        exit_config: ExitConfig | None = None,
    ):
        self.hold_bars = hold_bars
        self.stop_distance_points = stop_distance_points
        self._apply_exit_config(
            exit_config=exit_config,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
        )
        self.fast_length = fast_length
        self.slow_length = slow_length
        self.volatility_lookback = volatility_lookback
        self.min_avg_range = min_avg_range
        self.momentum_lookback = momentum_lookback

        self.filters = [
            TrendDirectionFilter(fast_length=self.fast_length, slow_length=self.slow_length),
            PullbackFilter(fast_length=self.fast_length),
            RecoveryTriggerFilter(fast_length=self.fast_length),
            VolatilityFilter(
                lookback=self.volatility_lookback,
                min_avg_range=self.min_avg_range,
            ),
            MomentumFilter(lookback=self.momentum_lookback),
        ]

        self.name = (
            "RefinedFiveFilterTrendStrategy"
            f"_HB{self.hold_bars}"
            f"_STOP{self.stop_distance_points}"
            f"_RANGE{self.min_avg_range}"
            f"_MOM{self.momentum_lookback}"
        )

    def generate_signal(self, data: pd.DataFrame, i: int) -> int:
        for filter_obj in self.filters:
            if not filter_obj.passes(data, i):
                return 0
        return 1
