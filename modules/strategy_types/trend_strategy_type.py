from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd

from modules.config_loader import get_timeframe_multiplier
from modules.engine import EngineConfig, MasterStrategyEngine
from modules.filter_combinator import build_filter_combo_name, generate_filter_combinations
from modules.filters import (
    BaseFilter,
    CloseAboveFastSMAFilter,
    HigherLowFilter,
    MomentumFilter,
    PullbackFilter,
    RecoveryTriggerFilter,
    TrendDirectionFilter,
    TrendSlopeFilter,
    TwoBarUpFilter,
    UpCloseFilter,
    VolatilityFilter,
)
from modules.refiner import StrategyParameterRefiner
from modules.strategy_types.base_strategy_type import BaseStrategyType


class _InlineTrendStrategy:
    direction = "LONG_ONLY"

    def __init__(
        self,
        filters: list[BaseFilter],
        hold_bars: int = 6,
        stop_distance_atr: float = 1.25,
        name: str | None = None,
    ):
        self.filters = filters
        self.hold_bars = hold_bars
        self.stop_distance_atr = stop_distance_atr
        self.name = name or f"ComboTrend_{build_filter_combo_name(filters)}"

    def generate_signal(self, data: pd.DataFrame, i: int) -> int:
        for f in self.filters:
            if not f.passes(data, i):
                return 0
        return 1


def _run_trend_combo_case(task: tuple[pd.DataFrame, EngineConfig, list[type]]) -> dict[str, Any]:
    data, cfg, combo_classes = task
    strat_type = TrendStrategyType()

    filter_objects = strat_type.build_filter_objects_from_classes(combo_classes)
    strategy = strat_type.build_combinable_strategy(
        filters=filter_objects,
        hold_bars=strat_type.default_hold_bars,
        stop_distance_points=strat_type.default_stop_distance_points,
    )

    engine = MasterStrategyEngine(data=data, config=cfg)
    engine.run(strategy=strategy)
    summary = engine.results()

    total_trades = int(str(summary.get("Total Trades", 0)).replace(",", ""))
    years_in_sample = (data.index.max() - data.index.min()).days / 365.25
    trades_per_year = total_trades / years_in_sample if years_in_sample > 0 else 0.0

    thresholds = strat_type.get_trade_filter_thresholds()
    passes = (
        total_trades >= thresholds["min_trades"]
        and trades_per_year >= thresholds["min_trades_per_year"]
    )

    def _pf(val: Any) -> float:
        return float(str(val).replace("$", "").replace(",", "").replace("%", "").strip() or 0.0)

    return {
        "strategy_name": str(summary.get("Strategy", "UnknownStrategy")),
        "filter_count": len(filter_objects),
        "filters": ",".join([f.name for f in filter_objects]),
        "filter_class_names": ",".join([c.__name__ for c in combo_classes]),
        "total_trades": total_trades,
        "trades_per_year": round(trades_per_year, 2),
        "passes_trade_filter": passes,
        "net_pnl": _pf(summary.get("Net PnL", 0.0)),
        "profit_factor": _pf(summary.get("Profit Factor", 0.0)),
        "average_trade": _pf(summary.get("Average Trade", 0.0)),
        "is_trades": int(summary.get("IS Trades", 0)),
        "oos_trades": int(summary.get("OOS Trades", 0)),
        "is_pf": _pf(summary.get("IS PF", 0.0)),
        "oos_pf": _pf(summary.get("OOS PF", 0.0)),
        "recent_12m_trades": int(summary.get("Recent 12m Trades", 0)),
        "recent_12m_pf": _pf(summary.get("Recent 12m PF", 0.0)),
        "quality_flag": str(summary.get("Quality Flag", "UNKNOWN")),
        "quality_score": _pf(summary.get("Quality Score", 0.0)),
        "pct_profitable_years": _pf(summary.get("Pct Profitable Years", 0.0)),
        "max_consecutive_losing_years": int(summary.get("Max Consecutive Losing Years", 0)),
        "consistency_flag": str(summary.get("Consistency Flag", "INSUFFICIENT_DATA")),
    }


class _TrendRefinementFactory:
    def __init__(self, strat_inst, combo_classes: list[type]):
        self.strat_inst = strat_inst
        self.combo_classes = combo_classes

    def __call__(
        self,
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
    ):
        return self.strat_inst.build_candidate_specific_strategy(
            self.combo_classes,
            hold_bars,
            stop_distance_points,
            min_avg_range,
            momentum_lookback,
        )


class TrendStrategyType(BaseStrategyType):
    name = "trend"
    min_filters_per_combo = 4
    max_filters_per_combo = 6

    default_hold_bars = 6
    default_stop_distance_points = 1.25

    def get_required_sma_lengths(self) -> list[int]:
        return [50, 200]

    def get_required_avg_range_lookbacks(self) -> list[int]:
        return [20]

    def get_required_momentum_lookbacks(self) -> list[int]:
        return [5, 8, 10, 14]

    def build_default_sanity_filters(self) -> list[BaseFilter]:
        return [
            TrendDirectionFilter(fast_length=50, slow_length=200),
            PullbackFilter(fast_length=50),
            RecoveryTriggerFilter(fast_length=50),
            VolatilityFilter(lookback=20, min_atr_mult=0.95),
            MomentumFilter(lookback=8),
            TrendSlopeFilter(fast_length=50, slope_bars=5),
        ]

    def build_default_strategy(self) -> _InlineTrendStrategy:
        return _InlineTrendStrategy(
            filters=self.build_default_sanity_filters(),
            hold_bars=self.default_hold_bars,
            stop_distance_atr=self.default_stop_distance_points,
            name="FilterBasedTrendStrategy",
        )

    def build_sanity_check_strategy(self) -> _InlineTrendStrategy:
        return self.build_default_strategy()

    def get_filter_classes(self) -> list[type]:
        return [
            TrendDirectionFilter,
            PullbackFilter,
            RecoveryTriggerFilter,
            VolatilityFilter,
            MomentumFilter,
            UpCloseFilter,
            TwoBarUpFilter,
            TrendSlopeFilter,
            CloseAboveFastSMAFilter,
            HigherLowFilter,
        ]

    def build_filter_objects_from_classes(self, combo_classes: list[type]) -> list[BaseFilter]:
        filters: list[BaseFilter] = []

        for cls in combo_classes:
            if cls is TrendDirectionFilter:
                filters.append(TrendDirectionFilter(fast_length=50, slow_length=200))
            elif cls is PullbackFilter:
                filters.append(PullbackFilter(fast_length=50))
            elif cls is RecoveryTriggerFilter:
                filters.append(RecoveryTriggerFilter(fast_length=50))
            elif cls is VolatilityFilter:
                filters.append(VolatilityFilter(lookback=20, min_atr_mult=0.95))
            elif cls is MomentumFilter:
                filters.append(MomentumFilter(lookback=8))
            elif cls is TrendSlopeFilter:
                filters.append(TrendSlopeFilter(fast_length=50, slope_bars=5))
            elif cls is CloseAboveFastSMAFilter:
                filters.append(CloseAboveFastSMAFilter(fast_length=50))
            elif cls is HigherLowFilter:
                filters.append(HigherLowFilter())
            else:
                filters.append(cls())

        return filters

    def build_combinable_strategy(
        self,
        filters: list[BaseFilter],
        hold_bars: int,
        stop_distance_points: float,
    ) -> _InlineTrendStrategy:
        return _InlineTrendStrategy(
            filters=filters,
            hold_bars=hold_bars,
            stop_distance_atr=stop_distance_points,
        )

    def build_candidate_specific_strategy(
        self,
        classes: list[type],
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
    ) -> _InlineTrendStrategy:
        filters: list[BaseFilter] = []

        for cls in classes:
            if cls is TrendDirectionFilter:
                filters.append(TrendDirectionFilter(fast_length=50, slow_length=200))
            elif cls is PullbackFilter:
                filters.append(PullbackFilter(fast_length=50))
            elif cls is RecoveryTriggerFilter:
                filters.append(RecoveryTriggerFilter(fast_length=50))
            elif cls is VolatilityFilter:
                filters.append(VolatilityFilter(lookback=20, min_atr_mult=min_avg_range if min_avg_range > 0 else 0.95))
            elif cls is MomentumFilter:
                filters.append(MomentumFilter(lookback=momentum_lookback if momentum_lookback > 0 else 8))
            elif cls is TrendSlopeFilter:
                filters.append(TrendSlopeFilter(fast_length=50, slope_bars=5))
            elif cls is CloseAboveFastSMAFilter:
                filters.append(CloseAboveFastSMAFilter(fast_length=50))
            elif cls is HigherLowFilter:
                filters.append(HigherLowFilter())
            else:
                filters.append(cls())

        return _InlineTrendStrategy(
            filters=filters,
            hold_bars=hold_bars,
            stop_distance_atr=stop_distance_points,
            name=f"RefinedTrend_HB{hold_bars}_ATR{stop_distance_points}_VOL{min_avg_range}_MOM{momentum_lookback}",
        )

    def get_promotion_thresholds(self) -> dict[str, float | bool]:
        return {
            "min_profit_factor": 0.75,
            "min_average_trade": 0.0,
            "require_positive_net_pnl": False,
            "min_trades": 60,
            "min_trades_per_year": 3.0,
            "max_promoted_candidates": 20,
        }

    def get_promotion_gate_config(self) -> dict[str, float | bool]:
        return self.get_promotion_thresholds()

    def get_trade_filter_thresholds(self) -> dict[str, float]:
        return {
            "min_trades": 60,
            "min_trades_per_year": 3.0,
        }

    def get_trade_filter_config(self) -> dict[str, float]:
        return self.get_trade_filter_thresholds()

    def get_active_refinement_grid_for_combo(
        self, classes: list[type], timeframe: str = "60m"
    ) -> dict[str, list]:
        base_hold_bars = [3, 4, 5, 6, 8, 10, 12, 15]
        mult = get_timeframe_multiplier(timeframe)

        if mult != 1.0:
            scaled = sorted(set(max(1, round(h * mult)) for h in base_hold_bars))
            if len(scaled) < 4:
                scaled = sorted(set(scaled + [1, 2, 3, 5]))
        else:
            scaled = base_hold_bars

        base_mom_lookbacks = [0, 5, 8, 10, 14]
        if mult != 1.0 and any(cls is MomentumFilter for cls in classes):
            scaled_mom = sorted(set(max(1, round(m * mult)) for m in base_mom_lookbacks if m > 0))
            if len(scaled_mom) < 3:
                scaled_mom = sorted(set(scaled_mom + [5, 10, 20]))
            momentum_lookback = [0] + scaled_mom
        else:
            momentum_lookback = base_mom_lookbacks if any(cls is MomentumFilter for cls in classes) else [0]

        grid = {
            "hold_bars": scaled,
            # stop_distance_points are ATR-based, unscaled
            "stop_distance_points": [0.75, 1.0, 1.25, 1.5, 2.0, 2.5],
        }

        grid["min_avg_range"] = [0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4] if any(cls is VolatilityFilter for cls in classes) else [0.0]
        grid["momentum_lookback"] = momentum_lookback

        return grid

    def get_refinement_grid_for_candidate(self, row: dict[str, Any]) -> dict[str, list]:
        return self.get_active_refinement_grid_for_combo(
            row.get("filter_classes", []), row.get("timeframe", "60m")
        )

    def run_family_filter_combination_sweep(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        max_workers: int = 10,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> pd.DataFrame:
        combinations = generate_filter_combinations(
            self.get_filter_classes(),
            self.min_filters_per_combo,
            self.max_filters_per_combo,
        )

        tasks = [(data, cfg, combo_classes) for combo_classes in combinations]
        results: list[dict[str, Any]] = []

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            for idx, res in enumerate(executor.map(_run_trend_combo_case, tasks), start=1):
                print(
                    f"  Combo {idx}/{len(combinations)} | {res['strategy_name']} | "
                    f"PF={res['profit_factor']:.2f} | Net={res['net_pnl']:.2f} | "
                    f"trades={res['total_trades']}"
                )
                res["filter_classes"] = combinations[idx - 1]
                results.append(res)
                if progress_callback is not None:
                    progress_callback(idx, len(combinations))

        if not results:
            return pd.DataFrame()

        return (
            pd.DataFrame(results)
            .sort_values(by=["net_pnl", "profit_factor", "average_trade"], ascending=[False, False, False])
            .reset_index(drop=True)
        )

    def run_top_combo_refinement(
        self,
        data: pd.DataFrame,
        cfg: EngineConfig,
        candidate_row: dict[str, Any],
        output_dir: str | Path = "Outputs",
        max_workers: int = 10,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> pd.DataFrame:
        classes = candidate_row.get("filter_classes", [])
        timeframe = cfg.timeframe
        grid = self.get_active_refinement_grid_for_combo(classes, timeframe=timeframe)
        thresholds = self.get_trade_filter_thresholds()

        refiner = StrategyParameterRefiner(
            MasterStrategyEngine,
            data,
            _TrendRefinementFactory(self, classes),
            cfg,
        )

        refinement_df = refiner.run_refinement(
            hold_bars=grid["hold_bars"],
            stop_distance_points=grid["stop_distance_points"],
            min_avg_range=grid["min_avg_range"],
            momentum_lookback=grid["momentum_lookback"],
            min_trades=thresholds["min_trades"],
            min_trades_per_year=thresholds["min_trades_per_year"],
            parallel=True,
            max_workers=max_workers,
            progress_callback=progress_callback,
        )

        if not refinement_df.empty:
            refinement_df["strategy_type"] = self.name
            refinement_df["combo_filters"] = candidate_row.get("filters", "")
            refinement_df["combo_filter_class_names"] = candidate_row.get("filter_class_names", "")
            refinement_df.to_csv(
                Path(output_dir) / f"{self.name}_top_combo_refinement_results_narrow.csv",
                index=False,
            )

        return refinement_df