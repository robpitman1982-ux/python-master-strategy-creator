#!/usr/bin/env python3
"""Batch sweep launcher — orchestrates sweeps across all markets/timeframes.

Generates individual sweep configs from cfd_markets.yaml, runs them
sequentially via run_local_sweep.py, tracks progress in a manifest,
and supports resume after interruption.

Usage:
    # Sweep all priority markets, all timeframes
    python run_cluster_sweep.py --markets ES NQ YM GC --timeframes 5m 15m 30m 60m daily

    # Sweep single market for testing
    python run_cluster_sweep.py --markets ES --timeframes daily

    # Resume interrupted sweep
    python run_cluster_sweep.py --resume

    # Check status of current sweep
    python run_cluster_sweep.py --status

    # Dry run — show plan without executing
    python run_cluster_sweep.py --markets ES NQ --timeframes daily 60m --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = REPO_ROOT / "sweep_manifest.json"
MARKETS_CONFIG = REPO_ROOT / "configs" / "cfd_markets.yaml"


def load_manifest() -> dict:
    """Load or create the sweep manifest."""
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH) as f:
            return json.load(f)
    return {"jobs": {}, "created": datetime.now().isoformat(), "updated": ""}


def save_manifest(manifest: dict) -> None:
    """Save the sweep manifest."""
    manifest["updated"] = datetime.now().isoformat()
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)


def job_key(market: str, timeframe: str) -> str:
    return f"{market}_{timeframe}"


def show_status() -> None:
    """Print current sweep status from manifest."""
    manifest = load_manifest()
    jobs = manifest.get("jobs", {})
    if not jobs:
        print("No sweep manifest found. Start a sweep first.")
        return

    # Count by status
    statuses = {}
    for j in jobs.values():
        s = j.get("status", "unknown")
        statuses[s] = statuses.get(s, 0) + 1

    print(f"Sweep Manifest: {MANIFEST_PATH}")
    print(f"  Created: {manifest.get('created', '?')}")
    print(f"  Updated: {manifest.get('updated', '?')}")
    print(f"  Total jobs: {len(jobs)}")
    for s, count in sorted(statuses.items()):
        print(f"    {s}: {count}")

    print(f"\n{'Market':<10} {'TF':<8} {'Status':<12} {'Duration':<10} {'Exit'}")
    print("-" * 55)
    for key in sorted(jobs.keys()):
        j = jobs[key]
        market = j.get("market", "?")
        tf = j.get("timeframe", "?")
        status = j.get("status", "?")
        duration = j.get("duration_secs", "")
        if duration:
            m, s = divmod(int(duration), 60)
            h, m = divmod(m, 60)
            duration = f"{h}h{m:02d}m{s:02d}s"
        exit_code = j.get("exit_code", "")
        print(f"  {market:<8} {tf:<8} {status:<12} {duration:<10} {exit_code}")


def build_single_config(
    market: str,
    timeframe: str,
    market_spec: dict,
    data_dir: str,
    workers: int,
) -> dict:
    """Build a sweep config for a single market/timeframe combo."""
    data_files = market_spec.get("data_files", {})
    if timeframe not in data_files:
        return {}

    engine = market_spec.get("engine", {})
    oos_date = market_spec.get("oos_split_date", "2020-01-01")

    return {
        "sweep": {
            "name": f"{market.lower()}_{timeframe}_cfd",
            "output_dir": "Outputs",
        },
        "datasets": [{
            "path": f"{data_dir}/{data_files[timeframe]}",
            "market": market,
            "timeframe": timeframe,
        }],
        "strategy_types": "all",
        "engine": {
            "initial_capital": 250000.0,
            "risk_per_trade": 0.01,
            "commission_per_contract": engine.get("commission_per_contract", 0),
            "slippage_ticks": engine.get("slippage_ticks", 0),
            "tick_value": engine.get("tick_value", 12.50),
            "dollars_per_point": engine.get("dollars_per_point", 50.0),
            "use_vectorized_trades": True,
        },
        "pipeline": {
            "max_workers_sweep": workers,
            "max_workers_refinement": workers,
            "max_candidates_to_refine": 5,
            "oos_split_date": oos_date,
            "skip_portfolio_evaluation": True,
            "skip_portfolio_selector": True,
        },
        "promotion_gate": {
            "min_profit_factor": 1.0,
            "min_average_trade": 0.0,
            "require_positive_net_pnl": False,
            "min_trades": 50,
            "min_trades_per_year": 3.0,
            "max_promoted_candidates": 20,
        },
        "leaderboard": {
            "min_net_pnl": 0.0,
            "min_pf": 1.0,
            "min_oos_pf": 1.0,
            "min_total_trades": 60,
        },
    }


def run_batch(
    markets: list[str],
    timeframes: list[str],
    data_dir: str = "Data",
    workers: int = 36,
    dry_run: bool = False,
    resume: bool = False,
) -> int:
    """Run sweeps for all market/timeframe combinations."""
    # Load market specs
    if not MARKETS_CONFIG.exists():
        print(f"ERROR: Markets config not found: {MARKETS_CONFIG}")
        print("Run: python scripts/generate_sweep_configs.py first")
        return 1

    with open(MARKETS_CONFIG) as f:
        all_markets = yaml.safe_load(f)

    # Validate markets
    unknown = set(markets) - set(all_markets.keys())
    if unknown:
        print(f"ERROR: Unknown markets: {', '.join(sorted(unknown))}")
        print(f"Available: {', '.join(sorted(all_markets.keys()))}")
        return 1

    # Build job list
    jobs = []
    for market in markets:
        for tf in timeframes:
            if tf in all_markets[market].get("data_files", {}):
                jobs.append((market, tf))

    if not jobs:
        print("No valid market/timeframe combinations found.")
        return 1

    # Load or create manifest
    manifest = load_manifest()
    if not resume:
        # Fresh sweep — reset manifest
        manifest = {"jobs": {}, "created": datetime.now().isoformat(), "updated": ""}

    # Plan
    print("=" * 60)
    print(f"CLUSTER SWEEP: {len(jobs)} jobs")
    print(f"  Markets:    {', '.join(markets)}")
    print(f"  Timeframes: {', '.join(timeframes)}")
    print(f"  Workers:    {workers}")
    print(f"  Data dir:   {data_dir}")
    print(f"  Resume:     {resume}")
    print("=" * 60)

    # Skip completed jobs
    pending_jobs = []
    for market, tf in jobs:
        key = job_key(market, tf)
        existing = manifest["jobs"].get(key, {})
        if existing.get("status") == "completed" and resume:
            print(f"  SKIP {market} {tf} (already completed)")
        else:
            pending_jobs.append((market, tf))
            manifest["jobs"][key] = {
                "market": market,
                "timeframe": tf,
                "status": "pending",
            }

    save_manifest(manifest)

    if not pending_jobs:
        print("\nAll jobs already completed!")
        return 0

    print(f"\n{len(pending_jobs)} job(s) to run:\n")
    for i, (market, tf) in enumerate(pending_jobs, 1):
        print(f"  {i:3d}. {market} {tf}")

    if dry_run:
        print("\n[DRY RUN] Would run the above jobs. Exiting.")
        return 0

    # Import here to avoid import cost during --status/--dry-run
    from run_local_sweep import run_sweep

    # Run jobs sequentially
    total = len(pending_jobs)
    failed = 0
    sweep_start = time.time()

    for i, (market, tf) in enumerate(pending_jobs, 1):
        key = job_key(market, tf)
        print(f"\n{'#' * 60}")
        print(f"# JOB {i}/{total}: {market} {tf}")
        print(f"{'#' * 60}")

        # Generate temp config
        spec = all_markets[market]
        config = build_single_config(market, tf, spec, data_dir, workers)
        if not config:
            print(f"  SKIP: no data file for {market} {tf}")
            manifest["jobs"][key]["status"] = "skipped"
            save_manifest(manifest)
            continue

        tmp_config_path = REPO_ROOT / f".tmp_sweep_{market}_{tf}.yaml"
        with open(tmp_config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        manifest["jobs"][key]["status"] = "running"
        manifest["jobs"][key]["started"] = datetime.now().isoformat()
        save_manifest(manifest)

        job_start = time.time()
        exit_code = run_sweep(str(tmp_config_path))
        job_duration = time.time() - job_start

        manifest["jobs"][key]["exit_code"] = exit_code
        manifest["jobs"][key]["duration_secs"] = round(job_duration, 1)
        manifest["jobs"][key]["finished"] = datetime.now().isoformat()

        if exit_code == 0:
            manifest["jobs"][key]["status"] = "completed"
        else:
            manifest["jobs"][key]["status"] = "failed"
            failed += 1

        save_manifest(manifest)

        # Clean up temp config
        try:
            tmp_config_path.unlink()
        except OSError:
            pass

        # ETA
        elapsed = time.time() - sweep_start
        avg_per_job = elapsed / i
        remaining = (total - i) * avg_per_job
        eta_h = int(remaining // 3600)
        eta_m = int((remaining % 3600) // 60)
        print(f"\n  Progress: {i}/{total}  ETA: ~{eta_h}h{eta_m:02d}m")

    # Aggregate leaderboard
    if failed < total:
        print(f"\n{'=' * 60}")
        print("Aggregating master leaderboard...")
        try:
            from modules.master_leaderboard import write_master_leaderboards
            output_dir = "Outputs"
            classic_df, bootcamp_df = write_master_leaderboards(output_dir)
            if classic_df is not None:
                print(f"  Master leaderboard: {len(classic_df)} strategies")
        except Exception as e:
            print(f"  Leaderboard aggregation failed: {e}")

    # Final summary
    total_time = time.time() - sweep_start
    h = int(total_time // 3600)
    m = int((total_time % 3600) // 60)
    s = int(total_time % 60)

    print(f"\n{'=' * 60}")
    print(f"BATCH SWEEP COMPLETE")
    print(f"  Total time: {h}h{m:02d}m{s:02d}s")
    print(f"  Completed:  {total - failed}/{total}")
    if failed:
        print(f"  Failed:     {failed}")
    print(f"  Manifest:   {MANIFEST_PATH}")
    print(f"{'=' * 60}")

    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch sweep launcher for local compute cluster"
    )
    parser.add_argument("--markets", nargs="*", default=None,
                        help="Markets to sweep (e.g., ES NQ GC)")
    parser.add_argument("--timeframes", nargs="*", default=None,
                        help="Timeframes to sweep (e.g., daily 60m 30m)")
    parser.add_argument("--data-dir", type=str, default="Data",
                        help="Data directory")
    parser.add_argument("--workers", type=int, default=36,
                        help="Parallel workers per sweep")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from manifest, skipping completed jobs")
    parser.add_argument("--status", action="store_true",
                        help="Show current sweep status")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show plan without executing")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.resume:
        # Load markets/timeframes from existing manifest
        manifest = load_manifest()
        jobs = manifest.get("jobs", {})
        if not jobs:
            print("No manifest found. Start a new sweep instead.")
            sys.exit(1)
        markets_set = set()
        tf_set = set()
        for j in jobs.values():
            markets_set.add(j["market"])
            tf_set.add(j["timeframe"])
        markets = sorted(markets_set)
        timeframes = sorted(tf_set)
        exit_code = run_batch(markets, timeframes, args.data_dir, args.workers,
                              args.dry_run, resume=True)
        sys.exit(exit_code)

    if not args.markets:
        # Default: all markets from cfd_markets.yaml
        if MARKETS_CONFIG.exists():
            with open(MARKETS_CONFIG) as f:
                all_markets = yaml.safe_load(f)
            args.markets = list(all_markets.keys())
        else:
            print("ERROR: No --markets specified and no cfd_markets.yaml found.")
            sys.exit(1)

    if not args.timeframes:
        args.timeframes = ["5m", "15m", "30m", "60m", "daily"]

    exit_code = run_batch(args.markets, args.timeframes, args.data_dir,
                          args.workers, args.dry_run)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
