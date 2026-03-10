from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class PlateauSummary:
    top_n: int
    hold_bars_values: list[int]
    stop_distance_values: list[float]
    min_avg_range_values: list[float]
    momentum_lookback_values: list[int]
    hold_bars_range: str
    stop_distance_range: str
    min_avg_range_range: str
    momentum_lookback_range: str
    best_pf_row: dict[str, Any]
    best_avg_trade_row: dict[str, Any]
    best_net_pnl_row: dict[str, Any]


class PlateauAnalyzer:
    """
    Examines the top refinement rows and summarizes repeated value zones.

    This is not yet a sophisticated plateau detector, but it provides a
    strong first-pass "candidate zone" view of where good results cluster.
    """

    def __init__(self, results_df: pd.DataFrame):
        self.results_df = results_df.copy()

    @staticmethod
    def _format_range(values: list[Any]) -> str:
        if not values:
            return "N/A"

        unique_vals = sorted(set(values))
        if len(unique_vals) == 1:
            return str(unique_vals[0])

        return f"{unique_vals[0]} to {unique_vals[-1]}"

    def analyze(self, top_n: int = 10) -> PlateauSummary | None:
        if self.results_df.empty:
            return None

        top_df = self.results_df.head(top_n).copy()

        hold_vals = sorted(top_df["hold_bars"].tolist())
        stop_vals = sorted(top_df["stop_distance_points"].tolist())
        range_vals = sorted(top_df["min_avg_range"].tolist())
        mom_vals = sorted(top_df["momentum_lookback"].tolist())

        best_pf_row = (
            self.results_df.sort_values(by="profit_factor", ascending=False)
            .iloc[0]
            .to_dict()
        )
        best_avg_trade_row = (
            self.results_df.sort_values(by="average_trade", ascending=False)
            .iloc[0]
            .to_dict()
        )
        best_net_pnl_row = (
            self.results_df.sort_values(by="net_pnl", ascending=False)
            .iloc[0]
            .to_dict()
        )

        return PlateauSummary(
            top_n=top_n,
            hold_bars_values=hold_vals,
            stop_distance_values=stop_vals,
            min_avg_range_values=range_vals,
            momentum_lookback_values=mom_vals,
            hold_bars_range=self._format_range(hold_vals),
            stop_distance_range=self._format_range(stop_vals),
            min_avg_range_range=self._format_range(range_vals),
            momentum_lookback_range=self._format_range(mom_vals),
            best_pf_row=best_pf_row,
            best_avg_trade_row=best_avg_trade_row,
            best_net_pnl_row=best_net_pnl_row,
        )

    def print_report(self, top_n: int = 10) -> None:
        summary = self.analyze(top_n=top_n)
        if summary is None:
            print("\nNo plateau summary available.")
            return

        print("\n📍 Candidate Zone Report")
        print(f"Top rows analyzed: {summary.top_n}")

        print("\nCandidate parameter zones from top results:")
        print(f"  hold_bars: {summary.hold_bars_range} | values={sorted(set(summary.hold_bars_values))}")
        print(
            f"  stop_distance_points: {summary.stop_distance_range} | "
            f"values={sorted(set(summary.stop_distance_values))}"
        )
        print(
            f"  min_avg_range: {summary.min_avg_range_range} | "
            f"values={sorted(set(summary.min_avg_range_values))}"
        )
        print(
            f"  momentum_lookback: {summary.momentum_lookback_range} | "
            f"values={sorted(set(summary.momentum_lookback_values))}"
        )

        pf_row = summary.best_pf_row
        print("\nAnchor best-PF point inside candidate zone:")
        print(
            f"  hold_bars={pf_row['hold_bars']}, "
            f"stop={pf_row['stop_distance_points']}, "
            f"min_avg_range={pf_row['min_avg_range']}, "
            f"momentum_lookback={pf_row['momentum_lookback']} | "
            f"PF={pf_row['profit_factor']:.2f}, "
            f"avg_trade={pf_row['average_trade']:.2f}, "
            f"net_pnl={pf_row['net_pnl']:.2f}"
        )