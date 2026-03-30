"""Generate strategy_returns.csv files for all accepted strategies.

Reads Outputs/ultimate_leaderboard_bootcamp.csv, rebuilds trades for each
accepted strategy, and writes per-dataset strategy_returns.csv files into
the corresponding Outputs/runs/{run_id}/Outputs/{MARKET}_{TIMEFRAME}/ folders.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

from modules.data_loader import load_tradestation_csv
from modules.portfolio_evaluator import _rebuild_strategy_from_leaderboard_row

REPO_ROOT = Path(__file__).resolve().parent
LEADERBOARD_PATH = REPO_ROOT / "Outputs" / "ultimate_leaderboard_bootcamp.csv"
DATA_DIR = REPO_ROOT / "Data"
RUNS_DIR = REPO_ROOT / "Outputs" / "runs"


def _dataset_to_folder(dataset: str) -> str:
    """'NQ_daily_2008_2026_tradestation.csv' -> 'NQ_daily'."""
    stem = dataset.replace("_tradestation.csv", "").replace(".csv", "")
    parts = stem.split("_")
    if len(parts) >= 2:
        return f"{parts[0]}_{parts[1]}"
    return stem


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

        # Load data once for this dataset
        t0 = time.time()
        data = load_tradestation_csv(data_csv)
        print(f"  Data loaded: {len(data)} bars ({time.time() - t0:.1f}s)")

        # Build daily returns and per-trade PnL for each strategy
        daily_returns: dict[str, pd.Series] = {}
        trade_rows: list[dict] = []  # per-trade PnL rows for strategy_trades.csv
        rebuilt = 0

        for _, row in group.iterrows():
            strategy_name = str(row.get("leader_strategy_name", "UNKNOWN")).strip()
            strategy_type = str(row.get("strategy_type", "")).strip()
            if strategy_name in ["", "NONE"]:
                continue

            # Use strategy_type prefix to disambiguate duplicate strategy names
            col_key = f"{strategy_type}_{strategy_name}" if strategy_type else strategy_name

            try:
                print(f"    Attempting rebuild: {col_key}")
                print(f"      strategy_type={strategy_type}, leader_source={row.get('leader_source','?')}")
                print(f"      best_combo_strategy_name={row.get('best_combo_strategy_name','?')}")
                print(f"      leader_hold_bars={row.get('leader_hold_bars','?')}, leader_exit_type={row.get('leader_exit_type','?')}")
                print(f"      leader_stop_distance_atr={row.get('leader_stop_distance_atr','?')}")
                print(f"      outputs_dir={outputs_dir}")

                trades_df, filters_str, cfg = _rebuild_strategy_from_leaderboard_row(
                    row=row,
                    data=data,
                    outputs_dir=outputs_dir,
                    market_symbol=market,
                    timeframe=timeframe,
                )

                if trades_df.empty:
                    print(f"    WARN: No trades rebuilt for {col_key} (empty DataFrame returned)")
                    continue

                trades_df["exit_time"] = pd.to_datetime(trades_df["exit_time"])
                trades_df["net_pnl"] = pd.to_numeric(trades_df["net_pnl"], errors="coerce").fillna(0.0)

                # Daily resampled returns (for correlation matrix)
                daily_pnl = trades_df.resample("D", on="exit_time")["net_pnl"].sum().fillna(0.0)
                daily_returns[col_key] = daily_pnl

                # Per-trade PnL rows (for MC simulation)
                for _, trade in trades_df.iterrows():
                    trade_rows.append({
                        "exit_time": trade["exit_time"],
                        "strategy": col_key,
                        "net_pnl": trade["net_pnl"],
                    })

                rebuilt += 1

            except Exception as e:
                import traceback
                print(f"    REBUILD FAILED for {col_key}: {e}")
                traceback.print_exc()

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
