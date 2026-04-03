from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from modules.consistency import analyse_yearly_consistency
from modules.strategies import ExitConfig, ExitType, build_exit_config


@dataclass
class EngineConfig:
    initial_capital: float = 250_000.0
    risk_per_trade: float = 0.01
    symbol: str = "UNKNOWN"
    commission_per_contract: float = 2.00
    slippage_ticks: int = 4
    tick_value: float = 12.50
    dollars_per_point: float = 50.0
    oos_split_date: str = "2019-01-01"
    timeframe: str = "60m"
    direction: str = "long"  # "long" or "short"


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

        required_cols = {"open", "high", "low", "close"}
        missing = required_cols - set(data.columns)
        if missing:
            raise ValueError(f"Engine data is missing required columns: {missing}")

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

        risk_amount = self.initial_capital * self.risk_per_trade
        if risk_amount <= 0:
            return 0

        contracts_float = risk_amount / (stop_distance_points * dollars_per_point)

        # Minimum 1 contract if a valid position can be taken at all.
        if contracts_float > 0:
            return max(1, int(np.floor(contracts_float)))

        return 0

    def _close_position(
        self,
        exit_time: pd.Timestamp,
        exit_price: float,
        bars_held: int,
        exit_reason: str,
    ) -> None:
        if self.position is None:
            return

        entry_price = float(self.position["entry_price"])
        contracts = int(self.position["contracts"])
        pos_direction = self.position.get("direction", "long")

        if pos_direction == "short":
            gross_pnl = (entry_price - exit_price) * self.config.dollars_per_point * contracts
        else:
            gross_pnl = (exit_price - entry_price) * self.config.dollars_per_point * contracts
        commission_cost = contracts * self.config.commission_per_contract * 2.0
        net_pnl = gross_pnl - commission_cost

        self.current_capital += net_pnl

        trade = Trade(
            entry_time=self.position["entry_time"],
            exit_time=exit_time,
            direction=pos_direction.upper(),
            entry_price=entry_price,
            exit_price=float(exit_price),
            contracts=contracts,
            pnl=float(net_pnl),
            bars_held=int(bars_held),
            exit_reason=exit_reason,
            mae_points=float(self.position["mae_points"]),
            mfe_points=float(self.position["mfe_points"]),
        )
        self.trades.append(trade)
        self.position = None

    def _update_open_position_excursions(self, bar_low: float, bar_high: float) -> None:
        if self.position is None:
            return

        entry_price = float(self.position["entry_price"])
        adverse_excursion = bar_low - entry_price
        favorable_excursion = bar_high - entry_price

        self.position["mae_points"] = min(float(self.position["mae_points"]), adverse_excursion)
        self.position["mfe_points"] = max(float(self.position["mfe_points"]), favorable_excursion)

    def _resolve_stop_distance_points(self, strategy, bar: pd.Series) -> float:
        """
        Supports both:
        - fixed-point stops via strategy.stop_distance_points
        - ATR-multiple stops via strategy.stop_distance_atr
        """
        if hasattr(strategy, "stop_distance_atr"):
            stop_mult = float(getattr(strategy, "stop_distance_atr", 0.0) or 0.0)
            atr_col = "atr_20"
            current_atr = float(bar.get(atr_col, np.nan))

            if pd.isna(current_atr) or current_atr <= 0:
                current_atr = 10.0

            return stop_mult * current_atr

        return float(getattr(strategy, "stop_distance_points", 10.0) or 10.0)

    @staticmethod
    def _resolve_current_atr(bar: pd.Series) -> float:
        current_atr = float(bar.get("atr_20", np.nan))
        if pd.isna(current_atr) or current_atr <= 0:
            return 10.0
        return current_atr

    def _resolve_exit_config(
        self,
        strategy,
        hold_bars: int,
        stop_distance_points: float,
    ) -> ExitConfig:
        return build_exit_config(
            exit_config=getattr(strategy, "exit_config", None),
            hold_bars=hold_bars,
            stop_distance_points=stop_distance_points,
            default_hold_bars=hold_bars,
            default_stop_distance_points=stop_distance_points,
        )

    @staticmethod
    def _resolve_fast_sma_column(strategy, data: pd.DataFrame) -> str | None:
        candidate_lengths: list[int] = []
        for filter_obj in getattr(strategy, "filters", []):
            fast_length = getattr(filter_obj, "fast_length", None)
            if isinstance(fast_length, int) and fast_length > 0:
                candidate_lengths.append(fast_length)

        for length in sorted(set(candidate_lengths)):
            column = f"sma_{length}"
            if column in data.columns:
                return column

        sma_columns = sorted(
            col for col in data.columns
            if isinstance(col, str) and col.startswith("sma_")
        )
        return sma_columns[0] if sma_columns else None

    def _resolve_signal_exit_price(
        self,
        strategy,
        bar: pd.Series,
        close_price: float,
    ) -> float | None:
        exit_config: ExitConfig | None = getattr(strategy, "exit_config", None)
        if exit_config is None:
            return None

        if exit_config.exit_type != ExitType.SIGNAL_EXIT:
            return None

        if (exit_config.signal_exit_reference or "").strip().lower() != "fast_sma":
            return None

        sma_column = self._resolve_fast_sma_column(strategy, self.data)
        if sma_column is None:
            return None

        fast_sma = float(bar.get(sma_column, np.nan))
        if pd.isna(fast_sma):
            return None

        # Session 28 foundation rule for long mean reversion:
        # exit once price has reverted back to or above the fast SMA.
        if close_price >= fast_sma:
            return close_price

        return None

    def run(
        self,
        strategy,
        hold_bars: Optional[int] = None,
        stop_distance_atr: Optional[float] = None,
        precomputed_signals: Optional[np.ndarray] = None,
    ) -> None:
        if len(self.data) < 2:
            raise ValueError("Not enough data to run backtest.")

        self.position = None
        self.trades = []
        self.equity_curve = []
        self.current_capital = float(self.initial_capital)
        self.strategy_name = getattr(strategy, "name", "UnknownStrategy")

        # Pre-convert to numpy arrays to avoid the massive Pandas overhead in the loop
        close_arr = self.data["close"].values
        high_arr = self.data["high"].values
        low_arr = self.data["low"].values
        timestamps = self.data.index.values

        # Pre-convert all timestamps to pd.Timestamp once — avoids repeated construction in hot loop
        ts_list: list[pd.Timestamp] = list(pd.DatetimeIndex(timestamps))

        # Optional columns
        atr_arr = self.data["atr_20"].values if "atr_20" in self.data.columns else np.full(len(self.data), 10.0)
        
        # Resolve exit logic
        hb = int(hold_bars if hold_bars is not None else getattr(strategy, "hold_bars", 3))
        slippage_points = self.config.slippage_ticks * (self.config.tick_value / self.config.dollars_per_point)
        
        # Optimization: Identify entry signal indices in advance
        if precomputed_signals is not None:
            signal_indices = np.flatnonzero(precomputed_signals)
        else:
            signal_indices = None

        n_bars = len(close_arr)
        i = 0
        while i < n_bars:
            # 1. Update equity curve for the current bar
            ts_val = ts_list[i]
            self.equity_curve.append({"datetime": ts_val, "equity": self.current_capital})

            # 2. Manage Open Position
            if self.position is not None:
                # Extract values for readability
                low_p = low_arr[i]
                high_p = high_arr[i]
                close_p = close_arr[i]

                bars_held = i - int(self.position["entry_index"])
                entry_p = float(self.position["entry_price"])
                pos_dir = self.position.get("direction", "long")
                is_long_pos = pos_dir == "long"

                # Exit Checks
                protective_stop_price = float(self.position["stop_price"])
                exit_config: ExitConfig = self.position["exit_config"]

                if is_long_pos:
                    # Long: update excursions
                    self.position["mae_points"] = min(float(self.position["mae_points"]), low_p - entry_p)
                    self.position["mfe_points"] = max(float(self.position["mfe_points"]), high_p - entry_p)
                    self.position["highest_high_since_entry"] = max(float(self.position["highest_high_since_entry"]), high_p)

                    # Break-even stop modifier (before checking protective stop)
                    if exit_config.break_even_atr is not None:
                        entry_atr = float(self.position.get("entry_atr", 10.0))
                        mfe = float(self.position["mfe_points"])
                        if mfe >= exit_config.break_even_atr * entry_atr:
                            be_stop = entry_p + exit_config.break_even_lock_atr * entry_atr
                            if be_stop > protective_stop_price:
                                self.position["stop_price"] = be_stop
                                protective_stop_price = be_stop

                    # Long stop
                    if low_p <= protective_stop_price:
                        stop_exit_price = protective_stop_price - (slippage_points / 2.0)
                        self._close_position(exit_time=ts_val, exit_price=stop_exit_price, bars_held=bars_held, exit_reason="STOP")
                        i += 1
                        continue

                    # Long profit target
                    if exit_config.exit_type == ExitType.PROFIT_TARGET and exit_config.profit_target_atr:
                        target_price = float(self.position["profit_target_price"])
                        if high_p >= target_price:
                            self._close_position(exit_time=ts_val, exit_price=target_price - (slippage_points / 2.0), bars_held=bars_held, exit_reason="PROFIT_TARGET")
                            i += 1
                            continue

                    # Long trailing stop
                    if exit_config.exit_type == ExitType.TRAILING_STOP and exit_config.trailing_stop_atr:
                        current_atr = atr_arr[i] if not np.isnan(atr_arr[i]) else 10.0
                        trailing_stop_price = (
                            float(self.position["highest_high_since_entry"])
                            - float(exit_config.trailing_stop_atr) * current_atr
                        )
                        self.position["trailing_stop_price"] = max(
                            float(self.position["trailing_stop_price"]),
                            trailing_stop_price,
                        )
                        if low_p <= float(self.position["trailing_stop_price"]):
                            self._close_position(
                                exit_time=ts_val,
                                exit_price=float(self.position["trailing_stop_price"]) - (slippage_points / 2.0),
                                bars_held=bars_held,
                                exit_reason="TRAILING_STOP",
                            )
                            i += 1
                            continue

                    # Long signal exit
                    signal_exit_price = self._resolve_signal_exit_price(strategy, self.data.iloc[i], close_p)
                    if signal_exit_price is not None:
                        self._close_position(exit_time=ts_val, exit_price=signal_exit_price - (slippage_points / 2.0), bars_held=bars_held, exit_reason="SIGNAL_EXIT")
                        i += 1
                        continue

                else:
                    # SHORT position management
                    self.position["mae_points"] = min(float(self.position["mae_points"]), -(high_p - entry_p))
                    self.position["mfe_points"] = max(float(self.position["mfe_points"]), -(low_p - entry_p))
                    self.position["lowest_low_since_entry"] = min(float(self.position["lowest_low_since_entry"]), low_p)

                    # Break-even stop modifier for shorts
                    if exit_config.break_even_atr is not None:
                        entry_atr = float(self.position.get("entry_atr", 10.0))
                        mfe = float(self.position["mfe_points"])
                        if mfe >= exit_config.break_even_atr * entry_atr:
                            be_stop = entry_p - exit_config.break_even_lock_atr * entry_atr
                            if be_stop < protective_stop_price:
                                self.position["stop_price"] = be_stop
                                protective_stop_price = be_stop

                    # Short stop (stop is ABOVE entry)
                    if high_p >= protective_stop_price:
                        stop_exit_price = protective_stop_price + (slippage_points / 2.0)
                        self._close_position(exit_time=ts_val, exit_price=stop_exit_price, bars_held=bars_held, exit_reason="STOP")
                        i += 1
                        continue

                    # Short profit target (target is BELOW entry)
                    if exit_config.exit_type == ExitType.PROFIT_TARGET and exit_config.profit_target_atr:
                        target_price = float(self.position["profit_target_price"])
                        if low_p <= target_price:
                            self._close_position(exit_time=ts_val, exit_price=target_price + (slippage_points / 2.0), bars_held=bars_held, exit_reason="PROFIT_TARGET")
                            i += 1
                            continue

                    # Short trailing stop (tracks lowest low since entry)
                    if exit_config.exit_type == ExitType.TRAILING_STOP and exit_config.trailing_stop_atr:
                        current_atr = atr_arr[i] if not np.isnan(atr_arr[i]) else 10.0
                        trailing_stop_price = (
                            float(self.position["lowest_low_since_entry"])
                            + float(exit_config.trailing_stop_atr) * current_atr
                        )
                        self.position["trailing_stop_price"] = min(
                            float(self.position["trailing_stop_price"]),
                            trailing_stop_price,
                        )
                        if high_p >= float(self.position["trailing_stop_price"]):
                            self._close_position(
                                exit_time=ts_val,
                                exit_price=float(self.position["trailing_stop_price"]) + (slippage_points / 2.0),
                                bars_held=bars_held,
                                exit_reason="TRAILING_STOP",
                            )
                            i += 1
                            continue

                # Early exit: cut losers after N bars if still losing
                if exit_config.early_exit_bars is not None and bars_held >= exit_config.early_exit_bars:
                    if is_long_pos:
                        unrealized = close_p - entry_p
                    else:
                        unrealized = entry_p - close_p
                    if unrealized < 0:
                        if is_long_pos:
                            early_price = close_p - (slippage_points / 2.0)
                        else:
                            early_price = close_p + (slippage_points / 2.0)
                        self._close_position(exit_time=ts_val, exit_price=early_price, bars_held=bars_held, exit_reason="EARLY_EXIT")
                        i += 1
                        continue

                # Time exit (same for both long and short)
                if bars_held >= hb:
                    if is_long_pos:
                        time_exit_price = close_p - (slippage_points / 2.0)
                    else:
                        time_exit_price = close_p + (slippage_points / 2.0)
                    self._close_position(exit_time=ts_val, exit_price=time_exit_price, bars_held=bars_held, exit_reason="TIME")
                    i += 1
                    continue

            # 3. Entry Logic
            if self.position is None:
                # FAST PATH: Skip forward to the next index where a signal actually exists
                if signal_indices is not None:
                    idx_search = np.searchsorted(signal_indices, i)
                    if idx_search < len(signal_indices):
                        next_signal_i = signal_indices[idx_search]
                        # Jump i to next_signal_i if we were going to iterate over dead space
                        if next_signal_i > i:
                            # Fill equity curve for skipped bars (bar i already appended above)
                            cap = self.current_capital
                            self.equity_curve.extend(
                                [{"datetime": ts_list[j], "equity": cap} for j in range(i + 1, next_signal_i)]
                            )
                            i = next_signal_i
                            ts_val = ts_list[i]  # update after skip
                    else:
                        # No more signals in the entire dataset, we can finish
                        cap = self.current_capital
                        self.equity_curve.extend(
                            [{"datetime": ts_list[j], "equity": cap} for j in range(i + 1, n_bars)]
                        )
                        break

                # Check for signal (now we know i is at a signal bar if signal_indices exists)
                signal = precomputed_signals[i] if precomputed_signals is not None else strategy.generate_signal(self.data, i)
                cfg_direction = getattr(self.config, "direction", "long")

                if signal:
                    cur_close = close_arr[i]
                    cur_high = high_arr[i]
                    cur_low  = low_arr[i]
                    cur_atr = atr_arr[i] if not np.isnan(atr_arr[i]) else 10.0

                    if stop_distance_atr is not None:
                        stop_dist_pts = float(stop_distance_atr) * cur_atr
                    else:
                        stop_dist_pts = self._resolve_stop_distance_points(strategy, self.data.iloc[i])

                    if stop_dist_pts <= 0:
                        i += 1
                        continue

                    exit_config = self._resolve_exit_config(strategy, hb, stop_dist_pts)
                    contracts = self.calculate_position_size_contracts(stop_distance_points=stop_dist_pts)

                    if contracts > 0:
                        if cfg_direction == "short":
                            entry_price = cur_close - (slippage_points / 2.0)
                            stop_price = entry_price + stop_dist_pts
                            self.position = {
                                "direction": "short",
                                "entry_index": i,
                                "entry_time": ts_val,
                                "entry_price": entry_price,
                                "stop_price": stop_price,
                                "entry_atr": cur_atr,
                                "lowest_low_since_entry": cur_low,
                                "trailing_stop_price": stop_price,
                                "profit_target_price": (
                                    entry_price - float(exit_config.profit_target_atr) * cur_atr
                                    if exit_config.profit_target_atr is not None
                                    else float("nan")
                                ),
                                "exit_config": exit_config,
                                "contracts": contracts,
                                "mae_points": 0.0,
                                "mfe_points": 0.0,
                            }
                        else:
                            entry_price = cur_close + (slippage_points / 2.0)
                            stop_price = entry_price - stop_dist_pts
                            self.position = {
                                "direction": "long",
                                "entry_index": i,
                                "entry_time": ts_val,
                                "entry_price": entry_price,
                                "stop_price": stop_price,
                                "entry_atr": cur_atr,
                                "highest_high_since_entry": cur_high,
                                "trailing_stop_price": stop_price,
                                "profit_target_price": (
                                    entry_price + float(exit_config.profit_target_atr) * cur_atr
                                    if exit_config.profit_target_atr is not None
                                    else float("nan")
                                ),
                                "exit_config": exit_config,
                                "contracts": contracts,
                                "mae_points": 0.0,
                                "mfe_points": 0.0,
                            }

            i += 1

        # 4. Handle End of Data
        if self.position is not None:
            final_time = self.data.index[-1]
            final_close = float(close_arr[-1])
            bars_held = len(self.data) - 1 - int(self.position["entry_index"])
            final_entry = float(self.position["entry_price"])
            pos_dir_final = self.position.get("direction", "long")

            if pos_dir_final == "short":
                self.position["mae_points"] = min(float(self.position["mae_points"]), -(high_arr[-1] - final_entry))
                self.position["mfe_points"] = max(float(self.position["mfe_points"]), -(low_arr[-1] - final_entry))
                self._close_position(
                    exit_time=final_time,
                    exit_price=final_close + (slippage_points / 2.0),
                    bars_held=bars_held,
                    exit_reason="FINAL_BAR",
                )
            else:
                self.position["mae_points"] = min(float(self.position["mae_points"]), low_arr[-1] - final_entry)
                self.position["mfe_points"] = max(float(self.position["mfe_points"]), high_arr[-1] - final_entry)
                self._close_position(
                    exit_time=final_time,
                    exit_price=final_close - (slippage_points / 2.0),
                    bars_held=bars_held,
                    exit_reason="FINAL_BAR",
                )

    def trades_dataframe(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([t.__dict__ for t in self.trades])

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
        return float(drawdown.min())

    @staticmethod
    def calculate_quality_score(
        is_pf: float,
        oos_pf: float,
        recent_pf: float,
        total_trades: int,
        is_trades: int,
        oos_trades: int,
        pct_profitable_years: float | None = None,
        max_consecutive_losing_years: int = 0,
    ) -> float:
        """
        Continuous quality score from 0.0 to 1.0.
        Rewards IS and OOS profit factors both above 1.0, balance between
        IS and OOS, higher trade counts, strong recent performance, and
        year-over-year consistency.
        """
        avg_pf = (is_pf + oos_pf) / 2.0
        pf_strength = max(0.0, min(1.0, (avg_pf - 0.8) / 1.2))

        if max(is_pf, oos_pf) > 0:
            pf_ratio = min(is_pf, oos_pf) / max(is_pf, oos_pf)
        else:
            pf_ratio = 0.0
        balance_score = pf_ratio

        trade_confidence = min(1.0, math.log1p(total_trades) / math.log1p(300))

        recent_score = max(0.0, min(1.0, (recent_pf - 0.5) / 2.0))

        oos_penalty = 1.0 if oos_trades >= 10 else 0.3

        # Component 6: Yearly consistency (neutral 0.5 if insufficient data)
        if pct_profitable_years is not None:
            streak_penalty = max(0.0, 1.0 - max_consecutive_losing_years * 0.15)
            consistency_component = pct_profitable_years * streak_penalty
        else:
            consistency_component = 0.5

        score = (
            pf_strength * 0.25
            + balance_score * 0.20
            + trade_confidence * 0.15
            + recent_score * 0.15
            + oos_penalty * 0.10
            + consistency_component * 0.15
        )

        return round(max(0.0, min(1.0, score)), 4)

    @staticmethod
    def _calc_pf_from_trade_list(trade_list: list[Trade]) -> float:
        gross_profit = sum(t.pnl for t in trade_list if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in trade_list if t.pnl < 0))

        if gross_loss > 0:
            return gross_profit / gross_loss

        if gross_profit > 0:
            return float(gross_profit)

        return 0.0

    def results(self) -> dict:
        total_pnl = self.current_capital - self.initial_capital
        total_trades = len(self.trades)

        gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss_raw = sum(t.pnl for t in self.trades if t.pnl < 0)
        gross_loss_abs = abs(gross_loss_raw)
        net_pnl = gross_profit + gross_loss_raw

        wins = sum(1 for t in self.trades if t.pnl > 0)
        losses = sum(1 for t in self.trades if t.pnl <= 0)
        win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
        average_trade = (net_pnl / total_trades) if total_trades > 0 else 0.0

        if gross_loss_abs > 0:
            profit_factor = gross_profit / gross_loss_abs
        elif gross_profit > 0:
            profit_factor = float(gross_profit)
        else:
            profit_factor = 0.0

        max_drawdown = self._calculate_max_drawdown()

        oos_split_date = pd.to_datetime(self.config.oos_split_date)

        if self.trades:
            max_date = max(t.exit_time for t in self.trades)
            recent_cutoff = max_date - pd.Timedelta(days=365)

            is_trades_list = [t for t in self.trades if t.exit_time < oos_split_date]
            oos_trades_list = [t for t in self.trades if t.exit_time >= oos_split_date]
            recent_trades_list = [t for t in self.trades if t.exit_time >= recent_cutoff]

            is_pf = self._calc_pf_from_trade_list(is_trades_list)
            oos_pf = self._calc_pf_from_trade_list(oos_trades_list)
            recent_pf = self._calc_pf_from_trade_list(recent_trades_list)

            is_trades_count = len(is_trades_list)
            oos_trades_count = len(oos_trades_list)
            recent_trades_count = len(recent_trades_list)
        else:
            is_pf = oos_pf = recent_pf = 0.0
            is_trades_count = oos_trades_count = recent_trades_count = 0

        # --- Quality flag with borderline detection ---
        BOUNDARY_BUFFER = 0.05

        if is_trades_count + oos_trades_count == 0:
            quality_flag = "NO_TRADES"
        elif is_trades_count < 50 and oos_trades_count >= 50:
            quality_flag = "LOW_IS_SAMPLE"
        elif is_trades_count >= 50 and oos_trades_count < 25:
            quality_flag = "EDGE_DECAYED_OOS"
        elif is_pf < 1.0 and oos_pf >= 1.2:
            quality_flag = "REGIME_DEPENDENT"
        elif is_pf > 1.2 and oos_pf < 1.0:
            quality_flag = "BROKEN_IN_OOS"
        elif is_pf >= 1.15 and oos_pf >= 1.15:
            quality_flag = "ROBUST"
        elif is_pf >= 1.0 and oos_pf >= 1.0:
            quality_flag = "STABLE"
        else:
            quality_flag = "MARGINAL"

        if quality_flag in ("ROBUST", "STABLE", "MARGINAL"):
            thresholds = [1.0, 1.15, 1.2]
            near_boundary = any(
                abs(pf - t) < BOUNDARY_BUFFER
                for pf in (is_pf, oos_pf)
                for t in thresholds
            )
            if near_boundary:
                quality_flag += "_BORDERLINE"

        # --- Yearly consistency analysis ---
        consistency = analyse_yearly_consistency(self.trades)

        quality_score = self.calculate_quality_score(
            is_pf=is_pf,
            oos_pf=oos_pf,
            recent_pf=recent_pf,
            total_trades=total_trades,
            is_trades=is_trades_count,
            oos_trades=oos_trades_count,
            pct_profitable_years=consistency["pct_profitable_years"] if consistency["consistency_flag"] != "INSUFFICIENT_DATA" else None,
            max_consecutive_losing_years=consistency["max_consecutive_losing_years"],
        )

        exit_reason_counts: dict[str, int] = {}
        for trade in self.trades:
            exit_reason_counts[trade.exit_reason] = exit_reason_counts.get(trade.exit_reason, 0) + 1

        average_mae = (
            sum(t.mae_points for t in self.trades) / total_trades if total_trades > 0 else 0.0
        )
        average_mfe = (
            sum(t.mfe_points for t in self.trades) / total_trades if total_trades > 0 else 0.0
        )

        return {
            "Strategy": self.strategy_name,
            "Symbol": self.config.symbol,
            "Initial Capital": f"${self.initial_capital:,.2f}",
            "Current Capital": f"${self.current_capital:,.2f}",
            "Net PnL": f"${total_pnl:,.2f}",
            "Gross Profit": f"${gross_profit:,.2f}",
            "Gross Loss": f"${gross_loss_raw:,.2f}",
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
            "IS Trades": is_trades_count,
            "OOS Trades": oos_trades_count,
            "IS PF": f"{is_pf:.2f}",
            "OOS PF": f"{oos_pf:.2f}",
            "Recent 12m Trades": recent_trades_count,
            "Recent 12m PF": f"{recent_pf:.2f}",
            "Quality Flag": quality_flag,
            "Quality Score": f"{quality_score:.4f}",
            "Pct Profitable Years": f"{consistency['pct_profitable_years']:.4f}",
            "Max Consecutive Losing Years": consistency["max_consecutive_losing_years"],
            "Consistency Flag": consistency["consistency_flag"],
        }
