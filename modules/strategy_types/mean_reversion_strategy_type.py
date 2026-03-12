from __future__ import annotations

import pandas as pd

from modules.filters import BaseFilter
from modules.strategies import BaseStrategy
from modules.strategy_types.base_strategy_type import BaseStrategyType


class BelowFastSMAFilter(BaseFilter):
    name = "BelowFastSMAFilter"

    def __init__(self, fast_length: int = 20):
        self.fast_length = fast_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length:
            return False

        sma_col = f"sma_{self.fast_length}"
        if sma_col not in data.columns:
            return False

        close_price = data.iloc[i]["close"]
        fast_sma = data.iloc[i][sma_col]

        if pd.isna(close_price) or pd.isna(fast_sma):
            return False

        return close_price < fast_sma


class DistanceBelowSMAFilter(BaseFilter):
    name = "DistanceBelowSMAFilter"

    def __init__(self, fast_length: int = 20, min_distance_points: float = 4.0):
        self.fast_length = fast_length
        self.min_distance_points = min_distance_points

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.fast_length:
            return False

        sma_col = f"sma_{self.fast_length}"
        if sma_col not in data.columns:
            return False

        close_price = data.iloc[i]["close"]
        fast_sma = data.iloc[i][sma_col]

        if pd.isna(close_price) or pd.isna(fast_sma):
            return False

        return (fast_sma - close_price) >= self.min_distance_points


class DownCloseFilter(BaseFilter):
    name = "DownCloseFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1:
            return False

        current_close = data.iloc[i]["close"]
        previous_close = data.iloc[i - 1]["close"]

        if pd.isna(current_close) or pd.isna(previous_close):
            return False

        return current_close < previous_close


class TwoBarDownFilter(BaseFilter):
    name = "TwoBarDownFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 2:
            return False

        c0 = data.iloc[i]["close"]
        c1 = data.iloc[i - 1]["close"]
        c2 = data.iloc[i - 2]["close"]

        if pd.isna(c0) or pd.isna(c1) or pd.isna(c2):
            return False

        return c0 < c1 and c1 < c2


class ReversalUpBarFilter(BaseFilter):
    name = "ReversalUpBarFilter"

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < 1:
            return False

        current_close = data.iloc[i]["close"]
        current_open = data.iloc[i]["open"]
        previous_close = data.iloc[i - 1]["close"]

        if pd.isna(current_close) or pd.isna(current_open) or pd.isna(previous_close):
            return False

        return current_close > current_open and current_close > previous_close


class LowVolatilityRegimeFilter(BaseFilter):
    name = "LowVolatilityRegimeFilter"

    def __init__(self, lookback: int = 20, max_avg_range: float = 14.0):
        self.lookback = lookback
        self.max_avg_range = max_avg_range

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.lookback:
            return False

        avg_range_col = f"avg_range_{self.lookback}"
        if avg_range_col not in data.columns:
            return False

        avg_range = data.iloc[i][avg_range_col]
        if pd.isna(avg_range):
            return False

        return avg_range <= self.max_avg_range


class AboveLongTermSMAFilter(BaseFilter):
    name = "AboveLongTermSMAFilter"

    def __init__(self, slow_length: int = 200):
        self.slow_length = slow_length

    def passes(self, data: pd.DataFrame, i: int) -> bool:
        if i < self.slow_length:
            return False

        sma_col = f"sma_{self.slow_length}"
        if sma_col not in data.columns:
            return False

        close_price = data.iloc[i]["close"]
        slow_sma = data.iloc[i][sma_col]

        if pd.isna(close_price) or pd.isna(slow_sma):
            return False

        return close_price > slow_sma


class CombinableMeanReversionStrategy(BaseStrategy):
    direction = "LONG_ONLY"

    def __init__(
        self,
        filters: list[BaseFilter],
        hold_bars: int = 4,
        stop_distance_points: float = 8.0,
    ):
        self.filters = filters
        self.hold_bars = hold_bars
        self.stop_distance_points = stop_distance_points

        filter_names = []
        for f in filters:
            short_name = f.name.replace("Filter", "")
            filter_names.append(short_name)

        self.name = f"ComboMeanReversion_{'_'.join(filter_names)}"

    def generate_signal(self, data: pd.DataFrame, i: int) -> int:
        for filter_obj in self.filters:
            if not filter_obj.passes(data, i):
                return 0
        return 1


class MeanReversionStrategyType(BaseStrategyType):
    name = "mean_reversion"

    min_filters_per_combo = 3
    max_filters_per_combo = 6

    default_hold_bars = 4
    default_stop_distance_points = 8.0

    def get_filter_classes(self) -> list[type]:
        return [
            BelowFastSMAFilter,
            DistanceBelowSMAFilter,
            DownCloseFilter,
            TwoBarDownFilter,
            ReversalUpBarFilter,
            LowVolatilityRegimeFilter,
            AboveLongTermSMAFilter,
        ]

    def build_filter_objects_from_classes(self, combo_classes: list[type]) -> list:
        filter_objects = []

        for cls in combo_classes:
            if cls is BelowFastSMAFilter:
                filter_objects.append(cls(fast_length=20))
            elif cls is DistanceBelowSMAFilter:
                filter_objects.append(cls(fast_length=20, min_distance_points=4.0))
            elif cls is DownCloseFilter:
                filter_objects.append(cls())
            elif cls is TwoBarDownFilter:
                filter_objects.append(cls())
            elif cls is ReversalUpBarFilter:
                filter_objects.append(cls())
            elif cls is LowVolatilityRegimeFilter:
                filter_objects.append(cls(lookback=20, max_avg_range=14.0))
            elif cls is AboveLongTermSMAFilter:
                filter_objects.append(cls(slow_length=200))
            else:
                filter_objects.append(cls())

        return filter_objects

    def build_combinable_strategy(
        self,
        filters: list,
        hold_bars: int,
        stop_distance_points: float,
    ):
        return CombinableMeanReversionStrategy(
            filters=filters,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
        )

    def build_default_sanity_filters(self) -> list:
        return [
            BelowFastSMAFilter(fast_length=20),
            DistanceBelowSMAFilter(fast_length=20, min_distance_points=4.0),
            DownCloseFilter(),
            TwoBarDownFilter(),
            ReversalUpBarFilter(),
            LowVolatilityRegimeFilter(lookback=20, max_avg_range=14.0),
            AboveLongTermSMAFilter(slow_length=200),
        ]

    def build_candidate_specific_strategy(
        self,
        promoted_combo_classes: list[type],
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
    ):
        filter_objects = []

        for cls in promoted_combo_classes:
            if cls is BelowFastSMAFilter:
                filter_objects.append(cls(fast_length=20))
            elif cls is DistanceBelowSMAFilter:
                filter_objects.append(cls(fast_length=20, min_distance_points=4.0))
            elif cls is DownCloseFilter:
                filter_objects.append(cls())
            elif cls is TwoBarDownFilter:
                filter_objects.append(cls())
            elif cls is ReversalUpBarFilter:
                filter_objects.append(cls())
            elif cls is LowVolatilityRegimeFilter:
                filter_objects.append(cls(lookback=20, max_avg_range=min_avg_range))
            elif cls is AboveLongTermSMAFilter:
                filter_objects.append(cls(slow_length=200))
            else:
                filter_objects.append(cls())

        return CombinableMeanReversionStrategy(
            filters=filter_objects,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
        )

    def get_active_refinement_grid_for_combo(
        self,
        promoted_combo_classes: list[type],
    ) -> dict[str, list]:
        grid: dict[str, list] = {
            "hold_bars": [2, 3, 4, 5, 6],
            "stop_distance_points": [6.0, 8.0, 10.0, 12.0],
        }

        if LowVolatilityRegimeFilter in promoted_combo_classes:
            grid["min_avg_range"] = [8.0, 10.0, 12.0, 14.0]

        return grid

    def get_trade_filter_thresholds(self) -> dict[str, float]:
        return {
            "min_trades": 150,
            "min_trades_per_year": 8.0,
        }

    def get_promotion_thresholds(self) -> dict[str, float | bool]:
        return {
            "min_profit_factor": 1.00,
            "min_average_trade": 0.0,
            "require_positive_net_pnl": False,
        }

    def get_required_sma_lengths(self) -> list[int]:
        return [20, 200]

    def get_required_avg_range_lookbacks(self) -> list[int]:
        return [20]

    def get_required_momentum_lookbacks(self) -> list[int]:
        return []