from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from modules.engine import EngineConfig


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

    @staticmethod
    def _parse_money(value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).replace("$", "").replace(",", "").strip()
        return float(text)

    @staticmethod
    def _parse_percent(value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).replace("%", "").strip()
        return float(text)

    def _calculate_years_in_sample(self) -> float:
        if self.data.empty:
            return 0.0

        start = self.data.index.min()
        end = self.data.index.max()
        total_days = (end - start).days

        if total_days <= 0:
            return 0.0

        return total_days / 365.25

    def run_refinement(
        self,
        hold_bars: list[int],
        stop_distance_points: list[float],
        min_avg_range: list[float],
        momentum_lookback: list[int],
        min_trades: int = 150,
        min_trades_per_year: float = 8.0,
    ) -> pd.DataFrame:
        self.results = []

        years_in_sample = self._calculate_years_in_sample()
        combinations = list(
            product(
                hold_bars,
                stop_distance_points,
                min_avg_range,
                momentum_lookback,
            )
        )

        total_runs = len(combinations)

        print("\n🎯 Running top-combo parameter refinement...")
        print(f"Total combinations: {total_runs}")
        print(f"Years in sample: {years_in_sample:.2f}")
        print(
            f"Trade filters: min_trades={min_trades}, "
            f"min_trades_per_year={min_trades_per_year:.2f}"
        )

        accepted_count = 0
        rejected_count = 0

        for run_number, (hb, stop_pts, min_range, mom_lb) in enumerate(combinations, start=1):
            print(
                f"  Run {run_number}/{total_runs} | "
                f"hold_bars={hb}, stop={stop_pts}, "
                f"min_avg_range={min_range}, momentum_lookback={mom_lb}"
            )

            strategy = self.strategy_factory(
                hold_bars=hb,
                stop_distance_points=float(stop_pts),
                min_avg_range=float(min_range),
                momentum_lookback=int(mom_lb),
            )

            engine = self.engine_class(data=self.data, config=self.config)
            engine.run(strategy=strategy)
            summary = engine.results()

            total_trades = int(summary["Total Trades"])
            trades_per_year = total_trades / years_in_sample if years_in_sample > 0 else 0.0

            passes_trade_filter = (
                total_trades >= min_trades
                and trades_per_year >= min_trades_per_year
            )

            if not passes_trade_filter:
                rejected_count += 1
                continue

            result = RefinementResult(
                strategy_name=str(summary["Strategy"]),
                hold_bars=int(hb),
                stop_distance_points=float(stop_pts),
                min_avg_range=float(min_range),
                momentum_lookback=int(mom_lb),
                total_trades=total_trades,
                trades_per_year=trades_per_year,
                passes_trade_filter=passes_trade_filter,
                net_pnl=self._parse_money(summary["Net PnL"]),
                gross_profit=self._parse_money(summary["Gross Profit"]),
                gross_loss=self._parse_money(summary["Gross Loss"]),
                average_trade=self._parse_money(summary["Average Trade"]),
                profit_factor=float(summary["Profit Factor"]),
                max_drawdown=self._parse_money(summary["Max Drawdown"]),
                win_rate=self._parse_percent(summary["Win Rate"]),
                average_mae_points=float(summary["Average MAE (pts)"]),
                average_mfe_points=float(summary["Average MFE (pts)"]),
            )
            self.results.append(result)
            accepted_count += 1

        print(f"\n✅ Accepted refinement sets: {accepted_count}")
        print(f"❌ Rejected refinement sets: {rejected_count}")

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

    def save_results_csv(self, filepath: str | Path) -> Path:
        df = self.results_dataframe()
        if df.empty:
            raise ValueError("No refinement results to save.")

        output_path = Path(filepath)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        return output_path