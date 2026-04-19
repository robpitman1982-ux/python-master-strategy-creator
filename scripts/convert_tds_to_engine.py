#!/usr/bin/env python3
"""Convert Tick Data Suite (Dukascopy/Metatrader) CSVs to TradeStation format.

TDS input:
    Date,Time,Open,High,Low,Close,Tick volume
    2012.01.16,00:00:00,1290.9,1296.9,1285.9,1295.6,4453

TradeStation output:
    "Date","Time","Open","High","Low","Close","Vol","OI"
    01/16/2012,00:00,1290.9,1296.9,1285.9,1295.6,4453,0

Usage:
    python scripts/convert_tds_to_engine.py --input-dir "C:/path/to/tds/" --output-dir "Data/"
    python scripts/convert_tds_to_engine.py --input-file "USA_500_Index_GMT+0_NO-DST_H1.csv" --output-dir "Data/"
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

# TDS symbol → engine market mapping
SYMBOL_MAP: dict[str, str] = {
    "USA_500_Index":     "ES",
    "USA_100_Technical": "NQ",
    "USA_30_Index":      "YM",
    "XAUUSD":            "GC",
    "XAGUSD":            "SI",
    "US_Light_Crude":    "CL",
    "EURUSD":            "EC",
    "USDJPY":            "JY",
    "GBPUSD":            "BP",
    "AUDUSD":            "AD",
    "High_Grade_Copper": "HG",
    "Natural_Gas":       "NG",
    "Bitcoin_USD":       "BTC",
    "US_Small_Cap_2000": "RTY",
    "Germany_40_Index":  "DAX",
    "Japan_225":         "N225",
    "UK_100_Index":      "FTSE",
    "Europe_50_Index":   "STOXX",
    "France_40_Index":   "CAC",
    "USDCAD":            "USDCAD",
    "USDCHF":            "USDCHF",
    "NZDUSD":            "NZDUSD",
    "US_Brent_Crude":    "BRENT",
    "Ether_USD":         "ETH",
    # Aliases for actual TDS filenames on c240 (longer variants)
    "Bitcoin_vs_US_Dollar":   "BTC",
    "Ether_vs_US_Dollar":     "ETH",
    "USA_100_Technical_Index": "NQ",
    "US_Brent_Crude_Oil":     "BRENT",
    "US_Light_Crude_Oil":     "CL",
}

# TDS timeframe suffix → engine timeframe label
TIMEFRAME_MAP: dict[str, str] = {
    "D1":  "daily",
    "H1":  "60m",
    "M30": "30m",
    "M15": "15m",
    "M5":  "5m",
    "M1":  "1m",
}


def parse_tds_filename(filename: str) -> tuple[str, str, str]:
    """Extract TDS symbol, engine market, and engine timeframe from filename.

    Expected pattern: {SYMBOL}_GMT+0_NO-DST_{TIMEFRAME}.csv
    Returns: (tds_symbol, engine_market, engine_timeframe)
    """
    stem = Path(filename).stem  # remove .csv

    # Split on _GMT+0_NO-DST_ or _GMT (fallback)
    if "_GMT+0_NO-DST_" in stem:
        parts = stem.split("_GMT+0_NO-DST_")
        tds_symbol = parts[0]
        tf_code = parts[1]
    elif "_GMT" in stem:
        idx = stem.index("_GMT")
        tds_symbol = stem[:idx]
        # Timeframe is after the last underscore
        tf_code = stem.rsplit("_", 1)[-1]
    else:
        raise ValueError(f"Cannot parse TDS filename: {filename}")

    market = SYMBOL_MAP.get(tds_symbol)
    if market is None:
        raise ValueError(
            f"Unknown TDS symbol '{tds_symbol}' from file '{filename}'. "
            f"Known symbols: {', '.join(sorted(SYMBOL_MAP.keys()))}"
        )

    timeframe = TIMEFRAME_MAP.get(tf_code)
    if timeframe is None:
        raise ValueError(
            f"Unknown timeframe code '{tf_code}' from file '{filename}'. "
            f"Known codes: {', '.join(sorted(TIMEFRAME_MAP.keys()))}"
        )

    return tds_symbol, market, timeframe


def convert_date(tds_date: str) -> str:
    """Convert YYYY.MM.DD → MM/DD/YYYY."""
    dt = datetime.strptime(tds_date.strip(), "%Y.%m.%d")
    return dt.strftime("%m/%d/%Y")


def convert_time(tds_time: str) -> str:
    """Convert HH:MM:SS → HH:MM (strip seconds)."""
    parts = tds_time.strip().split(":")
    return f"{parts[0]}:{parts[1]}"


def convert_file(input_path: Path, output_dir: Path) -> dict:
    """Convert a single TDS CSV to TradeStation format.

    Returns a summary dict with conversion stats.
    """
    tds_symbol, market, timeframe = parse_tds_filename(input_path.name)

    # Read input
    with open(input_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        return {
            "input": input_path.name,
            "output": None,
            "status": "SKIPPED (empty)",
            "rows": 0,
        }

    # Remove duplicates by (Date, Time) — keep last occurrence
    seen: dict[tuple[str, str], int] = {}
    for i, row in enumerate(rows):
        key = (row["Date"].strip(), row["Time"].strip())
        seen[key] = i
    unique_indices = sorted(seen.values())
    rows = [rows[i] for i in unique_indices]
    n_dupes = len(unique_indices) - len(seen)  # always 0 after dedup

    # Convert rows
    converted: list[dict[str, str]] = []
    skipped = 0
    for row in rows:
        date_raw = row.get("Date", "").strip()
        time_raw = row.get("Time", "").strip()
        if not date_raw or not time_raw:
            skipped += 1
            continue
        try:
            date_out = convert_date(date_raw)
        except ValueError:
            skipped += 1
            continue
        time_out = convert_time(time_raw)

        # OHLC — pass through as-is
        open_ = row.get("Open", "").strip()
        high_ = row.get("High", "").strip()
        low_ = row.get("Low", "").strip()
        close_ = row.get("Close", "").strip()

        if not all([open_, high_, low_, close_]):
            skipped += 1
            continue

        vol = row.get("Tick volume", "0").strip() or "0"

        converted.append({
            "Date": date_out,
            "Time": time_out,
            "Open": open_,
            "High": high_,
            "Low": low_,
            "Close": close_,
            "Vol": vol,
            "OI": "0",
        })

    if not converted:
        return {
            "input": input_path.name,
            "output": None,
            "status": "SKIPPED (no valid rows)",
            "rows": 0,
        }

    # Determine date range for output filename
    first_date = converted[0]["Date"]
    last_date = converted[-1]["Date"]
    start_year = datetime.strptime(first_date, "%m/%d/%Y").year
    end_year = datetime.strptime(last_date, "%m/%d/%Y").year

    output_name = f"{market}_{timeframe}_{start_year}_{end_year}_dukascopy.csv"
    output_path = output_dir / output_name

    # Write output with quoted headers
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        # Write quoted header
        f.write('"Date","Time","Open","High","Low","Close","Vol","OI"\n')
        for row in converted:
            f.write(
                f'{row["Date"]},{row["Time"]},'
                f'{row["Open"]},{row["High"]},{row["Low"]},{row["Close"]},'
                f'{row["Vol"]},{row["OI"]}\n'
            )

    return {
        "input": input_path.name,
        "output": output_name,
        "tds_symbol": tds_symbol,
        "market": market,
        "timeframe": timeframe,
        "rows_in": len(rows),
        "rows_out": len(converted),
        "skipped": skipped,
        "duplicates_removed": len(rows) - len(unique_indices) if len(rows) != len(unique_indices) else 0,
        "date_range": f"{first_date} - {last_date}",
        "status": "OK",
    }


def verify_conversion(input_path: Path, output_path: Path) -> None:
    """Verify converted file matches original TDS data."""
    import pandas as pd

    tds = pd.read_csv(input_path)
    ts = pd.read_csv(output_path)

    # Row count
    tds_rows = len(tds)
    ts_rows = len(ts)
    match = "PASS" if tds_rows == ts_rows else "FAIL"
    print(f"  Row count: TDS={tds_rows:,}  TS={ts_rows:,}  {match}")

    # OHLC check (compare as floats)
    for col in ["Open", "High", "Low", "Close"]:
        tds_vals = pd.to_numeric(tds[col], errors="coerce")
        ts_vals = pd.to_numeric(ts[col], errors="coerce")
        if tds_vals.equals(ts_vals):
            print(f"  {col}: PASS exact match")
        else:
            diff = (tds_vals - ts_vals).abs().max()
            print(f"  {col}: max diff = {diff}")

    # First/last rows
    print(f"  TDS first: {tds.iloc[0].to_dict()}")
    print(f"  TS  first: {ts.iloc[0].to_dict()}")
    print(f"  TDS last:  {tds.iloc[-1].to_dict()}")
    print(f"  TS  last:  {ts.iloc[-1].to_dict()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert TDS (Dukascopy) CSVs to TradeStation format"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input-dir", type=str, help="Directory containing TDS CSV files")
    group.add_argument("--input-file", type=str, help="Single TDS CSV file to convert")
    parser.add_argument("--output-dir", type=str, required=True, help="Output directory for converted files")
    parser.add_argument("--verify", action="store_true", help="Run verification after conversion")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    # Collect input files
    if args.input_file:
        files = [Path(args.input_file)]
    else:
        input_dir = Path(args.input_dir)
        if not input_dir.is_dir():
            print(f"ERROR: Input directory not found: {input_dir}")
            sys.exit(1)
        # Match TDS naming pattern: *_GMT+0_NO-DST_*.csv or *_GMT*.csv
        files = sorted(input_dir.glob("*_GMT*_*.csv"))
        if not files:
            # Fallback: try all CSVs
            files = sorted(input_dir.glob("*.csv"))

    if not files:
        print("No CSV files found.")
        sys.exit(1)

    print(f"Converting {len(files)} file(s) -> {output_dir}/\n")

    results = []
    for f in files:
        print(f"  Converting: {f.name}")
        try:
            result = convert_file(f, output_dir)
            results.append(result)
            if result["status"] == "OK":
                print(f"    ->{result['output']}  ({result['rows_out']:,} rows, {result['date_range']})")
            else:
                print(f"    ->{result['status']}")
        except Exception as e:
            print(f"    ->ERROR: {e}")
            results.append({"input": f.name, "status": f"ERROR: {e}", "rows_out": 0})

    # Summary
    ok = [r for r in results if r.get("status") == "OK"]
    print(f"\n{'='*60}")
    print(f"Conversion complete: {len(ok)}/{len(results)} files converted")
    for r in ok:
        print(f"  {r['output']:40s}  {r['rows_out']:>8,} rows  {r['date_range']}")

    # Verification
    if args.verify:
        print(f"\n{'='*60}")
        print("Verification:\n")
        for r in ok:
            input_path = next(f for f in files if f.name == r["input"])
            output_path = output_dir / r["output"]
            print(f"  {r['output']}:")
            verify_conversion(input_path, output_path)
            print()


if __name__ == "__main__":
    main()
