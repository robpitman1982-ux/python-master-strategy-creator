from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Type

import pandas as pd

from modules.engine import EngineConfig


@dataclass
class OptimizationResult:
    strategy_name: str
    hold_bars: int
    stop_distance_points: float
    total_trades: int
    net_pnl: float
    gross_profit: float
    gross_loss: float
    average_trade: float
    profit_factor: float
    max_drawdown: float
    win_rate: float
    average_mae_points: float
    average_mfe_points: float


class StrategyOptimizer:
    """
    Runs simple grid-search optimization over strategy parameters.
    """

    def __init__(
        self,
        engine_class: Type,
        data: pd.DataFrame,
        strategy_class: Type,
        config: EngineConfig | None = None,
    ):
        self.engine_class = engine_class
        self.data = data
        self.strategy_class = strategy_class
        self.config = config or EngineConfig()
        self.results: list[OptimizationResult] = []

    @staticmethod
    def _parse_money(value: Any) -> float:
        """
        Converts strings like '$-200,201.50' into float.
        """
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).replace("$", "").replace(",", "").strip()
        return float(text)

    @staticmethod
    def _parse_percent(value: Any) -> float:
        """
        Converts strings like '34.84%' into float.
        """
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).replace("%", "").strip()
        return float(text)

    def run_grid_search(
        self,
        hold_bars: list[int],
        stop_distance_points: list[float],
        min_trades: int = 0,
    ) -> pd.DataFrame:
        """
        Runs all combinations of hold_bars and stop_distance_points.
        Returns a dataframe of optimization results.
        """
        self.results = []

        combinations = list(product(hold_bars, stop_distance_points))
        total_runs = len(combinations)

        print("\n🔍 Running optimization grid search...")
        print(f"Total combinations: {total_runs}")

        for run_number, (hb, stop_pts) in enumerate(combinations, start=1):
            print(
                f"  Run {run_number}/{total_runs} | "
                f"hold_bars={hb}, stop_distance_points={stop_pts}"
            )

            strategy = self.strategy_class()
            strategy.hold_bars = hb
            strategy.stop_distance_points = float(stop_pts)

            engine = self.engine_class(data=self.data, config=self.config)
            engine.run(strategy=strategy)

            summary = engine.results()
            total_trades = int(summary["Total Trades"])

            if total_trades < min_trades:
                continue

            result = OptimizationResult(
                strategy_name=str(summary["Strategy"]),
                hold_bars=hb,
                stop_distance_points=float(stop_pts),
                total_trades=total_trades,
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

        return self.results_dataframe()

    def results_dataframe(self) -> pd.DataFrame:
        if not self.results:
            return pd.DataFrame()

        df = pd.DataFrame([r.__dict__ for r in self.results])

        sort_columns = ["profit_factor", "average_trade", "net_pnl"]
        existing_sort_columns = [col for col in sort_columns if col in df.columns]

        if existing_sort_columns:
            df = df.sort_values(
                by=existing_sort_columns,
                ascending=[False] * len(existing_sort_columns),
            ).reset_index(drop=True)

        return df

    def display_dataframe(self) -> pd.DataFrame:
        """
        Returns a cleaner dataframe for terminal display.
        """
        df = self.results_dataframe()
        if df.empty:
            return df

        display_columns = [
            "hold_bars",
            "stop_distance_points",
            "total_trades",
            "profit_factor",
            "average_trade",
            "net_pnl",
            "max_drawdown",
            "win_rate",
            "average_mae_points",
            "average_mfe_points",
        ]

        available_columns = [col for col in display_columns if col in df.columns]
        display_df = df[available_columns].copy()

        money_columns = ["average_trade", "net_pnl", "max_drawdown"]
        for col in money_columns:
            if col in display_df.columns:
                display_df[col] = display_df[col].round(2)

        float_columns = [
            "stop_distance_points",
            "profit_factor",
            "win_rate",
            "average_mae_points",
            "average_mfe_points",
        ]
        for col in float_columns:
            if col in display_df.columns:
                display_df[col] = display_df[col].round(2)

        return display_df

    def top_results(self, n: int = 10) -> pd.DataFrame:
        df = self.display_dataframe()
        if df.empty:
            return df
        return df.head(n)

    def save_results_csv(self, filepath: str | Path) -> Path:
        """
        Saves the full optimization results dataframe to CSV.
        """
        df = self.results_dataframe()
        if df.empty:
            raise ValueError("No optimization results to save.")

        output_path = Path(filepath)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        df.to_csv(output_path, index=False)
        return output_path