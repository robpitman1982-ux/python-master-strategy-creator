#!/usr/bin/env python3
"""Session 71 Task 5: Validate all 120 converted CSVs in ohlc_engine/."""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

TARGET_DIR = Path("/data/market_data/cfds/ohlc_engine")
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "session71" / "validation_report.json"

EXPECTED_HEADER = ["Date", "Time", "Open", "High", "Low", "Close", "Vol", "OI"]

ROW_RANGES = {
    "daily": (2_000, 5_000),
    "60m":   (40_000, 100_000),
    "30m":   (80_000, 250_000),
    "15m":   (150_000, 500_000),
    "5m":    (400_000, 1_500_000),
}


def validate_file(fpath: Path) -> dict:
    """Validate a single converted CSV. Returns {file, status, issues}."""
    fname = fpath.name
    issues = []

    # Parse symbol_tf from filename: {SYM}_{TF}_dukascopy.csv
    parts = fname.replace("_dukascopy.csv", "").rsplit("_", 1)
    if len(parts) != 2:
        return {"file": fname, "status": "fail", "rows": 0, "issues": [f"Cannot parse TF from filename: {fname}"]}
    symbol, tf = parts[0], parts[1]

    # Read file
    try:
        with open(fpath, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader)
            # Strip quotes from header
            header = [h.strip().strip('"') for h in header]
            rows = list(reader)
    except Exception as e:
        return {"file": fname, "status": "fail", "rows": 0, "issues": [f"Read error: {e}"]}

    # 1. Header check
    if header != EXPECTED_HEADER:
        issues.append(f"FAIL: header mismatch: got {header}, expected {EXPECTED_HEADER}")

    # 2. Row count > 0
    n_rows = len(rows)
    if n_rows == 0:
        return {"file": fname, "status": "fail", "rows": 0, "issues": ["FAIL: empty file"]}

    # 3. Parse timestamps
    timestamps = []
    bad_timestamps = 0
    for i, row in enumerate(rows):
        try:
            dt_str = f"{row[0].strip()} {row[1].strip()}"
            dt = datetime.strptime(dt_str, "%m/%d/%Y %H:%M")
            timestamps.append(dt)
        except (ValueError, IndexError):
            bad_timestamps += 1
            if bad_timestamps <= 3:
                issues.append(f"FAIL: unparseable timestamp row {i+2}: {row[:2]}")

    if bad_timestamps > 0:
        issues.append(f"FAIL: {bad_timestamps} unparseable timestamps total")

    # 4. Strictly increasing
    if len(timestamps) > 1:
        out_of_order = 0
        duplicates = 0
        for i in range(1, len(timestamps)):
            if timestamps[i] < timestamps[i-1]:
                out_of_order += 1
            elif timestamps[i] == timestamps[i-1]:
                duplicates += 1
        if out_of_order > 0:
            issues.append(f"WARN: {out_of_order} out-of-order timestamps")
        if duplicates > 0:
            issues.append(f"WARN: {duplicates} duplicate timestamps")

    # 6. Row count plausible
    if tf in ROW_RANGES:
        lo, hi = ROW_RANGES[tf]
        if n_rows < lo or n_rows > hi:
            issues.append(f"WARN: row count {n_rows:,} outside expected {lo:,}-{hi:,} for {tf}")

    # 7. OHLC sanity (sample first 1000 + last 1000 to avoid scanning millions)
    sample_indices = list(range(min(1000, n_rows))) + list(range(max(0, n_rows - 1000), n_rows))
    sample_indices = sorted(set(sample_indices))
    ohlc_issues = 0
    for i in sample_indices:
        row = rows[i]
        try:
            o, h, l, c = float(row[2]), float(row[3]), float(row[4]), float(row[5])
            if h < max(o, c, l) - 1e-9:
                ohlc_issues += 1
            if l > min(o, c, h) + 1e-9:
                ohlc_issues += 1
            if any(v <= 0 for v in [o, h, l, c]):
                ohlc_issues += 1
        except (ValueError, IndexError):
            ohlc_issues += 1
    if ohlc_issues > 0:
        issues.append(f"FAIL: {ohlc_issues} OHLC sanity failures in sampled rows")

    # 8. Vol non-negative
    vol_issues = 0
    for i in sample_indices:
        try:
            v = int(rows[i][6])
            if v < 0:
                vol_issues += 1
        except (ValueError, IndexError):
            vol_issues += 1
    if vol_issues > 0:
        issues.append(f"WARN: {vol_issues} volume issues in sampled rows")

    # Determine status
    has_fail = any("FAIL" in iss for iss in issues)
    has_warn = any("WARN" in iss for iss in issues)
    if has_fail:
        status = "fail"
    elif has_warn:
        status = "warn"
    else:
        status = "pass"

    return {"file": fname, "status": status, "rows": n_rows, "issues": issues}


def main() -> int:
    files = sorted(TARGET_DIR.glob("*.csv"))
    print(f"Validating {len(files)} files in {TARGET_DIR}")

    results = []
    for fpath in files:
        r = validate_file(fpath)
        results.append(r)
        tag = r["status"].upper()
        issues_str = f" [{len(r['issues'])} issues]" if r["issues"] else ""
        print(f"  [{tag:4s}] {r['file']} ({r['rows']:,} rows){issues_str}")
        for iss in r["issues"]:
            print(f"         {iss}")

    passed = sum(1 for r in results if r["status"] == "pass")
    warned = sum(1 for r in results if r["status"] == "warn")
    failed = sum(1 for r in results if r["status"] == "fail")

    report = {
        "total_files": len(results),
        "passed": passed,
        "warned": warned,
        "failed": failed,
        "per_file": results,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n{'='*60}")
    print(f"VALIDATION COMPLETE")
    print(f"  Total:   {len(results)}")
    print(f"  Passed:  {passed}")
    print(f"  Warned:  {warned}")
    print(f"  Failed:  {failed}")
    print(f"  Report:  {OUTPUT_PATH}")
    print(f"{'='*60}")

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
