"""
Master Leaderboard Aggregator

Scans all output directories under Outputs/ and consolidates every accepted
strategy leader into one ranked master table.

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
) -> pd.DataFrame:
    """
    Scan all subdirectories of outputs_root for family_leaderboard_results.csv,
    filter to accepted rows, add market/timeframe columns, rank, and return.

    Parameters
    ----------
    outputs_root:
        Root directory to scan (e.g. "Outputs").
    min_pf:
        Minimum overall profit factor to include in the master leaderboard.
    min_oos_pf:
        Minimum out-of-sample profit factor to include.

    Returns
    -------
    pd.DataFrame with columns: rank, market, timeframe, plus all leaderboard columns.
    Empty DataFrame if no accepted strategies found.
    """
    outputs_root = Path(outputs_root)
    all_rows: list[pd.DataFrame] = []

    if not outputs_root.exists():
        return pd.DataFrame()

    for subdir in sorted(outputs_root.iterdir()):
        if not subdir.is_dir():
            continue

        leaderboard_csv = subdir / "family_leaderboard_results.csv"
        if not leaderboard_csv.exists():
            continue

        try:
            df = pd.read_csv(leaderboard_csv)
        except Exception:
            continue

        if df.empty:
            continue

        # Filter to accepted rows only
        if "accepted_final" in df.columns:
            df = df[df["accepted_final"].astype(str).str.lower().isin(["true", "1", "yes"])]

        if df.empty:
            continue

        # Extract market and timeframe from directory name (e.g. "ES_60m" → "ES", "60m")
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

    # Apply optional PF filters
    if "leader_pf" in combined.columns:
        combined = combined[combined["leader_pf"].fillna(0.0) >= min_pf]
    if "oos_pf" in combined.columns:
        combined = combined[combined["oos_pf"].fillna(0.0) >= min_oos_pf]

    if combined.empty:
        return pd.DataFrame()

    # Sort by net pnl then PF descending
    sort_cols = [c for c in ["leader_net_pnl", "leader_pf"] if c in combined.columns]
    if sort_cols:
        combined = combined.sort_values(by=sort_cols, ascending=[False] * len(sort_cols))

    combined = combined.reset_index(drop=True)
    combined.insert(0, "rank", range(1, len(combined) + 1))

    # Ensure preferred output columns are present (extra columns OK)
    preferred_cols = [
        "rank", "market", "timeframe", "strategy_type", "leader_strategy_name",
        "quality_flag", "leader_pf", "leader_avg_trade", "leader_net_pnl", "leader_trades",
        "is_pf", "oos_pf", "recent_12m_pf", "leader_hold_bars", "leader_stop_distance_points",
        "best_combo_filters",
    ]
    output_cols = [c for c in preferred_cols if c in combined.columns]
    extra_cols = [c for c in combined.columns if c not in output_cols]
    combined = combined[output_cols + extra_cols]

    return combined


if __name__ == "__main__":
    df = aggregate_master_leaderboard()
    if df.empty:
        print("No accepted strategies found across any dataset.")
    else:
        print(f"\n{'=' * 72}")
        print(f"MASTER LEADERBOARD — {len(df)} accepted strategies")
        print(f"{'=' * 72}")
        print(df.to_string(index=False))
        output_path = Path("Outputs") / "master_leaderboard.csv"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        print(f"\nSaved to {output_path}")
