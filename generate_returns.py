"""Generate strategy_returns.csv files for all accepted strategies.

Reads the current canonical ultimate leaderboard, rebuilds trades for each
accepted strategy, and writes per-dataset strategy_returns.csv files into
the corresponding Outputs/runs/{run_id}/Outputs/{MARKET}_{TIMEFRAME}/ folders.

Uses ProcessPoolExecutor for CPU-bound strategy rebuilds (bypasses GIL).
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from modules.data_loader import load_tradestation_csv
from modules.portfolio_evaluator import _rebuild_strategy_from_leaderboard_row

REPO_ROOT = Path(__file__).resolve().parent
for candidate in (
    REPO_ROOT / "Outputs" / "ultimate_leaderboard_cfd.csv",
    REPO_ROOT / "Outputs" / "ultimate_leaderboard_FUTURES.csv",
    REPO_ROOT / "Outputs" / "ultimate_leaderboard.csv",
    REPO_ROOT / "Outputs" / "ultimate_leaderboard_bootcamp.csv",
):
    if candidate.exists():
        LEADERBOARD_PATH = candidate
        break
else:
    LEADERBOARD_PATH = REPO_ROOT / "Outputs" / "ultimate_leaderboard.csv"
DATA_DIR = REPO_ROOT / "Data"
RUNS_DIR = REPO_ROOT / "Outputs" / "runs"

_data_cache: dict[str, pd.DataFrame] = {}


def _load_cached(data_csv: Path) -> pd.DataFrame:
    """Load a CSV, returning cached copy if already loaded."""
    key = str(data_csv)
    if key not in _data_cache:
        _data_cache[key] = load_tradestation_csv(data_csv)
    return _data_cache[key]


def _dataset_to_folder(dataset: str) -> str:
    """'NQ_daily_2008_2026_tradestation.csv' -> 'NQ_daily'."""
    stem = dataset.replace("_tradestation.csv", "").replace(".csv", "")
    parts = stem.split("_")
    if len(parts) >= 2:
        return f"{parts[0]}_{parts[1]}"
    return stem


# --- ProcessPoolExecutor worker ---

_worker_data: dict = {}


def _worker_init(data_csv_path: str) -> None:
    """Initialize per-worker data cache (called once per process)."""
    _worker_data["data"] = load_tradestation_csv(data_csv_path)


def _rebuild_one(args: tuple) -> tuple[str, pd.Series, list[dict]] | None:
    """Rebuild a single strategy in a worker process."""
    row_dict, outputs_dir_str, market, timeframe = args
    data = _worker_data["data"]
    outputs_dir = Path(outputs_dir_str)

    strategy_name = str(row_dict.get("leader_strategy_name", "UNKNOWN")).strip()
    strategy_type = str(row_dict.get("strategy_type", "")).strip()
    if strategy_name in ["", "NONE"]:
        return None

    col_key = f"{strategy_type}_{strategy_name}" if strategy_type else strategy_name

    try:
        row = pd.Series(row_dict)
        trades_df, filters_str, cfg = _rebuild_strategy_from_leaderboard_row(
            row=row,
            data=data,
            outputs_dir=outputs_dir,
            market_symbol=market,
            timeframe=timeframe,
        )

        if trades_df.empty:
            return None

        trades_df["exit_time"] = pd.to_datetime(trades_df["exit_time"])
        trades_df["net_pnl"] = pd.to_numeric(trades_df["net_pnl"], errors="coerce").fillna(0.0)

        daily_pnl = trades_df.resample("D", on="exit_time")["net_pnl"].sum().fillna(0.0)

        per_trade: list[dict] = []
        for _, trade in trades_df.iterrows():
            per_trade.append({
                "exit_time": str(trade["exit_time"]),
                "strategy": col_key,
                "net_pnl": float(trade["net_pnl"]),
            })

        # Convert daily_pnl index to strings for pickling
        return (col_key, daily_pnl.to_dict(), per_trade)

    except Exception as e:
        print(f"    REBUILD FAILED for {col_key}: {e}")
        traceback.print_exc()
        return None


def main() -> None:
    if not LEADERBOARD_PATH.exists():
        print(f"ERROR: Leaderboard not found at {LEADERBOARD_PATH}")
        sys.exit(1)

    df = pd.read_csv(LEADERBOARD_PATH)
    mask = df["accepted_final"].astype(str).str.strip().str.lower() == "true"
    df = df[mask].copy()
    print(f"Loaded {len(df)} accepted strategies from {LEADERBOARD_PATH.name}")

    if df.empty:
        print("No accepted strategies found. Nothing to do.")
        return

    # Fix column name mismatch: CSV has leader_stop_distance_atr but
    # _rebuild_strategy_from_leaderboard_row reads leader_stop_distance_points
    if "leader_stop_distance_atr" in df.columns and "leader_stop_distance_points" not in df.columns:
        df["leader_stop_distance_points"] = df["leader_stop_distance_atr"]

    # Group by (run_id, dataset) so we load each data CSV only once
    grouped = df.groupby(["run_id", "dataset"])
    total_groups = len(grouped)
    total_written = 0

    for idx, ((run_id, dataset), group) in enumerate(grouped, 1):
        folder = _dataset_to_folder(dataset)
        parts = folder.split("_")
        market = parts[0] if parts else "UNKNOWN"
        timeframe = parts[1] if len(parts) >= 2 else "60m"

        print(f"\n[{idx}/{total_groups}] {run_id} / {folder}  ({len(group)} strategies)")

        # Locate data CSV
        data_csv = DATA_DIR / dataset
        if not data_csv.exists():
            print(f"  SKIP: Data file not found: {data_csv}")
            continue

        # Locate outputs dir (where promoted_candidates CSVs live)
        outputs_dir = RUNS_DIR / run_id / "Outputs" / folder
        if not outputs_dir.exists():
            print(f"  SKIP: Outputs dir not found: {outputs_dir}")
            continue

        # Load data once (for timing display only — workers load their own)
        t0 = time.time()
        data = _load_cached(data_csv)
        print(f"  Data loaded: {len(data)} bars ({time.time() - t0:.1f}s)")

        # Build daily returns and per-trade PnL for each strategy
        daily_returns: dict[str, pd.Series] = {}
        trade_rows: list[dict] = []
        rebuilt = 0

        # Prepare args for workers (dicts are picklable, pd.Series are not always)
        args_list = []
        for _, row in group.iterrows():
            args_list.append((
                row.to_dict(),
                str(outputs_dir),
                market,
                timeframe,
            ))

        max_workers = min(os.cpu_count() or 4, len(group))
        with ProcessPoolExecutor(
            max_workers=max_workers,
            initializer=_worker_init,
            initargs=(str(data_csv),),
        ) as executor:
            futures = {executor.submit(_rebuild_one, args): args for args in args_list}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    col_key, daily_pnl_dict, trades_list = result
                    # Reconstruct pd.Series from dict
                    daily_pnl = pd.Series(daily_pnl_dict)
                    daily_pnl.index = pd.to_datetime(daily_pnl.index)
                    daily_returns[col_key] = daily_pnl
                    trade_rows.extend(trades_list)
                    rebuilt += 1
                    print(f"    Rebuilt: {col_key}")

        if not daily_returns:
            print(f"  No strategies rebuilt for {folder}. Skipping CSV write.")
            continue

        # Write daily returns (for correlation)
        returns_df = pd.DataFrame(daily_returns)
        returns_df.index.name = "exit_time"
        returns_df = returns_df.fillna(0.0)

        out_path = outputs_dir / "strategy_returns.csv"
        returns_df.to_csv(out_path)
        print(f"  Wrote {out_path}  ({rebuilt} strategies, {len(returns_df)} days)")

        # Write per-trade PnL (for MC simulation)
        if trade_rows:
            trades_out = pd.DataFrame(trade_rows)
            trades_out = trades_out.sort_values("exit_time")
            trades_path = outputs_dir / "strategy_trades.csv"
            trades_out.to_csv(trades_path, index=False)
            print(f"  Wrote {trades_path}  ({len(trades_out)} individual trades)")

        total_written += 1

    print(f"\nDone. Wrote {total_written} strategy_returns.csv files.")


if __name__ == "__main__":
    main()
