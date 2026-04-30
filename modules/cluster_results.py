from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from modules.master_leaderboard import write_master_leaderboards
from modules.post_ultimate_gate import build_post_ultimate_gate
from modules.ultimate_leaderboard import (
    FUTURES_ULTIMATE_FILENAME,
    LEGACY_ULTIMATE_FILENAME,
    CFD_ULTIMATE_FILENAME,
    aggregate_ultimate_leaderboard,
)
from paths import EXPORTS_DIR, RUNS_DIR


RECOVERY_COLUMNS = [
    "rank",
    "market",
    "timeframe",
    "dataset",
    "strategy_type",
    "leader_strategy_name",
    "best_refined_strategy_name",
    "best_combo_strategy_name",
    "quality_flag",
    "accepted_final",
    "leader_source",
    "best_combo_filter_class_names",
    "best_combo_filters",
    "leader_hold_bars",
    "leader_stop_distance_atr",
    "leader_min_avg_range",
    "leader_momentum_lookback",
    "leader_exit_type",
    "leader_trailing_stop_atr",
    "leader_profit_target_atr",
    "leader_signal_exit_reference",
    "oos_pf",
    "recent_12m_pf",
    "calmar_ratio",
    "deflated_sharpe_ratio",
    "leader_pf",
    "leader_avg_trade",
    "leader_net_pnl",
    "leader_max_drawdown",
    "leader_trades",
    "run_id",
    "source_file",
    "discovered_at",
]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _job_key(market: str, timeframe: str) -> str:
    return f"{market}:{timeframe}"


def _job_run_name(market: str, timeframe: str) -> str:
    return f"{market.lower()}_{timeframe}_cfd"


def _dataset_dir_name(market: str, timeframe: str) -> str:
    return f"{market}_{timeframe}"


def _copy_path(src: Path, dst: Path) -> None:
    if dst.exists():
        if dst.is_dir():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    _copy_path(src, dst)
    return True


def _latest_run_id(runs_root: Path) -> str | None:
    latest_run_path = runs_root / "LATEST_RUN.txt"
    if not latest_run_path.exists():
        return None
    text = latest_run_path.read_text(encoding="utf-8").strip()
    return text or None


def _iter_export_files(exports_dir: Path) -> Iterable[Path]:
    if not exports_dir.exists():
        return []
    return sorted(path for path in exports_dir.iterdir() if path.is_file())


def export_recovery_artifacts(*, backup_root: Path) -> dict:
    import pandas as pd

    backup_root = Path(backup_root)
    leaderboards_dir = backup_root / "leaderboards"
    recovery_dir = backup_root / "recovery"
    recovery_dir.mkdir(parents=True, exist_ok=True)

    copied_files: list[str] = []
    manifest_entries: list[dict[str, object]] = []

    readme_path = recovery_dir / "README.txt"
    readme_text = (
        "Recovery exports for strategy reconstruction support.\n"
        "\n"
        "Each *_recovery.csv file keeps the strategy-defining fields from the source leaderboard:\n"
        "- market / timeframe / dataset\n"
        "- strategy family and strategy name\n"
        "- filter class names\n"
        "- refined parameters such as hold bars and ATR stop\n"
        "- ranking and robustness metrics\n"
        "\n"
        "These files are intentionally small and suitable for Google Drive backup.\n"
        "They improve disaster recovery, but they do NOT replace the repo/code for exact rebuild parity.\n"
    )
    readme_path.write_text(readme_text, encoding="utf-8")
    copied_files.append(str(readme_path))

    if leaderboards_dir.exists():
        for csv_path in sorted(leaderboards_dir.glob("ultimate_leaderboard*.csv")):
            try:
                df = pd.read_csv(csv_path)
            except Exception as exc:
                manifest_entries.append(
                    {
                        "source": str(csv_path),
                        "error": str(exc),
                    }
                )
                continue

            selected_columns = [col for col in RECOVERY_COLUMNS if col in df.columns]
            recovery_df = df[selected_columns].copy()
            recovery_path = recovery_dir / f"{csv_path.stem}_recovery.csv"
            recovery_df.to_csv(recovery_path, index=False)
            copied_files.append(str(recovery_path))
            manifest_entries.append(
                {
                    "source": str(csv_path),
                    "recovery_file": str(recovery_path),
                    "rows": int(len(recovery_df)),
                    "columns": selected_columns,
                }
            )

    manifest_path = recovery_dir / "recovery_manifest.json"
    _write_json(
        manifest_path,
        {
            "generated_utc": _utc_now(),
            "backup_root": str(backup_root),
            "leaderboards_dir": str(leaderboards_dir),
            "recovery_dir": str(recovery_dir),
            "files": manifest_entries,
        },
    )
    copied_files.append(str(manifest_path))

    return {
        "backup_root": str(backup_root),
        "recovery_dir": str(recovery_dir),
        "copied_files": copied_files,
    }


@dataclass(frozen=True)
class ClusterRunPaths:
    run_dir: Path
    artifacts_dir: Path
    outputs_dir: Path
    logs_dir: Path
    meta_dir: Path
    manifest_path: Path


def resolve_cluster_run_paths(run_id: str, *, storage_root: Path | None = None) -> ClusterRunPaths:
    runs_root = (storage_root / "runs") if storage_root is not None else RUNS_DIR
    run_dir = runs_root / run_id
    artifacts_dir = run_dir / "artifacts"
    return ClusterRunPaths(
        run_dir=run_dir,
        artifacts_dir=artifacts_dir,
        outputs_dir=artifacts_dir / "Outputs",
        logs_dir=artifacts_dir / "logs",
        meta_dir=run_dir / "meta",
        manifest_path=run_dir / "cluster_run_manifest.json",
    )


def ingest_host_results(
    *,
    run_id: str,
    host: str,
    source_root: str | Path,
    jobs: list[tuple[str, str]],
    log_path: str | Path | None = None,
    storage_root: Path | None = None,
    commit: str | None = None,
) -> dict:
    paths = resolve_cluster_run_paths(run_id, storage_root=storage_root)
    paths.outputs_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    paths.meta_dir.mkdir(parents=True, exist_ok=True)

    source_root = Path(source_root)
    manifest = _load_json(paths.manifest_path)
    manifest.setdefault("run_id", run_id)
    manifest.setdefault("created_utc", _utc_now())
    manifest["updated_utc"] = _utc_now()
    manifest.setdefault("hosts", {})
    manifest.setdefault("jobs", {})
    if commit:
        manifest["commit"] = commit

    host_entry = manifest["hosts"].setdefault(host, {})
    host_entry["source_root"] = str(source_root)
    host_entry["ingested_utc"] = _utc_now()
    host_entry["jobs"] = [_job_key(market, timeframe) for market, timeframe in jobs]
    if commit:
        host_entry["commit"] = commit

    copied_datasets: list[str] = []
    copied_files: list[str] = []
    source_outputs = source_root / "Outputs"

    for market, timeframe in jobs:
        run_name = _job_run_name(market, timeframe)
        dataset_name = _dataset_dir_name(market, timeframe)
        job_root = source_outputs / run_name
        dataset_src = job_root / dataset_name
        if not dataset_src.exists():
            alt_dataset_src = source_outputs / dataset_name
            if alt_dataset_src.exists():
                dataset_src = alt_dataset_src
                job_root = source_outputs
            else:
                raise FileNotFoundError(
                    f"Dataset output not found for {market}:{timeframe} under {source_outputs}"
                )

        dataset_dst = paths.outputs_dir / dataset_name
        _copy_path(dataset_src, dataset_dst)
        copied_datasets.append(dataset_name)

        # Preserve useful job-level files in a host-specific metadata area.
        host_meta_dir = paths.meta_dir / host / run_name
        host_meta_dir.mkdir(parents=True, exist_ok=True)
        for fname in (
            "master_leaderboard.csv",
            "master_leaderboard_cfd.csv",
            "sweep_manifest.json",
        ):
            if _copy_if_exists(job_root / fname, host_meta_dir / fname):
                copied_files.append(f"{host}/{run_name}/{fname}")

        manifest["jobs"][_job_key(market, timeframe)] = {
            "market": market,
            "timeframe": timeframe,
            "host": host,
            "dataset_dir": dataset_name,
            "source_root": str(source_root),
            "ingested_utc": _utc_now(),
        }

    if log_path is not None:
        log_src = Path(log_path)
        if log_src.exists():
            log_dst = paths.logs_dir / f"{host}.log"
            _copy_path(log_src, log_dst)
            host_entry["log_path"] = str(log_dst)

    _write_json(paths.manifest_path, manifest)
    return {
        "run_id": run_id,
        "host": host,
        "copied_datasets": copied_datasets,
        "copied_files": copied_files,
        "manifest_path": str(paths.manifest_path),
    }


def finalize_cluster_run(
    *,
    run_id: str,
    storage_root: Path | None = None,
    emit_cfd_alias: bool = True,
    publish_exports: bool = True,
) -> dict:
    storage_root = storage_root or RUNS_DIR.parent
    paths = resolve_cluster_run_paths(run_id, storage_root=storage_root)
    if not paths.outputs_dir.exists():
        raise FileNotFoundError(f"No outputs found for run {run_id}: {paths.outputs_dir}")

    classic_df, _ = write_master_leaderboards(
        outputs_root=paths.outputs_dir,
        include_bootcamp_scores=False,
        emit_cfd_alias=emit_cfd_alias,
    )

    exports_dir = (storage_root / "exports") if storage_root is not None else EXPORTS_DIR
    exports_dir.mkdir(parents=True, exist_ok=True)

    exported_files: list[str] = []
    master_path = paths.outputs_dir / "master_leaderboard.csv"
    if master_path.exists() and publish_exports:
        _copy_path(master_path, exports_dir / "master_leaderboard.csv")
        _copy_path(master_path, exports_dir / f"{run_id}_master_leaderboard.csv")
        exported_files.extend(
            [
                str(exports_dir / "master_leaderboard.csv"),
                str(exports_dir / f"{run_id}_master_leaderboard.csv"),
            ]
        )

    master_cfd_path = paths.outputs_dir / "master_leaderboard_cfd.csv"
    if master_cfd_path.exists() and publish_exports:
        _copy_path(master_cfd_path, exports_dir / "master_leaderboard_cfd.csv")
        _copy_path(master_cfd_path, exports_dir / f"{run_id}_master_leaderboard_cfd.csv")
        exported_files.extend(
            [
                str(exports_dir / "master_leaderboard_cfd.csv"),
                str(exports_dir / f"{run_id}_master_leaderboard_cfd.csv"),
            ]
        )

    ultimate_df = aggregate_ultimate_leaderboard(
        storage_root=storage_root,
        output_path=exports_dir / FUTURES_ULTIMATE_FILENAME,
        verbose=False,
    )
    if (exports_dir / FUTURES_ULTIMATE_FILENAME).exists():
        exported_files.append(str(exports_dir / FUTURES_ULTIMATE_FILENAME))
    if (exports_dir / LEGACY_ULTIMATE_FILENAME).exists():
        exported_files.append(str(exports_dir / LEGACY_ULTIMATE_FILENAME))
    if (exports_dir / CFD_ULTIMATE_FILENAME).exists():
        exported_files.append(str(exports_dir / CFD_ULTIMATE_FILENAME))

    for ultimate_name in (
        FUTURES_ULTIMATE_FILENAME,
        CFD_ULTIMATE_FILENAME,
    ):
        ultimate_path = exports_dir / ultimate_name
        if not ultimate_path.exists():
            continue
        gate_result = build_post_ultimate_gate(
            storage_root=storage_root,
            source_path=ultimate_path,
            output_dir=exports_dir,
        )
        exported_files.append(gate_result["audit_path"])
        exported_files.append(gate_result["gated_path"])
        for alias_path in gate_result.get("alias_paths", []):
            exported_files.append(alias_path)

    (storage_root / "runs" / "LATEST_RUN.txt").write_text(f"{run_id}\n", encoding="utf-8")

    manifest = _load_json(paths.manifest_path)
    manifest["finalized_utc"] = _utc_now()
    manifest["published_exports"] = publish_exports
    manifest["master_rows"] = 0 if classic_df.empty else int(len(classic_df))
    manifest["ultimate_rows"] = 0 if ultimate_df.empty else int(len(ultimate_df))
    _write_json(paths.manifest_path, manifest)

    return {
        "run_id": run_id,
        "master_rows": 0 if classic_df.empty else int(len(classic_df)),
        "ultimate_rows": 0 if ultimate_df.empty else int(len(ultimate_df)),
        "exported_files": exported_files,
        "manifest_path": str(paths.manifest_path),
    }


def mirror_storage_to_backup(
    *,
    storage_root: Path,
    backup_root: Path,
    run_id: str | None = None,
    include_all_runs: bool = False,
) -> dict:
    storage_root = Path(storage_root)
    backup_root = Path(backup_root)

    exports_dir = storage_root / "exports"
    runs_root = storage_root / "runs"
    leaderboards_backup_dir = backup_root / "leaderboards"
    sweep_results_backup_dir = backup_root / "sweep_results"
    runs_backup_dir = sweep_results_backup_dir / "runs"

    leaderboards_backup_dir.mkdir(parents=True, exist_ok=True)
    runs_backup_dir.mkdir(parents=True, exist_ok=True)

    copied_exports: list[str] = []
    copied_runs: list[str] = []

    for export_path in _iter_export_files(exports_dir):
        if export_path.suffix.lower() not in {".csv", ".txt", ".json"}:
            continue
        dst = leaderboards_backup_dir / export_path.name
        _copy_path(export_path, dst)
        copied_exports.append(str(dst))

    latest_run_id = _latest_run_id(runs_root)
    if latest_run_id is not None:
        latest_run_dst = sweep_results_backup_dir / "LATEST_RUN.txt"
        _copy_path(runs_root / "LATEST_RUN.txt", latest_run_dst)
        copied_exports.append(str(latest_run_dst))

    run_ids: list[str] = []
    if include_all_runs:
        run_ids = sorted(path.name for path in runs_root.iterdir() if path.is_dir())
    else:
        selected_run_id = run_id or latest_run_id
        if selected_run_id:
            run_ids = [selected_run_id]

    for selected_run_id in run_ids:
        run_src = runs_root / selected_run_id
        if not run_src.exists():
            raise FileNotFoundError(f"Run not found under storage root: {run_src}")
        run_dst = runs_backup_dir / selected_run_id
        _copy_path(run_src, run_dst)
        copied_runs.append(str(run_dst))

    recovery_result = export_recovery_artifacts(backup_root=backup_root)

    return {
        "backup_root": str(backup_root),
        "copied_exports": copied_exports,
        "copied_runs": copied_runs,
        "latest_run_id": latest_run_id,
        "recovery_files": recovery_result["copied_files"],
    }
