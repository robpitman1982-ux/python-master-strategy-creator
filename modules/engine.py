from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class EngineConfig:
    # Global Presets from Master Prompt
    initial_capital: float = 250_000.0
    risk_per_trade: float = 0.01
    symbol: str = "ES"

    # Friction Assumptions
    commission_per_contract: float = 2.00
    slippage_ticks: int = 4
    tick_value: float = 12.50
    dollars_per_point: float = 50.0


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
    exit_reason: str


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
        if dollars_per_point is None:
            dollars_per_point = self.config.dollars_per_point

        if stop_distance_points <= 0 or dollars_per_point <= 0:
            return 0

        risk_amount = self.current_capital * self.risk_per_trade
        contracts_float = risk_amount / (stop_distance_points * dollars_per_point)
        contracts = int(np.floor(contracts_float))

        return max(1, contracts) if contracts > 0 else 0

    def _close_position(
        self,
        exit_time: pd.Timestamp,
        exit_price: float,
        bars_held: int,
        exit_reason: str,
    ) -> None:
        entry_price = self.position["entry_price"]
        contracts = self.position["contracts"]

        gross_pnl = (exit_price - entry_price) * self.config.dollars_per_point * contracts
        commission_cost = contracts * self.config.commission_per_contract * 2.0
        net_pnl = gross_pnl - commission_cost

        self.current_capital += net_pnl

        trade = Trade(
            entry_time=self.position["entry_time"],
            exit_time=exit_time,
            direction="LONG",
            entry_price=entry_price,
            exit_price=exit_price,
            contracts=contracts,
            pnl=net_pnl,
            bars_held=bars_held,
            exit_reason=exit_reason,
        )
        self.trades.append(trade)
        self.position = None

    def run(self, strategy, hold_bars: int = 3, stop_distance_points: float = 10.0) -> None:
        if len(self.data) < 2:
            raise ValueError("Not enough data to run backtest.")

        self.position = None
        self.trades = []
        self.equity_curve = []
        self.current_capital = float(self.initial_capital)

        slippage_points = self.config.slippage_ticks * (
            self.config.tick_value / self.config.dollars_per_point
        )

        for i in range(len(self.data)):
            bar = self.data.iloc[i]
            timestamp = self.data.index[i]
            close_price = float(bar["close"])
            low_price = float(bar["low"])

            self.equity_curve.append(
                {
                    "datetime": timestamp,
                    "equity": self.current_capital,
                }
            )

            if self.position is not None:
                bars_held = i - self.position["entry_index"]
                stop_price = self.position["stop_price"]

                # 1. Stop-loss check first
                if low_price <= stop_price:
                    stop_exit_price = stop_price - (slippage_points / 2.0)
                    self._close_position(
                        exit_time=timestamp,
                        exit_price=stop_exit_price,
                        bars_held=bars_held,
                        exit_reason="STOP",
                    )
                    continue

                # 2. Time exit second
                if bars_held >= hold_bars:
                    time_exit_price = close_price - (slippage_points / 2.0)
                    self._close_position(
                        exit_time=timestamp,
                        exit_price=time_exit_price,
                        bars_held=bars_held,
                        exit_reason="TIME",
                    )
                    continue

            if self.position is None:
                signal = strategy.generate_signal(self.data, i)

                if signal == 1:
                    contracts = self.calculate_position_size_contracts(
                        stop_distance_points=stop_distance_points
                    )

                    if contracts > 0:
                        entry_price = close_price + (slippage_points / 2.0)
                        stop_price = entry_price - stop_distance_points

                        self.position = {
                            "entry_index": i,
                            "entry_time": timestamp,
                            "entry_price": entry_price,
                            "stop_price": stop_price,
                            "contracts": contracts,
                        }

        if self.position is not None:
            final_bar = self.data.iloc[-1]
            final_time = self.data.index[-1]
            final_close = float(final_bar["close"])
            bars_held = len(self.data) - 1 - self.position["entry_index"]

            final_exit_price = final_close - (slippage_points / 2.0)
            self._close_position(
                exit_time=final_time,
                exit_price=final_exit_price,
                bars_held=bars_held,
                exit_reason="FINAL_BAR",
            )

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
                    "exit_reason": t.exit_reason,
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

        exit_reason_counts: dict[str, int] = {}
        for trade in self.trades:
            exit_reason_counts[trade.exit_reason] = exit_reason_counts.get(trade.exit_reason, 0) + 1

        return {
            "Symbol": self.config.symbol,
            "Initial Capital": f"${self.initial_capital:,.2f}",
            "Current Capital": f"${self.current_capital:,.2f}",
            "Net PnL": f"${total_pnl:,.2f}",
            "Total Trades": total_trades,
            "Wins": wins,
            "Losses": losses,
            "Win Rate": f"{win_rate:.2f}%",
            "Exit Reasons": exit_reason_counts,
        }