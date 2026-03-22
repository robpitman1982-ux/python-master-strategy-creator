from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

import run_cloud_sweep
from dashboard_utils import parse_dataset_filename, read_console_selection, resolve_console_storage_paths
from paths import BACKUPS_DIR, RUN_STATUS_PATH


DEFAULT_TEMPLATE_CONFIG = Path("cloud/config_quick_test.yaml")


def _write_run_status(**payload: Any) -> None:
    RUN_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if RUN_STATUS_PATH.exists():
        try:
            existing = json.loads(RUN_STATUS_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing.update(payload)
    RUN_STATUS_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch a console-managed strategy run from the selected datasets.")
    parser.add_argument("--config-template", default=str(DEFAULT_TEMPLATE_CONFIG))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-vm", action="store_true")
    return parser.parse_args(argv)


def build_console_config(selected_datasets: list[str], template_path: Path) -> Path:
    template = yaml.safe_load(template_path.read_text(encoding="utf-8")) or {}
    template["datasets"] = []
    for filename in selected_datasets:
        info = parse_dataset_filename(filename)
        template["datasets"].append(
            {
                "path": filename,
                "market": info["market"],
                "timeframe": info["timeframe"],
            }
        )

    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    temp_config = BACKUPS_DIR / f"console_run_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.yaml"
    temp_config.write_text(yaml.safe_dump(template, sort_keys=False), encoding="utf-8")
    return temp_config


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    storage = resolve_console_storage_paths()
    selected_datasets = read_console_selection()
    if not selected_datasets:
        raise SystemExit("No datasets selected in the console. Choose datasets in the dashboard first.")

    temp_config = build_console_config(selected_datasets, Path(args.config_template))
    run_id = f"console-run-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    _write_run_status(
        run_id=run_id,
        vm_status="pending",
        run_state="starting",
        dataset=selected_datasets,
        start_time=datetime.now(UTC).isoformat(timespec="seconds"),
        end_time=None,
        storage_root=str(storage.root),
        temp_config=str(temp_config),
    )

    launcher_args = ["--config", str(temp_config)]
    if args.dry_run:
        launcher_args.append("--dry-run")
    if args.keep_vm:
        launcher_args.append("--keep-vm")

    exit_code = 1
    try:
        exit_code = run_cloud_sweep.main(launcher_args)
        _write_run_status(
            vm_status="completed",
            run_state="completed" if exit_code == 0 else "failed",
            end_time=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        return exit_code
    except Exception:
        _write_run_status(
            vm_status="unknown",
            run_state="failed",
            end_time=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
