from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from modules.master_leaderboard import write_master_leaderboards
from modules.ultimate_leaderboard import aggregate_ultimate_leaderboard
from paths import EXPORTS_DIR, RUNS_DIR


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
        output_path=exports_dir / "ultimate_leaderboard.csv",
        verbose=False,
    )
    exported_files.append(str(exports_dir / "ultimate_leaderboard.csv"))
    if (exports_dir / "ultimate_leaderboard_cfd.csv").exists():
        exported_files.append(str(exports_dir / "ultimate_leaderboard_cfd.csv"))

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
