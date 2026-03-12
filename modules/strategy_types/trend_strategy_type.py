"""
Trend Strategy Type
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd

from .base_strategy_type import BaseStrategyType
from modules.engine import EngineConfig, MasterStrategyEngine
from modules.filter_combinator import generate_filter_combinations
from modules.filters import (
    MomentumFilter,
    PullbackFilter,
    RecoveryTriggerFilter,
    TrendDirectionFilter,
    VolatilityFilter,
)
from modules.plateau_analyzer import PlateauAnalyzer
from modules.refiner import StrategyParameterRefiner
from modules.strategies import (
    CombinableFilterTrendStrategy,
    FilterBasedTrendStrategy,
    RefinedFiveFilterTrendStrategy,
)


def _safe_float(value: Any) -> float:
    text = str(value).replace("$", "").replace(",", "").replace("%", "").strip()
    if text == "":
        return 0.0
    return float(text)


def _safe_int(value: Any) -> int:
    text = str(value).replace(",", "").strip()
    if text == "":
        return 0
    return int(float(text))


def _run_trend_combo_case(task: tuple[pd.DataFrame, EngineConfig, list[type]]) -> dict[str, Any]:
    data, cfg, combo_classes = task

    filter_objects: list[Any] = []

    for cls in combo_classes:
        if cls is TrendDirectionFilter:
            filter_objects.append(cls(fast_length=50, slow_length=200))
        elif cls is PullbackFilter:
            filter_objects.append(cls(fast_length=50))
        elif cls is RecoveryTriggerFilter:
            filter_objects.append(cls(fast_length=50))
        elif cls is VolatilityFilter:
            filter_objects.append(cls(lookback=20, min_avg_range=8.0))
        elif cls is MomentumFilter:
            filter_objects.append(cls(lookback=10))
        else:
            filter_objects.append(cls())

    strategy = CombinableFilterTrendStrategy(
        filters=filter_objects,
        hold_bars=8,
        stop_distance_points=12.0,
    )

    engine = MasterStrategyEngine(data=data, config=cfg)
    engine.run(strategy=strategy)
    summary = engine.results()

    total_trades = _safe_int(summary.get("Total Trades", 0))
    years_in_sample = (data.index.max() - data.index.min()).days / 365.25
    trades_per_year = total_trades / years_in_sample if years_in_sample > 0 else 0.0

    thresholds = {
        "min_trades": 150,
        "min_trades_per_year": 8.0,
    }

    passes_trade_filter = (
        total_trades >= thresholds["min_trades"]
        and trades_per_year >= thresholds["min_trades_per_year"]
    )

    return {
        "strategy_name": str(summary.get("Strategy", "UnknownStrategy")),
        "filter_count": len(filter_objects),
        "filters": ",".join([f.name for f in filter_objects]),
        "total_trades": total_trades,
        "trades_per_year": round(trades_per_year, 2),
        "passes_trade_filter": passes_trade_filter,
        "net_pnl": _safe_float(summary.get("Net PnL", 0.0)),
        "gross_profit": _safe_float(summary.get("Gross Profit", 0.0)),
        "gross_loss": _safe_float(summary.get("Gross Loss", 0.0)),
        "average_trade": _safe_float(summary.get("Average Trade", 0.0)),
        "profit_factor": _safe_float(summary.get("Profit Factor", 0.0)),
        "max_drawdown": _safe_float(summary.get("Max Drawdown", 0.0)),
        "win_rate": _safe_float(summary.get("Win Rate", 0.0)),
        "avg_mae_pts": _safe_float(summary.get("Average MAE (pts)", 0.0)),
        "avg_mfe_pts": _safe_float(summary.get("Average MFE (pts)", 0.0)),
    }


class TrendStrategyType(BaseStrategyType):
    name = "trend"

    min_filters_per_combo = 3
    max_filters_per_combo = 5

    default_hold_bars = 8
    default_stop_distance_points = 12.0

    # -------------------------------------------------------------------------
    # Required feature dependencies
    # -------------------------------------------------------------------------
    def get_required_sma_lengths(self) -> list[int]:
        return [50, 200]

    def get_required_avg_range_lookbacks(self) -> list[int]:
        return [20]

    def get_required_momentum_lookbacks(self) -> list[int]:
        return [8, 10, 11, 12, 13, 14]

    # -------------------------------------------------------------------------
    # Filter stack definitions
    # -------------------------------------------------------------------------
    def get_filter_classes(self) -> list[type]:
        return [
            TrendDirectionFilter,
            PullbackFilter,
            RecoveryTriggerFilter,
            VolatilityFilter,
            MomentumFilter,
        ]

    def build_filter_objects_from_classes(self, combo_classes: list[type]) -> list:
        filter_objects: list[Any] = []

        for cls in combo_classes:
            if cls is TrendDirectionFilter:
                filter_objects.append(cls(fast_length=50, slow_length=200))
            elif cls is PullbackFilter:
                filter_objects.append(cls(fast_length=50))
            elif cls is RecoveryTriggerFilter:
                filter_objects.append(cls(fast_length=50))
            elif cls is VolatilityFilter:
                filter_objects.append(cls(lookback=20, min_avg_range=8.0))
            elif cls is MomentumFilter:
                filter_objects.append(cls(lookback=10))
            else:
                filter_objects.append(cls())

        return filter_objects

    def build_default_sanity_filters(self) -> list:
        return [
            TrendDirectionFilter(fast_length=50, slow_length=200),
            PullbackFilter(fast_length=50),
            RecoveryTriggerFilter(fast_length=50),
            VolatilityFilter(lookback=20, min_avg_range=8.0),
            MomentumFilter(lookback=10),
        ]

    # -------------------------------------------------------------------------
    # Strategy builders
    # -------------------------------------------------------------------------
    def build_default_strategy(self):
        return FilterBasedTrendStrategy()

    def build_sanity_check_strategy(self):
        return self.build_default_strategy()

    def build_combinable_strategy(
        self,
        filters: list,
        hold_bars: int,
        stop_distance_points: float,
    ):
        return CombinableFilterTrendStrategy(
            filters=filters,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
        )

    def build_combination_strategy(self, filters: dict[str, Any]):
        return CombinableFilterTrendStrategy(
            filters=filters["filter_objects"],
            hold_bars=filters.get("hold_bars", self.default_hold_bars),
            stop_distance_points=filters.get(
                "stop_distance_points",
                self.default_stop_distance_points,
            ),
        )

    def build_candidate_specific_strategy(
        self,
        promoted_combo_classes: list[type],
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
    ):
        return RefinedFiveFilterTrendStrategy(
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
            fast_length=50,
            slow_length=200,
            volatility_lookback=20,
            min_avg_range=min_avg_range,
            momentum_lookback=momentum_lookback,
        )

    def build_candidate_specific_refinement_factory(self, candidate_row: dict[str, Any]):
        return RefinedFiveFilterTrendStrategy

    # -------------------------------------------------------------------------
    # Thresholds and gates
    # -------------------------------------------------------------------------
    def get_trade_filter_thresholds(self) -> dict[str, float]:
        return {
            "min_trades": 150,
            "min_trades_per_year": 8.0,
        }

    def get_trade_filter_config(self) -> dict[str, float]:
        return self.get_trade_filter_thresholds()

    def get_promotion_thresholds(self) -> dict[str, float | bool]:
        return {
            "min_profit_factor": 1.00,
            "min_average_trade": 0.0,
            "require_positive_net_pnl": False,
        }

    def get_promotion_gate_config(self) -> dict[str, float | bool]:
        return self.get_promotion_thresholds()

    # -------------------------------------------------------------------------
    # Refinement grids
    # -------------------------------------------------------------------------
    def get_active_refinement_grid_for_combo(
        self,
        promoted_combo_classes: list[type],
    ) -> dict[str, list]:
        return {
            "hold_bars": [8, 9, 10, 11, 12],
            "stop_distance_points": [9.0, 10.0, 11.0, 12.0],
            "min_avg_range": [8.0, 8.5, 9.0, 9.5],
            "momentum_lookback": [11, 12, 13, 14],
        }

    def get_refinement_grid_for_candidate(self, candidate_row: dict[str, Any]) -> dict[str, list]:
        combo_classes = self.get_filter_classes()
        return self.get_active_refinement_grid_for_combo(combo_classes)

    # -------------------------------------------------------------------------
    # Sweep
    # -------------------------------------------------------------------------
    def run_filter_combination_sweep(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        max_workers: int = 10,
    ) -> pd.DataFrame:
        return self.run_family_filter_combination_sweep(
            data=data,
            cfg=cfg,
            max_workers=max_workers,
        )

    def run_family_filter_combination_sweep(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        max_workers: int = 10,
    ) -> pd.DataFrame:
        filter_classes = self.get_filter_classes()

        combinations = generate_filter_combinations(
            filter_classes=filter_classes,
            min_filters=self.min_filters_per_combo,
            max_filters=self.max_filters_per_combo,
        )

        print("\n🧪 Running trend filter combination sweep...")
        print(f"Total filter combinations: {len(combinations)}")
        print(f"Parallel mode: ON | max_workers={max_workers}")

        tasks = [(data, cfg, combo_classes) for combo_classes in combinations]
        results: list[dict[str, Any]] = []

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            for idx, result in enumerate(executor.map(_run_trend_combo_case, tasks), start=1):
                print(f"  Combo {idx}/{len(combinations)} | {result['strategy_name']}")
                results.append(result)

        results_df = pd.DataFrame(results)

        if not results_df.empty:
            results_df = results_df.sort_values(
                by=["passes_trade_filter", "profit_factor", "average_trade", "net_pnl"],
                ascending=[False, False, False, False],
            ).reset_index(drop=True)

        return results_df

    # -------------------------------------------------------------------------
    # Refinement
    # -------------------------------------------------------------------------
    def run_refinement_for_candidate(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        candidate_row: dict[str, Any],
        output_dir: str | Path = "Outputs",
        max_workers: int = 10,
    ) -> pd.DataFrame:
        refiner = StrategyParameterRefiner(
            engine_class=MasterStrategyEngine,
            data=data,
            strategy_factory=RefinedFiveFilterTrendStrategy,
            config=cfg,
        )

        grid = self.get_refinement_grid_for_candidate(candidate_row)
        trade_filters = self.get_trade_filter_thresholds()

        refinement_df = refiner.run_refinement(
            hold_bars=grid["hold_bars"],
            stop_distance_points=grid["stop_distance_points"],
            min_avg_range=grid["min_avg_range"],
            momentum_lookback=grid["momentum_lookback"],
            min_trades=trade_filters["min_trades"],
            min_trades_per_year=trade_filters["min_trades_per_year"],
            parallel=True,
            max_workers=max_workers,
        )

        if not refinement_df.empty:
            print("\n🎯 Top trend Refinement Results:")
            print(refiner.top_results(10))
            refiner.print_summary_report(top_n=10)

            plateau = PlateauAnalyzer(refinement_df)
            plateau.print_report(top_n=10)

            output_path = Path(output_dir) / "trend_top_combo_refinement_results_narrow.csv"
            saved_path = refiner.save_results_csv(output_path)
            print(f"\n💾 Narrow top-combo refinement saved to: {saved_path}")
        else:
            print("\nNo refinement results met the trade filters.")

        return refinement_df

    def run_top_combo_refinement(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        candidate_row: dict[str, Any],
        output_dir: str | Path = "Outputs",
        max_workers: int = 10,
    ) -> pd.DataFrame:
        return self.run_refinement_for_candidate(
            data=data,
            cfg=cfg,
            candidate_row=candidate_row,
            output_dir=output_dir,
            max_workers=max_workers,
        )