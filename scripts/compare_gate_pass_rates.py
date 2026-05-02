"""Compare post-ultimate gate pass rates before vs after Sprint 84+85.

Sprint 84 introduced trade_artifact_status patching of family leaderboards
plus fail-closed behaviour in post_ultimate_gate. Sprint 85 Phase A fixed
the CFD config bug in the rebuild path. This script reads two
ultimate_leaderboard_*_post_gate_audit.csv files (typically a backup of
the pre-Sprint-84 audit alongside the freshly-rebuilt one) and reports
the change in pass rate, by strategy type and quality flag.

Usage:
    python scripts/compare_gate_pass_rates.py \
        --before /data/sweep_results/exports/.archive/2026-05-03_pre_sprint84/ultimate_leaderboard_cfd_post_gate_audit.csv \
        --after  /data/sweep_results/exports/ultimate_leaderboard_cfd_post_gate_audit.csv

If only --after is given, it shows just the new state.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def _summary(df: pd.DataFrame, label: str) -> dict:
    if df.empty:
        return {"label": label, "total": 0}

    pass_col = df.get("post_gate_pass", pd.Series(dtype=bool)).astype(str).str.lower().eq("true")
    n = len(df)
    n_pass = int(pass_col.sum())

    by_status: dict[str, int] = {}
    if "gate_status" in df.columns:
        by_status = df["gate_status"].astype(str).value_counts().to_dict()

    by_artifact: dict[str, int] = {}
    if "trade_artifact_status" in df.columns:
        by_artifact = df["trade_artifact_status"].astype(str).value_counts().to_dict()

    by_strategy_type: dict[str, dict[str, int]] = {}
    if "strategy_type" in df.columns:
        for stype, group in df.groupby("strategy_type"):
            n_st = len(group)
            n_st_pass = int(group.get("post_gate_pass", pd.Series(dtype=bool)).astype(str).str.lower().eq("true").sum())
            by_strategy_type[str(stype)] = {"n": n_st, "pass": n_st_pass, "rate": round(n_st_pass / n_st, 3) if n_st else 0.0}

    by_quality: dict[str, dict[str, int]] = {}
    if "quality_flag" in df.columns:
        for q, group in df.groupby("quality_flag"):
            n_q = len(group)
            n_q_pass = int(group.get("post_gate_pass", pd.Series(dtype=bool)).astype(str).str.lower().eq("true").sum())
            by_quality[str(q)] = {"n": n_q, "pass": n_q_pass, "rate": round(n_q_pass / n_q, 3) if n_q else 0.0}

    by_timeframe: dict[str, dict[str, int]] = {}
    if "dataset" in df.columns:
        def _tf(s: str) -> str:
            try:
                parts = str(s).replace("_dukascopy", "").replace(".csv", "").split("_")
                return parts[1] if len(parts) > 1 else "?"
            except Exception:
                return "?"
        df = df.copy()
        df["_tf"] = df["dataset"].astype(str).map(_tf)
        for tf, group in df.groupby("_tf"):
            n_tf = len(group)
            n_tf_pass = int(group.get("post_gate_pass", pd.Series(dtype=bool)).astype(str).str.lower().eq("true").sum())
            by_timeframe[str(tf)] = {"n": n_tf, "pass": n_tf_pass, "rate": round(n_tf_pass / n_tf, 3) if n_tf else 0.0}

    return {
        "label": label,
        "total": n,
        "post_gate_pass": n_pass,
        "post_gate_pass_rate": round(n_pass / n, 3) if n else 0.0,
        "by_gate_status": by_status,
        "by_trade_artifact_status": by_artifact,
        "by_strategy_type": by_strategy_type,
        "by_quality_flag": by_quality,
        "by_timeframe": by_timeframe,
    }


def _print_summary(s: dict) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {s['label']}")
    print(f"{'=' * 72}")
    if s.get("total", 0) == 0:
        print("  (empty)")
        return
    print(f"  total rows: {s['total']}")
    print(f"  post_gate_pass: {s.get('post_gate_pass', 0)} ({100 * s.get('post_gate_pass_rate', 0):.1f}%)")
    if s.get("by_gate_status"):
        print("  by_gate_status:")
        for k, v in sorted(s["by_gate_status"].items(), key=lambda x: -x[1]):
            print(f"    {k:32s} {v}")
    if s.get("by_trade_artifact_status"):
        print("  by_trade_artifact_status:")
        for k, v in sorted(s["by_trade_artifact_status"].items(), key=lambda x: -x[1]):
            print(f"    {k:32s} {v}")
    if s.get("by_strategy_type"):
        print("  by_strategy_type (count, pass, rate):")
        for k, v in sorted(s["by_strategy_type"].items()):
            print(f"    {k:32s} n={v['n']:4d} pass={v['pass']:4d} rate={100*v['rate']:.1f}%")
    if s.get("by_timeframe"):
        print("  by_timeframe:")
        for k, v in sorted(s["by_timeframe"].items()):
            print(f"    {k:8s} n={v['n']:4d} pass={v['pass']:4d} rate={100*v['rate']:.1f}%")
    if s.get("by_quality_flag"):
        print("  by_quality_flag:")
        for k, v in sorted(s["by_quality_flag"].items()):
            print(f"    {k:32s} n={v['n']:4d} pass={v['pass']:4d} rate={100*v['rate']:.1f}%")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, default=None, help="Pre-fix audit CSV (optional)")
    parser.add_argument("--after", type=Path, required=True, help="Post-fix audit CSV")
    args = parser.parse_args()

    after_df = pd.read_csv(args.after)
    after_summary = _summary(after_df, f"AFTER  ({args.after.name})")

    if args.before:
        before_df = pd.read_csv(args.before)
        before_summary = _summary(before_df, f"BEFORE ({args.before.name})")
        _print_summary(before_summary)
        _print_summary(after_summary)
        # Diff highlights
        b_total = before_summary["total"]
        b_pass = before_summary["post_gate_pass"]
        a_total = after_summary["total"]
        a_pass = after_summary["post_gate_pass"]
        print(f"\n{'=' * 72}")
        print("  DIFF HIGHLIGHTS")
        print(f"{'=' * 72}")
        print(f"  total rows: {b_total} -> {a_total} (delta {a_total - b_total:+d})")
        print(f"  post_gate_pass: {b_pass} -> {a_pass} (delta {a_pass - b_pass:+d})")
        b_rate = before_summary["post_gate_pass_rate"]
        a_rate = after_summary["post_gate_pass_rate"]
        print(f"  pass rate: {100*b_rate:.1f}% -> {100*a_rate:.1f}% (delta {100*(a_rate - b_rate):+.1f}pp)")
    else:
        _print_summary(after_summary)


if __name__ == "__main__":
    main()
