"""
Master Leaderboard Aggregator

Scans all output directories under Outputs/ and consolidates accepted
strategies into cross-dataset leaderboards.

Usage:
    python -m modules.master_leaderboard
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def aggregate_master_leaderboard(
    outputs_root: str | Path = "Outputs",
    min_pf: float = 1.0,
    min_oos_pf: float = 1.0,
    leaderboard_filename: str | None = None,
    ranking: str = "classic",
) -> pd.DataFrame:
    """
    Scan all subdirectories of outputs_root for per-dataset leaderboard CSVs,
    filter to accepted rows, add market/timeframe columns, rank, and return.
    """
    outputs_root = Path(outputs_root)
    all_rows: list[pd.DataFrame] = []

    if leaderboard_filename is None:
        leaderboard_filename = (
            "family_leaderboard_bootcamp.csv"
            if ranking == "bootcamp"
            else "family_leaderboard_results.csv"
        )

    if not outputs_root.exists():
        return pd.DataFrame()

    for subdir in sorted(outputs_root.iterdir()):
        if not subdir.is_dir():
            continue

        leaderboard_csv = subdir / leaderboard_filename
        if not leaderboard_csv.exists():
            continue

        try:
            df = pd.read_csv(leaderboard_csv)
        except Exception:
            continue

        if df.empty:
            continue

        if "accepted_final" in df.columns:
            df = df[df["accepted_final"].astype(str).str.lower().isin(["true", "1", "yes"])]

        if df.empty:
            continue

        parts = subdir.name.split("_", 1)
        market = parts[0] if parts else subdir.name
        timeframe = parts[1] if len(parts) > 1 else "unknown"

        df = df.copy()
        df["market"] = market
        df["timeframe"] = timeframe
        all_rows.append(df)

    if not all_rows:
        return pd.DataFrame()

    combined = pd.concat(all_rows, ignore_index=True)

    if "leader_pf" in combined.columns:
        combined = combined[combined["leader_pf"].fillna(0.0) >= min_pf]
    if "oos_pf" in combined.columns:
        combined = combined[combined["oos_pf"].fillna(0.0) >= min_oos_pf]

    if combined.empty:
        return pd.DataFrame()

    sort_preferences = (
        ["bootcamp_score", "oos_pf", "leader_net_pnl"]
        if ranking == "bootcamp"
        else ["leader_net_pnl", "leader_pf"]
    )
    sort_cols = [c for c in sort_preferences if c in combined.columns]
    if sort_cols:
        combined = combined.sort_values(by=sort_cols, ascending=[False] * len(sort_cols))

    combined = combined.reset_index(drop=True)
    combined.insert(0, "rank", range(1, len(combined) + 1))

    preferred_cols = [
        "rank",
        "market",
        "timeframe",
        "strategy_type",
        "leader_strategy_name",
        "quality_flag",
        "leader_pf",
        "leader_avg_trade",
        "leader_net_pnl",
        "leader_trades",
        "leader_trades_per_year",
        "leader_win_rate",
        "bootcamp_score",
        "is_pf",
        "oos_pf",
        "recent_12m_pf",
        "leader_max_drawdown",
        "calmar_ratio",
        "oos_is_pf_ratio",
        "leader_pct_profitable_years",
        "leader_max_consecutive_losing_years",
        "leader_hold_bars",
        "leader_stop_distance_atr",
        "best_combo_filters",
    ]
    output_cols = [c for c in preferred_cols if c in combined.columns]
    extra_cols = [c for c in combined.columns if c not in output_cols]
    return combined[output_cols + extra_cols]


def write_master_leaderboards(
    outputs_root: str | Path = "Outputs",
    min_pf: float = 1.0,
    min_oos_pf: float = 1.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    outputs_root = Path(outputs_root)
    outputs_root.mkdir(parents=True, exist_ok=True)

    classic = aggregate_master_leaderboard(
        outputs_root=outputs_root,
        min_pf=min_pf,
        min_oos_pf=min_oos_pf,
        ranking="classic",
    )
    bootcamp = aggregate_master_leaderboard(
        outputs_root=outputs_root,
        min_pf=min_pf,
        min_oos_pf=min_oos_pf,
        ranking="bootcamp",
    )

    if not classic.empty:
        classic.to_csv(outputs_root / "master_leaderboard.csv", index=False)
    if not bootcamp.empty:
        bootcamp.to_csv(outputs_root / "master_leaderboard_bootcamp.csv", index=False)

    # Print locations of cross-timeframe output files if they exist
    cross_tf_files = [
        "cross_timeframe_correlation_matrix.csv",
        "cross_timeframe_portfolio_review.csv",
        "cross_timeframe_yearly_stats.csv",
    ]
    for fname in cross_tf_files:
        fpath = outputs_root / fname
        if fpath.exists():
            print(f"  Cross-TF output available: {fpath}")

    return classic, bootcamp


if __name__ == "__main__":
    classic_df, bootcamp_df = write_master_leaderboards()
    if classic_df.empty:
        print("No accepted strategies found across any dataset.")
    else:
        print(f"\n{'=' * 72}")
        print(f"MASTER LEADERBOARD - {len(classic_df)} accepted strategies")
        print(f"{'=' * 72}")
        print(classic_df.to_string(index=False))
        print(f"\nSaved to {Path('Outputs') / 'master_leaderboard.csv'}")
        if not bootcamp_df.empty:
            print(f"\n{'=' * 72}")
            print(f"BOOTCAMP MASTER LEADERBOARD - {len(bootcamp_df)} accepted strategies")
            print(f"{'=' * 72}")
            print(bootcamp_df.to_string(index=False))
            print(f"\nSaved to {Path('Outputs') / 'master_leaderboard_bootcamp.csv'}")
