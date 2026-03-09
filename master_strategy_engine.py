"""
Master Strategy Engine
Project: Python Master Strategy Creator
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from modules.data_loader import load_tradestation_csv


@dataclass
class EngineConfig:
    # Global Presets from Master Prompt
    initial_capital: float = 250_000.0
    risk_per_trade: float = 0.01  # ~1% equity
    symbol: str = "ES"

    # Friction Assumptions
    commission_per_contract: float = 2.00
    slippage_ticks: int = 4  # 2 ticks entry + 2 ticks exit total
    tick_value: float = 12.50  # ES tick value
    dollars_per_point: float = 50.0  # ES = $50 per point


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: str
    entry_price: float
    exit_price: float
    contracts: int
    pnl: float
    bars_held: int


class MasterStrategyEngine:
    def __init__(self, data: pd.DataFrame, config: Optional[EngineConfig] = None):
        if data is None or data.empty:
            raise ValueError("Data is empty. Cannot initialize engine.")

        self.data = data.copy()
        self.config = config or EngineConfig()

        self.initial_capital = float(self.config.initial_capital)
        self.current_capital = float(self.config.initial_capital)
        self.risk_per_trade = float(self.config.risk_per_trade)

        self.position: Optional[dict] = None
        self.trades: list[Trade] = []
        self.equity_curve: list[dict] = []

    def calculate_position_size_contracts(
        self,
        stop_distance_points: float,
        dollars_per_point: Optional[float] = None,
    ) -> int:
        """
        Calculates position size based on the 1% risk rule from the Master Prompt.
        """
        if dollars_per_point is None:
            dollars_per_point = self.config.dollars_per_point

        if stop_distance_points <= 0 or dollars_per_point <= 0:
            return 0

        risk_amount = self.current_capital * self.risk_per_trade
        contracts_float = risk_amount / (stop_distance_points * dollars_per_point)
        contracts = int(np.floor(contracts_float))

        # Minimum 1 contract if valid size > 0
        return max(1, contracts) if contracts > 0 else 0

    def generate_test_signal(self, i: int) -> int:
        """
        Very simple placeholder strategy:
        Go long if current close > previous close.
        Returns:
            1 = enter long
            0 = no action
        """
        if i < 1:
            return 0

        current_close = self.data["close"].iloc[i]
        previous_close = self.data["close"].iloc[i - 1]

        if current_close > previous_close:
            return 1

        return 0

    def run(self, hold_bars: int = 3, stop_distance_points: float = 10.0) -> None:
        """
        Minimal working backtest loop.

        Logic:
        - If flat, use a simple test signal to enter long.
        - If in a trade, exit after `hold_bars`.
        - Record trade and update equity.
        """
        if len(self.data) < 2:
            raise ValueError("Not enough data to run backtest.")

        self.position = None
        self.trades = []
        self.equity_curve = []

        slippage_points = self.config.slippage_ticks * (self.config.tick_value / self.config.dollars_per_point)

        for i in range(len(self.data)):
            bar = self.data.iloc[i]
            timestamp = self.data.index[i]
            close_price = float(bar["close"])

            # Record current equity snapshot
            self.equity_curve.append(
                {
                    "datetime": timestamp,
                    "equity": self.current_capital,
                }
            )

            # If in position, check exit
            if self.position is not None:
                bars_held = i - self.position["entry_index"]

                if bars_held >= hold_bars:
                    exit_price = close_price - slippage_points / 2.0
                    entry_price = self.position["entry_price"]
                    contracts = self.position["contracts"]

                    gross_pnl = (exit_price - entry_price) * self.config.dollars_per_point * contracts
                    commission_cost = contracts * self.config.commission_per_contract * 2.0
                    net_pnl = gross_pnl - commission_cost

                    self.current_capital += net_pnl

                    trade = Trade(
                        entry_time=self.position["entry_time"],
                        exit_time=timestamp,
                        direction="LONG",
                        entry_price=entry_price,
                        exit_price=exit_price,
                        contracts=contracts,
                        pnl=net_pnl,
                        bars_held=bars_held,
                    )
                    self.trades.append(trade)
                    self.position = None

                    continue

            # If flat, check entry
            if self.position is None:
                signal = self.generate_test_signal(i)

                if signal == 1:
                    contracts = self.calculate_position_size_contracts(
                        stop_distance_points=stop_distance_points
                    )

                    if contracts > 0:
                        entry_price = close_price + slippage_points / 2.0

                        self.position = {
                            "entry_index": i,
                            "entry_time": timestamp,
                            "entry_price": entry_price,
                            "contracts": contracts,
                        }

        # Optional: close any open trade on final bar
        if self.position is not None:
            final_bar = self.data.iloc[-1]
            final_time = self.data.index[-1]
            final_close = float(final_bar["close"])

            exit_price = final_close - slippage_points / 2.0
            entry_price = self.position["entry_price"]
            contracts = self.position["contracts"]
            bars_held = len(self.data) - 1 - self.position["entry_index"]

            gross_pnl = (exit_price - entry_price) * self.config.dollars_per_point * contracts
            commission_cost = contracts * self.config.commission_per_contract * 2.0
            net_pnl = gross_pnl - commission_cost

            self.current_capital += net_pnl

            trade = Trade(
                entry_time=self.position["entry_time"],
                exit_time=final_time,
                direction="LONG",
                entry_price=entry_price,
                exit_price=exit_price,
                contracts=contracts,
                pnl=net_pnl,
                bars_held=bars_held,
            )
            self.trades.append(trade)
            self.position = None

    def trades_dataframe(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()

        return pd.DataFrame(
            [
                {
                    "entry_time": t.entry_time,
                    "exit_time": t.exit_time,
                    "direction": t.direction,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "contracts": t.contracts,
                    "pnl": t.pnl,
                    "bars_held": t.bars_held,
                }
                for t in self.trades
            ]
        )

    def results(self) -> dict:
        total_pnl = self.current_capital - self.initial_capital
        total_trades = len(self.trades)
        wins = sum(1 for t in self.trades if t.pnl > 0)
        losses = sum(1 for t in self.trades if t.pnl <= 0)
        win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0

        return {
            "Symbol": self.config.symbol,
            "Initial Capital": f"${self.initial_capital:,.2f}",
            "Current Capital": f"${self.current_capital:,.2f}",
            "Net PnL": f"${total_pnl:,.2f}",
            "Total Trades": total_trades,
            "Wins": wins,
            "Losses": losses,
            "Win Rate": f"{win_rate:.2f}%",
        }


def print_data_summary(df: pd.DataFrame, name: str = "DATA") -> None:
    print(f"\n=== {name} SUMMARY ===")
    print(f"Rows: {len(df):,}")
    print(f"Start: {df.index.min()}")
    print(f"End:   {df.index.max()}")
    print("Columns:", list(df.columns))
    print("\nHead:")
    print(df.head(3))
    print("\nTail:")
    print(df.tail(3))


if __name__ == "__main__":
    CSV_PATH = Path("Data") / "ES_60m_2008_2026_tradestation.csv"

    print("Loading data from:", CSV_PATH)
    data = load_tradestation_csv(CSV_PATH, debug=True)
    print("Data loaded successfully.")

    print_data_summary(data, name="ES Data (2008+)")

    cfg = EngineConfig(
        initial_capital=250_000.0,
        risk_per_trade=0.01,
        symbol="ES",
    )
    engine = MasterStrategyEngine(data=data, config=cfg)

    print("\n🚀 Master Strategy Engine Initialized.")
    print("Engine Results Snapshot (Before Run):", engine.results())

    engine.run(hold_bars=3, stop_distance_points=10.0)

    print("\n✅ Backtest run completed.")
    print("Engine Results Snapshot (After Run):", engine.results())

    trades_df = engine.trades_dataframe()
    if not trades_df.empty:
        print("\nFirst 5 Trades:")
        print(trades_df.head())