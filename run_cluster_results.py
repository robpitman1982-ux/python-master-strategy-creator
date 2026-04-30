#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from modules.cluster_results import finalize_cluster_run, ingest_host_results
from run_cluster_sweep import parse_job_specs


def _cmd_ingest(args: argparse.Namespace) -> int:
    jobs = parse_job_specs(args.jobs)
    result = ingest_host_results(
        run_id=args.run_id,
        host=args.host,
        source_root=args.source_root,
        jobs=jobs,
        log_path=args.log_path,
        storage_root=Path(args.storage_root).expanduser() if args.storage_root else None,
        commit=args.commit,
    )
    print(
        f"Ingested {len(result['copied_datasets'])} dataset(s) for {args.host} into run {args.run_id}"
    )
    for dataset_name in result["copied_datasets"]:
        print(f"  - {dataset_name}")
    print(f"Manifest: {result['manifest_path']}")
    return 0


def _cmd_finalize(args: argparse.Namespace) -> int:
    result = finalize_cluster_run(
        run_id=args.run_id,
        storage_root=Path(args.storage_root).expanduser() if args.storage_root else None,
        emit_cfd_alias=not args.no_cfd_alias,
        publish_exports=not args.no_publish_exports,
    )
    print(
        f"Finalized run {result['run_id']}: "
        f"master_rows={result['master_rows']}, ultimate_rows={result['ultimate_rows']}"
    )
    for path_text in result["exported_files"]:
        print(f"  Exported: {path_text}")
    print(f"Manifest: {result['manifest_path']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest local-cluster sweep results into strategy_console_storage and rebuild leaderboards."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest-host", help="Copy one host's finished job results into a canonical run.")
    ingest.add_argument("--run-id", required=True)
    ingest.add_argument("--host", required=True)
    ingest.add_argument("--source-root", required=True, help="Remote/local temp tree root, e.g. /tmp/psc_9ed5648")
    ingest.add_argument("--jobs", nargs="+", required=True, help="Exact MARKET:TIMEFRAME job list for this host")
    ingest.add_argument("--log-path", help="Optional path to the host log file")
    ingest.add_argument("--storage-root", help="Override strategy_console_storage root")
    ingest.add_argument("--commit", help="Commit SHA used for the run")
    ingest.set_defaults(func=_cmd_ingest)

    finalize = subparsers.add_parser("finalize-run", help="Build run-scoped master and cumulative ultimate leaderboards.")
    finalize.add_argument("--run-id", required=True)
    finalize.add_argument("--storage-root", help="Override strategy_console_storage root")
    finalize.add_argument("--no-cfd-alias", action="store_true", help="Do not emit master_leaderboard_cfd.csv")
    finalize.add_argument("--no-publish-exports", action="store_true", help="Do not mirror run master / ultimate into exports/")
    finalize.set_defaults(func=_cmd_finalize)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
