#!/usr/bin/env python3
"""Session 71 Task 2: Batch convert TDS CSVs to engine format using ThreadPoolExecutor."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.convert_tds_to_engine import convert_file

DEFAULT_INVENTORY = Path(__file__).resolve().parent.parent / "docs" / "session71" / "source_inventory.json"
DEFAULT_LOG = Path(__file__).resolve().parent.parent / "docs" / "session71" / "conversion_log.json"


def convert_one(entry: dict, force: bool) -> dict:
    """Convert a single file. Returns result dict."""
    source = Path(entry["source_path"])
    target = Path(entry["target_path"])
    symbol = entry["symbol"]
    tf = entry["timeframe"]

    # Skip if already exists and not forced
    if not force and target.exists() and target.stat().st_size > 0:
        return {
            "source": str(source),
            "target": str(target),
            "symbol": symbol,
            "timeframe": tf,
            "status": "skipped",
            "error": None,
            "rows_in": 0,
            "rows_out": 0,
            "elapsed_s": 0.0,
        }

    t0 = time.monotonic()
    try:
        # convert_file writes to output_dir with its own naming ({SYM}_{TF}_{YEAR}_{YEAR}_dukascopy.csv)
        # We need canonical name ({SYM}_{TF}_dukascopy.csv), so convert to temp then rename
        target.parent.mkdir(parents=True, exist_ok=True)
        result = convert_file(source, target.parent)
        elapsed = time.monotonic() - t0

        if result["status"] != "OK":
            return {
                "source": str(source),
                "target": str(target),
                "symbol": symbol,
                "timeframe": tf,
                "status": "failed",
                "error": f"convert_file returned: {result['status']}",
                "rows_in": result.get("rows_in", 0),
                "rows_out": result.get("rows_out", 0),
                "elapsed_s": elapsed,
            }

        # Rename from year-range name to canonical name if different
        actual_output = target.parent / result["output"]
        if actual_output != target:
            if target.exists():
                target.unlink()
            actual_output.rename(target)

        return {
            "source": str(source),
            "target": str(target),
            "symbol": symbol,
            "timeframe": tf,
            "status": "ok",
            "error": None,
            "rows_in": result.get("rows_in", 0),
            "rows_out": result.get("rows_out", 0),
            "elapsed_s": elapsed,
        }
    except Exception as e:
        elapsed = time.monotonic() - t0
        return {
            "source": str(source),
            "target": str(target),
            "symbol": symbol,
            "timeframe": tf,
            "status": "failed",
            "error": str(e),
            "rows_in": 0,
            "rows_out": 0,
            "elapsed_s": elapsed,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch convert TDS CSVs to engine format")
    parser.add_argument("--workers", type=int, default=8, help="Thread pool size (default 8)")
    parser.add_argument("--dry-run", action="store_true", help="Print plan only")
    parser.add_argument("--force", action="store_true", help="Re-convert even if target exists")
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY, help="Inventory JSON path")
    args = parser.parse_args()

    with open(args.inventory) as f:
        inventory = json.load(f)

    # Categorize
    to_skip = [e for e in inventory if e["already_converted"] and not args.force]
    to_convert = [e for e in inventory if not e["already_converted"] or args.force]

    print(f"Inventory: {len(inventory)} files")
    print(f"  Skip (already converted): {len(to_skip)}")
    print(f"  Pending conversion: {len(to_convert)}")
    print(f"  Workers: {args.workers}")

    # Check for duplicate targets
    targets = [e["target_path"] for e in inventory]
    dupes = set(t for t in targets if targets.count(t) > 1)
    if dupes:
        print(f"\nERROR: Duplicate target paths: {dupes}")
        return 1

    if args.dry_run:
        print("\n--- DRY RUN ---")
        for e in to_skip:
            print(f"  SKIP  {e['symbol']}_{e['timeframe']}: {e['target_path']}")
        for e in to_convert:
            print(f"  CONV  {e['symbol']}_{e['timeframe']}: {e['source_path']} -> {e['target_path']}")
        print(f"\nDry run complete. {len(to_convert)} files would be converted.")
        return 0

    # Execute conversions
    t0 = time.monotonic()
    results = []

    # Add skip results
    for e in to_skip:
        results.append({
            "source": e["source_path"],
            "target": e["target_path"],
            "symbol": e["symbol"],
            "timeframe": e["timeframe"],
            "status": "skipped",
            "error": None,
            "rows_in": 0,
            "rows_out": 0,
            "elapsed_s": 0.0,
        })

    # Convert in parallel
    ok_count = 0
    fail_count = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(convert_one, e, args.force): e for e in to_convert}
        for future in as_completed(futures):
            entry = futures[future]
            result = future.result()
            results.append(result)
            tag = result["status"].upper()
            rows = f"{result['rows_in']}->{result['rows_out']}" if result["rows_out"] else ""
            elapsed = f"{result['elapsed_s']:.1f}s"
            print(f"  [{tag:7s}] {result['symbol']}_{result['timeframe']} {rows} {elapsed}")
            if result["status"] == "ok":
                ok_count += 1
            elif result["status"] == "failed":
                fail_count += 1
                print(f"           ERROR: {result['error']}")

    total_elapsed = time.monotonic() - t0

    # Write log
    log_path = DEFAULT_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w") as f:
        json.dump(results, f, indent=2)

    # Summary
    skip_count = sum(1 for r in results if r["status"] == "skipped")
    print(f"\n{'='*60}")
    print(f"BATCH CONVERSION COMPLETE")
    print(f"  Total:    {len(results)}")
    print(f"  OK:       {ok_count}")
    print(f"  Skipped:  {skip_count}")
    print(f"  Failed:   {fail_count}")
    print(f"  Elapsed:  {total_elapsed:.1f}s")
    print(f"  Log:      {log_path}")
    print(f"{'='*60}")

    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
