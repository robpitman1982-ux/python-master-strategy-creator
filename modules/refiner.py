from __future__ import annotations

import os
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from modules.engine import EngineConfig


# -------------------------------------------------------------------
# Worker globals for parallel processing
# -------------------------------------------------------------------
_WORKER_ENGINE_CLASS = None
_WORKER_DATA = None
_WORKER_STRATEGY_FACTORY = None
_WORKER_CONFIG = None


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

    start = data.index.min()
    end = data.index.max()
    total_days = (end - start).days

    if total_days <= 0:
        return 0.0

    return total_days / 365.25


def _init_refinement_worker(
    engine_class: type,
    data: pd.DataFrame,
    strategy_factory: Callable[..., Any],
    config: EngineConfig,
) -> None:
    global _WORKER_ENGINE_CLASS, _WORKER_DATA, _WORKER_STRATEGY_FACTORY, _WORKER_CONFIG

    _WORKER_ENGINE_CLASS = engine_class
    _WORKER_DATA = data
    _WORKER_STRATEGY_FACTORY = strategy_factory
    _WORKER_CONFIG = config


def _run_refinement_case(task: dict[str, Any]) -> dict[str, Any]:
    strategy = _WORKER_STRATEGY_FACTORY(
        hold_bars=task["hold_bars"],
        stop_distance_points=task["stop_distance_points"],
        min_avg_range=task["min_avg_range"],
        momentum_lookback=task["momentum_lookback"],
    )

    engine = _WORKER_ENGINE_CLASS(data=_WORKER_DATA, config=_WORKER_CONFIG)
    engine.run(strategy=strategy)
    summary = engine.results()

    total_trades = int(summary["Total Trades"])
    years_in_sample = float(task["years_in_sample"])
    trades_per_year = total_trades / years_in_sample if years_in_sample > 0 else 0.0

    passes_trade_filter = (
        total_trades >= task["min_trades"]
        and trades_per_year >= task["min_trades_per_year"]
    )

    return {
        "strategy_name": str(summary["Strategy"]),
        "hold_bars": int(task["hold_bars"]),
        "stop_distance_points": float(task["stop_distance_points"]),
        "min_avg_range": float(task["min_avg_range"]),
        "momentum_lookback": int(task["momentum_lookback"]),
        "total_trades": total_trades,
        "trades_per_year": trades_per_year,
        "passes_trade_filter": passes_trade_filter,
        "net_pnl": _parse_money(summary["Net PnL"]),
        "gross_profit": _parse_money(summary["Gross Profit"]),
        "gross_loss": _parse_money(summary["Gross Loss"]),
        "average_trade": _parse_money(summary["Average Trade"]),
        "profit_factor": float(summary["Profit Factor"]),
        "max_drawdown": _parse_money(summary["Max Drawdown"]),
        "win_rate": _parse_percent(summary["Win Rate"]),
        "average_mae_points": float(summary["Average MAE (pts)"]),
        "average_mfe_points": float(summary["Average MFE (pts)"]),
    }


@dataclass
class RefinementResult:
    strategy_name: str
    hold_bars: int
    stop_distance_points: float
    min_avg_range: float
    momentum_lookback: int
    total_trades: int
    trades_per_year: float
    passes_trade_filter: bool
    net_pnl: float
    gross_profit: float
    gross_loss: float
    average_trade: float
    profit_factor: float
    max_drawdown: float
    win_rate: float
    average_mae_points: float
    average_mfe_points: float


class StrategyParameterRefiner:
    """
    Refines a chosen promising strategy/filter stack by sweeping a manageable
    grid of internal parameter values.
    """

    def __init__(
        self,
        engine_class: type,
        data: pd.DataFrame,
        strategy_factory: Callable[..., Any],
        config: EngineConfig | None = None,
    ):
        self.engine_class = engine_class
        self.data = data
        self.strategy_factory = strategy_factory
        self.config = config or EngineConfig()
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
        min_trades: int = 150,
        min_trades_per_year: float = 8.0,
        parallel: bool = True,
        max_workers: int | None = None,
    ) -> pd.DataFrame:
        self.results = []

        years_in_sample = _calculate_years_in_sample(self.data)
        combinations = list(
            product(
                hold_bars,
                stop_distance_points,
                min_avg_range,
                momentum_lookback,
            )
        )

        total_runs = len(combinations)
        accepted_count = 0
        rejected_count = 0
        start_time = time.perf_counter()

        if max_workers is None:
            max_workers = self._default_max_workers()

        print("\n🎯 Running top-combo parameter refinement...")
        print(f"Total combinations: {total_runs}")
        print(f"Years in sample: {years_in_sample:.2f}")
        print(
            f"Trade filters: min_trades={min_trades}, "
            f"min_trades_per_year={min_trades_per_year:.2f}"
        )
        print(
            f"Parallel mode: {'ON' if parallel else 'OFF'} | "
            f"max_workers={max_workers if parallel else 1}"
        )

        tasks = [
            {
                "hold_bars": hb,
                "stop_distance_points": float(stop_pts),
                "min_avg_range": float(min_range),
                "momentum_lookback": int(mom_lb),
                "years_in_sample": years_in_sample,
                "min_trades": min_trades,
                "min_trades_per_year": min_trades_per_year,
            }
            for hb, stop_pts, min_range, mom_lb in combinations
        ]

        if parallel and total_runs > 1:
            with ProcessPoolExecutor(
                max_workers=max_workers,
                initializer=_init_refinement_worker,
                initargs=(
                    self.engine_class,
                    self.data,
                    self.strategy_factory,
                    self.config,
                ),
            ) as executor:
                for idx, result in enumerate(executor.map(_run_refinement_case, tasks), start=1):
                    if result["passes_trade_filter"]:
                        accepted_count += 1
                        self.results.append(RefinementResult(**result))
                    else:
                        rejected_count += 1

                    print(
                        f"  Done {idx}/{total_runs} | "
                        f"hb={result['hold_bars']}, "
                        f"stop={result['stop_distance_points']}, "
                        f"range={result['min_avg_range']}, "
                        f"mom={result['momentum_lookback']} | "
                        f"PF={result['profit_factor']:.2f} | "
                        f"{'ACCEPT' if result['passes_trade_filter'] else 'REJECT'}"
                    )
        else:
            _init_refinement_worker(
                self.engine_class,
                self.data,
                self.strategy_factory,
                self.config,
            )

            for idx, task in enumerate(tasks, start=1):
                result = _run_refinement_case(task)

                if result["passes_trade_filter"]:
                    accepted_count += 1
                    self.results.append(RefinementResult(**result))
                else:
                    rejected_count += 1

                print(
                    f"  Done {idx}/{total_runs} | "
                    f"hb={result['hold_bars']}, "
                    f"stop={result['stop_distance_points']}, "
                    f"range={result['min_avg_range']}, "
                    f"mom={result['momentum_lookback']} | "
                    f"PF={result['profit_factor']:.2f} | "
                    f"{'ACCEPT' if result['passes_trade_filter'] else 'REJECT'}"
                )

        elapsed = time.perf_counter() - start_time

        print(f"\n✅ Accepted refinement sets: {accepted_count}")
        print(f"❌ Rejected refinement sets: {rejected_count}")
        print(f"⏱ Refinement runtime: {elapsed:.2f} seconds")

        return self.results_dataframe()

    def results_dataframe(self) -> pd.DataFrame:
        if not self.results:
            return pd.DataFrame()

        df = pd.DataFrame([r.__dict__ for r in self.results])
        df = df.sort_values(
            by=["profit_factor", "average_trade", "net_pnl"],
            ascending=[False, False, False],
        ).reset_index(drop=True)

        return df

    def display_dataframe(self) -> pd.DataFrame:
        df = self.results_dataframe()
        if df.empty:
            return df

        display_columns = [
            "hold_bars",
            "stop_distance_points",
            "min_avg_range",
            "momentum_lookback",
            "total_trades",
            "trades_per_year",
            "profit_factor",
            "average_trade",
            "net_pnl",
            "max_drawdown",
            "win_rate",
            "average_mae_points",
            "average_mfe_points",
        ]

        available_columns = [c for c in display_columns if c in df.columns]
        out = df[available_columns].copy()

        round_cols = [
            "stop_distance_points",
            "min_avg_range",
            "trades_per_year",
            "profit_factor",
            "average_trade",
            "net_pnl",
            "max_drawdown",
            "win_rate",
            "average_mae_points",
            "average_mfe_points",
        ]
        for col in round_cols:
            if col in out.columns:
                out[col] = out[col].round(2)

        return out

    def top_results(self, n: int = 10) -> pd.DataFrame:
        df = self.display_dataframe()
        if df.empty:
            return df
        return df.head(n)

    def summary_report(self, top_n: int = 10) -> dict[str, Any]:
        df = self.results_dataframe()
        if df.empty:
            return {}

        top_df = df.head(top_n)

        best_pf = df.sort_values(by="profit_factor", ascending=False).iloc[0].to_dict()
        best_avg_trade = df.sort_values(by="average_trade", ascending=False).iloc[0].to_dict()
        best_net_pnl = df.sort_values(by="net_pnl", ascending=False).iloc[0].to_dict()

        hold_counter = Counter(top_df["hold_bars"].tolist())
        stop_counter = Counter(top_df["stop_distance_points"].tolist())
        range_counter = Counter(top_df["min_avg_range"].tolist())
        mom_counter = Counter(top_df["momentum_lookback"].tolist())

        return {
            "best_pf": best_pf,
            "best_average_trade": best_avg_trade,
            "best_net_pnl": best_net_pnl,
            "top_n": top_n,
            "common_hold_bars": hold_counter.most_common(),
            "common_stop_distance_points": stop_counter.most_common(),
            "common_min_avg_range": range_counter.most_common(),
            "common_momentum_lookback": mom_counter.most_common(),
        }

    def print_summary_report(self, top_n: int = 10) -> None:
        report = self.summary_report(top_n=top_n)
        if not report:
            print("\nNo refinement summary available.")
            return

        print("\n🧠 Refinement Summary Report")

        best_pf = report["best_pf"]
        print("\nBest Profit Factor setting:")
        print(
            f"  hold_bars={best_pf['hold_bars']}, "
            f"stop={best_pf['stop_distance_points']}, "
            f"min_avg_range={best_pf['min_avg_range']}, "
            f"momentum_lookback={best_pf['momentum_lookback']} | "
            f"PF={best_pf['profit_factor']:.2f}, "
            f"avg_trade={best_pf['average_trade']:.2f}, "
            f"net_pnl={best_pf['net_pnl']:.2f}"
        )

        best_avg_trade = report["best_average_trade"]
        print("\nBest Average Trade setting:")
        print(
            f"  hold_bars={best_avg_trade['hold_bars']}, "
            f"stop={best_avg_trade['stop_distance_points']}, "
            f"min_avg_range={best_avg_trade['min_avg_range']}, "
            f"momentum_lookback={best_avg_trade['momentum_lookback']} | "
            f"avg_trade={best_avg_trade['average_trade']:.2f}, "
            f"PF={best_avg_trade['profit_factor']:.2f}, "
            f"net_pnl={best_avg_trade['net_pnl']:.2f}"
        )

        best_net_pnl = report["best_net_pnl"]
        print("\nBest Net PnL setting:")
        print(
            f"  hold_bars={best_net_pnl['hold_bars']}, "
            f"stop={best_net_pnl['stop_distance_points']}, "
            f"min_avg_range={best_net_pnl['min_avg_range']}, "
            f"momentum_lookback={best_net_pnl['momentum_lookback']} | "
            f"net_pnl={best_net_pnl['net_pnl']:.2f}, "
            f"PF={best_net_pnl['profit_factor']:.2f}, "
            f"avg_trade={best_net_pnl['average_trade']:.2f}"
        )

        print(f"\nMost common values in top {report['top_n']} results:")
        print(f"  hold_bars: {report['common_hold_bars']}")
        print(f"  stop_distance_points: {report['common_stop_distance_points']}")
        print(f"  min_avg_range: {report['common_min_avg_range']}")
        print(f"  momentum_lookback: {report['common_momentum_lookback']}")

    def save_results_csv(self, filepath: str | Path) -> Path:
        df = self.results_dataframe()
        if df.empty:
            raise ValueError("No refinement results to save.")

        output_path = Path(filepath)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        return output_path