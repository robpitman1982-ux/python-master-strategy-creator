from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd

from modules.config_loader import get_timeframe_multiplier, scale_lookbacks
from modules.engine import EngineConfig, MasterStrategyEngine
from modules.filter_combinator import build_filter_combo_name, generate_filter_combinations
from modules.vectorized_signals import compute_combined_signal_mask
from modules.filters import (
    ATRExpansionRatioFilter,
    ATRPercentileFilter,
    BaseFilter,
    BreakoutCloseStrengthFilter,
    BreakoutDistanceFilter,
    BreakoutRetestFilter,
    BreakoutTrendFilter,
    CompressionFilter,
    ConsecutiveNarrowRangeFilter,
    EfficiencyRatioFilter,
    FailedBreakoutExclusionFilter,
    ExpansionBarFilter,
    GapUpFilter,
    HigherHighFilter,
    InsideBarFilter,
    OutsideBarFilter,
    PriorRangePositionFilter,
    RangeBreakoutFilter,
    RisingBaseFilter,
    TightRangeFilter,
)
from modules.refiner import StrategyParameterRefiner
from modules.strategies import ExitType, build_exit_config
from modules.strategy_types.base_strategy_type import BaseStrategyType


class _InlineBreakoutStrategy:
    direction = "LONG_ONLY"

    def __init__(
        self,
        filters: list[BaseFilter],
        hold_bars: int = 4,
        stop_distance_atr: float = 1.25,
        name: str | None = None,
        exit_type: ExitType | str | None = None,
        trailing_stop_atr: float | None = None,
        break_even_atr: float | None = None,
        early_exit_bars: int | None = None,
        exit_config=None,
    ):
        self.filters = filters
        self.hold_bars = hold_bars
        self.stop_distance_atr = stop_distance_atr
        self.exit_config = build_exit_config(
            exit_config=exit_config,
            exit_type=exit_type,
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_atr,
            trailing_stop_atr=trailing_stop_atr,
            break_even_atr=break_even_atr,
            early_exit_bars=early_exit_bars,
            default_hold_bars=hold_bars,
            default_stop_distance_points=stop_distance_atr,
        )
        self.name = name or f"ComboBreakout_{build_filter_combo_name(filters)}"

    def generate_signal(self, data: pd.DataFrame, i: int) -> int:
        for f in self.filters:
            if not f.passes(data, i):
                return 0
        return 1


# Module-level shared state — set once per worker via initializer, avoids re-serialising
# the full DataFrame with every task (critical for large datasets like 5m).
_breakout_shared_data: pd.DataFrame | None = None
_breakout_shared_cfg: EngineConfig | None = None


def _breakout_worker_init(data: pd.DataFrame, cfg: EngineConfig) -> None:
    global _breakout_shared_data, _breakout_shared_cfg
    _breakout_shared_data = data
    _breakout_shared_cfg = cfg


def _run_breakout_combo_case(args) -> dict[str, Any]:
    if isinstance(args, tuple):
        combo_classes, cfg = args
    else:
        combo_classes, cfg = args, _breakout_shared_cfg
    data = _breakout_shared_data
    strat_type = BreakoutStrategyType()

    filter_objects = strat_type.build_filter_objects_from_classes(combo_classes, timeframe=cfg.timeframe)
    strategy = strat_type.build_combinable_strategy(
        filters=filter_objects,
        hold_bars=strat_type.default_hold_bars,
        stop_distance_points=strat_type.default_stop_distance_points,
    )

    # Vectorized path: compute signal mask once, pass to engine
    signal_mask = compute_combined_signal_mask(filter_objects, data)

    engine = MasterStrategyEngine(data=data, config=cfg)
    engine.run(strategy=strategy, precomputed_signals=signal_mask)
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
        "max_drawdown": _pf(summary.get("Max Drawdown", 0.0)),
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


class _BreakoutRefinementFactory:
    def __init__(self, strat_inst, combo_classes: list[type], timeframe: str = "60m"):
        self.strat_inst = strat_inst
        self.combo_classes = combo_classes
        self.timeframe = timeframe

    def __call__(
        self,
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
        exit_type: ExitType | str | None = None,
        profit_target_atr: float | None = None,
        trailing_stop_atr: float | None = None,
        signal_exit_reference: str | None = None,
    ):
        return self.strat_inst.build_candidate_specific_strategy(
            self.combo_classes,
            hold_bars,
            stop_distance_points,
            min_avg_range,
            momentum_lookback,
            timeframe=self.timeframe,
            exit_type=exit_type,
            profit_target_atr=profit_target_atr,
            trailing_stop_atr=trailing_stop_atr,
            signal_exit_reference=signal_exit_reference,
        )


class BreakoutStrategyType(BaseStrategyType):
    name = "breakout"
    min_filters_per_combo = 3
    max_filters_per_combo = 5

    default_hold_bars = 4
    default_stop_distance_points = 1.25

    def get_supported_exit_types(self) -> list[ExitType]:
        return [ExitType.TIME_STOP, ExitType.TRAILING_STOP]

    def get_default_exit_type(self) -> ExitType:
        return ExitType.TIME_STOP

    def get_exit_parameter_grid_for_combo(
        self,
        promoted_combo_classes: list[type],
        timeframe: str = "60m",
    ) -> dict[str, list]:
        return {
            "exit_type": [ExitType.TIME_STOP, ExitType.TRAILING_STOP],
            "trailing_stop_atr": [1.5, 2.5, 3.5, 5.0],
            "break_even_atr": [None, 0.75],
            "early_exit_bars": [None, 3],
        }

    def get_required_sma_lengths(self, timeframe: str = "60m") -> list[int]:
        mult = get_timeframe_multiplier(timeframe)
        return scale_lookbacks([50, 200], mult, min_val=5)

    def get_required_avg_range_lookbacks(self, timeframe: str = "60m") -> list[int]:
        mult = get_timeframe_multiplier(timeframe)
        return scale_lookbacks([10, 20, 50], mult, min_val=5)

    def get_required_momentum_lookbacks(self, timeframe: str = "60m") -> list[int]:
        return []

    def build_default_sanity_filters(self) -> list[BaseFilter]:
        return [
            CompressionFilter(lookback=20, max_atr_mult=0.90),
            RangeBreakoutFilter(lookback=20),
            ExpansionBarFilter(lookback=20, expansion_multiplier=1.15),
            BreakoutTrendFilter(fast_length=50, slow_length=200),
            BreakoutCloseStrengthFilter(close_position_threshold=0.60),
        ]

    def build_default_strategy(self) -> _InlineBreakoutStrategy:
        return _InlineBreakoutStrategy(
            filters=self.build_default_sanity_filters(),
            hold_bars=self.default_hold_bars,
            stop_distance_atr=self.default_stop_distance_points,
            name="FilterBasedBreakoutStrategy",
        )

    def build_sanity_check_strategy(self) -> _InlineBreakoutStrategy:
        return self.build_default_strategy()

    def get_filter_classes(self) -> list[type]:
        return [
            CompressionFilter,
            RangeBreakoutFilter,
            ExpansionBarFilter,
            BreakoutRetestFilter,
            BreakoutTrendFilter,
            BreakoutCloseStrengthFilter,
            PriorRangePositionFilter,
            BreakoutDistanceFilter,
            RisingBaseFilter,
            TightRangeFilter,
            InsideBarFilter,
            OutsideBarFilter,
            ATRPercentileFilter,
            HigherHighFilter,
            GapUpFilter,
            EfficiencyRatioFilter,
            ATRExpansionRatioFilter,
            ConsecutiveNarrowRangeFilter,
            FailedBreakoutExclusionFilter,
        ]

    def build_filter_objects_from_classes(self, combo_classes: list[type], timeframe: str = "60m") -> list[BaseFilter]:
        mult = get_timeframe_multiplier(timeframe)
        fast_sma = max(10, round(50 * mult))
        slow_sma = max(20, round(200 * mult))
        lookback = max(5, round(20 * mult))

        filters: list[BaseFilter] = []

        for cls in combo_classes:
            if cls is EfficiencyRatioFilter:
                filters.append(EfficiencyRatioFilter(lookback=max(5, round(14 * mult)), min_ratio=0.45, mode="above"))
            elif cls is ATRExpansionRatioFilter:
                filters.append(ATRExpansionRatioFilter(short_period=10, long_period=50, threshold=1.10, mode="expanding"))
            elif cls is ConsecutiveNarrowRangeFilter:
                filters.append(ConsecutiveNarrowRangeFilter(lookback=5, range_ratio=0.80, min_narrow_count=3))
            elif cls is FailedBreakoutExclusionFilter:
                filters.append(FailedBreakoutExclusionFilter(lookback=3, range_lookback=lookback))
            elif cls is CompressionFilter:
                filters.append(CompressionFilter(lookback=lookback, max_atr_mult=0.90))
            elif cls is RangeBreakoutFilter:
                filters.append(RangeBreakoutFilter(lookback=lookback))
            elif cls is ExpansionBarFilter:
                filters.append(ExpansionBarFilter(lookback=lookback, expansion_multiplier=1.15))
            elif cls is BreakoutRetestFilter:
                filters.append(BreakoutRetestFilter(lookback=lookback, atr_buffer_mult=0.00))
            elif cls is BreakoutTrendFilter:
                filters.append(BreakoutTrendFilter(fast_length=fast_sma, slow_length=slow_sma))
            elif cls is BreakoutCloseStrengthFilter:
                filters.append(BreakoutCloseStrengthFilter(close_position_threshold=0.60))
            elif cls is PriorRangePositionFilter:
                filters.append(PriorRangePositionFilter(lookback=lookback, min_position_in_range=0.55))
            elif cls is BreakoutDistanceFilter:
                filters.append(BreakoutDistanceFilter(lookback=lookback, min_breakout_atr=0.05))
            elif cls is RisingBaseFilter:
                filters.append(RisingBaseFilter(lookback=max(3, round(5 * mult))))
            elif cls is TightRangeFilter:
                filters.append(TightRangeFilter(lookback=lookback, max_bar_range_mult=0.90))
            elif cls is ATRPercentileFilter:
                filters.append(ATRPercentileFilter(lookback=100, min_percentile=0.0, max_percentile=0.3))
            else:
                filters.append(cls())

        return filters

    def build_combinable_strategy(
        self,
        filters: list[BaseFilter],
        hold_bars: int,
        stop_distance_points: float,
    ) -> _InlineBreakoutStrategy:
        return _InlineBreakoutStrategy(
            filters=filters,
            hold_bars=hold_bars,
            stop_distance_atr=stop_distance_points,
            exit_type=self.get_default_exit_type(),
        )

    def build_candidate_specific_strategy(
        self,
        classes: list[type],
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
        timeframe: str = "60m",
        exit_type: ExitType | str | None = None,
        profit_target_atr: float | None = None,
        trailing_stop_atr: float | None = None,
        signal_exit_reference: str | None = None,
        break_even_atr: float | None = None,
        early_exit_bars: int | None = None,
    ) -> _InlineBreakoutStrategy:
        mult = get_timeframe_multiplier(timeframe)
        fast_sma = max(10, round(50 * mult))
        slow_sma = max(20, round(200 * mult))
        lookback = max(5, round(20 * mult))

        filters: list[BaseFilter] = []

        for cls in classes:
            if cls is CompressionFilter:
                # Always use the same default as build_filter_objects_from_classes.
                # During refinement, precomputed_signals override strategy.generate_signal(),
                # so min_avg_range never actually affected CompressionFilter entry decisions.
                filters.append(CompressionFilter(lookback=lookback, max_atr_mult=0.90))
            elif cls is RangeBreakoutFilter:
                filters.append(RangeBreakoutFilter(lookback=lookback))
            elif cls is ExpansionBarFilter:
                filters.append(ExpansionBarFilter(lookback=lookback, expansion_multiplier=1.15))
            elif cls is BreakoutRetestFilter:
                filters.append(BreakoutRetestFilter(lookback=lookback, atr_buffer_mult=0.00))
            elif cls is BreakoutTrendFilter:
                filters.append(BreakoutTrendFilter(fast_length=fast_sma, slow_length=slow_sma))
            elif cls is BreakoutCloseStrengthFilter:
                filters.append(BreakoutCloseStrengthFilter(close_position_threshold=0.60))
            elif cls is PriorRangePositionFilter:
                filters.append(PriorRangePositionFilter(lookback=lookback, min_position_in_range=0.55))
            elif cls is BreakoutDistanceFilter:
                filters.append(BreakoutDistanceFilter(lookback=lookback, min_breakout_atr=0.05))
            elif cls is RisingBaseFilter:
                filters.append(RisingBaseFilter(lookback=max(3, round(5 * mult))))
            elif cls is TightRangeFilter:
                filters.append(TightRangeFilter(lookback=lookback, max_bar_range_mult=0.90))
            elif cls is ATRPercentileFilter:
                filters.append(ATRPercentileFilter(lookback=100, min_percentile=0.0, max_percentile=0.3))
            elif cls is EfficiencyRatioFilter:
                filters.append(EfficiencyRatioFilter(lookback=max(5, round(14 * mult)), min_ratio=0.45, mode="above"))
            elif cls is ATRExpansionRatioFilter:
                filters.append(ATRExpansionRatioFilter(short_period=10, long_period=50, threshold=1.10, mode="expanding"))
            elif cls is ConsecutiveNarrowRangeFilter:
                filters.append(ConsecutiveNarrowRangeFilter(lookback=5, range_ratio=0.80, min_narrow_count=3))
            elif cls is FailedBreakoutExclusionFilter:
                filters.append(FailedBreakoutExclusionFilter(lookback=3, range_lookback=lookback))
            else:
                filters.append(cls())

        return _InlineBreakoutStrategy(
            filters=filters,
            hold_bars=hold_bars,
            stop_distance_atr=stop_distance_points,
            exit_type=exit_type or self.get_default_exit_type(),
            trailing_stop_atr=trailing_stop_atr,
            break_even_atr=break_even_atr,
            early_exit_bars=early_exit_bars,
            name=f"RefinedBreakout_HB{hold_bars}_ATR{stop_distance_points}_COMP{min_avg_range}_MOM{momentum_lookback}",
        )

    def get_promotion_thresholds(self) -> dict[str, float | bool]:
        return {
            "min_profit_factor": 0.70,
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
        base_hold_bars = [2, 3, 4, 5, 6, 8, 10]
        mult = get_timeframe_multiplier(timeframe)

        if mult != 1.0:
            scaled = sorted(set(max(1, round(h * mult)) for h in base_hold_bars))
            if len(scaled) < 4:
                scaled = sorted(set(scaled + [1, 2, 3, 5]))
        else:
            scaled = base_hold_bars

        grid = {
            "hold_bars": scaled,
            # stop_distance_points are ATR-based, unscaled
            "stop_distance_points": [0.5, 0.75, 1.0, 1.25, 1.5],
        }

        grid["min_avg_range"] = [0.60, 0.70, 0.80, 0.90, 1.00] if any(cls is CompressionFilter for cls in classes) else [0.0]
        grid["momentum_lookback"] = [0]
        grid.update(self.get_exit_parameter_grid_for_combo(classes, timeframe=timeframe))

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
        executor: Optional[Any] = None,
    ) -> pd.DataFrame:
        combinations = generate_filter_combinations(
            self.get_filter_classes(),
            self.min_filters_per_combo,
            self.max_filters_per_combo,
        )

        results: list[dict[str, Any]] = []

        try:
            if executor is not None:
                _executor = executor
            else:
                _executor = ProcessPoolExecutor(
                    max_workers=max_workers,
                    initializer=_breakout_worker_init,
                    initargs=(data, cfg),
                )
            try:
                tasks = [(combo, cfg) for combo in combinations]
                for idx, res in enumerate(_executor.map(_run_breakout_combo_case, tasks), start=1):
                    print(
                        f"  Combo {idx}/{len(combinations)} | {res['strategy_name']} | "
                        f"PF={res['profit_factor']:.2f} | Net={res['net_pnl']:.2f} | "
                        f"trades={res['total_trades']}"
                    )
                    res["filter_classes"] = combinations[idx - 1]
                    results.append(res)
                    if progress_callback is not None:
                        progress_callback(idx, len(combinations))
            finally:
                if executor is None:
                    _executor.shutdown(wait=True)
        except (OSError, PermissionError) as exc:
            print(f"\n[WARN] Parallel breakout sweep unavailable ({exc}). Falling back to sequential execution.")
            _breakout_worker_init(data, cfg)
            for idx, combo_classes in enumerate(combinations, start=1):
                res = _run_breakout_combo_case((combo_classes, cfg))
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

        # Compute filter signal mask once — reused across all refinement grid variants
        filter_objects = self.build_filter_objects_from_classes(classes, timeframe=timeframe)
        precomputed_signals = compute_combined_signal_mask(filter_objects, data)

        refiner = StrategyParameterRefiner(
            MasterStrategyEngine,
            data,
            _BreakoutRefinementFactory(self, classes, timeframe=timeframe),
            cfg,
            precomputed_signals=precomputed_signals,
        )

        refinement_df = refiner.run_refinement(
            hold_bars=grid["hold_bars"],
            stop_distance_points=grid["stop_distance_points"],
            min_avg_range=grid["min_avg_range"],
            momentum_lookback=grid["momentum_lookback"],
            exit_type=grid.get("exit_type"),
            trailing_stop_atr=grid.get("trailing_stop_atr"),
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
