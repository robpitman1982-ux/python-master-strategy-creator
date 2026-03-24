"""
Bootcamp leaderboard report utility.

Usage:
    python -m modules.bootcamp_report --outputs-dir Outputs
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from modules.master_leaderboard import aggregate_master_leaderboard


def load_bootcamp_leaderboard(outputs_dir: str | Path = "Outputs") -> pd.DataFrame:
    outputs_dir = Path(outputs_dir)
    master_csv = outputs_dir / "master_leaderboard_bootcamp.csv"

    if master_csv.exists():
        try:
            df = pd.read_csv(master_csv)
            if not df.empty:
                return df
        except Exception:
            pass

    return aggregate_master_leaderboard(outputs_root=outputs_dir, ranking="bootcamp")


def build_bootcamp_report(outputs_dir: str | Path = "Outputs", top_n: int = 10) -> pd.DataFrame:
    leaderboard = load_bootcamp_leaderboard(outputs_dir=outputs_dir)
    if leaderboard.empty:
        return leaderboard

    sort_cols = [c for c in ["bootcamp_score", "oos_pf", "leader_net_pnl"] if c in leaderboard.columns]
    if sort_cols:
        leaderboard = leaderboard.sort_values(by=sort_cols, ascending=[False] * len(sort_cols))

    keep_cols = [
        "rank",
        "market",
        "timeframe",
        "strategy_type",
        "leader_strategy_name",
        "bootcamp_score",
        "leader_pf",
        "oos_pf",
        "leader_max_drawdown",
        "leader_trades_per_year",
        "quality_flag",
    ]
    leaderboard = leaderboard[[c for c in keep_cols if c in leaderboard.columns]].copy()
    return leaderboard.head(top_n).reset_index(drop=True)


def format_bootcamp_report(report_df: pd.DataFrame) -> str:
    if report_df.empty:
        return "No Bootcamp leaderboard data found."

    display = report_df.copy()
    if "bootcamp_score" in display.columns:
        display["bootcamp_score"] = display["bootcamp_score"].map(lambda v: f"{float(v):.2f}")
    if "leader_pf" in display.columns:
        display["leader_pf"] = display["leader_pf"].map(lambda v: f"{float(v):.2f}")
    if "oos_pf" in display.columns:
        display["oos_pf"] = display["oos_pf"].map(lambda v: f"{float(v):.2f}")
    if "leader_max_drawdown" in display.columns:
        display["leader_max_drawdown"] = display["leader_max_drawdown"].map(lambda v: f"{float(v):.2f}")
    if "leader_trades_per_year" in display.columns:
        display["leader_trades_per_year"] = display["leader_trades_per_year"].map(lambda v: f"{float(v):.2f}")

    return display.to_string(index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print a summary of Bootcamp-ranked strategies.")
    parser.add_argument("--outputs-dir", type=str, default="Outputs", help="Outputs directory to inspect.")
    parser.add_argument("--top-n", type=int, default=10, help="Number of rows to print.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_df = build_bootcamp_report(outputs_dir=args.outputs_dir, top_n=args.top_n)
    print(format_bootcamp_report(report_df))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
