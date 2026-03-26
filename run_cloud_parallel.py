"""
Parallel dual-VM launcher for strategy sweeps.

Launches two VMs in fire-and-forget mode sequentially — VM-A then VM-B.
Each VM is independent and self-deletes after uploading results to GCS.
Merge results locally after both complete using:

    python cloud/download_run.py --latest-pair

Example usage:
    python run_cloud_parallel.py --fire-and-forget
    python run_cloud_parallel.py --config-a cloud/config_es_vm_a.yaml --config-b cloud/config_es_vm_b.yaml --fire-and-forget
    python run_cloud_parallel.py --dry-run
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from cloud.launch_gcp_run import REPO_ROOT, main as launcher_main

DEFAULT_CONFIG_A = REPO_ROOT / "cloud" / "config_es_vm_a.yaml"
DEFAULT_CONFIG_B = REPO_ROOT / "cloud" / "config_es_vm_b.yaml"


def _ensure_console_storage_env() -> None:
    """Auto-detect strategy_console_storage if env var not already set."""
    if os.environ.get("STRATEGY_CONSOLE_STORAGE"):
        return
    candidates = [
        Path.home() / "strategy_console_storage",
        Path("/home/robpitman1982/strategy_console_storage"),
    ]
    for candidate in candidates:
        if candidate.exists() and (candidate / "uploads").exists():
            os.environ["STRATEGY_CONSOLE_STORAGE"] = str(candidate)
            print(f"Auto-detected storage: {candidate}")
            return
    repo_local = Path(__file__).resolve().parent / "strategy_console_storage"
    if repo_local.exists():
        os.environ["STRATEGY_CONSOLE_STORAGE"] = str(repo_local)
        print(f"Using repo-local storage: {repo_local}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch two GCP VMs in parallel for a split strategy sweep.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Launch both VMs with default split configs (SPOT, fire-and-forget)
  python run_cloud_parallel.py --fire-and-forget

  # Dry run only — shows manifests without creating VMs
  python run_cloud_parallel.py --dry-run

  # Use on-demand VMs when SPOT unavailable
  python run_cloud_parallel.py --config-a cloud/config_es_vm_a_ondemand.yaml \\
                                --config-b cloud/config_es_vm_b_ondemand.yaml \\
                                --fire-and-forget
""",
    )
    parser.add_argument(
        "--config-a",
        default=str(DEFAULT_CONFIG_A.relative_to(REPO_ROOT)),
        help="Config YAML for VM-A (default: cloud/config_es_vm_a.yaml)",
    )
    parser.add_argument(
        "--config-b",
        default=str(DEFAULT_CONFIG_B.relative_to(REPO_ROOT)),
        help="Config YAML for VM-B (default: cloud/config_es_vm_b.yaml)",
    )
    parser.add_argument(
        "--fire-and-forget",
        action="store_true",
        help="Upload bundle to GCS then exit (VM runs independently).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run preflight and manifest creation only; no VM created.",
    )
    parser.add_argument(
        "--keep-vm",
        action="store_true",
        help="Preserve VMs after run for inspection.",
    )
    return parser.parse_args(argv)


def build_launcher_argv(config: str, args: argparse.Namespace) -> list[str]:
    argv = ["--config", config]
    if args.fire_and_forget:
        argv.append("--fire-and-forget")
    if args.dry_run:
        argv.append("--dry-run")
    if args.keep_vm:
        argv.append("--keep-vm")
    return argv


def main(argv: list[str] | None = None) -> int:
    _ensure_console_storage_env()
    args = parse_args(argv)

    mode = "DRY RUN" if args.dry_run else ("FIRE-AND-FORGET" if args.fire_and_forget else "BLOCKING")
    print(f"=== Parallel dual-VM launch ({mode}) ===")
    print(f"  VM-A config: {args.config_a}")
    print(f"  VM-B config: {args.config_b}")
    print()

    # Launch VM-A
    print("--- Launching VM-A ---")
    argv_a = build_launcher_argv(args.config_a, args)
    exit_a = launcher_main(argv_a)
    print(f"VM-A launcher finished with exit code: {exit_a}")
    print()

    if not args.dry_run and exit_a != 0:
        print("WARNING: VM-A launcher returned non-zero exit code. Proceeding with VM-B anyway.")
    print("--- Launching VM-B ---")
    argv_b = build_launcher_argv(args.config_b, args)
    exit_b = launcher_main(argv_b)
    print(f"VM-B launcher finished with exit code: {exit_b}")
    print()

    # Summary
    print("=== Launch summary ===")
    print(f"  VM-A: {'OK' if exit_a == 0 else 'FAILED'} (exit {exit_a})")
    print(f"  VM-B: {'OK' if exit_b == 0 else 'FAILED'} (exit {exit_b})")

    if not args.dry_run and args.fire_and_forget:
        print()
        print("Both VMs are running independently. When complete, merge results with:")
        print("  python cloud/download_run.py --latest-pair")

    # Return 0 only if both succeeded
    return 0 if exit_a == 0 and exit_b == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
