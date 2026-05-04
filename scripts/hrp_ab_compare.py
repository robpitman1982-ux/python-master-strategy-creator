#!/usr/bin/env python3
"""HRP A/B comparison for Sprint 96 verdict gate.

Runs the portfolio selector twice on the same gated leaderboard:
  A: HRP=OFF (control)
  B: HRP=ON

Compares the top portfolio per program on:
- strategy_names list (PARITY check; if HRP=OFF leaves names unchanged
  vs prior runs that's good)
- avg active_corr within portfolio
- n_distinct_markets in portfolio
- n_distinct_timeframes in portfolio

Output: a single comparison report to stdout + JSON file.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd


def run_selector(
    leaderboard_path: str,
    runs_base: str,
    output_root: str,
    label: str,
    hrp_enabled: bool,
    program: str = "high_stakes_5k",
) -> tuple[Path, float]:
    """Run run_portfolio_all_programs.py with HRP toggled via env var.

    Returns (output_dir, elapsed_seconds).
    """
    out_dir = Path(output_root) / label
    out_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    # We don't have a CLI flag for HRP — toggle via a config override file.
    # Easier: set the flag via temp config, point selector at it.
    # Actually simplest: write a small override config that the selector reads.
    # But run_portfolio_all_programs uses the global config.yaml.
    # Cleanest path: edit config.yaml in-place around the run.
    env["PSC_HRP_OVERRIDE"] = "1" if hrp_enabled else "0"

    cmd = [
        sys.executable, "run_portfolio_all_programs.py",
        "--programs", program,
        "--leaderboard-path", leaderboard_path,
        "--runs-base-path", runs_base,
        "--output-root", str(out_dir),
        "--archive-backup-root", "",  # skip archival for the A/B
    ]
    print(f"\n=== Running {label} (HRP={hrp_enabled}) ===")
    t0 = time.time()
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    elapsed = time.time() - t0
    log_path = out_dir / "run.log"
    log_path.write_text((result.stdout or "") + "\n---STDERR---\n" + (result.stderr or ""))
    print(f"  exit={result.returncode}  elapsed={elapsed:.1f}s  log={log_path}")
    return out_dir, elapsed


def diversity_metrics(report_path: Path, top_n: int = 1) -> dict[str, Any]:
    """Read portfolio_selector_report.csv and compute diversity for top portfolio(s)."""
    if not report_path.is_file():
        return {"error": f"missing {report_path}"}
    df = pd.read_csv(report_path)
    if df.empty:
        return {"error": "empty report"}

    top = df.head(top_n).iloc[0]
    strategy_names = str(top.get("strategy_names", "")).split("|")
    markets = set()
    timeframes = set()
    for s in strategy_names:
        # Format example: "N225_daily_RefinedBreakout_HB2_..."
        parts = s.split("_", 2)
        if len(parts) >= 2:
            markets.add(parts[0])
            timeframes.add(parts[1])
    return {
        "verdict": str(top.get("verdict", "?")),
        "n_strategies": int(top.get("n_strategies", 0)),
        "strategy_names": strategy_names,
        "n_distinct_markets": len(markets),
        "n_distinct_timeframes": len(timeframes),
        "markets": sorted(markets),
        "timeframes": sorted(timeframes),
        "avg_correlation": float(top.get("avg_correlation", 0.0)),
        "diversity_score": float(top.get("diversity_score", 0.0)),
        "cluster_diversity": float(top.get("cluster_diversity", 0.0)) if "cluster_diversity" in top else None,
        "final_pass_rate": float(top.get("final_pass_rate", 0.0)),
        "p95_worst_dd_pct": float(top.get("p95_worst_dd_pct", 0.0)),
        "median_trades_to_fund": float(top.get("median_trades_to_fund", 0.0)),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--leaderboard", required=True)
    p.add_argument("--runs-base", required=True)
    p.add_argument("--output-root", default="Outputs/hrp_ab")
    p.add_argument("--program", default="high_stakes_5k",
                   help="Single program to A/B (default: high_stakes_5k)")
    args = p.parse_args()

    print(f"HRP A/B test on program={args.program}")
    print(f"Leaderboard: {args.leaderboard}")
    print(f"Runs base:   {args.runs_base}")

    a_dir, a_elapsed = run_selector(
        args.leaderboard, args.runs_base, args.output_root,
        label="A_hrp_off", hrp_enabled=False, program=args.program,
    )
    b_dir, b_elapsed = run_selector(
        args.leaderboard, args.runs_base, args.output_root,
        label="B_hrp_on", hrp_enabled=True, program=args.program,
    )

    report_a = a_dir / f"portfolio_{args.program}" / "portfolio_selector_report.csv"
    report_b = b_dir / f"portfolio_{args.program}" / "portfolio_selector_report.csv"

    metrics_a = diversity_metrics(report_a)
    metrics_b = diversity_metrics(report_b)

    print("\n=== HRP=OFF (control) ===")
    print(json.dumps(metrics_a, indent=2, default=str))
    print("\n=== HRP=ON ===")
    print(json.dumps(metrics_b, indent=2, default=str))

    # Compute deltas
    print("\n=== DELTAS ===")
    if "error" in metrics_a or "error" in metrics_b:
        print("Cannot compute deltas due to errors above")
        return 1

    avg_corr_drop = metrics_a["avg_correlation"] - metrics_b["avg_correlation"]
    avg_corr_drop_pct = (avg_corr_drop / metrics_a["avg_correlation"] * 100) if metrics_a["avg_correlation"] else 0
    market_delta = metrics_b["n_distinct_markets"] - metrics_a["n_distinct_markets"]
    timeframe_delta = metrics_b["n_distinct_timeframes"] - metrics_a["n_distinct_timeframes"]

    print(f"avg active_corr: {metrics_a['avg_correlation']:.4f} -> {metrics_b['avg_correlation']:.4f} "
          f"(drop {avg_corr_drop:+.4f} = {avg_corr_drop_pct:+.1f}%)")
    print(f"n_distinct_markets:    {metrics_a['n_distinct_markets']} -> {metrics_b['n_distinct_markets']} (Δ {market_delta:+d})")
    print(f"n_distinct_timeframes: {metrics_a['n_distinct_timeframes']} -> {metrics_b['n_distinct_timeframes']} (Δ {timeframe_delta:+d})")
    print(f"strategy_names same:   {metrics_a['strategy_names'] == metrics_b['strategy_names']}")
    print(f"runtime A: {a_elapsed:.1f}s, B: {b_elapsed:.1f}s")

    # Verdict against pre-reg gate
    print("\n=== VERDICT GATE (Sprint 96 pre-reg) ===")
    gate_corr_drop = avg_corr_drop_pct >= 10.0
    gate_market = market_delta >= 1
    gate_timeframe = timeframe_delta >= 1
    any_gate = gate_corr_drop or gate_market or gate_timeframe
    print(f"  active_corr drop >= 10%:        {'PASS' if gate_corr_drop else 'fail'} ({avg_corr_drop_pct:+.1f}%)")
    print(f"  n_markets +1:                   {'PASS' if gate_market else 'fail'} ({market_delta:+d})")
    print(f"  n_timeframes +1:                {'PASS' if gate_timeframe else 'fail'} ({timeframe_delta:+d})")
    print(f"  ANY of above (CANDIDATES):      {'PASS' if any_gate else 'FAIL (SUSPICIOUS verdict)'}")

    # Save JSON
    out_json = Path(args.output_root) / "hrp_ab_summary.json"
    out_json.write_text(json.dumps({
        "program": args.program,
        "control": metrics_a,
        "hrp_on": metrics_b,
        "elapsed": {"A": a_elapsed, "B": b_elapsed},
        "verdict": {
            "active_corr_drop_pct": avg_corr_drop_pct,
            "market_delta": market_delta,
            "timeframe_delta": timeframe_delta,
            "any_gate_passed": any_gate,
        },
    }, indent=2, default=str))
    print(f"\nJSON summary: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
