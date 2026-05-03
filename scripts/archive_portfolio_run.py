#!/usr/bin/env python3
"""Archive portfolio_selector reports to Google Drive backup.

Target structure:
    G:/My Drive/strategy-data-backup/portfolio_selector/
        portfolio_runs_history.csv               # master summary, one row per program-run
        <run_timestamp>/
            <program>/
                portfolio_selector_report.csv    # archived copy of the report
                portfolio_selector_matrix.csv    # if present
                portfolio_selector_*_corr.csv

Usage:
    # Archive a single run-output directory (e.g. /tmp/portfolio_runs_2026-05-03)
    python scripts/archive_portfolio_run.py \
        --source-dir /tmp/portfolio_runs_2026-05-03 \
        --backup-root "G:/My Drive/strategy-data-backup/portfolio_selector" \
        --run-timestamp 2026-05-03T07:00

    # Or call from another script after run_portfolio_all_programs.py finishes:
    python -m scripts.archive_portfolio_run --source-dir Outputs --run-timestamp $(date -u +%Y-%m-%dT%H%M)
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent

HISTORY_COLUMNS = [
    "run_timestamp_utc",
    "program",
    "firm",
    "account_size",
    "verdict",
    "rank",
    "n_strategies",
    "strategy_names",
    "final_pass_rate",
    "step1_pass_rate",
    "step2_pass_rate",
    "step3_pass_rate",
    "p95_worst_dd_pct",
    "median_trades_to_fund",
    "est_months_median",
    "min_lot_check_passed",
    "smallest_strategy_lots",
    "infeasible_strategies",
    "robustness_score",
    "avg_oos_pf",
    "avg_correlation",
    "diversity_score",
    "composite_score",
    "micro_contracts",
    "max_overnight_hold_share",
    "max_weekend_hold_share",
    "max_swap_per_micro_per_night",
    "report_path_archive",
]

# Inferred from program directory name prefix
PROGRAM_TO_FIRM = {
    "bootcamp": ("the5ers", "Bootcamp"),
    "high_stakes": ("the5ers", "HighStakes"),
    "hyper_growth": ("the5ers", "HyperGrowth"),
    "pro_growth": ("the5ers", "ProGrowth"),
    "ftmo_swing_1step": ("ftmo", "Swing1Step"),
    "ftmo_swing_2step": ("ftmo", "Swing2Step"),
}


def _infer_firm_and_program(program_dir_name: str) -> tuple[str, str, float]:
    """Parse 'portfolio_ftmo_swing_1step_130k' -> ('ftmo', 'Swing1Step', 130000)."""
    name = program_dir_name.replace("portfolio_", "", 1)
    # Find the longest matching prefix from PROGRAM_TO_FIRM
    matched_key = ""
    for key in sorted(PROGRAM_TO_FIRM.keys(), key=len, reverse=True):
        if name.startswith(key):
            matched_key = key
            break
    if not matched_key:
        return ("unknown", name, 0.0)
    firm, prog_label = PROGRAM_TO_FIRM[matched_key]
    suffix = name[len(matched_key):].lstrip("_")  # e.g. "130k", "250k", "5k"
    account_size = 0.0
    if suffix.endswith("k"):
        try:
            account_size = float(suffix[:-1]) * 1000
        except ValueError:
            pass
    elif suffix.endswith("m"):
        try:
            account_size = float(suffix[:-1]) * 1_000_000
        except ValueError:
            pass
    return (firm, prog_label, account_size)


def _load_history(history_path: Path) -> pd.DataFrame:
    if history_path.exists():
        try:
            return pd.read_csv(history_path)
        except Exception:
            pass
    return pd.DataFrame(columns=HISTORY_COLUMNS)


def _write_history(history: pd.DataFrame, history_path: Path) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    # Preserve column order even if some are missing in the frame
    for col in HISTORY_COLUMNS:
        if col not in history.columns:
            history[col] = None
    history = history[HISTORY_COLUMNS]
    history.to_csv(history_path, index=False, quoting=csv.QUOTE_MINIMAL)


def archive_one_program(
    program_dir: Path,
    backup_root: Path,
    run_timestamp: str,
    history_rows: list[dict],
) -> tuple[bool, str]:
    """Archive one portfolio_<program> directory and return (success, message)."""
    report = program_dir / "portfolio_selector_report.csv"
    if not report.exists():
        return (False, f"no report: {report}")

    firm, program_label, account_size = _infer_firm_and_program(program_dir.name)
    program_key = program_dir.name.replace("portfolio_", "", 1)

    target_dir = backup_root / run_timestamp / program_key
    target_dir.mkdir(parents=True, exist_ok=True)
    archived_path = target_dir / "portfolio_selector_report.csv"
    shutil.copy2(report, archived_path)

    # Also archive correlation/matrix outputs if present
    for sibling in [
        "portfolio_selector_matrix.csv",
        "portfolio_selector_active_corr.csv",
        "portfolio_selector_dd_corr.csv",
        "portfolio_selector_tail_coloss.csv",
    ]:
        src = program_dir / sibling
        if src.exists():
            shutil.copy2(src, target_dir / sibling)

    # Generate single-page PDF summary alongside the CSVs (in both source
    # and Drive archive). Soft-fails if matplotlib is missing.
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from scripts.portfolio_report_pdf import render_pdf
        # In the source program dir
        try:
            render_pdf(report)
        except Exception as exc:
            print(f"      PDF (source) skipped: {exc}")
        # In the archive
        try:
            render_pdf(archived_path)
        except Exception as exc:
            print(f"      PDF (archive) skipped: {exc}")
    except Exception as exc:
        print(f"      PDF generator unavailable: {exc}")

    df = pd.read_csv(report)
    if df.empty:
        return (False, f"empty report: {report}")

    # Append every rank, not just rank 1, so the history is complete
    for _, row in df.iterrows():
        history_rows.append({
            "run_timestamp_utc": run_timestamp,
            "program": program_key,
            "firm": firm,
            "account_size": account_size,
            "verdict": row.get("verdict"),
            "rank": row.get("rank"),
            "n_strategies": row.get("n_strategies"),
            "strategy_names": row.get("strategy_names"),
            "final_pass_rate": row.get("final_pass_rate"),
            "step1_pass_rate": row.get("step1_pass_rate"),
            "step2_pass_rate": row.get("step2_pass_rate"),
            "step3_pass_rate": row.get("step3_pass_rate"),
            "p95_worst_dd_pct": row.get("p95_worst_dd_pct"),
            "median_trades_to_fund": row.get("median_trades_to_fund"),
            "est_months_median": row.get("est_months_median"),
            "min_lot_check_passed": row.get("min_lot_check_passed"),
            "smallest_strategy_lots": row.get("smallest_strategy_lots"),
            "infeasible_strategies": row.get("infeasible_strategies"),
            "robustness_score": row.get("robustness_score"),
            "avg_oos_pf": row.get("avg_oos_pf"),
            "avg_correlation": row.get("avg_correlation"),
            "diversity_score": row.get("diversity_score"),
            "composite_score": row.get("composite_score"),
            "micro_contracts": row.get("micro_contracts"),
            "max_overnight_hold_share": row.get("max_overnight_hold_share"),
            "max_weekend_hold_share": row.get("max_weekend_hold_share"),
            "max_swap_per_micro_per_night": row.get("max_swap_per_micro_per_night"),
            "report_path_archive": str(archived_path.relative_to(backup_root.parent.parent))
                if backup_root.parent.parent in archived_path.parents else str(archived_path),
        })

    return (True, f"archived {len(df)} portfolios from {program_key}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True,
                        help="Output root containing portfolio_<program>/ subdirs")
    parser.add_argument(
        "--backup-root",
        default=r"G:\My Drive\strategy-data-backup\portfolio_selector",
        help="Drive backup destination",
    )
    parser.add_argument("--run-timestamp", default=None,
                        help="Run timestamp tag (default: now in UTC)")
    args = parser.parse_args()

    source = Path(args.source_dir)
    backup_root = Path(args.backup_root)
    if not source.exists():
        print(f"ERROR: source not found: {source}", file=sys.stderr)
        return 1

    run_timestamp = args.run_timestamp or datetime.now(UTC).strftime("%Y-%m-%dT%H%M")
    backup_root.mkdir(parents=True, exist_ok=True)
    history_path = backup_root / "portfolio_runs_history.csv"
    history = _load_history(history_path)

    new_rows: list[dict] = []
    n_archived = 0
    for child in sorted(source.iterdir()):
        if not child.is_dir() or not child.name.startswith("portfolio_"):
            continue
        ok, msg = archive_one_program(child, backup_root, run_timestamp, new_rows)
        print(f"  {'[OK]' if ok else '[--]'} {child.name}: {msg}")
        if ok:
            n_archived += 1

    if not new_rows:
        print("No portfolio reports archived.")
        return 0

    new_df = pd.DataFrame(new_rows)
    combined = pd.concat([history, new_df], ignore_index=True)
    combined = combined.drop_duplicates(
        subset=["run_timestamp_utc", "program", "rank"], keep="last"
    )
    _write_history(combined, history_path)
    print(f"\n{n_archived} program(s) archived under {backup_root / run_timestamp}")
    print(f"History updated: {history_path} ({len(combined)} rows total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
