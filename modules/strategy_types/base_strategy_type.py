from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd
from modules.engine import EngineConfig
from modules.strategies import ExitType


class BaseStrategyType(ABC):
    """
    Base interface for all strategy families.
    Every strategy type must implement these methods so the master engine 
    can generically orchestrate sweeps and refinements across any family.
    """

    name: str = "base"

    min_filters_per_combo: int = 3
    max_filters_per_combo: int = 5

    default_hold_bars: int = 3
    default_stop_distance_points: float = 10.0

    @abstractmethod
    def get_supported_exit_types(self) -> list[ExitType]:
        raise NotImplementedError

    @abstractmethod
    def get_default_exit_type(self) -> ExitType:
        raise NotImplementedError

    def get_exit_parameter_grid_for_combo(
        self,
        promoted_combo_classes: list[type],
        timeframe: str = "60m",
    ) -> dict[str, list]:
        return {"exit_type": [self.get_default_exit_type()]}

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
        exit_type: ExitType | str | None = None,
        profit_target_atr: float | None = None,
        trailing_stop_atr: float | None = None,
        signal_exit_reference: str | None = None,
    ):
        raise NotImplementedError

    @abstractmethod
    def get_active_refinement_grid_for_combo(
        self,
        promoted_combo_classes: list[type],
    ) -> dict[str, list]:
        raise NotImplementedError

    @abstractmethod
    def get_refinement_grid_for_candidate(
        self, 
        candidate_row: dict[str, Any]
    ) -> dict[str, list]:
        raise NotImplementedError

    @abstractmethod
    def get_trade_filter_thresholds(self) -> dict[str, float]:
        raise NotImplementedError

    @abstractmethod
    def get_trade_filter_config(self) -> dict[str, float]:
        raise NotImplementedError

    @abstractmethod
    def get_promotion_thresholds(self) -> dict[str, float | bool]:
        raise NotImplementedError

    @abstractmethod
    def get_promotion_gate_config(self) -> dict[str, float | bool]:
        raise NotImplementedError

    @abstractmethod
    def get_required_sma_lengths(self, timeframe: str = "60m") -> list[int]:
        raise NotImplementedError

    @abstractmethod
    def get_required_avg_range_lookbacks(self, timeframe: str = "60m") -> list[int]:
        raise NotImplementedError

    @abstractmethod
    def get_required_momentum_lookbacks(self, timeframe: str = "60m") -> list[int]:
        raise NotImplementedError

    @abstractmethod
    def run_family_filter_combination_sweep(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        max_workers: int = 10,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def run_top_combo_refinement(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        candidate_row: dict[str, Any],
        output_dir: str | Path = "Outputs",
        max_workers: int = 10,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> pd.DataFrame:
        raise NotImplementedError
