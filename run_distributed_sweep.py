#!/usr/bin/env python3
"""Plan an exact multi-host CFD sweep dispatch.

This script does not start remote work. It builds and validates the same exact
job configs that each host would run, then prints per-host commands using
run_cluster_sweep.py --jobs so assignments cannot turn into a cross-product.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from modules.distributed_sweep import (
    assign_jobs_to_hosts,
    build_host_command,
    format_job_spec,
    job_weight,
    parse_host_specs,
)
from modules.instrument_universe import InstrumentUniverseError, validate_sweep_config
from run_cluster_sweep import (
    MARKETS_CONFIG,
    build_job_list,
    build_single_config,
    parse_job_specs,
)


def load_markets_config(path: Path = MARKETS_CONFIG) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Markets config not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def validate_jobs(
    jobs: list[tuple[str, str]],
    all_markets: dict,
    *,
    data_dir: str,
    workers: int,
) -> list[str]:
    errors: list[str] = []
    for market, timeframe in jobs:
        config = build_single_config(
            market=market,
            timeframe=timeframe,
            market_spec=all_markets[market],
            data_dir=data_dir,
            workers=workers,
        )
        try:
            validate_sweep_config(config, require_existing_data=False)
        except InstrumentUniverseError as exc:
            errors.append(f"{market}:{timeframe}: {exc}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan an exact distributed CFD sweep")
    parser.add_argument("--hosts", nargs="+", required=True,
                        help="Host specs as HOST:WORKERS, e.g. c240:36 gen8:24")
    parser.add_argument("--markets", nargs="*", default=None,
                        help="Markets to sweep when --jobs is not supplied")
    parser.add_argument("--timeframes", nargs="*", default=None,
                        help="Timeframes to sweep when --jobs is not supplied")
    parser.add_argument("--jobs", nargs="*", default=None,
                        help="Exact jobs in MARKET:TIMEFRAME form")
    parser.add_argument("--data-dir", default="/data/market_data/cfds/ohlc_engine",
                        help="Data directory visible from each host")
    parser.add_argument("--remote-root", default="~/python-master-strategy-creator",
                        help="Repo path on each host for the printed commands")
    parser.add_argument("--dry-run-commands", action="store_true",
                        help="Print host commands with run_cluster_sweep.py --dry-run")
    args = parser.parse_args()

    try:
        hosts = parse_host_specs(args.hosts)
        all_markets = load_markets_config()

        if args.jobs:
            explicit_jobs = parse_job_specs(args.jobs)
            markets = sorted({market for market, _ in explicit_jobs})
            timeframes = sorted({tf for _, tf in explicit_jobs})
        else:
            explicit_jobs = None
            markets = args.markets or sorted(all_markets.keys())
            timeframes = args.timeframes or ["daily", "60m", "30m", "15m"]

        jobs = build_job_list(all_markets, markets, timeframes, explicit_jobs)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    assignments = assign_jobs_to_hosts(jobs, hosts)

    validation_errors: list[str] = []
    for host in hosts:
        host_jobs = assignments[host.name]
        validation_errors.extend(
            validate_jobs(
                host_jobs,
                all_markets,
                data_dir=args.data_dir,
                workers=host.workers,
            )
        )

    print("=" * 72)
    print(f"DISTRIBUTED CFD SWEEP PLAN: {len(jobs)} jobs across {len(hosts)} hosts")
    print(f"Data dir:    {args.data_dir}")
    print(f"Remote root: {args.remote_root}")
    print("=" * 72)

    for host in hosts:
        host_jobs = assignments[host.name]
        weight = sum(job_weight(job) for job in host_jobs)
        print(f"\n{host.name} ({host.workers} workers): {len(host_jobs)} jobs, weight {weight:g}")
        print("  Jobs: " + " ".join(format_job_spec(job) for job in host_jobs))
        command = build_host_command(
            host_jobs,
            data_dir=args.data_dir,
            workers=host.workers,
            remote_root=args.remote_root,
            dry_run=args.dry_run_commands,
        )
        print(f"  Command: {command}")

    if validation_errors:
        print("\nVALIDATION FAILURES:")
        for error in validation_errors:
            print(f"  - {error}")
        sys.exit(1)

    print("\nValidation: OK")
    print("No remote work was started.")


if __name__ == "__main__":
    main()
