from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from paths import CONSOLE_SELECTION_PATH, CONSOLE_STORAGE_ROOT, EXPORTS_DIR, LEGACY_RESULTS_DIR, RUN_STATUS_PATH, UPLOADS_DIR

RESULT_FILE_NAMES = [
    "master_leaderboard.csv",
    "portfolio_review_table.csv",
    "correlation_matrix.csv",
    "yearly_stats_breakdown.csv",
    "strategy_returns.csv",
    "family_leaderboard_results.csv",
    "family_summary_results.csv",
]

UPLOAD_SUFFIXES = {".csv", ".parquet", ".txt", ".zip", ".gz"}
EXPORT_SUFFIXES = {".csv", ".zip", ".json", ".gz"}

HOURLY_RATE_ESTIMATES: dict[str, dict[str, float]] = {
    "n2-highcpu-96": {"STANDARD": 3.31, "SPOT": 0.72},
    "n2-highcpu-48": {"STANDARD": 1.66, "SPOT": 0.36},
    "n2-highcpu-32": {"STANDARD": 1.10, "SPOT": 0.24},
    "n2-highcpu-16": {"STANDARD": 0.55, "SPOT": 0.12},
    "n2-highcpu-8":  {"STANDARD": 0.28, "SPOT": 0.06},
}

BADGE_MAP = {
    "run_completed_verified": "Verified Complete",
    "run_completed_unverified": "Complete, Unverified",
    "artifact_download_failed": "Artifact Download Failed",
    "artifact_verification_failed": "Artifact Verification Failed",
    "remote_start_failed": "Remote Start Failed",
    "remote_monitor_failed": "Monitor Failed",
    "remote_run_failed": "Remote Run Failed",
    "vm_missing_before_retrieval": "VM Missing Before Retrieval",
    "unexpected_launcher_failure": "Launcher Failure",
    "remote_failed_artifacts_preserved": "Remote Failed, Artifacts Preserved",
    "dry_run_complete": "Dry Run Only",
    "vm_preserved_for_inspection": "VM Preserved",
    "vm_already_gone": "VM Already Gone",
    "vm_destroyed": "VM Destroyed",
    "preflight_passed": "Preflight Passed",
    "prepared": "Prepared",
    "running": "Running",
}


@dataclass(frozen=True)
class ResultSource:
    key: str
    category: str
    label: str
    base_path: Path
    outputs_dir: Path | None
    run_dir: Path | None
    launcher_status: dict[str, Any]
    run_manifest: dict[str, Any]


@dataclass(frozen=True)
class ConsoleStoragePaths:
    root: Path
    uploads: Path
    runs: Path
    exports: Path
    backups: Path


@dataclass(frozen=True)
class StorageFileEntry:
    name: str
    path: Path
    size_bytes: int
    modified_at: datetime | None
    category: str


@dataclass(frozen=True)
class ReadinessReport:
    state: str
    summary: str
    checks: list[tuple[str, bool]]


def read_json_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def resolve_console_storage_paths(root: Path | None = None) -> ConsoleStoragePaths:
    if root is None:
        root = CONSOLE_STORAGE_ROOT
    root = root.expanduser()
    return ConsoleStoragePaths(
        root=root,
        uploads=root / "uploads",
        runs=root / "runs",
        exports=root / "exports",
        backups=root / "backups",
    )


def canonical_runs_root(storage: ConsoleStoragePaths | None = None) -> Path:
    paths = storage or resolve_console_storage_paths()
    return paths.runs


def _sorted_files(directory: Path, *, allowed_suffixes: set[str] | None = None) -> list[StorageFileEntry]:
    if not directory.exists():
        return []

    payload: list[StorageFileEntry] = []
    for path in directory.iterdir():
        if not path.is_file():
            continue
        if allowed_suffixes is not None and path.suffix.lower() not in allowed_suffixes:
            continue
        stat = path.stat()
        payload.append(
            StorageFileEntry(
                name=path.name,
                path=path,
                size_bytes=int(stat.st_size),
                modified_at=datetime.fromtimestamp(stat.st_mtime, UTC),
                category=directory.name,
            )
        )
    return sorted(payload, key=lambda item: item.modified_at or datetime.min.replace(tzinfo=UTC), reverse=True)


def list_uploaded_datasets(storage: ConsoleStoragePaths | None = None) -> list[StorageFileEntry]:
    paths = storage or resolve_console_storage_paths()
    return _sorted_files(paths.uploads, allowed_suffixes=UPLOAD_SUFFIXES)


def list_export_files(storage: ConsoleStoragePaths | None = None) -> list[StorageFileEntry]:
    paths = storage or resolve_console_storage_paths()
    return _sorted_files(paths.exports, allowed_suffixes=EXPORT_SUFFIXES)


def read_console_selection(path: Path = CONSOLE_SELECTION_PATH) -> list[str]:
    payload = read_json_file(path)
    selected = payload.get("selected_datasets", [])
    if isinstance(selected, list):
        return [str(item) for item in selected]
    return []


def write_console_selection(selected_datasets: list[str], path: Path = CONSOLE_SELECTION_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"selected_datasets": selected_datasets}, indent=2), encoding="utf-8")


def read_console_run_status(path: Path = RUN_STATUS_PATH) -> dict[str, Any]:
    return read_json_file(path)


def discover_launcher_run_dirs(results_root: Path = LEGACY_RESULTS_DIR) -> list[Path]:
    if not results_root.exists():
        return []
    run_dirs = [path for path in results_root.iterdir() if path.is_dir() and (path / "launcher_status.json").exists()]
    return sorted(run_dirs, key=lambda path: path.stat().st_mtime, reverse=True)


def discover_storage_run_dirs(storage: ConsoleStoragePaths | None = None) -> list[Path]:
    paths = storage or resolve_console_storage_paths()
    if not paths.runs.exists():
        return []
    run_dirs = [path for path in paths.runs.iterdir() if path.is_dir()]
    return sorted(run_dirs, key=lambda path: path.stat().st_mtime, reverse=True)


def collect_launcher_dataset_statuses(run_dir: Path) -> list[dict[str, Any]]:
    launcher_status = read_json_file(run_dir / "launcher_status.json")
    embedded_statuses = launcher_status.get("dataset_statuses")
    if isinstance(embedded_statuses, list) and embedded_statuses:
        return embedded_statuses

    artifacts_outputs = run_dir / "artifacts" / "Outputs"
    payload: list[dict[str, Any]] = []
    if artifacts_outputs.exists():
        for status_path in sorted(artifacts_outputs.glob("*/status.json")):
            status = read_json_file(status_path)
            if status:
                payload.append(status)
    return payload


def _resolve_outputs_dir(run_dir: Path) -> Path | None:
    candidates = [
        run_dir / "artifacts" / "Outputs",
        run_dir / "Outputs",
        run_dir / "outputs",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_launcher_run_record(run_dir: Path) -> dict[str, Any]:
    launcher_status = read_json_file(run_dir / "launcher_status.json")
    if not launcher_status:
        launcher_status = read_json_file(run_dir / "metadata.json")
    run_manifest = read_json_file(run_dir / "run_manifest.json")
    artifact_status = read_json_file(run_dir / "artifacts" / "run_status.json")
    dataset_statuses = collect_launcher_dataset_statuses(run_dir)
    outputs_dir = _resolve_outputs_dir(run_dir)
    if outputs_dir is None and (run_dir / "leaderboard.csv").exists():
        outputs_dir = run_dir
    return {
        "run_dir": run_dir,
        "launcher_status": launcher_status,
        "run_manifest": run_manifest,
        "artifact_status": artifact_status,
        "dataset_statuses": dataset_statuses,
        "outputs_dir": outputs_dir,
    }


def collect_launcher_run_records(results_root: Path = LEGACY_RESULTS_DIR) -> list[dict[str, Any]]:
    return [load_launcher_run_record(run_dir) for run_dir in discover_launcher_run_dirs(results_root)]


def collect_console_run_records(
    *,
    storage: ConsoleStoragePaths | None = None,
    repo_results_root: Path = LEGACY_RESULTS_DIR,
    include_legacy_fallback: bool = False,
) -> list[dict[str, Any]]:
    paths = storage or resolve_console_storage_paths()
    records: list[dict[str, Any]] = []
    seen: set[Path] = set()

    for run_dir in discover_storage_run_dirs(paths):
        records.append(load_launcher_run_record(run_dir))
        seen.add(run_dir.resolve())

    if include_legacy_fallback or not records:
        for run_dir in discover_launcher_run_dirs(repo_results_root):
            resolved = run_dir.resolve()
            if resolved in seen:
                continue
            records.append(load_launcher_run_record(run_dir))

    return sorted(records, key=lambda record: record["run_dir"].stat().st_mtime, reverse=True)


def humanize_token(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return "Unknown"
    return text.replace("_", " ").replace("-", " ").title()


def badge_for_value(value: str | None) -> str:
    text = str(value or "").strip()
    if text in BADGE_MAP:
        return BADGE_MAP[text]
    return humanize_token(text)


def billing_status_for_launcher(launcher_status: dict[str, Any]) -> str:
    vm_outcome = str(launcher_status.get("vm_outcome", "")).strip()
    instance_exists_at_end = launcher_status.get("instance_exists_at_end")
    artifact_verified = bool(launcher_status.get("artifact_verified"))

    if vm_outcome == "vm_destroyed":
        return "stopped"
    if instance_exists_at_end is False:
        return "stopped" if artifact_verified else "maybe_stopped"
    if vm_outcome == "vm_preserved_for_inspection" and instance_exists_at_end is True:
        return "still_running"
    if vm_outcome == "vm_already_gone":
        return "maybe_stopped"
    return "unknown"


def operator_action_summary(launcher_status: dict[str, Any]) -> str:
    action = str(launcher_status.get("operator_action") or "").strip()
    if action:
        return action

    run_outcome = str(launcher_status.get("run_outcome") or "").strip()
    vm_outcome = str(launcher_status.get("vm_outcome") or "").strip()
    if run_outcome == "run_completed_verified":
        return "Latest run is verified. No manual action required."
    if vm_outcome == "vm_preserved_for_inspection":
        return "VM is still running. Download artifacts or inspect remotely, then delete the instance."
    if run_outcome in {"artifact_download_failed", "artifact_verification_failed", "remote_monitor_failed"}:
        return "Artifacts are incomplete locally. Use recovery commands below."
    return "Review the latest launcher status before taking action."


def build_test_run_readiness(
    *,
    storage: ConsoleStoragePaths | None = None,
    run_records: list[dict[str, Any]] | None = None,
    uploaded_datasets: list[StorageFileEntry] | None = None,
) -> ReadinessReport:
    paths = storage or resolve_console_storage_paths()
    records = run_records if run_records is not None else collect_console_run_records(storage=paths)
    datasets = uploaded_datasets if uploaded_datasets is not None else list_uploaded_datasets(paths)

    checks = [
        ("storage root exists", paths.root.exists()),
        ("uploads directory exists", paths.uploads.exists()),
        ("runs directory exists", paths.runs.exists()),
        ("exports directory exists", paths.exports.exists()),
        ("at least one dataset uploaded", len(datasets) > 0),
        ("run metadata readable", records is not None),
    ]
    passed = sum(1 for _, ok in checks if ok)

    if passed == len(checks):
        return ReadinessReport("ready", "Console looks ready for tonight's test run.", checks)
    if passed >= max(1, len(checks) - 2):
        return ReadinessReport("partially ready", "Console is mostly ready, but a few checks still need attention.", checks)
    return ReadinessReport("not ready", "Console is missing key prerequisites for tonight's test run.", checks)


def classify_run_status(launcher_status: dict[str, Any]) -> str:
    state = str(launcher_status.get("state", "")).strip()
    run_outcome = str(launcher_status.get("run_outcome", "")).strip()
    vm_outcome = str(launcher_status.get("vm_outcome", "")).strip()

    if state == "dry_run_complete" or run_outcome == "dry_run_complete":
        return "dry-run"
    if state == "running":
        return "running"
    if vm_outcome == "vm_preserved_for_inspection":
        return "preserved"
    if run_outcome in {"run_completed_verified", "run_completed_unverified"}:
        return "completed"
    if run_outcome in {
        "artifact_download_failed",
        "artifact_verification_failed",
        "remote_start_failed",
        "remote_monitor_failed",
        "remote_run_failed",
        "vm_missing_before_retrieval",
        "unexpected_launcher_failure",
        "remote_failed_artifacts_preserved",
    }:
        return "failed"
    if vm_outcome == "vm_already_gone":
        return "failed"
    if "failed" in state or "failed" in run_outcome:
        return "failed"
    return "unknown"


def build_run_choice_label(record: dict[str, Any]) -> str:
    status = record["launcher_status"]
    run_id = status.get("run_id", record["run_dir"].name)
    updated = status.get("updated_utc", "unknown")
    category = classify_run_status(status)
    prefix_map = {
        "running": "Running",
        "completed": "Completed",
        "preserved": "Preserved",
        "failed": "Failed",
        "dry-run": "Dry Run",
        "unknown": "Unknown",
    }
    prefix = prefix_map.get(category, "Unknown")
    return f"{run_id} | {prefix} | {updated}"


def format_bytes(num_bytes: int | float | None) -> str:
    if not isinstance(num_bytes, (int, float)) or num_bytes <= 0:
        return "Pending"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    unit = units[0]
    for candidate in units:
        unit = candidate
        if value < 1024 or candidate == units[-1]:
            break
        value /= 1024
    return f"{value:.1f} {unit}"


def format_duration(seconds: float | int | None) -> str:
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return "-"
    total_seconds = int(seconds)
    hours, rem = divmod(total_seconds, 3600)
    minutes, sec = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {sec}s"
    return f"{sec}s"


def format_currency(value: float | None) -> str:
    if value is None:
        return "Unknown"
    return f"${value:,.2f}"


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "Unknown"
    return value.astimezone(UTC).isoformat(timespec="seconds")


def infer_provisioning_model(record: dict[str, Any]) -> str:
    launcher_status = record.get("launcher_status", {})
    run_manifest = record.get("run_manifest", {})
    for source in (launcher_status, run_manifest):
        provisioning = str(source.get("provisioning_model", "")).strip().upper()
        if provisioning:
            return provisioning
    return "Unknown"


def estimate_run_cost(record: dict[str, Any]) -> dict[str, Any]:
    launcher_status = record.get("launcher_status", {})
    run_manifest = record.get("run_manifest", {})
    machine_type = str(run_manifest.get("machine_type") or launcher_status.get("machine_type") or "unknown").strip()
    provisioning_model = infer_provisioning_model(record)
    created_at = parse_timestamp(launcher_status.get("created_utc") or run_manifest.get("created_utc"))
    updated_at = parse_timestamp(launcher_status.get("updated_utc"))
    elapsed_seconds = 0.0
    if created_at and updated_at:
        elapsed_seconds = max((updated_at - created_at).total_seconds(), 0.0)

    pricing = HOURLY_RATE_ESTIMATES.get(machine_type, {})
    hourly_rate = pricing.get(provisioning_model)
    if hourly_rate is None and len(pricing) == 1:
        hourly_rate = next(iter(pricing.values()))

    total_cost = None if hourly_rate is None else hourly_rate * (elapsed_seconds / 3600)
    billing_active = billing_status_for_launcher(launcher_status) == "still_running"
    return {
        "machine_type": machine_type or "unknown",
        "provisioning_model": provisioning_model,
        "elapsed_seconds": elapsed_seconds,
        "hourly_rate": hourly_rate,
        "estimated_total_cost": total_cost,
        "billing_active": billing_active,
    }


def parse_dataset_identity(dataset_name: str) -> tuple[str, str]:
    parts = str(dataset_name or "").split("_", 1)
    market = parts[0] if parts and parts[0] else "Unknown"
    timeframe = parts[1] if len(parts) > 1 else "Unknown"
    return market, timeframe


def parse_dataset_filename(filename: str) -> dict[str, str]:
    stem = Path(filename).stem
    parts = stem.split("_")
    market = parts[0] if parts else "Unknown"
    timeframe = next((part for part in parts if part.endswith(("m", "h")) or part == "daily"), "unknown")
    return {
        "filename": filename,
        "market": market,
        "timeframe": timeframe,
    }


def normalize_dataset_status(status: dict[str, Any]) -> dict[str, Any]:
    dataset = str(status.get("dataset", "Unknown"))
    market, timeframe = parse_dataset_identity(dataset)
    completed = status.get("families_completed", [])
    remaining = status.get("families_remaining", [])
    pct = float(status.get("progress_pct", 0) or 0)
    eta = float(status.get("eta_seconds", 0) or 0)
    elapsed = float(status.get("elapsed_seconds", 0) or 0)
    return {
        "dataset": dataset,
        "market": status.get("market", market),
        "timeframe": status.get("timeframe", timeframe),
        "current_family": status.get("current_family", "?"),
        "current_stage": status.get("current_stage", "?"),
        "progress_pct": pct,
        "eta_seconds": eta,
        "elapsed_seconds": elapsed,
        "families_completed": completed if isinstance(completed, list) else [],
        "families_remaining": remaining if isinstance(remaining, list) else [],
    }


def summarize_dataset_progress(dataset_statuses: list[dict[str, Any]], run_manifest: dict[str, Any]) -> dict[str, Any]:
    normalized = [normalize_dataset_status(status) for status in dataset_statuses]
    declared_datasets = run_manifest.get("datasets", [])
    total_datasets = len(declared_datasets) if isinstance(declared_datasets, list) and declared_datasets else len(normalized)
    completed_datasets = sum(1 for status in normalized if status["progress_pct"] >= 100 or not status["families_remaining"])
    active_dataset = next((status["dataset"] for status in normalized if status["progress_pct"] < 100), normalized[0]["dataset"] if normalized else "Unknown")
    total_completed_families = sum(len(status["families_completed"]) for status in normalized)
    total_remaining_families = sum(len(status["families_remaining"]) for status in normalized)
    return {
        "dataset_statuses": normalized,
        "completed_datasets": completed_datasets,
        "total_datasets": total_datasets,
        "active_dataset": active_dataset,
        "completed_families": total_completed_families,
        "remaining_families": total_remaining_families,
    }


def detect_result_files(base: Path | None) -> dict[str, Path | None]:
    if base is None or not base.exists():
        return {name: None for name in RESULT_FILE_NAMES}
    payload: dict[str, Path | None] = {}
    for name in RESULT_FILE_NAMES:
        matches = list(base.rglob(name))
        payload[name] = matches[0] if matches else None
    return payload


def pick_best_candidate_file(base: Path | None) -> Path | None:
    files = detect_result_files(base)
    for name in ["master_leaderboard.csv", "family_leaderboard_results.csv", "family_summary_results.csv"]:
        if files.get(name):
            return files[name]
    return None


def load_log_tail(run_dir: Path, line_count: int = 60) -> str:
    candidates = [
        run_dir / "artifacts" / "logs" / "engine_run.log",
        run_dir / "logs" / "engine_run.log",
        run_dir / "engine_run.log",
    ]
    for candidate in candidates:
        if candidate.exists():
            lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(lines[-line_count:]) or "(log is empty)"
    return ""


def collect_result_sources(
    results_root: Path = LEGACY_RESULTS_DIR,
    *,
    storage: ConsoleStoragePaths | None = None,
    include_legacy_fallback: bool = False,
) -> list[ResultSource]:
    sources: list[ResultSource] = []

    for record in collect_console_run_records(
        storage=storage,
        repo_results_root=results_root,
        include_legacy_fallback=include_legacy_fallback,
    ):
        run_dir = record["run_dir"]
        outputs_dir = record["outputs_dir"]
        status = record["launcher_status"]
        label = f"{build_run_choice_label(record)} | {'artifacts ready' if outputs_dir else 'no artifacts yet'}"
        sources.append(
            ResultSource(
                key=f"cloud::{run_dir}",
                category="Cloud Runs",
                label=label,
                base_path=outputs_dir or run_dir,
                outputs_dir=outputs_dir,
                run_dir=run_dir,
                launcher_status=status,
                run_manifest=record["run_manifest"],
            )
        )

    for directory in sorted(Path(".").glob("cloud_outputs*"), key=lambda path: path.stat().st_mtime, reverse=True):
        if directory.is_dir():
            sources.append(
                ResultSource(
                    key=f"legacy::{directory}",
                    category="Legacy Cloud Outputs",
                    label=f"{directory.name} | legacy cloud outputs",
                    base_path=directory,
                    outputs_dir=directory,
                    run_dir=None,
                    launcher_status={},
                    run_manifest={},
                )
            )

    outputs_root = Path("Outputs")
    if outputs_root.exists():
        sources.append(
            ResultSource(
                key=f"local::{outputs_root}",
                category="Local Outputs",
                label="Outputs | local root",
                base_path=outputs_root,
                outputs_dir=outputs_root,
                run_dir=None,
                launcher_status={},
                run_manifest={},
            )
        )
    return sources


def choose_default_result_source(sources: list[ResultSource]) -> str | None:
    for source in sources:
        if source.category == "Cloud Runs" and source.outputs_dir and source.outputs_dir.exists():
            return source.key
    return sources[0].key if sources else None


def format_duration_short(seconds: float | int | None) -> str:
    """Compact duration: '1h 23m', '45m', '30s'."""
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return "—"
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, sec = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{sec}s"


def status_color(category: str) -> str:
    """Return a CSS class name for a run status category."""
    mapping = {
        "running": "status-info",
        "completed": "status-success",
        "preserved": "status-warning",
        "failed": "status-error",
        "dry-run": "status-neutral",
        "unknown": "status-neutral",
    }
    return mapping.get(category, "status-neutral")


def load_strategy_results(outputs_dir: Path | None) -> dict[str, Any]:
    """Load all result files from a run's outputs directory.

    Returns a dict with keys: leaderboard, portfolio, correlation, yearly, returns.
    Values are DataFrames or None if the file is missing or unreadable.
    """
    import pandas as pd  # local import to avoid hard dependency at module level

    result: dict[str, Any] = {
        "leaderboard": None,
        "portfolio": None,
        "correlation": None,
        "yearly": None,
        "returns": None,
    }
    if outputs_dir is None or not outputs_dir.exists():
        return result

    files = detect_result_files(outputs_dir)

    def _safe_csv(path: Path | None) -> Any:
        if path is None or not path.exists():
            return None
        try:
            return pd.read_csv(path)
        except Exception:
            return None

    def _safe_parquet(path: Path | None) -> Any:
        if path is None or not path.exists():
            return None
        try:
            return pd.read_parquet(path, engine="pyarrow")
        except Exception:
            try:
                return pd.read_csv(path)
            except Exception:
                return None

    # Prefer master_leaderboard, fall back to family files
    lb_path = files.get("master_leaderboard.csv") or files.get("family_leaderboard_results.csv") or files.get("family_summary_results.csv")
    result["leaderboard"] = _safe_csv(lb_path)
    result["portfolio"] = _safe_csv(files.get("portfolio_review_table.csv"))
    result["correlation"] = _safe_csv(files.get("correlation_matrix.csv"))
    result["yearly"] = _safe_csv(files.get("yearly_stats_breakdown.csv"))
    result["returns"] = _safe_csv(files.get("strategy_returns.csv"))

    return result


def load_promoted_candidates(outputs_dir: Path | None) -> Any:
    """Aggregate all *_promoted_candidates.csv files from an outputs directory.

    Used by the Live Monitor tab to show which combos passed the promotion gate
    across all completed families and datasets.
    """
    import pandas as pd

    if outputs_dir is None or not outputs_dir.exists():
        return None

    candidate_files = list(outputs_dir.rglob("*_promoted_candidates.csv"))
    if not candidate_files:
        return None

    frames = []
    for path in sorted(candidate_files):
        try:
            df = pd.read_csv(path)
            if "dataset" not in df.columns:
                df["dataset"] = path.parent.name
            frames.append(df)
        except Exception:
            continue

    if not frames:
        return None

    combined = pd.concat(frames, ignore_index=True)
    if "profit_factor" in combined.columns:
        combined = combined.sort_values("profit_factor", ascending=False)
    return combined
