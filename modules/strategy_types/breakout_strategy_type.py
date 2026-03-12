from __future__ import annotations

import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Iterable

import pandas as pd

from modules.engine import MasterStrategyEngine, EngineConfig
from modules.filters import (
    CompressionFilter,
    PriorRangePositionFilter,
    RangeBreakoutFilter,
    MinimumBreakDistanceFilter,
    ExpansionBarFilter,
    BreakoutCloseStrengthFilter,
    BreakoutTrendFilter,
)
from modules.strategy_types.base_strategy_type import BaseStrategyType


# =============================================================================
# INLINE BREAKOUT STRATEGY
# =============================================================================
class _InlineBreakoutStrategy:
    """
    Small self-contained breakout strategy so this strategy type does not depend
    on missing breakout classes inside modules.strategies.
    """

    name = "FilterBasedBreakoutStrategy"

    def __init__(
        self,
        filters: list[Any],
        hold_bars: int = 10,
        stop_distance_points: float = 14.0,
    ) -> None:
        self.filters = filters
        self.hold_bars = hold_bars
        self.stop_distance_points = stop_distance_points

    def clone(self) -> "_InlineBreakoutStrategy":
        return _InlineBreakoutStrategy(
            filters=self.filters,
            hold_bars=self.hold_bars,
            stop_distance_points=self.stop_distance_points,
        )


# =============================================================================
# BREAKOUT STRATEGY TYPE
# =============================================================================
class BreakoutStrategyType(BaseStrategyType):
    name = "breakout"
    strategy_type_name = "breakout"

    # -------------------------------------------------------------------------
    # Required feature lookbacks
    # -------------------------------------------------------------------------
    def get_required_sma_lengths(self) -> list[int]:
        return [50, 200]

    def get_required_avg_range_lookbacks(self) -> list[int]:
        return [20]

    def get_required_momentum_lookbacks(self) -> list[int]:
        return []

    # -------------------------------------------------------------------------
    # Default / sanity setup
    # -------------------------------------------------------------------------
    def build_default_sanity_filters(self) -> list[Any]:
        return [
            CompressionFilter(lookback=20, compression_threshold=0.85),
            PriorRangePositionFilter(lookback=20, min_position_in_range=0.60),
            RangeBreakoutFilter(lookback=20),
            MinimumBreakDistanceFilter(min_break_distance_points=1.0),
            ExpansionBarFilter(lookback=20, min_expansion_multiple=1.20),
            BreakoutCloseStrengthFilter(min_close_strength=0.60),
            BreakoutTrendFilter(sma_column="sma_50"),
        ]

    def build_default_strategy(self) -> _InlineBreakoutStrategy:
        return _InlineBreakoutStrategy(
            filters=self.build_default_sanity_filters(),
            hold_bars=10,
            stop_distance_points=14.0,
        )

    def build_sanity_check_strategy(self) -> _InlineBreakoutStrategy:
        return self.build_default_strategy()

    # -------------------------------------------------------------------------
    # Filter library
    # -------------------------------------------------------------------------
    def get_filter_classes(self) -> list[type]:
        return [
            CompressionFilter,
            PriorRangePositionFilter,
            RangeBreakoutFilter,
            MinimumBreakDistanceFilter,
            ExpansionBarFilter,
            BreakoutCloseStrengthFilter,
            BreakoutTrendFilter,
        ]

    def build_filter_objects_from_classes(self, filter_classes: list[type]) -> list[Any]:
        filters: list[Any] = []

        for cls in filter_classes:
            if cls is CompressionFilter:
                filters.append(CompressionFilter(lookback=20, compression_threshold=0.85))
            elif cls is PriorRangePositionFilter:
                filters.append(PriorRangePositionFilter(lookback=20, min_position_in_range=0.60))
            elif cls is RangeBreakoutFilter:
                filters.append(RangeBreakoutFilter(lookback=20))
            elif cls is MinimumBreakDistanceFilter:
                filters.append(MinimumBreakDistanceFilter(min_break_distance_points=1.0))
            elif cls is ExpansionBarFilter:
                filters.append(ExpansionBarFilter(lookback=20, min_expansion_multiple=1.20))
            elif cls is BreakoutCloseStrengthFilter:
                filters.append(BreakoutCloseStrengthFilter(min_close_strength=0.60))
            elif cls is BreakoutTrendFilter:
                filters.append(BreakoutTrendFilter(sma_column="sma_50"))
            else:
                raise ValueError(f"Unsupported breakout filter class: {cls}")

        return filters

    def build_combinable_strategy(self, filters: list[Any]) -> _InlineBreakoutStrategy:
        return _InlineBreakoutStrategy(
            filters=filters,
            hold_bars=10,
            stop_distance_points=14.0,
        )

    def build_candidate_specific_strategy(
        self,
        candidate_row: dict[str, Any],
        hold_bars: int,
        stop_distance_points: float,
    ) -> _InlineBreakoutStrategy:
        filter_classes = candidate_row["filter_classes"]
        filters = self.build_filter_objects_from_classes(filter_classes)
        return _InlineBreakoutStrategy(
            filters=filters,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
        )

    # -------------------------------------------------------------------------
    # Promotion / trade thresholds
    # -------------------------------------------------------------------------
    def get_promotion_gate_config(self) -> dict[str, Any]:
        return {
            "min_profit_factor": 1.00,
            "min_average_trade": 0.0,
            "require_positive_net_pnl": False,
            "min_trades": 150,
            "min_trades_per_year": 8.0,
        }

    # Compatibility with abstract / older interface
    def get_promotion_thresholds(self) -> dict[str, Any]:
        return self.get_promotion_gate_config()

    def get_trade_filter_thresholds(self) -> dict[str, Any]:
        return {
            "min_trades": 150,
            "min_trades_per_year": 8.0,
        }

    # -------------------------------------------------------------------------
    # Refinement grid
    # -------------------------------------------------------------------------
    def get_active_refinement_grid_for_combo(self, candidate_row: dict[str, Any]) -> dict[str, list[Any]]:
        return {
            "hold_bars": [4, 6, 8, 10],
            "stop_distance_points": [10.0, 12.0, 14.0, 16.0],
            "min_avg_range": [6.0, 7.0, 8.0, 9.0],
            "momentum_lookback": [10, 15, 20, 25],
        }

    # Compatibility name used by master engine
    def get_refinement_grid_for_candidate(self, candidate_row: dict[str, Any]) -> dict[str, list[Any]]:
        return self.get_active_refinement_grid_for_combo(candidate_row)

    # -------------------------------------------------------------------------
    # Sweep / refinement runners
    # -------------------------------------------------------------------------
    def run_filter_combination_sweep(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        max_workers: int = 10,
    ) -> pd.DataFrame:
        print("\n🧪 Running breakout filter combination sweep...")

        filter_classes = self.get_filter_classes()

        combos: list[list[type]] = []
        for r in range(3, len(filter_classes) + 1):
            combos.extend(list(itertools.combinations(filter_classes, r)))

        total = len(combos)
        print(f"Total filter combinations: {total}")
        print(f"Parallel mode: ON | max_workers={max_workers}")

        results: list[dict[str, Any]] = []

        def evaluate_combo(combo_idx: int, combo: tuple[type, ...]) -> dict[str, Any]:
            combo_classes = list(combo)
            combo_name = "ComboBreakout_" + "_".join(cls.__name__.replace("Filter", "") for cls in combo_classes)
            print(f"  Combo {combo_idx}/{total} | {combo_name}")

            filters = self.build_filter_objects_from_classes(combo_classes)
            strategy = self.build_combinable_strategy(filters)

            engine = MasterStrategyEngine(data=data, config=cfg)
            engine.run(strategy=strategy)
            stats = engine.results()

            total_trades = int(stats.get("Total Trades", 0))
            profit_factor = float(stats.get("Profit Factor", 0.0))
            avg_trade = _parse_money(stats.get("Average Trade", 0.0))
            net_pnl = _parse_money(stats.get("Net PnL", 0.0))

            years = max((data.index.max() - data.index.min()).days / 365.25, 1e-9)
            trades_per_year = total_trades / years if years > 0 else 0.0

            return {
                "strategy_name": combo_name,
                "filter_classes": combo_classes,
                "filters": ",".join(cls.__name__ for cls in combo_classes),
                "profit_factor": profit_factor,
                "average_trade": avg_trade,
                "net_pnl": net_pnl,
                "total_trades": total_trades,
                "trades_per_year": trades_per_year,
                "avg_mfe_pts": float(stats.get("Average MFE (pts)", 0.0)),
                "avg_mae_pts": float(stats.get("Average MAE (pts)", 0.0)),
            }

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(evaluate_combo, idx + 1, combo): (idx, combo)
                for idx, combo in enumerate(combos)
            }
            for future in as_completed(futures):
                results.append(future.result())

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        df = df.sort_values(
            by=["profit_factor", "average_trade", "net_pnl"],
            ascending=[False, False, False],
        ).reset_index(drop=True)

        return df

    def run_family_filter_combination_sweep(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        max_workers: int = 10,
    ) -> pd.DataFrame:
        return self.run_filter_combination_sweep(data=data, cfg=cfg, max_workers=max_workers)

    def run_top_combo_refinement(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        candidate_row: dict[str, Any],
        max_workers: int = 10,
    ) -> pd.DataFrame:
        print("\n🎯 Running top-combo parameter refinement...")

        grid = self.get_active_refinement_grid_for_combo(candidate_row)

        hold_bars_values = grid["hold_bars"]
        stop_values = grid["stop_distance_points"]
        range_values = grid["min_avg_range"]
        mom_values = grid["momentum_lookback"]

        combos = list(itertools.product(
            hold_bars_values,
            stop_values,
            range_values,
            mom_values,
        ))

        total = len(combos)
        years = max((data.index.max() - data.index.min()).days / 365.25, 1e-9)
        trade_filters = self.get_trade_filter_thresholds()

        print(f"Total combinations: {total}")
        print(f"Years in sample: {years:.2f}")
        print(
            f"Trade filters: min_trades={trade_filters['min_trades']}, "
            f"min_trades_per_year={trade_filters['min_trades_per_year']:.2f}"
        )
        print(f"Parallel mode: ON | max_workers={max_workers}")

        accepted_rows: list[dict[str, Any]] = []
        rejected_rows = 0

        def evaluate_refinement(combo_idx: int, combo: tuple[Any, ...]) -> tuple[dict[str, Any], bool]:
            hold_bars, stop_distance_points, min_avg_range, momentum_lookback = combo

            strategy = self.build_candidate_specific_strategy(
                candidate_row=candidate_row,
                hold_bars=hold_bars,
                stop_distance_points=stop_distance_points,
            )

            engine = MasterStrategyEngine(data=data, config=cfg)
            engine.run(strategy=strategy)
            stats = engine.results()

            total_trades = int(stats.get("Total Trades", 0))
            trades_per_year = total_trades / years if years > 0 else 0.0
            profit_factor = float(stats.get("Profit Factor", 0.0))
            average_trade = _parse_money(stats.get("Average Trade", 0.0))
            net_pnl = _parse_money(stats.get("Net PnL", 0.0))

            passes_trade_filter = (
                total_trades >= trade_filters["min_trades"]
                and trades_per_year >= trade_filters["min_trades_per_year"]
            )

            accepted = passes_trade_filter

            row = {
                "strategy_name": (
                    f"RefinedBreakoutStrategy_"
                    f"HB{hold_bars}_STOP{stop_distance_points}_"
                    f"RANGE{min_avg_range}_MOM{momentum_lookback}"
                ),
                "hold_bars": hold_bars,
                "stop_distance_points": stop_distance_points,
                "min_avg_range": min_avg_range,
                "momentum_lookback": momentum_lookback,
                "profit_factor": profit_factor,
                "average_trade": average_trade,
                "net_pnl": net_pnl,
                "total_trades": total_trades,
                "trades_per_year": trades_per_year,
                "average_mfe_points": float(stats.get("Average MFE (pts)", 0.0)),
                "average_mae_points": float(stats.get("Average MAE (pts)", 0.0)),
            }

            status = "ACCEPT" if accepted else "REJECT"
            print(
                f"  Done {combo_idx}/{total} | "
                f"hb={hold_bars}, stop={stop_distance_points}, "
                f"range={min_avg_range}, mom={momentum_lookback} | "
                f"PF={profit_factor:.2f} | {status}"
            )

            return row, accepted

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(evaluate_refinement, idx + 1, combo): combo
                for idx, combo in enumerate(combos)
            }
            for future in as_completed(futures):
                row, accepted = future.result()
                if accepted:
                    accepted_rows.append(row)
                else:
                    rejected_rows += 1

        print(f"\n✅ Accepted refinement sets: {len(accepted_rows)}")
        print(f"❌ Rejected refinement sets: {rejected_rows}")

        if not accepted_rows:
            return pd.DataFrame()

        df = pd.DataFrame(accepted_rows)
        df = df.sort_values(
            by=["profit_factor", "average_trade", "net_pnl"],
            ascending=[False, False, False],
        ).reset_index(drop=True)

        return df

    def run_refinement_for_candidate(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        candidate_row: dict[str, Any],
        max_workers: int = 10,
    ) -> pd.DataFrame:
        return self.run_top_combo_refinement(
            data=data,
            cfg=cfg,
            candidate_row=candidate_row,
            max_workers=max_workers,
        )


# =============================================================================
# HELPERS
# =============================================================================
def _parse_money(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("$", "").replace(",", "").strip()
    if not text:
        return 0.0
    return float(text)