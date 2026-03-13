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
    symbol: str = "UNKNOWN"

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
    mae_points: float
    mfe_points: float


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
        self.strategy_name: str = "UnknownStrategy"

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
            mae_points=float(self.position["mae_points"]),
            mfe_points=float(self.position["mfe_points"]),
        )
        self.trades.append(trade)
        self.position = None

    def _update_open_position_excursions(self, bar_low: float, bar_high: float) -> None:
        if self.position is None:
            return

        entry_price = self.position["entry_price"]

        adverse_excursion = bar_low - entry_price
        favorable_excursion = bar_high - entry_price

        self.position["mae_points"] = min(self.position["mae_points"], adverse_excursion)
        self.position["mfe_points"] = max(self.position["mfe_points"], favorable_excursion)

    def run(
        self,
        strategy,
        hold_bars: Optional[int] = None,
        stop_distance_points: Optional[float] = None,
    ) -> None:
        if len(self.data) < 2:
            raise ValueError("Not enough data to run backtest.")

        self.position = None
        self.trades = []
        self.equity_curve = []
        self.current_capital = float(self.initial_capital)
        self.strategy_name = getattr(strategy, "name", "UnknownStrategy")

        if hold_bars is None:
            hold_bars = getattr(strategy, "hold_bars", 3)

        # Backward compatibility + ATR Injection
        stop_dist_val = stop_distance_points if stop_distance_points is not None else getattr(strategy, "stop_distance_points", 10.0)
        use_atr = hasattr(strategy, "stop_distance_atr")
        if use_atr:
            stop_mult = getattr(strategy, "stop_distance_atr")

        slippage_points = self.config.slippage_ticks * (
            self.config.tick_value / self.config.dollars_per_point
        )

        for i in range(len(self.data)):
            bar = self.data.iloc[i]
            timestamp = self.data.index[i]
            close_price = float(bar["close"])
            low_price = float(bar["low"])
            high_price = float(bar["high"])

            self.equity_curve.append(
                {
                    "datetime": timestamp,
                    "equity": self.current_capital,
                }
            )

            if self.position is not None:
                bars_held = i - self.position["entry_index"]

                self._update_open_position_excursions(
                    bar_low=low_price,
                    bar_high=high_price,
                )

                stop_price = self.position["stop_price"]

                if low_price <= stop_price:
                    stop_exit_price = stop_price - (slippage_points / 2.0)
                    self._close_position(
                        exit_time=timestamp,
                        exit_price=stop_exit_price,
                        bars_held=bars_held,
                        exit_reason="STOP",
                    )
                    continue

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
                    # Calculate dynamic stop based on current ATR
                    if use_atr:
                        current_atr = float(bar.get("atr_20", 10.0))
                        if pd.isna(current_atr) or current_atr <= 0:
                            current_atr = 10.0
                        stop_dist_pts = stop_mult * current_atr
                    else:
                        stop_dist_pts = stop_dist_val

                    contracts = self.calculate_position_size_contracts(
                        stop_distance_points=stop_dist_pts
                    )

                    if contracts > 0:
                        entry_price = close_price + (slippage_points / 2.0)
                        stop_price = entry_price - stop_dist_pts

                        self.position = {
                            "entry_index": i,
                            "entry_time": timestamp,
                            "entry_price": entry_price,
                            "stop_price": stop_price,
                            "contracts": contracts,
                            "mae_points": 0.0,
                            "mfe_points": 0.0,
                        }

        if self.position is not None:
            final_bar = self.data.iloc[-1]
            final_time = self.data.index[-1]
            final_close = float(final_bar["close"])
            final_low = float(final_bar["low"])
            final_high = float(final_bar["high"])
            bars_held = len(self.data) - 1 - self.position["entry_index"]

            self._update_open_position_excursions(
                bar_low=final_low,
                bar_high=final_high,
            )

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
                    "mae_points": t.mae_points,
                    "mfe_points": t.mfe_points,
                }
                for t in self.trades
            ]
        )

    def equity_curve_dataframe(self) -> pd.DataFrame:
        if not self.equity_curve:
            return pd.DataFrame()

        return pd.DataFrame(self.equity_curve)

    def _calculate_max_drawdown(self) -> float:
        equity_df = self.equity_curve_dataframe()
        if equity_df.empty or "equity" not in equity_df.columns:
            return 0.0

        running_peak = equity_df["equity"].cummax()
        drawdown = equity_df["equity"] - running_peak
        max_drawdown = float(drawdown.min())

        return max_drawdown

    def results(self) -> dict:
        total_pnl = self.current_capital - self.initial_capital
        total_trades = len(self.trades)

        gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = sum(t.pnl for t in self.trades if t.pnl < 0)
        net_pnl = gross_profit + gross_loss

        wins = sum(1 for t in self.trades if t.pnl > 0)
        losses = sum(1 for t in self.trades if t.pnl <= 0)
        win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
        average_trade = (net_pnl / total_trades) if total_trades > 0 else 0.0

        if gross_loss != 0:
            profit_factor = gross_profit / abs(gross_loss)
        else:
            profit_factor = 0.0

        max_drawdown = self._calculate_max_drawdown()

        exit_reason_counts: dict[str, int] = {}
        for trade in self.trades:
            exit_reason_counts[trade.exit_reason] = exit_reason_counts.get(trade.exit_reason, 0) + 1

        average_mae = (
            sum(t.mae_points for t in self.trades) / total_trades
            if total_trades > 0
            else 0.0
        )
        average_mfe = (
            sum(t.mfe_points for t in self.trades) / total_trades
            if total_trades > 0
            else 0.0
        )

        return {
            "Strategy": self.strategy_name,
            "Symbol": self.config.symbol,
            "Initial Capital": f"${self.initial_capital:,.2f}",
            "Current Capital": f"${self.current_capital:,.2f}",
            "Net PnL": f"${total_pnl:,.2f}",
            "Gross Profit": f"${gross_profit:,.2f}",
            "Gross Loss": f"${gross_loss:,.2f}",
            "Average Trade": f"${average_trade:,.2f}",
            "Profit Factor": f"{profit_factor:.2f}",
            "Max Drawdown": f"${max_drawdown:,.2f}",
            "Average MAE (pts)": f"{average_mae:.2f}",
            "Average MFE (pts)": f"{average_mfe:.2f}",
            "Total Trades": total_trades,
            "Wins": wins,
            "Losses": losses,
            "Win Rate": f"{win_rate:.2f}%",
            "Exit Reasons": exit_reason_counts,
        }