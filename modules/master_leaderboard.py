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

from modules.leaderboard_ranking import sort_aggregate_leaderboard
from modules.statistics import annotate_dataframe_with_dsr


def _count_sweep_trials(subdir: Path, strategy_type: str) -> int:
    """Count rows in the family's sweep results CSV (= number of combos tested).

    Returns 0 if the file does not exist; caller should treat 0 as "unknown"
    and fall back to a default trial count.
    """
    csv_path = subdir / f"{strategy_type}_filter_combination_sweep_results.csv"
    if not csv_path.exists():
        return 0
    try:
        # Cheap line count — header + rows
        with open(csv_path, encoding="utf-8") as f:
            n_lines = sum(1 for _ in f)
        return max(n_lines - 1, 0)  # subtract header
    except OSError:
        return 0


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

    if ranking == "bootcamp":
        return pd.DataFrame()

    if leaderboard_filename is None:
        leaderboard_filename = "family_leaderboard_results.csv"

    if not outputs_root.exists():
        return pd.DataFrame()

    leaderboard_paths = sorted(outputs_root.rglob(leaderboard_filename))
    for leaderboard_csv in leaderboard_paths:
        if not leaderboard_csv.is_file():
            continue

        subdir = leaderboard_csv.parent

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

        # Per-leader trial count: number of combos in the family's sweep CSV.
        # Falls back to 100 (a conservative default) if the sweep CSV is missing.
        if "strategy_type" in df.columns:
            df["n_trials_in_search"] = df["strategy_type"].apply(
                lambda st: _count_sweep_trials(subdir, str(st)) or 100
            )
        else:
            df["n_trials_in_search"] = 100

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

    combined = sort_aggregate_leaderboard(combined)

    combined = combined.reset_index(drop=True)
    combined.insert(0, "rank", range(1, len(combined) + 1))

    # Add Deflated Sharpe Ratio per leader. Trial count comes from the sweep
    # CSV row count populated above.
    if "leader_pf" in combined.columns and "leader_trades" in combined.columns:
        annotate_dataframe_with_dsr(
            combined,
            pf_col="leader_pf",
            n_trades_col="leader_trades",
            n_trials_col="n_trials_in_search",
        )

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
        "deflated_sharpe_ratio",
        "sharpe_per_trade",
        "n_trials_in_search",
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
    include_bootcamp_scores: bool = False,
    emit_cfd_alias: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    outputs_root = Path(outputs_root)
    outputs_root.mkdir(parents=True, exist_ok=True)

    classic = aggregate_master_leaderboard(
        outputs_root=outputs_root,
        min_pf=min_pf,
        min_oos_pf=min_oos_pf,
        ranking="classic",
    )
    bootcamp = pd.DataFrame()

    if not classic.empty:
        classic.to_csv(outputs_root / "master_leaderboard.csv", index=False)
        if emit_cfd_alias:
            classic.to_csv(outputs_root / "master_leaderboard_cfd.csv", index=False)

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
