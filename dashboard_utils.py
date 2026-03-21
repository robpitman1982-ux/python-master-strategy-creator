from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


RESULT_FILE_NAMES = [
    "master_leaderboard.csv",
    "portfolio_review_table.csv",
    "correlation_matrix.csv",
    "yearly_stats_breakdown.csv",
    "strategy_returns.csv",
    "family_leaderboard_results.csv",
    "family_summary_results.csv",
]

HOURLY_RATE_ESTIMATES: dict[str, dict[str, float]] = {
    "n2-highcpu-96": {"STANDARD": 5.40, "SPOT": 1.62},
    "n2-highcpu-48": {"STANDARD": 2.70, "SPOT": 0.81},
    "n2-highcpu-32": {"STANDARD": 1.80, "SPOT": 0.54},
    "n2-highcpu-16": {"STANDARD": 0.90, "SPOT": 0.27},
}

BADGE_MAP = {
    "run_completed_verified": "🟢 Verified Complete",
    "run_completed_unverified": "🟡 Complete, Unverified",
    "artifact_download_failed": "🔴 Artifact Download Failed",
    "artifact_verification_failed": "🔴 Artifact Verification Failed",
    "remote_start_failed": "🔴 Remote Start Failed",
    "remote_monitor_failed": "🔴 Monitor Failed",
    "remote_run_failed": "🔴 Remote Run Failed",
    "vm_missing_before_retrieval": "🔴 VM Missing Before Retrieval",
    "unexpected_launcher_failure": "🔴 Launcher Failure",
    "remote_failed_artifacts_preserved": "🔴 Remote Failed, Artifacts Preserved",
    "dry_run_complete": "⚪ Dry Run Only",
    "vm_preserved_for_inspection": "🟠 VM Preserved",
    "vm_already_gone": "⚫ VM Already Gone",
    "vm_destroyed": "✅ VM Destroyed",
    "preflight_passed": "🔵 Preflight Passed",
    "prepared": "🔵 Prepared",
    "running": "🟢 Running",
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


def discover_launcher_run_dirs(results_root: Path = Path("cloud_results")) -> list[Path]:
    if not results_root.exists():
        return []
    run_dirs = [path for path in results_root.iterdir() if path.is_dir() and (path / "launcher_status.json").exists()]
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


def load_launcher_run_record(run_dir: Path) -> dict[str, Any]:
    launcher_status = read_json_file(run_dir / "launcher_status.json")
    run_manifest = read_json_file(run_dir / "run_manifest.json")
    artifact_status = read_json_file(run_dir / "artifacts" / "run_status.json")
    dataset_statuses = collect_launcher_dataset_statuses(run_dir)
    outputs_dir = run_dir / "artifacts" / "Outputs"
    return {
        "run_dir": run_dir,
        "launcher_status": launcher_status,
        "run_manifest": run_manifest,
        "artifact_status": artifact_status,
        "dataset_statuses": dataset_statuses,
        "outputs_dir": outputs_dir if outputs_dir.exists() else None,
    }


def collect_launcher_run_records(results_root: Path = Path("cloud_results")) -> list[dict[str, Any]]:
    return [load_launcher_run_record(run_dir) for run_dir in discover_launcher_run_dirs(results_root)]


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
    if state == "run_completed_verified" or run_outcome == "run_completed_verified":
        return "completed"
    if state == "run_completed_unverified" or run_outcome == "run_completed_unverified":
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
        "running": "🟢 Running",
        "completed": "✅ Completed",
        "preserved": "🟠 Preserved",
        "failed": "🔴 Failed",
        "dry-run": "⚪ Dry Run",
        "unknown": "⚪ Unknown",
    }
    prefix = prefix_map.get(category, "⚪ Unknown")
    return f"{run_id} | {prefix} | {updated}"


def format_bytes(num_bytes: int | float | None) -> str:
    if not isinstance(num_bytes, (int, float)) or num_bytes <= 0:
        return "Pending"
    return f"{num_bytes / (1024 * 1024):.1f} MB"


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
    vm_outcome = str(launcher_status.get("vm_outcome", "")).strip()
    billing_active = vm_outcome != "vm_destroyed" and str(launcher_status.get("state", "")).strip() != "dry_run_complete"

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


def collect_result_sources(results_root: Path = Path("cloud_results")) -> list[ResultSource]:
    sources: list[ResultSource] = []

    for record in collect_launcher_run_records(results_root):
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
        for directory in sorted(outputs_root.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True):
            if directory.is_dir():
                sources.append(
                    ResultSource(
                        key=f"local::{directory}",
                        category="Local Outputs",
                        label=f"{directory.name} | local dataset output",
                        base_path=directory,
                        outputs_dir=directory,
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
