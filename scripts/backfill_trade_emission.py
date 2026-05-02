"""Backfill strategy_trades.csv + strategy_returns.csv on existing sweep runs.

Sprint 84 made trade emission part of the canonical sweep finalize path, but
runs completed before the sprint shipped have family_leaderboard_results.csv
without per-trade artifacts. This script walks one or more run directories,
finds every dataset with a leaderboard but no strategy_trades.csv, loads the
matching OHLC data, and runs emit_trade_artifacts() to produce the missing
artifacts in-place. Idempotent: re-running on a fully-backfilled run is a no-op.

Usage (run on c240):
    python scripts/backfill_trade_emission.py \
        --runs-root /data/sweep_results/runs \
        --data-root /data/market_data/cfds/ohlc_engine \
        --run-id 2026-04-30_es_nq_validation \
        --run-id 2026-05-01_10market_cfd_non5m

Or scan every run under runs-root:
    python scripts/backfill_trade_emission.py \
        --runs-root /data/sweep_results/runs \
        --data-root /data/market_data/cfds/ohlc_engine \
        --all
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.data_loader import load_tradestation_csv
from modules.trade_emission import apply_parity_status, emit_trade_artifacts


def _dataset_to_market_tf(dataset_dir_name: str) -> tuple[str, str] | None:
    """ES_60m -> (ES, 60m). Returns None for unparseable names."""
    parts = dataset_dir_name.split("_")
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def _find_data_csv(market: str, timeframe: str, data_roots: list[Path]) -> Path | None:
    """Look for a market+timeframe CSV across multiple data roots.

    Tries CFD Dukascopy naming first (ES_60m_dukascopy.csv), then TradeStation
    futures naming (ES_60m_2008_2026_tradestation.csv glob).
    """
    for root in data_roots:
        if not root.exists():
            continue
        # CFD Dukascopy convention
        cfd_path = root / f"{market}_{timeframe}_dukascopy.csv"
        if cfd_path.exists():
            return cfd_path
        # TradeStation futures convention
        for candidate in root.glob(f"{market}_{timeframe}_*_tradestation.csv"):
            return candidate
        # Generic fallback: any market_timeframe*.csv
        for candidate in root.glob(f"{market}_{timeframe}*.csv"):
            return candidate
    return None


def _list_dataset_dirs(run_dir: Path) -> list[Path]:
    """Find every dataset dir containing family_leaderboard_results.csv."""
    dataset_dirs: list[Path] = []
    # Canonical layout: runs/<run>/artifacts/Outputs/<MARKET_TF>/family_leaderboard_results.csv
    for lb in run_dir.rglob("family_leaderboard_results.csv"):
        dataset_dirs.append(lb.parent)
    return sorted(set(dataset_dirs))


def backfill_run(
    run_dir: Path,
    data_roots: list[Path],
    *,
    force: bool = False,
) -> dict[str, str]:
    """Backfill every dataset under run_dir that lacks strategy_trades.csv.

    Returns dict[dataset_dir_name -> outcome_string].
    """
    results: dict[str, str] = {}
    dataset_dirs = _list_dataset_dirs(run_dir)
    if not dataset_dirs:
        print(f"[backfill] No leaderboards under {run_dir}")
        return results

    print(f"[backfill] {run_dir}: {len(dataset_dirs)} datasets to inspect")

    for ds_dir in dataset_dirs:
        ds_name = ds_dir.name
        leaderboard_csv = ds_dir / "family_leaderboard_results.csv"
        trades_csv = ds_dir / "strategy_trades.csv"

        if trades_csv.exists() and not force:
            print(f"  [SKIP] {ds_name}: strategy_trades.csv already exists")
            results[ds_name] = "SKIPPED_EXISTS"
            continue

        market_tf = _dataset_to_market_tf(ds_name)
        if market_tf is None:
            print(f"  [WARN] {ds_name}: unparseable dataset name, skipping")
            results[ds_name] = "BAD_NAME"
            continue
        market, timeframe = market_tf

        data_csv = _find_data_csv(market, timeframe, data_roots)
        if data_csv is None:
            print(f"  [WARN] {ds_name}: no data CSV found for {market}/{timeframe}")
            results[ds_name] = "NO_DATA"
            continue

        print(f"  [{ds_name}] Loading {data_csv.name}")
        t0 = time.perf_counter()
        try:
            data = load_tradestation_csv(data_csv)
        except Exception as exc:
            print(f"    [ERROR] failed to load data: {exc}")
            results[ds_name] = "DATA_LOAD_FAILED"
            continue
        print(f"    Loaded {len(data):,} bars in {time.perf_counter() - t0:.1f}s")

        try:
            emission_results = emit_trade_artifacts(
                leaderboard_csv=leaderboard_csv,
                data=data,
                output_dir=ds_dir,
                market=market,
                timeframe=timeframe,
            )
            apply_parity_status(leaderboard_csv, emission_results)
        except Exception as exc:
            print(f"    [ERROR] emission failed: {exc}")
            import traceback as _tb
            _tb.print_exc()
            results[ds_name] = "EMISSION_FAILED"
            continue

        n_ok = sum(1 for r in emission_results.values() if r.status == "OK")
        n_failed = sum(
            1 for r in emission_results.values()
            if r.status in {"PARITY_FAILED", "REBUILD_FAILED", "NO_TRADES"}
        )
        results[ds_name] = f"OK_{n_ok}_FAILED_{n_failed}"
        print(f"  [{ds_name}] {n_ok} OK, {n_failed} failed")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=Path("/data/sweep_results/runs"),
        help="Root containing per-run directories",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        action="append",
        default=None,
        help="Where to find OHLC CSVs (can repeat). "
        "Default: /data/market_data/cfds/ohlc_engine and /data/market_data/futures",
    )
    parser.add_argument(
        "--run-id",
        action="append",
        default=None,
        help="Specific run_id to backfill (can repeat). Mutually exclusive with --all.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Backfill every run under runs-root.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing strategy_trades.csv files.",
    )
    args = parser.parse_args()

    data_roots = args.data_root or [
        Path("/data/market_data/cfds/ohlc_engine"),
        Path("/data/market_data/futures"),
    ]

    if args.all and args.run_id:
        parser.error("--all and --run-id are mutually exclusive")
    if not args.all and not args.run_id:
        parser.error("specify either --all or one or more --run-id")

    if args.all:
        run_dirs = sorted(p for p in args.runs_root.iterdir() if p.is_dir())
    else:
        run_dirs = [args.runs_root / rid for rid in args.run_id]

    summary: dict[str, dict[str, str]] = {}
    overall_start = time.perf_counter()
    for run_dir in run_dirs:
        if not run_dir.exists():
            print(f"[backfill] Run dir does not exist: {run_dir}")
            continue
        print(f"\n{'=' * 72}\n{run_dir}\n{'=' * 72}")
        summary[run_dir.name] = backfill_run(run_dir, data_roots, force=args.force)

    print(f"\n{'=' * 72}\nBACKFILL SUMMARY ({time.perf_counter() - overall_start:.1f}s)\n{'=' * 72}")
    for run_name, results in summary.items():
        n_total = len(results)
        n_ok = sum(1 for v in results.values() if v.startswith("OK_"))
        n_skipped = sum(1 for v in results.values() if v == "SKIPPED_EXISTS")
        print(f"  {run_name}: {n_ok}/{n_total} backfilled, {n_skipped} already had artifacts")
        for ds, outcome in results.items():
            if outcome not in {"SKIPPED_EXISTS"} and not outcome.startswith("OK_"):
                print(f"    [{outcome}] {ds}")


if __name__ == "__main__":
    main()
