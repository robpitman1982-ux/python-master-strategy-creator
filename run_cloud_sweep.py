from __future__ import annotations

import argparse

from cloud.launch_gcp_run import DEFAULT_CONFIG, REPO_ROOT, main as launcher_main


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
    args, passthrough = parse_args(argv)
    return launcher_main(build_launcher_argv(args, passthrough))


if __name__ == "__main__":
    raise SystemExit(main())
