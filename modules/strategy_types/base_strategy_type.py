from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseStrategyType(ABC):
    """
    Base interface for all strategy families.
    """

    name: str = "base"

    @abstractmethod
    def get_feature_requirements(self) -> dict[str, list[int]]:
        raise NotImplementedError

    @abstractmethod
    def get_filter_classes(self) -> list[type]:
        raise NotImplementedError

    @abstractmethod
    def build_filter_objects_from_classes(self, combo_classes: list[type]) -> list:
        raise NotImplementedError

    @abstractmethod
    def create_combo_strategy(
        self,
        combo_classes: list[type],
        hold_bars: int,
        stop_distance_points: float,
    ):
        raise NotImplementedError

    @abstractmethod
    def create_refinement_strategy(
        self,
        hold_bars: int,
        stop_distance_points: float,
        **kwargs: Any,
    ):
        raise NotImplementedError

    @abstractmethod
    def create_refinement_strategy_from_combo(
        self,
        combo_classes: list[type],
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
    ):
        raise NotImplementedError

    @abstractmethod
    def get_refinement_grid(self) -> dict[str, list[Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_trade_filter_thresholds(self) -> dict[str, float]:
        raise NotImplementedError

    @abstractmethod
    def get_combo_sweep_defaults(self) -> dict[str, float]:
        raise NotImplementedError

    @abstractmethod
    def get_active_refinement_grid_for_combo(
        self,
        combo_classes: list[type],
    ) -> dict[str, list[Any]]:
        """
        Return only the refinement dimensions that matter for this promoted combo.
        Must always include:
            - hold_bars
            - stop_distance_points
        """
        raise NotImplementedError