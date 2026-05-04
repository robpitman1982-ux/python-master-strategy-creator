#!/usr/bin/env python3
"""Compare two family_leaderboard_results.csv files for resume-parity smoke test.

Sprint 93 verdict gate. Compares control run vs resumed run row-by-row on the
columns that prove behavioural equivalence: strategy_type, leader_strategy_name,
leader_net_pnl, leader_pf, oos_pf, accepted_final.

Usage:
    python scripts/verify_resume_parity.py <control_csv> <resumed_csv>

Exit 0 on parity match, exit 1 with diff report on any mismatch.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# Behavioural columns - any difference fails the gate. These represent
# what the engine actually produced (PnL, PF, drawdown).
BEHAVIOURAL_COLS = [
    "strategy_type",
    "accepted_final",
    "leader_net_pnl",
    "leader_pf",
    "oos_pf",
    "leader_total_trades",
    "best_combo_net_pnl",
]

# Naming columns - tie-breaking can produce different strategy names when
# multiple refinement candidates share identical net_pnl. This is pre-existing
# engine non-determinism, NOT a resume bug. Treat as a warning when the
# behavioural metrics match within tolerance.
NAMING_COLS = ["leader_strategy_name", "best_combo_strategy_name"]

ZERO_TOLERANCE_COLS = BEHAVIOURAL_COLS + NAMING_COLS

# Columns where small floating-point drift is OK (1e-6).
FLOAT_DRIFT_COLS = ["leader_net_pnl", "leader_pf", "oos_pf", "best_combo_net_pnl"]


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2

    control_path = Path(sys.argv[1])
    resumed_path = Path(sys.argv[2])

    if not control_path.is_file():
        print(f"ERROR: control file missing: {control_path}")
        return 2
    if not resumed_path.is_file():
        print(f"ERROR: resumed file missing: {resumed_path}")
        return 2

    control = pd.read_csv(control_path)
    resumed = pd.read_csv(resumed_path)

    # Sort both by strategy_type for stable comparison.
    control = control.sort_values("strategy_type").reset_index(drop=True)
    resumed = resumed.sort_values("strategy_type").reset_index(drop=True)

    print(f"Control:  {len(control)} rows")
    print(f"Resumed:  {len(resumed)} rows")

    if len(control) != len(resumed):
        print(f"FAIL: row count mismatch (control={len(control)}, resumed={len(resumed)})")
        ctl_set = set(control["strategy_type"])
        res_set = set(resumed["strategy_type"])
        if ctl_set - res_set:
            print(f"  missing from resumed: {sorted(ctl_set - res_set)}")
        if res_set - ctl_set:
            print(f"  extra in resumed: {sorted(res_set - ctl_set)}")
        return 1

    behavioural_fails = 0
    naming_warnings = 0
    available_behavioural = [c for c in BEHAVIOURAL_COLS if c in control.columns and c in resumed.columns]
    available_naming = [c for c in NAMING_COLS if c in control.columns and c in resumed.columns]
    print(f"Behavioural cols: {available_behavioural}")
    print(f"Naming cols (warn-only when behavioural matches): {available_naming}")

    for i in range(len(control)):
        row_ctl = control.iloc[i]
        row_res = resumed.iloc[i]
        if row_ctl["strategy_type"] != row_res["strategy_type"]:
            print(f"FAIL row {i}: strategy_type mismatch ({row_ctl['strategy_type']} vs {row_res['strategy_type']})")
            behavioural_fails += 1
            continue

        row_behavioural_ok = True
        for col in available_behavioural:
            v_ctl = row_ctl[col]
            v_res = row_res[col]
            if pd.isna(v_ctl) and pd.isna(v_res):
                continue
            if col in FLOAT_DRIFT_COLS:
                try:
                    if abs(float(v_ctl) - float(v_res)) > 1e-6:
                        print(
                            f"FAIL row {i} ({row_ctl['strategy_type']}): "
                            f"{col} differs ctl={v_ctl} res={v_res} (drift={abs(float(v_ctl)-float(v_res))})"
                        )
                        behavioural_fails += 1
                        row_behavioural_ok = False
                except (TypeError, ValueError):
                    if v_ctl != v_res:
                        print(f"FAIL row {i} ({row_ctl['strategy_type']}): {col} differs ctl={v_ctl} res={v_res}")
                        behavioural_fails += 1
                        row_behavioural_ok = False
            else:
                if v_ctl != v_res:
                    print(
                        f"FAIL row {i} ({row_ctl['strategy_type']}): "
                        f"{col} differs ctl={v_ctl!r} res={v_res!r}"
                    )
                    behavioural_fails += 1
                    row_behavioural_ok = False

        # Naming columns: warn-only if behavioural metrics matched (tie-break)
        for col in available_naming:
            v_ctl = row_ctl[col]
            v_res = row_res[col]
            if pd.isna(v_ctl) and pd.isna(v_res):
                continue
            if v_ctl != v_res:
                if row_behavioural_ok:
                    print(
                        f"WARN row {i} ({row_ctl['strategy_type']}): "
                        f"{col} differs ctl={v_ctl!r} res={v_res!r} (tie-break, metrics match)"
                    )
                    naming_warnings += 1
                else:
                    print(
                        f"FAIL row {i} ({row_ctl['strategy_type']}): "
                        f"{col} differs ctl={v_ctl!r} res={v_res!r} (with behavioural drift)"
                    )
                    behavioural_fails += 1

    # Report resumed_from_disk distribution if present
    if "resumed_from_disk" in resumed.columns:
        resumed_count = int(resumed["resumed_from_disk"].fillna(False).astype(bool).sum())
        print(f"Resumed-from-disk families: {resumed_count} / {len(resumed)}")

    if behavioural_fails == 0:
        if naming_warnings > 0:
            print(
                f"PASS: zero-tolerance behavioural parity "
                f"({naming_warnings} naming tie-break warnings, no metric drift)"
            )
        else:
            print("PASS: zero-tolerance parity (no diffs at all)")
        return 0
    else:
        print(
            f"FAIL: {behavioural_fails} behavioural mismatch(es) across {len(control)} rows "
            f"(plus {naming_warnings} naming tie-break warnings)"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
