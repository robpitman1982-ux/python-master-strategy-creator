from __future__ import annotations

import os
import inspect
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from itertools import product
from typing import Any, Callable, Optional

import pandas as pd

from modules.engine import EngineConfig
from modules.strategies import ExitType, normalize_exit_type

_WORKER_ENGINE_CLASS = None
_WORKER_DATA = None
_WORKER_STRATEGY_FACTORY = None
_WORKER_CONFIG = None
_WORKER_PRECOMPUTED_SIGNALS = None


def _parse_money(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("$", "").replace(",", "").strip()
    return float(text)


def _parse_percent(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("%", "").strip()
    return float(text)


def _calculate_years_in_sample(data: pd.DataFrame) -> float:
    if data.empty:
        return 0.0
    total_days = (data.index.max() - data.index.min()).days
    return total_days / 365.25 if total_days > 0 else 0.0


def _init_refinement_worker(
    engine_class: type,
    data: pd.DataFrame,
    strategy_factory: Callable[..., Any],
    config: EngineConfig,
    precomputed_signals=None,
) -> None:
    global _WORKER_ENGINE_CLASS, _WORKER_DATA, _WORKER_STRATEGY_FACTORY, _WORKER_CONFIG, _WORKER_PRECOMPUTED_SIGNALS
    _WORKER_ENGINE_CLASS = engine_class
    _WORKER_DATA = data
    _WORKER_STRATEGY_FACTORY = strategy_factory
    _WORKER_CONFIG = config
    _WORKER_PRECOMPUTED_SIGNALS = precomputed_signals


def _run_refinement_case(task: dict[str, Any]) -> dict[str, Any]:
    strategy_kwargs = {
        "hold_bars": task["hold_bars"],
        "stop_distance_points": task["stop_distance_points"],
        "min_avg_range": task["min_avg_range"],
        "momentum_lookback": task["momentum_lookback"],
        "exit_type": task.get("exit_type"),
        "profit_target_atr": task.get("profit_target_atr"),
        "trailing_stop_atr": task.get("trailing_stop_atr"),
        "signal_exit_reference": task.get("signal_exit_reference"),
        "break_even_atr": task.get("break_even_atr"),
        "early_exit_bars": task.get("early_exit_bars"),
    }
    signature = inspect.signature(_WORKER_STRATEGY_FACTORY)
    accepts_var_kwargs = any(
        param.kind == inspect.Parameter.VAR_KEYWORD
        for param in signature.parameters.values()
    )
    if not accepts_var_kwargs:
        strategy_kwargs = {
            key: value
            for key, value in strategy_kwargs.items()
            if key in signature.parameters
        }
    strategy = _WORKER_STRATEGY_FACTORY(**strategy_kwargs)

    engine = _WORKER_ENGINE_CLASS(data=_WORKER_DATA, config=_WORKER_CONFIG)
    if getattr(_WORKER_CONFIG, "use_vectorized_trades", False):
        engine.run_vectorized(strategy=strategy, precomputed_signals=_WORKER_PRECOMPUTED_SIGNALS)
    else:
        engine.run(strategy=strategy, precomputed_signals=_WORKER_PRECOMPUTED_SIGNALS)
    summary = engine.results()
    exit_config = getattr(strategy, "exit_config", None)

    total_trades = int(summary["Total Trades"])
    years_in_sample = float(task["years_in_sample"])
    trades_per_year = total_trades / years_in_sample if years_in_sample > 0 else 0.0

    min_trades = int(task["min_trades"])
    min_trades_per_year = float(task["min_trades_per_year"])

    passes_trade_filter = (
        total_trades >= min_trades and trades_per_year >= min_trades_per_year
    )

    reject_reason = "ACCEPT"
    if total_trades < min_trades:
        reject_reason = f"REJECT_LOW_TRADES({total_trades}<{min_trades})"
    elif trades_per_year < min_trades_per_year:
        reject_reason = f"REJECT_LOW_TRADES_PER_YEAR({trades_per_year:.2f}<{min_trades_per_year:.2f})"

    return {
        "strategy_name": str(summary["Strategy"]),
        "hold_bars": int(task["hold_bars"]),
        "stop_distance_points": float(task["stop_distance_points"]),
        "min_avg_range": float(task["min_avg_range"]),
        "momentum_lookback": int(task["momentum_lookback"]),
        "exit_type": (
            str(exit_config.exit_type.value)
            if exit_config is not None and getattr(exit_config, "exit_type", None) is not None
            else str(task.get("exit_type") or "")
        ),
        "trailing_stop_atr": (
            float(exit_config.trailing_stop_atr)
            if exit_config is not None and exit_config.trailing_stop_atr is not None
            else None
        ),
        "profit_target_atr": (
            float(exit_config.profit_target_atr)
            if exit_config is not None and exit_config.profit_target_atr is not None
            else None
        ),
        "signal_exit_reference": (
            str(exit_config.signal_exit_reference)
            if exit_config is not None and exit_config.signal_exit_reference
            else None
        ),
        "break_even_atr": (
            float(exit_config.break_even_atr)
            if exit_config is not None and exit_config.break_even_atr is not None
            else None
        ),
        "early_exit_bars": (
            int(exit_config.early_exit_bars)
            if exit_config is not None and exit_config.early_exit_bars is not None
            else None
        ),
        "total_trades": total_trades,
        "trades_per_year": trades_per_year,
        "passes_trade_filter": passes_trade_filter,
        "reject_reason": reject_reason,
        "net_pnl": _parse_money(summary["Net PnL"]),
        "gross_profit": _parse_money(summary["Gross Profit"]),
        "gross_loss": _parse_money(summary["Gross Loss"]),
        "average_trade": _parse_money(summary["Average Trade"]),
        "profit_factor": float(summary["Profit Factor"]),
        "max_drawdown": _parse_money(summary["Max Drawdown"]),
        "win_rate": _parse_percent(summary["Win Rate"]),
        "average_mae_points": float(summary["Average MAE (pts)"]),
        "average_mfe_points": float(summary["Average MFE (pts)"]),
        "is_trades": int(summary.get("IS Trades", 0)),
        "oos_trades": int(summary.get("OOS Trades", 0)),
        "is_pf": float(summary.get("IS PF", 0.0)),
        "oos_pf": float(summary.get("OOS PF", 0.0)),
        "recent_12m_trades": int(summary.get("Recent 12m Trades", 0)),
        "recent_12m_pf": float(summary.get("Recent 12m PF", 0.0)),
        "quality_flag": str(summary.get("Quality Flag", "UNKNOWN")),
        "quality_score": _parse_money(summary.get("Quality Score", "0.0")),
        "pct_profitable_years": _parse_money(summary.get("Pct Profitable Years", "0.0")),
        "max_consecutive_losing_years": int(summary.get("Max Consecutive Losing Years", 0)),
        "consistency_flag": str(summary.get("Consistency Flag", "INSUFFICIENT_DATA")),
    }


def _task_signature(task: dict[str, Any]) -> tuple:
    """Build dedup key from parameters that affect results."""
    return (
        task.get("hold_bars"),
        task.get("stop_distance_points"),
        task.get("min_avg_range"),
        task.get("momentum_lookback"),
        task.get("exit_type"),
        task.get("trailing_stop_atr"),
        task.get("profit_target_atr"),
        task.get("break_even_atr"),
        task.get("early_exit_bars"),
    )


@dataclass
class RefinementResult:
    strategy_name: str
    hold_bars: int
    stop_distance_points: float
    min_avg_range: float
    momentum_lookback: int
    exit_type: str
    trailing_stop_atr: float | None
    profit_target_atr: float | None
    signal_exit_reference: str | None
    break_even_atr: float | None
    early_exit_bars: int | None
    total_trades: int
    trades_per_year: float
    passes_trade_filter: bool
    reject_reason: str
    net_pnl: float
    gross_profit: float
    gross_loss: float
    average_trade: float
    profit_factor: float
    max_drawdown: float
    win_rate: float
    average_mae_points: float
    average_mfe_points: float
    is_trades: int
    oos_trades: int
    is_pf: float
    oos_pf: float
    recent_12m_trades: int
    recent_12m_pf: float
    quality_flag: str
    quality_score: float
    pct_profitable_years: float
    max_consecutive_losing_years: int
    consistency_flag: str


class StrategyParameterRefiner:
    def __init__(
        self,
        engine_class: type,
        data: pd.DataFrame,
        strategy_factory: Callable[..., Any],
        config: EngineConfig | None = None,
        precomputed_signals=None,
    ):
        self.engine_class = engine_class
        self.data = data
        self.strategy_factory = strategy_factory
        self.config = config or EngineConfig()
        self.precomputed_signals = precomputed_signals
        self.results: list[RefinementResult] = []

    def _default_max_workers(self) -> int:
        cpu_count = os.cpu_count() or 4
        return max(1, min(6, cpu_count - 2))

    def run_refinement(
        self,
        hold_bars: list[int],
        stop_distance_points: list[float],
        min_avg_range: list[float],
        momentum_lookback: list[int],
        exit_type: list[ExitType | str] | None = None,
        trailing_stop_atr: list[float] | None = None,
        profit_target_atr: list[float] | None = None,
        signal_exit_reference: list[str] | None = None,
        min_trades: int = 150,
        min_trades_per_year: float = 8.0,
        parallel: bool = True,
        max_workers: int | None = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> pd.DataFrame:
        self.results = []

        years_in_sample = _calculate_years_in_sample(self.data)
        base_combinations = list(product(hold_bars, stop_distance_points, min_avg_range, momentum_lookback))

        exit_types = list(exit_type or [])
        if not exit_types:
            exit_types = [None]

        trailing_stop_values = [float(v) for v in (trailing_stop_atr or [None]) if v is not None]
        profit_target_values = [float(v) for v in (profit_target_atr or [None]) if v is not None]
        signal_exit_values = [str(v) for v in (signal_exit_reference or [None]) if v]

        tasks: list[dict[str, Any]] = []
        for hb, stop, rng, mom in base_combinations:
            for requested_exit_type in exit_types:
                normalized_exit_type = (
                    normalize_exit_type(requested_exit_type)
                    if requested_exit_type is not None
                    else None
                )

                common = {
                    "hold_bars": hb,
                    "stop_distance_points": float(stop),
                    "min_avg_range": float(rng),
                    "momentum_lookback": int(mom),
                    "years_in_sample": years_in_sample,
                    "min_trades": min_trades,
                    "min_trades_per_year": min_trades_per_year,
                    "exit_type": normalized_exit_type.value if normalized_exit_type is not None else None,
                    "profit_target_atr": None,
                    "trailing_stop_atr": None,
                    "signal_exit_reference": None,
                }

                if normalized_exit_type == ExitType.TRAILING_STOP:
                    for trailing_value in trailing_stop_values or [1.5]:
                        task = dict(common)
                        task["trailing_stop_atr"] = float(trailing_value)
                        tasks.append(task)
                elif normalized_exit_type == ExitType.PROFIT_TARGET:
                    for target_value in profit_target_values or [1.0]:
                        task = dict(common)
                        task["profit_target_atr"] = float(target_value)
                        tasks.append(task)
                elif normalized_exit_type == ExitType.SIGNAL_EXIT:
                    for signal_value in signal_exit_values or ["fast_sma"]:
                        task = dict(common)
                        task["signal_exit_reference"] = signal_value
                        tasks.append(task)
                else:
                    tasks.append(common)

        # ── Deduplicate tasks before dispatch ────────────────────────────
        seen: set[tuple] = set()
        unique_tasks: list[dict[str, Any]] = []
        for task in tasks:
            sig = _task_signature(task)
            if sig not in seen:
                seen.add(sig)
                unique_tasks.append(task)
        removed = len(tasks) - len(unique_tasks)
        if removed > 0:
            print(f"Refinement: {len(tasks)} tasks -> {len(unique_tasks)} unique ({removed} duplicates removed)")
        tasks = unique_tasks

        total_runs = len(tasks)

        accepted_count = 0
        rejected_count = 0
        start_time = time.perf_counter()

        if max_workers is None:
            max_workers = self._default_max_workers()

        print("\nRunning top-combo parameter refinement...")
        print(f"Total combinations: {total_runs} | Years in sample: {years_in_sample:.2f}")
        print(f"Trade filters: min_trades={min_trades}, min_trades_per_year={min_trades_per_year:.2f}")

        if parallel and total_runs > 1:
            try:
                with ProcessPoolExecutor(
                    max_workers=max_workers,
                    initializer=_init_refinement_worker,
                    initargs=(self.engine_class, self.data, self.strategy_factory, self.config, self.precomputed_signals),
                ) as executor:
                    futures = {
                        executor.submit(_run_refinement_case, task): i
                        for i, task in enumerate(tasks)
                    }
                    completed = 0
                    for future in as_completed(futures):
                        completed += 1
                        try:
                            result = future.result()
                        except Exception as exc:
                            print(f"  Task failed: {exc}")
                            continue

                        if result["passes_trade_filter"]:
                            accepted_count += 1
                            self.results.append(RefinementResult(**result))
                        else:
                            rejected_count += 1

                        print(
                            f"  Done {completed}/{total_runs} | "
                            f"hb={result['hold_bars']}, stop={result['stop_distance_points']}, "
                            f"range={result['min_avg_range']}, mom={result['momentum_lookback']}, "
                            f"exit={result['exit_type']} | "
                            f"PF={result['profit_factor']:.2f} | Net={result['net_pnl']:.2f} | "
                            f"trades={result['total_trades']} | {result['reject_reason']}"
                        )
                        if progress_callback is not None:
                            progress_callback(completed, total_runs)
            except (OSError, PermissionError) as exc:
                print(f"\n[WARN] Parallel refinement unavailable ({exc}). Falling back to sequential execution.")
                parallel = False

        if not parallel or total_runs <= 1:
            _init_refinement_worker(self.engine_class, self.data, self.strategy_factory, self.config, self.precomputed_signals)
            for idx, task in enumerate(tasks, start=1):
                result = _run_refinement_case(task)

                if result["passes_trade_filter"]:
                    accepted_count += 1
                    self.results.append(RefinementResult(**result))
                else:
                    rejected_count += 1

                print(
                    f"  Done {idx}/{total_runs} | "
                    f"hb={result['hold_bars']}, stop={result['stop_distance_points']}, "
                    f"range={result['min_avg_range']}, mom={result['momentum_lookback']}, "
                    f"exit={result['exit_type']} | "
                    f"PF={result['profit_factor']:.2f} | Net={result['net_pnl']:.2f} | "
                    f"trades={result['total_trades']} | {result['reject_reason']}"
                )
                if progress_callback is not None:
                    progress_callback(idx, total_runs)

        print(f"\nAccepted refinement sets: {accepted_count}")
        print(f"Rejected refinement sets: {rejected_count}")
        print(f"Refinement runtime: {(time.perf_counter() - start_time):.2f} seconds")

        return self.results_dataframe()

    def results_dataframe(self) -> pd.DataFrame:
        if not self.results:
            return pd.DataFrame()

        return (
            pd.DataFrame([r.__dict__ for r in self.results])
            .sort_values(by=["net_pnl", "profit_factor", "average_trade"], ascending=[False, False, False])
            .reset_index(drop=True)
        )

    def display_dataframe(self) -> pd.DataFrame:
        df = self.results_dataframe()
        if df.empty:
            return df

        display_columns = [
            "hold_bars",
            "stop_distance_points",
            "min_avg_range",
            "momentum_lookback",
            "exit_type",
            "trailing_stop_atr",
            "profit_target_atr",
            "signal_exit_reference",
            "total_trades",
            "trades_per_year",
            "quality_flag",
            "is_pf",
            "oos_pf",
            "profit_factor",
            "average_trade",
            "net_pnl",
            "max_drawdown",
            "win_rate",
            "reject_reason",
        ]
        out = df[[c for c in display_columns if c in df.columns]].copy()

        for col in [
            "stop_distance_points",
            "min_avg_range",
            "trades_per_year",
            "trailing_stop_atr",
            "profit_target_atr",
            "profit_factor",
            "average_trade",
            "net_pnl",
            "max_drawdown",
            "win_rate",
            "is_pf",
            "oos_pf",
        ]:
            if col in out.columns:
                out[col] = out[col].round(2)

        return out

    def top_results(self, n: int = 10) -> pd.DataFrame:
        return self.display_dataframe().head(n)

    def summary_report(self, top_n: int = 10) -> dict[str, Any]:
        df = self.results_dataframe()
        if df.empty:
            return {}

        top_df = df.head(top_n)

        return {
            "best_pf": df.sort_values(by="profit_factor", ascending=False).iloc[0].to_dict(),
            "best_average_trade": df.sort_values(by="average_trade", ascending=False).iloc[0].to_dict(),
            "best_net_pnl": df.sort_values(by="net_pnl", ascending=False).iloc[0].to_dict(),
            "top_n": top_n,
            "common_hold_bars": Counter(top_df["hold_bars"].tolist()).most_common(),
            "common_stop_distance_points": Counter(top_df["stop_distance_points"].tolist()).most_common(),
            "common_min_avg_range": Counter(top_df["min_avg_range"].tolist()).most_common(),
            "common_momentum_lookback": Counter(top_df["momentum_lookback"].tolist()).most_common(),
        }

    def print_summary_report(self, top_n: int = 10) -> None:
        report = self.summary_report(top_n=top_n)
        if not report:
            print("\nNo refinement summary available.")
            return

        print("\nRefinement Summary Report")
        b = report["best_net_pnl"]
        print(
            f"\nBest Net PnL setting:\n"
            f"  hold_bars={b['hold_bars']}, stop={b['stop_distance_points']}, "
            f"min_avg_range={b['min_avg_range']}, momentum_lookback={b['momentum_lookback']} | "
            f"Flag={b['quality_flag']} | PF={b['profit_factor']:.2f}, "
            f"avg_trade={b['average_trade']:.2f}, net_pnl={b['net_pnl']:.2f}"
        )
