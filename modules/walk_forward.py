"""Walk-forward validation utilities.

Replaces (or supplements) fixed IS/OOS split with rolling windowed analysis.
A single fixed-split IS/OOS is brittle: a strategy that fits well on 70% of
history may collapse one parameter perturbation away. Walk-forward asks the
sharper question: does the edge survive across rolling slices of history?

Design:
- Input is a DataFrame of trades with `exit_time` (datetime) and a PnL column.
- Window: train_years on the left, test_years on the right.
- Step the window forward step_years at a time, generate (train, test) pairs.
- Per window, compute t-statistic of mean trade PnL.
- Aggregate: mean test_t, min test_t, count of windows, all pairs returned
  for diagnostic.
- Pass criteria: mean test_t >= min_mean_t AND min test_t >= min_min_t AND
  n_windows >= min_windows.

This is a per-strategy validation layer — call once per accepted strategy
during the leaderboard / portfolio selection stage. Not a sweep-time check
(too expensive: needs trade-level reconstruction).

Reference: Pardo, R. (2008). The Evaluation and Optimization of Trading
Strategies. Wiley. Chapter on walk-forward analysis.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class WindowStat:
    """One (train, test) window's statistics."""
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    train_n: int
    test_n: int
    train_t: float
    test_t: float
    train_mean_pnl: float
    test_mean_pnl: float


@dataclass
class WalkForwardResult:
    """Aggregate walk-forward statistics for a single strategy.

    Pass criteria intentionally evaluated by `passes_gate()` rather than
    stored as a flag, so different consumers (leaderboard vs portfolio
    selector vs operator review) can apply different thresholds without
    re-running the analysis.
    """
    n_windows: int
    mean_test_t: float
    min_test_t: float
    median_test_t: float
    train_test_t_correlation: float  # high = train predicts test
    windows: list[WindowStat] = field(default_factory=list)

    def passes_gate(
        self,
        min_mean_t: float = 1.0,
        min_min_t: float = -0.5,
        min_windows: int = 3,
    ) -> bool:
        """Apply the standard walk-forward gate.

        - mean_test_t >= min_mean_t (edge holds on average)
        - min_test_t >= min_min_t (no catastrophic regime failure)
        - n_windows >= min_windows (enough samples to be meaningful)
        """
        if self.n_windows < min_windows:
            return False
        if not math.isfinite(self.mean_test_t) or not math.isfinite(self.min_test_t):
            return False
        return self.mean_test_t >= min_mean_t and self.min_test_t >= min_min_t

    def to_dict(self) -> dict:
        """Flat representation suitable for a DataFrame row."""
        return {
            "wf_n_windows": self.n_windows,
            "wf_mean_test_t": round(self.mean_test_t, 4),
            "wf_min_test_t": round(self.min_test_t, 4),
            "wf_median_test_t": round(self.median_test_t, 4),
            "wf_train_test_corr": round(self.train_test_t_correlation, 4),
        }


def _t_stat(pnls: np.ndarray) -> float:
    """One-sample t-statistic of the mean PnL against zero.

    Returns 0.0 for n < 2 or zero variance (degenerate inputs).
    """
    n = pnls.shape[0]
    if n < 2:
        return 0.0
    mu = float(pnls.mean())
    sd = float(pnls.std(ddof=1))
    if sd <= 0.0 or not math.isfinite(sd):
        return 0.0
    return mu / (sd / math.sqrt(n))


def compute_walk_forward(
    trades_df: pd.DataFrame,
    pnl_col: str = "net_pnl",
    time_col: str = "exit_time",
    train_years: int = 3,
    test_years: int = 1,
    step_years: int = 1,
    min_trades_per_window: int = 20,
) -> WalkForwardResult:
    """Compute walk-forward statistics for a single strategy's trades.

    Args:
        trades_df: DataFrame with columns including time_col (datetime-like)
                   and pnl_col (numeric). Order doesn't matter; will be sorted.
        pnl_col: column containing per-trade PnL.
        time_col: column containing trade exit timestamp.
        train_years: years in the train portion of each window.
        test_years: years in the test portion.
        step_years: how far the window advances each iteration.
        min_trades_per_window: skip windows where train OR test has fewer trades.

    Returns:
        WalkForwardResult. n_windows == 0 indicates the trade history was
        too short or sparse to form any valid window.
    """
    if trades_df is None or trades_df.empty:
        return WalkForwardResult(0, 0.0, 0.0, 0.0, 0.0)
    if pnl_col not in trades_df.columns or time_col not in trades_df.columns:
        return WalkForwardResult(0, 0.0, 0.0, 0.0, 0.0)

    df = trades_df[[time_col, pnl_col]].copy()
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df = df.dropna(subset=[time_col])
    if df.empty:
        return WalkForwardResult(0, 0.0, 0.0, 0.0, 0.0)

    df = df.sort_values(time_col).reset_index(drop=True)

    history_start = df[time_col].iloc[0]
    history_end = df[time_col].iloc[-1]
    span_years = (history_end - history_start).days / 365.25

    required_span = train_years + test_years
    if span_years < required_span:
        return WalkForwardResult(0, 0.0, 0.0, 0.0, 0.0)

    windows: list[WindowStat] = []
    train_start = history_start

    while True:
        train_end = train_start + pd.DateOffset(years=train_years)
        test_start = train_end
        test_end = test_start + pd.DateOffset(years=test_years)

        if test_end > history_end + pd.Timedelta(days=1):
            break

        train_mask = (df[time_col] >= train_start) & (df[time_col] < train_end)
        test_mask = (df[time_col] >= test_start) & (df[time_col] < test_end)

        train_pnls = df.loc[train_mask, pnl_col].to_numpy(dtype=float)
        test_pnls = df.loc[test_mask, pnl_col].to_numpy(dtype=float)

        if len(train_pnls) >= min_trades_per_window and len(test_pnls) >= min_trades_per_window:
            windows.append(WindowStat(
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                train_n=len(train_pnls),
                test_n=len(test_pnls),
                train_t=_t_stat(train_pnls),
                test_t=_t_stat(test_pnls),
                train_mean_pnl=float(train_pnls.mean()),
                test_mean_pnl=float(test_pnls.mean()),
            ))

        train_start = train_start + pd.DateOffset(years=step_years)

    if not windows:
        return WalkForwardResult(0, 0.0, 0.0, 0.0, 0.0)

    test_ts = np.array([w.test_t for w in windows], dtype=float)
    train_ts = np.array([w.train_t for w in windows], dtype=float)

    if len(test_ts) >= 2 and train_ts.std() > 0 and test_ts.std() > 0:
        corr = float(np.corrcoef(train_ts, test_ts)[0, 1])
    else:
        corr = 0.0

    return WalkForwardResult(
        n_windows=len(windows),
        mean_test_t=float(test_ts.mean()),
        min_test_t=float(test_ts.min()),
        median_test_t=float(np.median(test_ts)),
        train_test_t_correlation=corr,
        windows=windows,
    )


def annotate_dataframe_with_walk_forward(
    leaderboard_df: pd.DataFrame,
    trades_by_strategy: dict[str, pd.DataFrame],
    strategy_col: str = "leader_strategy_name",
    pnl_col: str = "net_pnl",
    time_col: str = "exit_time",
    train_years: int = 3,
    test_years: int = 1,
    step_years: int = 1,
    min_trades_per_window: int = 20,
    min_mean_t: float = 1.0,
    min_min_t: float = -0.5,
    min_windows: int = 3,
) -> pd.DataFrame:
    """Add walk-forward columns to a leaderboard DataFrame.

    Adds: wf_n_windows, wf_mean_test_t, wf_min_test_t, wf_median_test_t,
          wf_train_test_corr, wf_passes (boolean from passes_gate).

    Strategies missing from `trades_by_strategy` get NaN/0 columns and
    wf_passes=False — does not raise.

    Modifies df in place AND returns it for chaining.
    """
    if leaderboard_df is None or leaderboard_df.empty:
        return leaderboard_df
    if strategy_col not in leaderboard_df.columns:
        return leaderboard_df

    rows_added: list[dict] = []
    for _, row in leaderboard_df.iterrows():
        name = str(row[strategy_col])
        trades = trades_by_strategy.get(name)
        if trades is None or trades.empty:
            rows_added.append({
                "wf_n_windows": 0,
                "wf_mean_test_t": 0.0,
                "wf_min_test_t": 0.0,
                "wf_median_test_t": 0.0,
                "wf_train_test_corr": 0.0,
                "wf_passes": False,
            })
            continue

        result = compute_walk_forward(
            trades,
            pnl_col=pnl_col,
            time_col=time_col,
            train_years=train_years,
            test_years=test_years,
            step_years=step_years,
            min_trades_per_window=min_trades_per_window,
        )
        d = result.to_dict()
        d["wf_passes"] = result.passes_gate(
            min_mean_t=min_mean_t,
            min_min_t=min_min_t,
            min_windows=min_windows,
        )
        rows_added.append(d)

    addendum = pd.DataFrame(rows_added, index=leaderboard_df.index)
    for col in addendum.columns:
        leaderboard_df[col] = addendum[col]
    return leaderboard_df
