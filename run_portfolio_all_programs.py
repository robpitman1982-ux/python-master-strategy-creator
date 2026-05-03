#!/usr/bin/env python3
"""Run portfolio selection across all prop firm programs.

Usage:
    python run_portfolio_all_programs.py
    python run_portfolio_all_programs.py --programs bootcamp_250k high_stakes_100k
    python run_portfolio_all_programs.py --programs all
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import time
from pathlib import Path

from modules.config_loader import load_config
from modules.portfolio_selector import run_portfolio_selection

PROGRAMS = {
    "bootcamp_250k": {"prop_firm_program": "bootcamp", "prop_firm_target": 250_000},
    "high_stakes_5k": {"prop_firm_program": "high_stakes", "prop_firm_target": 5_000},
    "high_stakes_100k": {"prop_firm_program": "high_stakes", "prop_firm_target": 100_000},
    "hyper_growth_5k": {"prop_firm_program": "hyper_growth", "prop_firm_target": 5_000},
    "pro_growth_5k": {"prop_firm_program": "pro_growth", "prop_firm_target": 5_000},
    # FTMO Australia (synthetic Swing config; verified against PDF + deep-dive scrape)
    "ftmo_swing_1step_30k": {"prop_firm_program": "ftmo_swing_1step", "prop_firm_target": 30_000},
    "ftmo_swing_1step_130k": {"prop_firm_program": "ftmo_swing_1step", "prop_firm_target": 130_000},
    "ftmo_swing_2step_130k": {"prop_firm_program": "ftmo_swing_2step", "prop_firm_target": 130_000},
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run portfolio selector for all prop firm programs")
    parser.add_argument("--programs", nargs="+", default=["all"],
                        help="Programs to run (default: all)")
    parser.add_argument("--n-sims", type=int, default=None,
                        help="Override MC simulation count")
    parser.add_argument("--leaderboard-path", type=str, default="Outputs/ultimate_leaderboard_cfd.csv",
                        help="Path to ultimate leaderboard CSV (selector picks gated variant if prefer_gated_leaderboard=true in config)")
    parser.add_argument("--runs-base-path", type=str, default="Outputs/runs",
                        help="Root containing per-run artifact directories (strategy_trades.csv etc)")
    parser.add_argument("--output-root", type=str, default="Outputs",
                        help="Where per-program output dirs are created")
    parser.add_argument(
        "--archive-backup-root", type=str,
        default=r"G:\My Drive\strategy-data-backup\portfolio_selector",
        help="Backup destination for portfolio reports + master history CSV. "
             "Set to empty string to skip archival.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    programs = list(PROGRAMS.keys()) if "all" in args.programs else args.programs
    config = load_config()
    results: dict[str, dict] = {}

    for prog_name in programs:
        if prog_name not in PROGRAMS:
            print(f"WARNING: Unknown program '{prog_name}', skipping. Valid: {list(PROGRAMS.keys())}")
            continue

        prog_cfg = PROGRAMS[prog_name]
        print(f"\n{'=' * 60}")
        print(f"RUNNING: {prog_name}")
        print(f"  Program: {prog_cfg['prop_firm_program']}")
        print(f"  Target:  ${prog_cfg['prop_firm_target']:,.0f}")
        print(f"{'=' * 60}")

        # Override config with program-specific settings
        ps_cfg = config.setdefault("pipeline", {}).setdefault("portfolio_selector", {})
        ps_cfg["prop_firm_program"] = prog_cfg["prop_firm_program"]
        ps_cfg["prop_firm_target"] = prog_cfg["prop_firm_target"]

        if args.n_sims is not None:
            ps_cfg["n_sims_mc"] = args.n_sims

        output_dir = os.path.join(args.output_root, f"portfolio_{prog_name}")
        os.makedirs(output_dir, exist_ok=True)

        t0 = time.time()
        try:
            result = run_portfolio_selection(
                leaderboard_path=args.leaderboard_path,
                runs_base_path=args.runs_base_path,
                output_dir=output_dir,
                config=config,
            )
        except Exception as e:
            print(f"  ERROR: {e}")
            result = {"status": f"error: {e}"}
        elapsed = time.time() - t0

        results[prog_name] = {**result, "elapsed_seconds": round(elapsed, 1)}
        print(f"  Completed in {elapsed:.1f}s — status: {result.get('status')}")

    # Write combined summary
    _write_combined_summary(results, output_root=args.output_root)

    # Archive each portfolio_selector_report.csv + append to history CSV in
    # the Drive backup folder (or whatever --archive-backup-root points to).
    if args.archive_backup_root:
        try:
            from datetime import UTC, datetime
            import subprocess
            run_ts = datetime.now(UTC).strftime("%Y-%m-%dT%H%M")
            archive_cmd = [
                "python", "scripts/archive_portfolio_run.py",
                "--source-dir", args.output_root,
                "--backup-root", args.archive_backup_root,
                "--run-timestamp", run_ts,
            ]
            print(f"\nArchiving portfolio reports to {args.archive_backup_root} ...")
            subprocess.run(archive_cmd, check=False)
        except Exception as exc:
            print(f"WARNING: portfolio archival failed: {exc}")

    # Print final summary
    print(f"\n{'=' * 60}")
    print("ALL PROGRAMS COMPLETE")
    print(f"{'=' * 60}")
    total_time = sum(r.get("elapsed_seconds", 0) for r in results.values())
    for prog_name, result in results.items():
        status = result.get("status", "unknown")
        elapsed = result.get("elapsed_seconds", 0)
        top = result.get("top_portfolio")
        if top:
            n_strats = top.get("n_strategies", "?")
            pass_rate = top.get("opt_final_pass_rate", top.get("final_pass_rate", 0))
            print(f"  {prog_name:25s}  {status:12s}  {elapsed:6.1f}s  "
                  f"{n_strats} strats  {pass_rate:.1%} pass")
        else:
            print(f"  {prog_name:25s}  {status:12s}  {elapsed:6.1f}s")
    print(f"\n  Total time: {total_time:.1f}s")


def _write_combined_summary(results: dict[str, dict], output_root: str = "Outputs") -> None:
    """Write a single CSV comparing top portfolio across all programs."""
    out_path = os.path.join(output_root, "portfolio_combined_summary.csv")
    os.makedirs(output_root, exist_ok=True)

    rows: list[dict] = []
    for prog_name, result in results.items():
        top = result.get("top_portfolio")
        row: dict = {
            "program": prog_name,
            "status": result.get("status", "unknown"),
            "elapsed_seconds": result.get("elapsed_seconds", 0),
            "n_candidates": result.get("n_candidates", 0),
            "n_combinations_tested": result.get("n_combinations_tested", 0),
        }
        if top:
            row.update({
                "n_strategies": top.get("n_strategies", 0),
                "strategy_names": "|".join(top.get("strategy_names", [])),
                "final_pass_rate": round(top.get("opt_final_pass_rate",
                                                  top.get("final_pass_rate", 0)), 4),
                "p95_worst_dd_pct": round(top.get("opt_p95_dd",
                                                   top.get("p95_worst_dd_pct", 0)), 4),
                "median_trades_to_pass": round(top.get("median_trades_to_pass", 0), 0),
                "diversity_score": round(top.get("diversity", 0), 4),
                "robustness_score": round(top.get("robustness_score", 0), 4),
            })
        rows.append(row)

    if rows:
        fieldnames = list(rows[0].keys())
        # Ensure all rows have all fields
        for r in rows:
            for f in fieldnames:
                r.setdefault(f, "")
            for f in r:
                if f not in fieldnames:
                    fieldnames.append(f)

        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nCombined summary written to {out_path}")


if __name__ == "__main__":
    main()
