"""
Trend Strategy Type
"""

from __future__ import annotations

from typing import Any

from .base_strategy_type import BaseStrategyType


class TrendStrategyType(BaseStrategyType):

    name = "trend"

    # ---------------------------------------------------
    # REQUIRED FEATURE LOOKBACKS
    # ---------------------------------------------------

    def get_required_sma_lengths(self) -> list[int]:
        return [20, 50, 100, 200]

    def get_required_avg_range_lookbacks(self) -> list[int]:
        return [14]

    def get_required_momentum_lookbacks(self) -> list[int]:
        return [14]

    # ---------------------------------------------------
    # SANITY CHECK STRATEGY
    # ---------------------------------------------------

    def build_default_strategy(self):

        def strategy(data, params):
            return None

        return strategy

    def build_default_sanity_filters(self) -> dict[str, Any]:
        return {}

    # ---------------------------------------------------
    # COMBINATION SWEEP
    # ---------------------------------------------------

    def build_combination_strategy(self, filters: dict[str, Any]):

        def strategy(data, params):
            return None

        return strategy

    # ---------------------------------------------------
    # CANDIDATE STRATEGY
    # ---------------------------------------------------

    def build_candidate_specific_strategy(self, candidate_row: dict[str, Any]):

        def strategy(data, params):
            return None

        return strategy

    # ---------------------------------------------------
    # PROMOTION GATE
    # ---------------------------------------------------

    def get_promotion_thresholds(self) -> dict[str, Any]:

        return {
            "min_profit_factor": 1.05,
            "min_average_trade": 0,
            "require_positive_net_pnl": True,
            "min_trades": 100,
            "min_trades_per_year": 10,
        }

    # ---------------------------------------------------
    # REFINEMENT
    # ---------------------------------------------------

    def build_candidate_specific_refinement_factory(self, candidate_row: dict[str, Any]):
        return None

    def get_refinement_grid_for_candidate(self, candidate_row: dict[str, Any]):
        return {}