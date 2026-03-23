from __future__ import annotations

import argparse
import os
from pathlib import Path

from cloud.launch_gcp_run import DEFAULT_CONFIG, REPO_ROOT, main as launcher_main


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


def parse_args(argv: list[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="One-click wrapper for the GCP strategy sweep launcher.")
    parser.add_argument("--config", default=DEFAULT_CONFIG.relative_to(REPO_ROOT).as_posix(), help="Config YAML to run.")
    parser.add_argument("--dry-run", action="store_true", help="Run preflight, manifest, and bundle creation only.")
    parser.add_argument("--keep-vm", action="store_true", help="Preserve the VM after the run for inspection.")
    parser.add_argument("--keep-remote", action="store_true", help="Preserve the remote staging directory after the run.")
    return parser.parse_known_args(argv)


def build_launcher_argv(args: argparse.Namespace, passthrough: list[str]) -> list[str]:
    launcher_argv = ["--config", args.config]
    if args.dry_run:
        launcher_argv.append("--dry-run")
    if args.keep_vm:
        launcher_argv.append("--keep-vm")
    if args.keep_remote:
        launcher_argv.append("--keep-remote")
    launcher_argv.extend(passthrough)
    return launcher_argv


def main(argv: list[str] | None = None) -> int:
    _ensure_console_storage_env()
    args, passthrough = parse_args(argv)
    launcher_argv = build_launcher_argv(args, passthrough)
    print(f"Starting sweep with config: {args.config}")
    if args.dry_run:
        print("Mode: DRY RUN (no VM will be created)")
    exit_code = launcher_main(launcher_argv)
    print(f"Launcher finished with exit code: {exit_code}")

    if not args.dry_run:
        try:
            from modules.ultimate_leaderboard import aggregate_ultimate_leaderboard
            ul = aggregate_ultimate_leaderboard()
            if not ul.empty:
                print(f"\n✅ Ultimate leaderboard updated: {len(ul)} strategies across all runs")
            else:
                print("\n⚠️  No accepted strategies found across any runs")
        except Exception as e:
            print(f"\n⚠️  Ultimate leaderboard update failed: {e}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
