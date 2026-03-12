from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseStrategyType(ABC):
    """
    Base interface for all strategy families.
    Every strategy type must implement the methods the master engine expects.
    """

    name: str = "base"

    min_filters_per_combo: int = 3
    max_filters_per_combo: int = 5

    default_hold_bars: int = 3
    default_stop_distance_points: float = 10.0

    @abstractmethod
    def get_filter_classes(self) -> list[type]:
        raise NotImplementedError

    @abstractmethod
    def build_filter_objects_from_classes(self, combo_classes: list[type]) -> list:
        raise NotImplementedError

    @abstractmethod
    def build_combinable_strategy(
        self,
        filters: list,
        hold_bars: int,
        stop_distance_points: float,
    ):
        raise NotImplementedError

    @abstractmethod
    def build_default_sanity_filters(self) -> list:
        raise NotImplementedError

    @abstractmethod
    def build_candidate_specific_strategy(
        self,
        promoted_combo_classes: list[type],
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
    ):
        raise NotImplementedError

    @abstractmethod
    def get_active_refinement_grid_for_combo(
        self,
        promoted_combo_classes: list[type],
    ) -> dict[str, list]:
        raise NotImplementedError

    @abstractmethod
    def get_trade_filter_thresholds(self) -> dict[str, float]:
        raise NotImplementedError

    @abstractmethod
    def get_promotion_thresholds(self) -> dict[str, float | bool]:
        raise NotImplementedError

    @abstractmethod
    def get_required_sma_lengths(self) -> list[int]:
        raise NotImplementedError

    @abstractmethod
    def get_required_avg_range_lookbacks(self) -> list[int]:
        raise NotImplementedError

    @abstractmethod
    def get_required_momentum_lookbacks(self) -> list[int]:
        raise NotImplementedError