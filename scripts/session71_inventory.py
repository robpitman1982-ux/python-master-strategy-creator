#!/usr/bin/env python3
"""Session 71 Task 1: Inventory Dukascopy source CSVs and map to engine targets."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add repo root to path so we can import the converter
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.convert_tds_to_engine import parse_tds_filename

SOURCE_DIR = Path("/data/market_data/cfds/ohlc")
TARGET_DIR = Path("/data/market_data/cfds/ohlc_engine")
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "session71" / "source_inventory.json"


def main() -> int:
    SOURCE_DIR_resolved = SOURCE_DIR
    TARGET_DIR_resolved = TARGET_DIR

    sources = sorted(f for f in os.listdir(SOURCE_DIR_resolved) if f.endswith(".csv"))
    inventory = []
    unmappable = []

    for fname in sources:
        source_path = str(SOURCE_DIR_resolved / fname)
        size_bytes = os.path.getsize(source_path)
        try:
            tds_symbol, engine_symbol, engine_tf = parse_tds_filename(fname)
        except ValueError as e:
            unmappable.append({"file": fname, "error": str(e)})
            continue

        target_name = f"{engine_symbol}_{engine_tf}_dukascopy.csv"
        target_path = str(TARGET_DIR_resolved / target_name)
        already = os.path.exists(target_path) and os.path.getsize(target_path) > 0

        inventory.append({
            "source_path": source_path,
            "target_path": target_path,
            "symbol": engine_symbol,
            "timeframe": engine_tf,
            "tds_symbol": tds_symbol,
            "tds_tf": fname.split("_")[-1].replace(".csv", ""),
            "size_bytes": size_bytes,
            "already_converted": already,
        })

    # Check for duplicate targets
    targets = [e["target_path"] for e in inventory]
    dupes = [t for t in targets if targets.count(t) > 1]
    if dupes:
        print(f"ERROR: Duplicate target paths detected: {set(dupes)}")
        return 1

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(inventory, f, indent=2)

    already = sum(1 for e in inventory if e["already_converted"])
    pending = len(inventory) - already
    print(f"Found {len(sources)} sources | {already} already converted | {pending} pending | {len(unmappable)} unmappable")

    if unmappable:
        print("\nUnmappable files:")
        for u in unmappable:
            print(f"  {u['file']}: {u['error']}")
        return 1

    print(f"\nInventory written to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
