from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, product
from typing import Any, Callable

import pandas as pd

from modules.engine import EngineConfig, MasterStrategyEngine
from modules.filters import (
    BreakoutCloseStrengthFilter,
    BreakoutTrendFilter,
    CompressionFilter,
    ExpansionBarFilter,
    MinimumBreakDistanceFilter,
    PriorRangePositionFilter,
    RangeBreakoutFilter,
)
from modules.strategies import BaseStrategy
from modules.strategy_types.base_strategy_type import BaseStrategyType


class FilterBasedBreakoutStrategy(BaseStrategy):
    """
    Simple breakout strategy that enters long when all supplied filters pass.
    Exits by stop or time stop.
    """

    def __init__(
        self,
        filters: list[Any],
        hold_bars: int = 6,
        stop_distance_points: float = 12.0,
        strategy_name: str = "FilterBasedBreakoutStrategy",
    ) -> None:
        self.filters = filters
        self.hold_bars = hold_bars
        self.stop_distance_points = stop_distance_points
        self.strategy_name = strategy_name

    def on_bar(self, i: int, data: pd.DataFrame, state: dict[str, Any]) -> None:
        if i < 1:
            return

        # Manage open trade first
        if state.get("in_position", False):
            bars_held = i - state["entry_index"]
            low_price = float(data.iloc[i]["low"])

            if low_price <= state["stop_price"]:
                exit_price = state["stop_price"]
                state["exit_trade"](i, exit_price, "STOP")
                return

            if bars_held >= self.hold_bars:
                exit_price = float(data.iloc[i]["close"])
                state["exit_trade"](i, exit_price, "TIME")
                return

            return

        # Flat: evaluate entry
        for flt in self.filters:
            if not flt.passes(i, data):
                return

        entry_price = float(data.iloc[i]["close"])
        stop_price = entry_price - self.stop_distance_points
        state["enter_trade"](i, entry_price, stop_price, self.strategy_name)


@dataclass
class _SweepResult:
    strategy_name: str
    filters: str
    hold_bars: int
    stop_distance_points: float
    min_avg_range: float
    momentum_lookback: int
    net_pnl: float
    average_trade: float
    profit_factor: float
    max_drawdown: float
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    avg_mae_pts: float
    avg_mfe_pts: float
    trades_per_year: float


class BreakoutStrategyType(BaseStrategyType):
    name = "breakout"

    # ------------------------------------------------------------------
    # Required feature dependencies
    # ------------------------------------------------------------------
    def get_required_sma_lengths(self) -> list[int]:
        return [50, 200]

    def get_required_avg_range_lookbacks(self) -> list[int]:
        return [20]

    def get_required_momentum_lookbacks(self) -> list[int]:
        return []

    # ------------------------------------------------------------------
    # Promotion / trade thresholds
    # ------------------------------------------------------------------
    def get_promotion_gate_config(self) -> dict[str, Any]:
        return {
            "min_profit_factor": 1.00,
            "min_average_trade": 0.0,
            "require_positive_net_pnl": False,
            "min_trades": 150,
            "min_trades_per_year": 8.0,
        }

    def get_trade_filter_thresholds(self) -> dict[str, Any]:
        return {
            "min_trades": 150,
            "min_trades_per_year": 8.0,
        }

    # ------------------------------------------------------------------
    # Filter library
    # ------------------------------------------------------------------
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
                filters.append(CompressionFilter(lookback=20, threshold=0.75))
            elif cls is PriorRangePositionFilter:
                filters.append(
                    PriorRangePositionFilter(
                        lookback=20,
                        min_position_in_range=0.60,
                    )
                )
            elif cls is RangeBreakoutFilter:
                filters.append(RangeBreakoutFilter(lookback=20))
            elif cls is MinimumBreakDistanceFilter:
                filters.append(MinimumBreakDistanceFilter(min_break_distance=1.0))
            elif cls is ExpansionBarFilter:
                filters.append(ExpansionBarFilter(multiplier=1.2))
            elif cls is BreakoutCloseStrengthFilter:
                filters.append(BreakoutCloseStrengthFilter(min_close_position=0.65))
            elif cls is BreakoutTrendFilter:
                filters.append(BreakoutTrendFilter(fast_sma_col="sma_50", slow_sma_col="sma_200"))
            else:
                raise ValueError(f"Unsupported breakout filter class: {cls}")

        return filters

    # ------------------------------------------------------------------
    # Baseline / sanity strategy
    # ------------------------------------------------------------------
    def build_default_sanity_filters(self) -> list[Any]:
        return [
            CompressionFilter(lookback=20, threshold=0.75),
            PriorRangePositionFilter(lookback=20, min_position_in_range=0.60),
            RangeBreakoutFilter(lookback=20),
            MinimumBreakDistanceFilter(min_break_distance=1.0),
            ExpansionBarFilter(multiplier=1.2),
            BreakoutCloseStrengthFilter(min_close_position=0.65),
            BreakoutTrendFilter(fast_sma_col="sma_50", slow_sma_col="sma_200"),
        ]

    def build_default_strategy(self) -> BaseStrategy:
        return FilterBasedBreakoutStrategy(
            filters=self.build_default_sanity_filters(),
            hold_bars=6,
            stop_distance_points=12.0,
            strategy_name="FilterBasedBreakoutStrategy",
        )

    def build_sanity_check_strategy(self) -> BaseStrategy:
        return self.build_default_strategy()

    # ------------------------------------------------------------------
    # Generic strategy builders
    # ------------------------------------------------------------------
    def build_combinable_strategy(
        self,
        filters: list[Any],
        hold_bars: int = 6,
        stop_distance_points: float = 12.0,
        strategy_name: str = "ComboBreakoutStrategy",
    ) -> BaseStrategy:
        return FilterBasedBreakoutStrategy(
            filters=filters,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
            strategy_name=strategy_name,
        )

    def build_candidate_specific_strategy(
        self,
        candidate_row: dict[str, Any],
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
    ) -> BaseStrategy:
        filter_names = [
            name.strip()
            for name in str(candidate_row.get("filters", "")).split(",")
            if name.strip()
        ]

        class_map = {cls.__name__: cls for cls in self.get_filter_classes()}
        selected_classes = [class_map[name] for name in filter_names if name in class_map]
        filters = self.build_filter_objects_from_classes(selected_classes)

        strategy_name = (
            f"RefinedBreakoutStrategy_HB{hold_bars}_STOP{stop_distance_points}"
            f"_RANGE{min_avg_range}_MOM{momentum_lookback}"
        )

        return self.build_combinable_strategy(
            filters=filters,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
            strategy_name=strategy_name,
        )

    # ------------------------------------------------------------------
    # Sweep / refinement helpers
    # ------------------------------------------------------------------
    def _run_single_backtest(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        strategy: BaseStrategy,
    ) -> dict[str, Any]:
        engine = MasterStrategyEngine(data=data, config=cfg)
        engine.run(strategy=strategy)

        results = engine.results()
        trades_df = engine.trades_dataframe()

        total_trades = int(results.get("Total Trades", 0))
        years = max((data.index.max() - data.index.min()).days / 365.25, 1e-9)
        trades_per_year = total_trades / years if years > 0 else 0.0

        return {
            "strategy_name": str(results.get("Strategy", "UnknownStrategy")),
            "net_pnl": self._parse_money(results.get("Net PnL", 0.0)),
            "average_trade": self._parse_money(results.get("Average Trade", 0.0)),
            "profit_factor": float(results.get("Profit Factor", 0.0)),
            "max_drawdown": self._parse_money(results.get("Max Drawdown", 0.0)),
            "total_trades": total_trades,
            "wins": int(results.get("Wins", 0)),
            "losses": int(results.get("Losses", 0)),
            "win_rate": self._parse_percent(results.get("Win Rate", 0.0)),
            "avg_mae_pts": float(results.get("Average MAE (pts)", 0.0)),
            "avg_mfe_pts": float(results.get("Average MFE (pts)", 0.0)),
            "trades_per_year": trades_per_year,
            "trades_df": trades_df,
        }

    @staticmethod
    def _parse_money(value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        return float(str(value).replace("$", "").replace(",", "").strip() or 0.0)

    @staticmethod
    def _parse_percent(value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        return float(str(value).replace("%", "").strip() or 0.0)

    # ------------------------------------------------------------------
    # Combination sweep
    # ------------------------------------------------------------------
    def run_filter_combination_sweep(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        max_workers: int = 1,
    ) -> pd.DataFrame:
        print("\n🧪 Running breakout filter combination sweep...")

        filter_classes = self.get_filter_classes()

        combo_class_sets: list[tuple[type, ...]] = []
        for r in range(3, len(filter_classes) + 1):
            combo_class_sets.extend(list(combinations(filter_classes, r)))

        print(f"Total filter combinations: {len(combo_class_sets)}")
        print(f"Parallel mode: ON | max_workers={max_workers}")

        rows: list[dict[str, Any]] = []

        for idx, combo_classes in enumerate(combo_class_sets, start=1):
            combo_name = "ComboBreakout_" + "_".join(cls.__name__.replace("Filter", "") for cls in combo_classes)
            print(f"  Combo {idx}/{len(combo_class_sets)} | {combo_name}")

            filters = self.build_filter_objects_from_classes(list(combo_classes))
            strategy = self.build_combinable_strategy(
                filters=filters,
                hold_bars=6,
                stop_distance_points=12.0,
                strategy_name=combo_name,
            )

            result = self._run_single_backtest(data=data, cfg=cfg, strategy=strategy)

            rows.append(
                {
                    "strategy_name": combo_name,
                    "filters": ",".join(cls.__name__ for cls in combo_classes),
                    "hold_bars": 6,
                    "stop_distance_points": 12.0,
                    "min_avg_range": 0.0,
                    "momentum_lookback": 0,
                    "net_pnl": result["net_pnl"],
                    "average_trade": result["average_trade"],
                    "profit_factor": result["profit_factor"],
                    "max_drawdown": result["max_drawdown"],
                    "total_trades": result["total_trades"],
                    "wins": result["wins"],
                    "losses": result["losses"],
                    "win_rate": result["win_rate"],
                    "avg_mae_pts": result["avg_mae_pts"],
                    "avg_mfe_pts": result["avg_mfe_pts"],
                    "trades_per_year": result["trades_per_year"],
                }
            )

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values(
                by=["profit_factor", "average_trade", "net_pnl"],
                ascending=[False, False, False],
            ).reset_index(drop=True)

        return df

    def run_family_filter_combination_sweep(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        max_workers: int = 1,
    ) -> pd.DataFrame:
        return self.run_filter_combination_sweep(
            data=data,
            cfg=cfg,
            max_workers=max_workers,
        )

    # ------------------------------------------------------------------
    # Candidate refinement
    # ------------------------------------------------------------------
    def get_active_refinement_grid_for_combo(
        self,
        candidate_row: dict[str, Any],
    ) -> dict[str, list[Any]]:
        return {
            "hold_bars": [4, 6, 8, 10],
            "stop_distance_points": [10.0, 12.0, 14.0, 16.0],
            "min_avg_range": [0.0],
            "momentum_lookback": [0],
        }

    def get_refinement_grid_for_candidate(
        self,
        candidate_row: dict[str, Any],
    ) -> dict[str, list[Any]]:
        return self.get_active_refinement_grid_for_combo(candidate_row)

    def build_candidate_specific_refinement_factory(
        self,
        candidate_row: dict[str, Any],
    ) -> Callable[[int, float, float, int], BaseStrategy]:
        def factory(
            hold_bars: int,
            stop_distance_points: float,
            min_avg_range: float,
            momentum_lookback: int,
        ) -> BaseStrategy:
            return self.build_candidate_specific_strategy(
                candidate_row=candidate_row,
                hold_bars=hold_bars,
                stop_distance_points=stop_distance_points,
                min_avg_range=min_avg_range,
                momentum_lookback=momentum_lookback,
            )

        return factory

    def run_top_combo_refinement(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        candidate_row: dict[str, Any],
        max_workers: int = 1,
    ) -> pd.DataFrame:
        print("\n🎯 Running top-combo parameter refinement...")

        grid = self.get_active_refinement_grid_for_combo(candidate_row)
        combos = list(
            product(
                grid["hold_bars"],
                grid["stop_distance_points"],
                grid["min_avg_range"],
                grid["momentum_lookback"],
            )
        )

        years = max((data.index.max() - data.index.min()).days / 365.25, 1e-9)
        thresholds = self.get_trade_filter_thresholds()

        print(f"Total combinations: {len(combos)}")
        print(f"Years in sample: {years:.2f}")
        print(
            f"Trade filters: min_trades={thresholds['min_trades']}, "
            f"min_trades_per_year={thresholds['min_trades_per_year']:.2f}"
        )
        print(f"Parallel mode: ON | max_workers={max_workers}")

        rows: list[dict[str, Any]] = []

        for idx, (hb, stop, min_range, mom_lb) in enumerate(combos, start=1):
            strategy = self.build_candidate_specific_strategy(
                candidate_row=candidate_row,
                hold_bars=hb,
                stop_distance_points=stop,
                min_avg_range=min_range,
                momentum_lookback=mom_lb,
            )

            result = self._run_single_backtest(data=data, cfg=cfg, strategy=strategy)

            accept = (
                result["total_trades"] >= thresholds["min_trades"]
                and result["trades_per_year"] >= thresholds["min_trades_per_year"]
            )

            print(
                f"  Done {idx}/{len(combos)} | "
                f"hb={hb}, stop={stop}, range={min_range}, mom={mom_lb} | "
                f"PF={result['profit_factor']:.2f} | "
                f"{'ACCEPT' if accept else 'REJECT'}"
            )

            if not accept:
                continue

            rows.append(
                {
                    "strategy_name": result["strategy_name"],
                    "hold_bars": hb,
                    "stop_distance_points": stop,
                    "min_avg_range": min_range,
                    "momentum_lookback": mom_lb,
                    "net_pnl": result["net_pnl"],
                    "average_trade": result["average_trade"],
                    "profit_factor": result["profit_factor"],
                    "max_drawdown": result["max_drawdown"],
                    "total_trades": result["total_trades"],
                    "wins": result["wins"],
                    "losses": result["losses"],
                    "win_rate": result["win_rate"],
                    "average_mae_points": result["avg_mae_pts"],
                    "average_mfe_points": result["avg_mfe_pts"],
                    "trades_per_year": result["trades_per_year"],
                }
            )

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values(
                by=["profit_factor", "average_trade", "net_pnl"],
                ascending=[False, False, False],
            ).reset_index(drop=True)

        print(f"\n✅ Accepted refinement sets: {len(df)}")
        print(f"❌ Rejected refinement sets: {len(combos) - len(df)}")

        if not df.empty:
            print(f"\n🎯 Top breakout Refinement Results:")
            print(df.head(10))

        return df

    def run_refinement_for_candidate(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        candidate_row: dict[str, Any],
        max_workers: int = 1,
    ) -> pd.DataFrame:
        return self.run_top_combo_refinement(
            data=data,
            cfg=cfg,
            candidate_row=candidate_row,
            max_workers=max_workers,
        )