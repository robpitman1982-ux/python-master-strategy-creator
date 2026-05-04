"""Backfill best_refined_filter_class_names on existing family_leaderboard_results.csv.

Session 97 Bug #3 fix: leaderboard CSVs written before commit aa961ff lack the
best_refined_filter_class_names + best_refined_filters columns. Without them,
the rebuild path loads the wrong filter combo when the refined winner came
from a different promoted candidate than `best_combo_*` (the best raw-sweep
combo).

This script reads each leaderboard CSV, looks up the matching row in
<strategy_type>_top_combo_refinement_results_narrow.csv (matching the leader's
hold_bars/stop/range/momentum + exit_type + signal_exit_reference +
trailing_stop_atr + profit_target_atr, then taking max net_pnl on ties), and
writes the missing columns back to the leaderboard.

Idempotent: if a leaderboard already has best_refined_filter_class_names
populated for a row, it is left alone.

Usage:
    python scripts/backfill_best_refined_filters.py \\
        --output-dir Outputs/nq_5m_long_bases/NQ_5m
    # Or scan multiple:
    python scripts/backfill_best_refined_filters.py \\
        --output-dir Outputs/nq_5m_long_bases/NQ_5m \\
        --output-dir Outputs/nq_5m_short_bases/NQ_5m \\
        --output-dir Outputs/nq_5m_subtypes/NQ_5m
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd


def _safe_eq(a, b) -> bool:
    """Equality that treats NaN==NaN as True."""
    a_nan = a is None or (isinstance(a, float) and math.isnan(a))
    b_nan = b is None or (isinstance(b, float) and math.isnan(b))
    if a_nan and b_nan:
        return True
    if a_nan or b_nan:
        return False
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)


def _find_refined_combo(
    refinement_df: pd.DataFrame,
    leader_strategy_name: str,
    leader_hold_bars,
    leader_stop_atr,
    leader_min_avg_range,
    leader_momentum_lookback,
    leader_exit_type,
    leader_signal_exit_reference,
    leader_trailing_stop_atr,
    leader_profit_target_atr,
    leader_net_pnl,
) -> tuple[str, str] | None:
    """Find the refinement row matching the leader, return (filters, filter_class_names)."""
    if refinement_df.empty:
        return None

    df = refinement_df
    mask = df["strategy_name"].astype(str) == str(leader_strategy_name)
    if not mask.any():
        return None
    df = df[mask]

    def _matches_col(df_, col, val):
        if col not in df_.columns:
            return df_
        return df_[df_[col].apply(lambda x: _safe_eq(x, val))]

    df = _matches_col(df, "hold_bars", leader_hold_bars)
    df = _matches_col(df, "stop_distance_points", leader_stop_atr)
    df = _matches_col(df, "min_avg_range", leader_min_avg_range)
    df = _matches_col(df, "momentum_lookback", leader_momentum_lookback)
    df = _matches_col(df, "exit_type", leader_exit_type)
    df = _matches_col(df, "signal_exit_reference", leader_signal_exit_reference)
    df = _matches_col(df, "trailing_stop_atr", leader_trailing_stop_atr)
    df = _matches_col(df, "profit_target_atr", leader_profit_target_atr)

    if df.empty:
        return None

    # Tie-break: prefer the row whose net_pnl matches the leader's. Otherwise
    # take max net_pnl (the leader is selected as max-net_pnl winner).
    if pd.notna(leader_net_pnl):
        df = df.assign(_pnl_diff=(df["net_pnl"] - float(leader_net_pnl)).abs())
        df = df.sort_values("_pnl_diff").reset_index(drop=True)
        winner = df.iloc[0]
    else:
        winner = df.sort_values("net_pnl", ascending=False).iloc[0]

    filters_str = str(winner.get("combo_filters", "") or "")
    classes_str = str(winner.get("combo_filter_class_names", "") or "")
    return filters_str, classes_str


def backfill_leaderboard(output_dir: Path) -> dict[str, str]:
    """Patch one leaderboard CSV in-place. Returns row-level outcomes."""
    leaderboard_path = output_dir / "family_leaderboard_results.csv"
    if not leaderboard_path.exists():
        return {"_error": f"missing leaderboard: {leaderboard_path}"}

    lb = pd.read_csv(leaderboard_path)
    if lb.empty:
        return {"_error": "empty leaderboard"}

    # Ensure target columns exist.
    if "best_refined_filters" not in lb.columns:
        lb["best_refined_filters"] = ""
    if "best_refined_filter_class_names" not in lb.columns:
        lb["best_refined_filter_class_names"] = ""

    outcomes: dict[str, str] = {}

    for idx, row in lb.iterrows():
        strategy_type = str(row.get("strategy_type", "")).strip()
        if not strategy_type:
            continue

        leader_source = str(row.get("leader_source", "")).strip().lower()
        existing_classes = str(row.get("best_refined_filter_class_names", "") or "").strip()

        # Skip non-refined rows: leader is the raw combo, no need to look up
        # refinement data.
        if leader_source != "refined":
            outcomes[strategy_type] = "SKIPPED_NOT_REFINED"
            continue

        # Idempotent: skip rows already populated.
        if existing_classes and existing_classes.lower() not in {"nan", "none", ""}:
            outcomes[strategy_type] = "SKIPPED_ALREADY_POPULATED"
            continue

        refinement_csv = output_dir / f"{strategy_type}_top_combo_refinement_results_narrow.csv"
        if not refinement_csv.exists():
            outcomes[strategy_type] = "MISSING_REFINEMENT_CSV"
            continue

        try:
            refinement_df = pd.read_csv(refinement_csv)
        except Exception as exc:
            outcomes[strategy_type] = f"READ_ERROR: {exc}"
            continue

        match = _find_refined_combo(
            refinement_df,
            leader_strategy_name=row.get("leader_strategy_name", ""),
            leader_hold_bars=row.get("leader_hold_bars"),
            leader_stop_atr=row.get("leader_stop_distance_atr"),
            leader_min_avg_range=row.get("leader_min_avg_range"),
            leader_momentum_lookback=row.get("leader_momentum_lookback"),
            leader_exit_type=row.get("leader_exit_type"),
            leader_signal_exit_reference=row.get("leader_signal_exit_reference"),
            leader_trailing_stop_atr=row.get("leader_trailing_stop_atr"),
            leader_profit_target_atr=row.get("leader_profit_target_atr"),
            leader_net_pnl=row.get("leader_net_pnl"),
        )

        if match is None:
            outcomes[strategy_type] = "NO_MATCH_FOUND"
            continue

        filters_str, classes_str = match
        lb.at[idx, "best_refined_filters"] = filters_str
        lb.at[idx, "best_refined_filter_class_names"] = classes_str
        outcomes[strategy_type] = f"PATCHED ({classes_str[:60]}...)" if len(classes_str) > 60 else f"PATCHED ({classes_str})"

    lb.to_csv(leaderboard_path, index=False)
    return outcomes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        action="append",
        required=True,
        help="Path to a dataset output directory containing family_leaderboard_results.csv. Can repeat.",
    )
    args = parser.parse_args()

    print(f"Backfilling {len(args.output_dir)} dataset(s)...")
    for out_dir in args.output_dir:
        print(f"\n=== {out_dir} ===")
        results = backfill_leaderboard(out_dir)
        for strategy_type, outcome in results.items():
            print(f"  {strategy_type}: {outcome}")


if __name__ == "__main__":
    main()
