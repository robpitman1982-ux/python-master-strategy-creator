from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from modules.filters import BaseFilter
from modules.strategies import BaseStrategy


class BaseStrategyType(ABC):
    """
    Base abstraction for a strategy family.

    A strategy type defines:
    - what features must be precomputed
    - which filter classes belong to the family
    - how filter objects are instantiated
    - how combo strategies are built
    - how refinement strategies are built
    - default refinement grid
    - minimum trade thresholds
    """

    name: str = "base"

    @abstractmethod
    def get_feature_requirements(self) -> dict[str, list[int]]:
        """
        Returns the precompute requirements for this strategy family.

        Example:
        {
            "sma_lengths": [50, 200],
            "avg_range_lookbacks": [20],
            "momentum_lookbacks": [8, 10, 11, 12, 13, 14],
        }
        """
        raise NotImplementedError

    @abstractmethod
    def get_filter_classes(self) -> list[type[BaseFilter]]:
        """
        Returns the available filter classes for this strategy family.
        """
        raise NotImplementedError

    @abstractmethod
    def build_filter_objects_from_classes(
        self,
        combo_classes: list[type[BaseFilter]],
    ) -> list[BaseFilter]:
        """
        Instantiates filter objects from filter classes.
        """
        raise NotImplementedError

    @abstractmethod
    def create_combo_strategy(
        self,
        combo_classes: list[type[BaseFilter]],
        hold_bars: int,
        stop_distance_points: float,
    ) -> BaseStrategy:
        """
        Builds a combinable strategy instance from a chosen filter stack.
        """
        raise NotImplementedError

    @abstractmethod
    def create_refinement_strategy(
        self,
        hold_bars: int,
        stop_distance_points: float,
        **kwargs: Any,
    ) -> BaseStrategy:
        """
        Builds the refinable strategy instance for narrow parameter searches.
        """
        raise NotImplementedError

    @abstractmethod
    def get_refinement_grid(self) -> dict[str, list[Any]]:
        """
        Returns the default refinement grid for this strategy family.
        """
        raise NotImplementedError

    def get_trade_filter_thresholds(self) -> dict[str, float]:
        """
        Default trade-frequency filters from the master prompt / current engine.
        Override later per strategy family if needed.
        """
        return {
            "min_trades": 150,
            "min_trades_per_year": 8.0,
        }

    def get_combo_sweep_defaults(self) -> dict[str, float]:
        """
        Default combo-sweep execution parameters.
        """
        return {
            "hold_bars": 8,
            "stop_distance_points": 12.0,
        }