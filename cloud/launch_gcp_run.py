from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from modules.config_loader import load_config
from paths import EXPORTS_DIR, REPO_DATA_DIR, REPO_ROOT as SHARED_REPO_ROOT, RUNS_DIR, UPLOADS_DIR


REPO_ROOT = SHARED_REPO_ROOT
DEFAULT_RESULTS_ROOT = RUNS_DIR
DEFAULT_CONFIG = REPO_ROOT / "cloud" / "config_es_all_timeframes_gcp96.yaml"
DEFAULT_ZONE = "us-central1-a"
DEFAULT_MACHINE_TYPE = "n2-highcpu-96"
DEFAULT_INSTANCE_NAME = "strategy-sweep"
DEFAULT_BOOT_DISK_SIZE = "120GB"
DEFAULT_IMAGE_FAMILY = "ubuntu-2404-lts-amd64"
DEFAULT_IMAGE_PROJECT = "ubuntu-os-cloud"
DEFAULT_BUNDLE_NAME = "input_bundle.tar.gz"
LATEST_RUN_FILE_NAME = "LATEST_RUN.txt"
DEFAULT_STRATEGY_CONSOLE_INSTANCE = "strategy-console"
DEFAULT_STRATEGY_CONSOLE_ZONE = "us-central1-c"
DEFAULT_STRATEGY_CONSOLE_REMOTE_ROOT = "/home/robpitman1982/strategy_console_storage"
DEFAULT_STRATEGY_CONSOLE_REMOTE_USER = "robpitman1982"
DEFAULT_BUCKET_NAME = "strategy-artifacts-robpitman"
DEFAULT_BUCKET_URI = f"gs://{DEFAULT_BUCKET_NAME}"


EXCLUDED_DIR_NAMES = {
    ".git",
    ".github",
    ".hypothesis",
    ".idea",
    ".nox",
    ".pytest_cache",
    ".streamlit",
    ".tmp",
    ".tmp_pytest",
    ".tmp_pytest_run",
    ".tox",
    ".vscode",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "__pycache__",
    "Data",
    "Outputs",
    "cloud_results",
    "htmlcov",
    "node_modules",
}
EXCLUDED_DIR_PREFIXES = ("cloud_outputs", ".tmp_pytest")
EXCLUDED_FILE_SUFFIXES = {".pyc", ".pyo"}
EXCLUDED_FILE_NAMES = {".coverage", DEFAULT_BUNDLE_NAME}
MEANINGFUL_OUTPUT_FILE_NAMES = {
    "family_summary_results.csv",
    "family_leaderboard_results.csv",
    "portfolio_review_table.csv",
    "strategy_returns.csv",
    "correlation_matrix.csv",
    "yearly_stats_breakdown.csv",
    "master_leaderboard.csv",
}


@dataclass
class DatasetSpec:
    market: str
    timeframe: str
    local_path: str
    file_name: str
    bundle_repo_path: str
    size_bytes: int
    sha256: str


@dataclass
class RunManifest:
    run_id: str
    created_utc: str
    created_local: str
    run_label: str
    instance_name: str
    zone: str
    machine_type: str
    provisioning_model: str
    boot_disk_size: str | None
    image_family: str | None
    config_path: str
    config_sha256: str
    project_id: str | None
    datasets: list[dict[str, Any]]
    remote_run_root: str
    remote_bundle_path: str
    remote_runner_path: str
    remote_status_path: str
    remote_artifact_tarball: str
    local_results_dir: str


@dataclass
class PreflightResult:
    config_path: Path
    config_sha256: str
    gcloud_bin: str
    project_id: str
    datasets: list[DatasetSpec]


@dataclass
class ArtifactDownloadResult:
    tarball_path: Path
    extracted_dir: Path
    tarball_size_bytes: int


@dataclass
class ArtifactVerificationResult:
    artifacts_downloaded: bool = False
    extraction_verified: bool = False
    expected_outputs_present: bool = False
    artifact_verified: bool = False
    tarball_exists: bool = False
    tarball_size_bytes: int = 0
    extracted_dir_exists: bool = False
    expected_subdirs_present: bool = False
    expected_files: list[str] | None = None
    verification_message: str = ""
    effective_remote_state: str = "unknown"


@dataclass(frozen=True)
class DestroyDecision:
    destroy_allowed: bool
    destroy_reason: str
    instance_exists_at_end: bool | None
    billing_should_be_stopped: bool | None
    operator_action: str
    recovery_commands: list[str]


RUN_OUTCOME_DRY_RUN_COMPLETE = "dry_run_complete"
RUN_OUTCOME_COMPLETED_VERIFIED = "run_completed_verified"
RUN_OUTCOME_COMPLETED_UNVERIFIED = "run_completed_unverified"
RUN_OUTCOME_ARTIFACT_DOWNLOAD_FAILED = "artifact_download_failed"
RUN_OUTCOME_ARTIFACT_VERIFICATION_FAILED = "artifact_verification_failed"
RUN_OUTCOME_REMOTE_START_FAILED = "remote_start_failed"
RUN_OUTCOME_REMOTE_MONITOR_FAILED = "remote_monitor_failed"
RUN_OUTCOME_REMOTE_INTERRUPTED_VM_PRESERVED = "remote_interrupted_vm_preserved"
RUN_OUTCOME_VM_MISSING_BEFORE_RETRIEVAL = "vm_missing_before_retrieval"
RUN_OUTCOME_UNEXPECTED_LAUNCHER_FAILURE = "unexpected_launcher_failure"
RUN_OUTCOME_REMOTE_RUN_FAILED = "remote_run_failed"

VM_OUTCOME_DESTROYED = "vm_destroyed"
VM_OUTCOME_PRESERVED = "vm_preserved_for_inspection"
VM_OUTCOME_ALREADY_GONE = "vm_already_gone"

EXPLICIT_SUCCESS_RUN_OUTCOMES = {RUN_OUTCOME_COMPLETED_VERIFIED}
TERMINAL_RUN_OUTCOMES = {
    RUN_OUTCOME_DRY_RUN_COMPLETE,
    RUN_OUTCOME_COMPLETED_VERIFIED,
    RUN_OUTCOME_COMPLETED_UNVERIFIED,
    RUN_OUTCOME_ARTIFACT_DOWNLOAD_FAILED,
    RUN_OUTCOME_ARTIFACT_VERIFICATION_FAILED,
    RUN_OUTCOME_REMOTE_START_FAILED,
    RUN_OUTCOME_REMOTE_MONITOR_FAILED,
    RUN_OUTCOME_REMOTE_INTERRUPTED_VM_PRESERVED,
    RUN_OUTCOME_VM_MISSING_BEFORE_RETRIEVAL,
    RUN_OUTCOME_UNEXPECTED_LAUNCHER_FAILURE,
    RUN_OUTCOME_REMOTE_RUN_FAILED,
}

DEFAULT_MONITOR_TIMEOUT_SECONDS = 24 * 60 * 60
DEFAULT_SSH_READY_TIMEOUT_SECONDS = 420
REMOTE_STATUS_UNKNOWN = "unknown"


class LauncherStatusStore:
    def __init__(
        self,
        run_dir: Path,
        *,
        run_id: str,
        instance_name: str,
        zone: str,
        config_path: str,
        local_results_dir: str,
        remote_run_root: str,
        created_utc: str,
        created_local: str,
        run_label: str,
    ):
        self.run_dir = run_dir
        self.latest_path = run_dir / "launcher_status.json"
        self.events_path = run_dir / "launcher_status.jsonl"
        self.base_payload = {
            "run_id": run_id,
            "instance_name": instance_name,
            "zone": zone,
            "config_path": config_path,
            "created_utc": created_utc,
            "created_local": created_local,
            "run_label": run_label,
            "local_results_dir": local_results_dir,
            "remote_run_root": remote_run_root,
            "bundle_size_bytes": None,
            "run_outcome": None,
            "vm_outcome": None,
            "failure_reason": None,
            "destroy_allowed": False,
            "destroy_reason": None,
            "artifacts_downloaded": False,
            "artifact_verified": False,
            "extraction_verified": False,
            "expected_outputs_present": False,
            "instance_exists_at_end": None,
            "billing_should_be_stopped": None,
            "operator_action": None,
            "recovery_commands": [],
            "remote_artifact_exists": None,
            "final_retrieval_attempted": False,
            "final_retrieval_success": False,
        }

    def current_payload(self) -> dict[str, Any]:
        payload = dict(self.base_payload)
        if self.latest_path.exists():
            try:
                existing_payload = json.loads(self.latest_path.read_text(encoding="utf-8"))
                if isinstance(existing_payload, dict):
                    payload.update(existing_payload)
            except Exception:
                pass
        for key, value in self.base_payload.items():
            payload.setdefault(key, value)
        return payload

    def update(self, state: str, stage: str, message: str, **extra: Any) -> None:
        payload = self.current_payload()

        for key, value in extra.items():
            if value is not None:
                payload[key] = value

        payload.update(
            {
                "run_id": self.base_payload["run_id"],
                "instance_name": self.base_payload["instance_name"],
                "zone": self.base_payload["zone"],
                "config_path": self.base_payload["config_path"],
                "created_utc": self.base_payload["created_utc"],
                "created_local": self.base_payload["created_local"],
                "run_label": self.base_payload["run_label"],
                "local_results_dir": self.base_payload["local_results_dir"],
                "remote_run_root": self.base_payload["remote_run_root"],
                "state": state,
                "stage": stage,
                "message": message,
                "updated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            }
        )
        self.latest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")


def build_default_artifact_verification() -> ArtifactVerificationResult:
    return ArtifactVerificationResult(expected_files=[])


def infer_remote_state_from_artifacts(extracted_dir: Path, remote_state: str) -> str:
    normalized = str(remote_state or "").strip().lower()
    if normalized and normalized != REMOTE_STATUS_UNKNOWN:
        return normalized

    status_path = extracted_dir / "run_status.json"
    if not status_path.exists():
        return normalized or REMOTE_STATUS_UNKNOWN

    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        return normalized or REMOTE_STATUS_UNKNOWN

    inferred = str(payload.get("state", "")).strip().lower()
    return inferred or normalized or REMOTE_STATUS_UNKNOWN


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_gcloud_binary() -> str:
    candidates: list[Path | str] = []
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.extend(
            [
                Path(local_appdata) / "Google" / "Cloud SDK" / "google-cloud-sdk" / "bin" / "gcloud.cmd",
                Path(local_appdata) / "Google" / "Cloud SDK" / "google-cloud-sdk" / "bin" / "gcloud.exe",
            ]
        )

    candidates.extend(["gcloud.cmd", "gcloud.exe", "gcloud"])

    for candidate in candidates:
        if isinstance(candidate, Path):
            if candidate.exists():
                return str(candidate)
            continue
        found = shutil.which(candidate)
        if found:
            return found

    raise FileNotFoundError("Could not locate gcloud. Install Google Cloud SDK or add it to PATH.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Windows-first GCP launcher for the strategy engine.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG.relative_to(REPO_ROOT)), help="Config YAML to run.")
    parser.add_argument("--instance-name", default=DEFAULT_INSTANCE_NAME)
    parser.add_argument("--zone", default=DEFAULT_ZONE)
    parser.add_argument("--machine-type", default=DEFAULT_MACHINE_TYPE)
    parser.add_argument("--project", default=None, help="Optional GCP project override.")
    parser.add_argument("--results-root", default=str(DEFAULT_RESULTS_ROOT))
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--boot-disk-size", default=DEFAULT_BOOT_DISK_SIZE)
    parser.add_argument("--image-family", default=DEFAULT_IMAGE_FAMILY)
    parser.add_argument("--image-project", default=DEFAULT_IMAGE_PROJECT)
    parser.add_argument("--dry-run", action="store_true", help="Run preflight, manifest, and bundle creation only.")
    parser.add_argument("--keep-vm", action="store_true", help="Do not destroy the VM at the end.")
    parser.add_argument("--keep-remote", action="store_true", help="Do not delete remote staging before exit.")
    parser.add_argument(
        "--recover-run",
        default=None,
        help="Recover artifacts for an existing run directory under results-root instead of launching a new VM.",
    )
    parser.add_argument(
        "--provisioning-model",
        default="SPOT",
        choices=["SPOT", "STANDARD"],
        help="GCP provisioning model.",
    )
    parser.add_argument(
        "--fire-and-forget",
        action="store_true",
        help="Launch engine and exit. VM will self-upload artifacts to strategy-console and self-delete.",
    )
    return parser.parse_args(argv)


def absolute_repo_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def sanitize_run_token(value: str) -> str:
    text = str(value).strip().replace("\r", "").replace("\n", "")
    return text.strip()


def make_run_id(instance_name: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return sanitize_run_token(f"{instance_name}-{stamp}")


def format_local_timestamp(dt: datetime) -> str:
    local_dt = dt.astimezone()
    return f"{local_dt.strftime('%Y-%m-%d %H:%M:%S')} {local_dt.tzname() or 'local'}"


def summarize_datasets_for_label(datasets: list[DatasetSpec]) -> str:
    if not datasets:
        return "no-datasets"

    markets = sorted({ds.market for ds in datasets})
    timeframes = [ds.timeframe for ds in datasets]
    market_text = "-".join(markets)
    timeframe_text = timeframes[0] if len(timeframes) == 1 else f"{len(timeframes)}tf"
    return f"{market_text}_{timeframe_text}"


def make_run_label(created_at: datetime, datasets: list[DatasetSpec]) -> str:
    return f"{created_at.astimezone().strftime('%Y-%m-%d_%H-%M')}_{summarize_datasets_for_label(datasets)}"


def remote_paths_for_run(run_id: str) -> dict[str, str]:
    clean_run_id = sanitize_run_token(run_id)
    run_root = f"/tmp/strategy_engine_runs/{clean_run_id}"
    return {
        "run_root": run_root,
        "bundle": f"{run_root}/{DEFAULT_BUNDLE_NAME}",
        "runner": f"{run_root}/remote_runner.sh",
        "status": f"{run_root}/run_status.json",
        "artifact_tarball": f"{run_root}/artifacts.tar.gz",
        "config": f"{run_root}/config.yaml",
    }


REMOTE_RUNNER_SCRIPT = r"""#!/bin/bash
set -euo pipefail

RUN_ROOT="$1"
FIRE_AND_FORGET_ENABLED="__FIRE_AND_FORGET_ENABLED__"
BUCKET_URI="__BUCKET_URI__"
COMPUTE_ZONE="__COMPUTE_ZONE__"
BUNDLE_STAGING_URI="__BUNDLE_STAGING_URI__"
STATUS_PATH="$RUN_ROOT/run_status.json"
BUNDLE_PATH="$RUN_ROOT/input_bundle.tar.gz"
LOG_DIR="$RUN_ROOT/logs"
RUNNER_LOG="$LOG_DIR/runner.log"
ENGINE_LOG="$LOG_DIR/engine_run.log"
ARTIFACTS_DIR="$RUN_ROOT/preserved"
ARTIFACT_TARBALL="$RUN_ROOT/artifacts.tar.gz"
REPO_DIR="$RUN_ROOT/repo"

mkdir -p "$RUN_ROOT" "$LOG_DIR" "$ARTIFACTS_DIR"
touch "$RUNNER_LOG"
exec > >(tee -a "$RUNNER_LOG") 2>&1

write_status() {
    local state="$1"
    local stage="$2"
    local message="$3"
    local exit_code="${4:-0}"
    python3 - "$STATUS_PATH" "$state" "$stage" "$message" "$exit_code" "$ARTIFACT_TARBALL" "$ENGINE_LOG" "$RUN_ROOT" <<'PY'
import json
import sys
from datetime import datetime, UTC
from pathlib import Path

status_path = Path(sys.argv[1])
state = sys.argv[2]
stage = sys.argv[3]
message = sys.argv[4]
exit_code = int(sys.argv[5])
artifact_tarball = sys.argv[6]
engine_log = sys.argv[7]
run_root = sys.argv[8]

payload = {}
if status_path.exists():
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}

payload.update(
    {
        "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "state": state,
        "stage": stage,
        "message": message,
        "exit_code": exit_code,
        "artifact_tarball": artifact_tarball,
        "engine_log": engine_log,
        "run_root": run_root,
    }
)

status_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
PY
}

preserve_outputs() {
    rm -rf "$ARTIFACTS_DIR"
    mkdir -p "$ARTIFACTS_DIR"
    cp "$STATUS_PATH" "$ARTIFACTS_DIR/" 2>/dev/null || true
    cp "$RUN_ROOT/manifest.json" "$ARTIFACTS_DIR/" 2>/dev/null || true
    cp "$RUN_ROOT/config.yaml" "$ARTIFACTS_DIR/" 2>/dev/null || true
    if [ -d "$LOG_DIR" ]; then
        cp -R "$LOG_DIR" "$ARTIFACTS_DIR/logs"
    fi
    if [ -d "$REPO_DIR/Outputs" ]; then
        cp -R "$REPO_DIR/Outputs" "$ARTIFACTS_DIR/Outputs"
    fi
    tar -czf "$ARTIFACT_TARBALL" -C "$ARTIFACTS_DIR" .
}

write_status "running" "bootstrap" "Preparing remote run root"

if [ ! -f "$BUNDLE_PATH" ]; then
    if [ -n "$BUNDLE_STAGING_URI" ]; then
        write_status "running" "bundle_download" "Downloading input bundle from GCS staging"
        if gcloud storage cp "$BUNDLE_STAGING_URI" "$BUNDLE_PATH"; then
            echo "[bootstrap] Bundle downloaded from GCS staging."
        else
            write_status "failed" "bundle_download" "Failed to download input bundle from GCS staging" 1
            preserve_outputs
            exit 1
        fi
    else
        write_status "failed" "bootstrap" "Input bundle missing" 1
        preserve_outputs
        exit 1
    fi
fi

write_status "running" "python_bootstrap" "Installing python3.12 runtime and venv tooling"
if ! sudo apt-get update -qq; then
    write_status "failed" "python_bootstrap" "Failed updating apt metadata for python3.12 bootstrap" 1
    preserve_outputs
    exit 1
fi

if ! sudo apt-get install -y -qq python3.12 python3.12-venv python3.12-dev tar >/dev/null 2>&1; then
    write_status "failed" "python_bootstrap" "python3.12 not available on remote VM" 1
    preserve_outputs
    exit 1
fi

if ! command -v python3.12 >/dev/null 2>&1; then
    write_status "failed" "python_bootstrap" "python3.12 not available on remote VM" 1
    preserve_outputs
    exit 1
fi

rm -rf "$REPO_DIR"
if ! tar -xzf "$BUNDLE_PATH" -C "$RUN_ROOT"; then
    write_status "failed" "extract" "Failed extracting input bundle" 1
    preserve_outputs
    exit 1
fi

if ! python3 - "$RUN_ROOT/manifest.json" "$RUN_ROOT/config.yaml" "$REPO_DIR" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
config_path = Path(sys.argv[2])
repo_dir = Path(sys.argv[3])

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
datasets = manifest.get("datasets", [])

if not config_path.exists():
    raise SystemExit(f"config missing: {config_path}")
if not repo_dir.exists():
    raise SystemExit(f"repo missing: {repo_dir}")
if not datasets:
    raise SystemExit("manifest datasets list is empty")

for dataset in datasets:
    target = repo_dir / dataset["bundle_repo_path"]
    expected_size = int(dataset["size_bytes"])
    if not target.exists():
        raise SystemExit(f"dataset missing: {target}")
    if target.stat().st_size != expected_size:
        raise SystemExit(f"dataset size mismatch: {target}")
    if target.stat().st_size <= 0:
        raise SystemExit(f"dataset empty: {target}")
PY
then
    write_status "failed" "validate" "Manifest validation failed" 1
    preserve_outputs
    exit 1
fi

echo "[env] system python:"
command -v python3 || true
python3 --version || true

echo "[env] required python:"
command -v python3.12 || true
python3.12 --version || true

write_status "running" "validated" "Inputs validated; creating virtual environment with python3.12"
rm -rf "$RUN_ROOT/venv"
if ! python3.12 -m venv "$RUN_ROOT/venv"; then
    write_status "failed" "python_bootstrap" "Failed creating virtual environment with python3.12" 1
    preserve_outputs
    exit 1
fi
source "$RUN_ROOT/venv/bin/activate"

echo "[env] venv python:"
python --version || true
pip --version || true

if ! python -m pip install --upgrade pip >/dev/null 2>&1; then
    write_status "failed" "pip" "Failed upgrading pip in remote virtual environment" 1
    preserve_outputs
    exit 1
fi

PIP_EXIT=0
if [ -f "$REPO_DIR/requirements.txt" ]; then
    python -m pip install --quiet -r "$REPO_DIR/requirements.txt" || PIP_EXIT=$?
else
    python -m pip install --quiet numpy pandas pyyaml pytest || PIP_EXIT=$?
fi
if [ "$PIP_EXIT" -ne 0 ]; then
    write_status "failed" "pip" "Dependency installation failed" "$PIP_EXIT"
    preserve_outputs
    exit "$PIP_EXIT"
fi

write_status "running" "engine_start" "Starting master strategy engine"
ENGINE_EXIT=0
(
    cd "$REPO_DIR" && \
    python -u master_strategy_engine.py --config "$RUN_ROOT/config.yaml"
) >"$ENGINE_LOG" 2>&1 || ENGINE_EXIT=$?

if [ "$ENGINE_EXIT" -eq 0 ]; then
    write_status "completed" "artifacts" "Engine completed successfully" 0
else
    write_status "failed" "artifacts" "Engine failed" "$ENGINE_EXIT"
fi

preserve_outputs
if [ "$ENGINE_EXIT" -eq 0 ]; then
    write_status "completed" "finished" "Engine completed successfully" 0
else
    write_status "failed" "finished" "Engine failed" "$ENGINE_EXIT"
fi

# --- FIRE-AND-FORGET: Upload artifacts to GCS Bucket and self-delete ---
if [ "$FIRE_AND_FORGET_ENABLED" = "1" ] && [ "$ENGINE_EXIT" -eq 0 ]; then
    RUN_ID=$(basename "$RUN_ROOT")

    echo "[upload] Uploading artifacts to Bucket: $BUCKET_URI"

    # Prevent any interactive prompts during fire-and-forget upload
    export CLOUDSDK_CORE_DISABLE_PROMPTS=1

    # 1. Upload the tarball
    echo "[upload] Copying artifacts to cloud storage..."
    if gcloud storage cp "$ARTIFACT_TARBALL" "$BUCKET_URI/runs/$RUN_ID/artifacts.tar.gz"; then
        echo "[upload] Artifacts tarball uploaded."
    else
        write_status "completed" "upload_failed" "Upload artifacts to bucket failed." 1
        echo "[error] Upload failed. VM preserved."
        exit 1
    fi

    # 2. Upload status file
    echo "[upload] Copying status file..."
    gcloud storage cp "$STATUS_PATH" "$BUCKET_URI/runs/$RUN_ID/run_status.json" || true

    # 3. Verify
    echo "[upload] Verifying upload..."
    if gcloud storage ls "$BUCKET_URI/runs/$RUN_ID/artifacts.tar.gz" >/dev/null; then
        write_status "completed" "uploaded" "Artifacts uploaded to Bucket. VM will self-delete." 0
        echo "[cleanup] Upload confirmed. Self-deleting in 10 seconds..."
        sleep 10
        gcloud compute instances delete "$(hostname)" --zone="$COMPUTE_ZONE" --quiet
    else
        write_status "completed" "upload_failed" "Upload verification failed. VM preserved." 1
        echo "[error] Upload verification failed. VM preserved."
    fi
fi

exit "$ENGINE_EXIT"
"""


def resolve_required_datasets(config: dict[str, Any], repo_root: Path) -> list[DatasetSpec]:
    datasets = config.get("datasets", [])
    if not datasets:
        raise ValueError("Config does not define any datasets.")

    resolved: list[DatasetSpec] = []
    for entry in datasets:
        path_str = str(entry.get("path", ""))
        try:
            local_path = resolve_dataset_path(path_str)
        except FileNotFoundError:
            candidate = Path(path_str)
            if not candidate.is_absolute():
                repo_relative = (repo_root / candidate).resolve()
                if repo_relative.exists():
                    local_path = repo_relative
                else:
                    raise
            else:
                raise
        if not local_path.exists():
            raise FileNotFoundError(f"Dataset not found: {local_path}")
        if not local_path.is_file():
            raise FileNotFoundError(f"Dataset is not a file: {local_path}")
        if local_path.stat().st_size <= 0:
            raise ValueError(f"Dataset is empty: {local_path}")

        resolved.append(
            DatasetSpec(
                market=str(entry.get("market", "UNKNOWN")),
                timeframe=str(entry.get("timeframe", "UNKNOWN")),
                local_path=str(local_path),
                file_name=local_path.name,
                bundle_repo_path=f"Data/{local_path.name}",
                size_bytes=local_path.stat().st_size,
                sha256=sha256_file(local_path),
            )
        )
    return resolved


def resolve_dataset_path(path: str) -> Path:
    raw = str(path or "").strip()
    if not raw:
        raise FileNotFoundError("Dataset path is empty.")

    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        if candidate.exists():
            return candidate.resolve()
        raise FileNotFoundError(f"Dataset not found: {candidate}")

    uploads_candidate = (UPLOADS_DIR / candidate.name).resolve()
    if uploads_candidate.exists():
        return uploads_candidate

    repo_data_candidate = (REPO_DATA_DIR / candidate.name).resolve()
    if repo_data_candidate.exists():
        return repo_data_candidate

    raise FileNotFoundError(
        "Dataset not found. Attempted paths: "
        f"{uploads_candidate} ; {repo_data_candidate}"
    )


def build_remote_config(config: dict[str, Any], datasets: list[DatasetSpec]) -> dict[str, Any]:
    remote_config = copy.deepcopy(config)
    remote_config["datasets"] = [
        {
            "path": ds.bundle_repo_path,
            "market": ds.market,
            "timeframe": ds.timeframe,
        }
        for ds in datasets
    ]
    remote_config["output_dir"] = "Outputs"
    return remote_config


def build_manifest(
    *,
    run_id: str,
    config_path: Path,
    config_sha256: str,
    instance_name: str,
    zone: str,
    machine_type: str,
    provisioning_model: str,
    boot_disk_size: str | None,
    image_family: str | None,
    project_id: str | None,
    datasets: list[DatasetSpec],
    local_results_dir: Path,
) -> RunManifest:
    remote = remote_paths_for_run(run_id)
    created_at = datetime.now(UTC)
    return RunManifest(
        run_id=run_id,
        created_utc=created_at.isoformat(timespec="seconds"),
        created_local=format_local_timestamp(created_at),
        run_label=make_run_label(created_at, datasets),
        instance_name=instance_name,
        zone=zone,
        machine_type=machine_type,
        provisioning_model=provisioning_model,
        boot_disk_size=boot_disk_size,
        image_family=image_family,
        config_path=str(config_path),
        config_sha256=config_sha256,
        project_id=project_id,
        datasets=[asdict(ds) for ds in datasets],
        remote_run_root=remote["run_root"],
        remote_bundle_path=remote["bundle"],
        remote_runner_path=remote["runner"],
        remote_status_path=remote["status"],
        remote_artifact_tarball=remote["artifact_tarball"],
        local_results_dir=str(local_results_dir),
    )


def should_skip_dir(name: str) -> bool:
    return name in EXCLUDED_DIR_NAMES or any(name.startswith(prefix) for prefix in EXCLUDED_DIR_PREFIXES)


def iter_repo_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for root, dirs, filenames in os.walk(repo_root):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]
        for filename in filenames:
            file_path = root_path / filename
            if file_path.suffix in EXCLUDED_FILE_SUFFIXES:
                continue
            if file_path.name in EXCLUDED_FILE_NAMES:
                continue
            rel = file_path.relative_to(repo_root)
            if rel.parts and rel.parts[0] == "Data":
                continue
            files.append(file_path)
    return sorted(files)


def _deterministic_tar_info(arcname: str, size: int, is_dir: bool = False) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=arcname)
    info.size = 0 if is_dir else size
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o755 if is_dir else 0o644
    info.type = tarfile.DIRTYPE if is_dir else tarfile.REGTYPE
    return info


def _add_bytes_to_tar(tar: tarfile.TarFile, arcname: str, payload: bytes) -> None:
    info = _deterministic_tar_info(arcname, len(payload))
    tar.addfile(info, io.BytesIO(payload))


def _add_file_to_tar(tar: tarfile.TarFile, file_path: Path, arcname: str) -> None:
    payload = file_path.read_bytes()
    _add_bytes_to_tar(tar, arcname, payload)


def create_input_bundle(
    *,
    bundle_path: Path,
    repo_root: Path,
    manifest: RunManifest,
    remote_config: dict[str, Any],
    datasets: list[DatasetSpec],
) -> None:
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_bytes = json.dumps(asdict(manifest), indent=2).encode("utf-8")
    config_bytes = yaml.safe_dump(remote_config, sort_keys=False).encode("utf-8")

    with tarfile.open(bundle_path, "w:gz") as tar:
        for file_path in iter_repo_files(repo_root):
            rel = file_path.relative_to(repo_root)
            _add_file_to_tar(tar, file_path, str(Path("repo") / rel).replace("\\", "/"))

        for dataset in datasets:
            _add_file_to_tar(tar, Path(dataset.local_path), str(Path("repo") / dataset.bundle_repo_path).replace("\\", "/"))

        _add_bytes_to_tar(tar, "manifest.json", manifest_bytes)
        _add_bytes_to_tar(tar, "config.yaml", config_bytes)


def build_gcloud_base(gcloud_bin: str, project: str | None) -> list[str]:
    base = [gcloud_bin]
    if project:
        base.extend(["--project", project])
    return base


def run_command(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    check: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env["CLOUDSDK_SSH_NATIVE"] = "1"
    if env:
        merged_env.update(env)
    return subprocess.run(
        command,
        text=True,
        capture_output=capture_output,
        check=check,
        env=merged_env,
    )


def get_active_project(gcloud_bin: str, explicit_project: str | None) -> str | None:
    if explicit_project:
        return explicit_project
    result = run_command([gcloud_bin, "config", "get-value", "project"], check=False)
    project = (result.stdout or "").strip()
    if project and project != "(unset)":
        return project
    return None


def run_preflight(config_path: Path, explicit_project: str | None) -> PreflightResult:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    if not config_path.is_file():
        raise FileNotFoundError(f"Config path is not a file: {config_path}")

    gcloud_bin = resolve_gcloud_binary()
    project_id = get_active_project(gcloud_bin, explicit_project)
    if not project_id:
        raise RuntimeError("No active GCP project resolved. Run `gcloud config set project <PROJECT_ID>` or pass --project.")

    config = load_config(config_path)
    datasets = resolve_required_datasets(config, REPO_ROOT)

    return PreflightResult(
        config_path=config_path,
        config_sha256=sha256_file(config_path),
        gcloud_bin=gcloud_bin,
        project_id=project_id,
        datasets=datasets,
    )


def print_preflight_summary(result: PreflightResult) -> None:
    print("Preflight Summary")
    print("=" * 60)
    print(f"Config:   {result.config_path}")
    print(f"Project:  {result.project_id}")
    print(f"gcloud:   {result.gcloud_bin}")
    print(f"Datasets: {len(result.datasets)}")
    for dataset in result.datasets:
        size_mb = dataset.size_bytes / (1024 * 1024)
        print(f"  - {dataset.market} {dataset.timeframe}: {dataset.local_path} ({size_mb:.1f} MB)")
    print("=" * 60)


def detect_remote_runner_state(
    gcloud_base: list[str],
    instance_name: str,
    zone: str,
    remote_run_root: str,
    remote_runner_path: str,
    remote_status_path: str,
    remote_artifact_tarball: str,
) -> dict[str, Any]:
    command = (
        "python3 - <<'PY'\n"
        "import json\n"
        "import subprocess\n"
        "from pathlib import Path\n"
        f"run_root = Path({remote_run_root!r})\n"
        f"runner_path = Path({remote_runner_path!r})\n"
        f"status_path = Path({remote_status_path!r})\n"
        f"artifact_tarball = Path({remote_artifact_tarball!r})\n"
        "payload = {\n"
        "    'runner_process_active': False,\n"
        "    'status_exists': status_path.exists(),\n"
        "    'status_terminal': False,\n"
        "    'status_state': '',\n"
        "    'artifact_exists': artifact_tarball.exists() and artifact_tarball.stat().st_size > 0 if artifact_tarball.exists() else False,\n"
        "    'runner_log_exists': False,\n"
        "    'runner_log_non_empty': False,\n"
        "}\n"
        "if status_path.exists():\n"
        "    try:\n"
        "        status_payload = json.loads(status_path.read_text(encoding='utf-8'))\n"
        "        state = str(status_payload.get('state', '')).lower()\n"
        "        payload['status_state'] = state\n"
        "        payload['status_terminal'] = state in {'completed', 'failed'}\n"
        "    except Exception:\n"
        "        pass\n"
        "runner_log = run_root / 'logs' / 'runner.log'\n"
        "payload['runner_log_exists'] = runner_log.exists()\n"
        "payload['runner_log_non_empty'] = runner_log.exists() and runner_log.stat().st_size > 0\n"
        "try:\n"
        "    result = subprocess.run(['pgrep', '-af', str(runner_path)], capture_output=True, text=True, check=False)\n"
        "    payload['runner_process_active'] = bool((result.stdout or '').strip())\n"
        "except Exception:\n"
        "    payload['runner_process_active'] = False\n"
        "print(json.dumps(payload))\n"
        "PY"
    )
    result = ssh_command(gcloud_base, instance_name, zone, command, check=False)
    try:
        return json.loads((result.stdout or "").strip() or "{}")
    except json.JSONDecodeError:
        return {}


def should_restart_remote_orchestration(remote_guard: dict[str, Any]) -> tuple[bool, str]:
    if remote_guard.get("runner_process_active"):
        return False, "remote runner already active"
    if remote_guard.get("status_terminal"):
        return False, f"remote status already terminal ({remote_guard.get('status_state', 'unknown')})"
    if remote_guard.get("artifact_exists"):
        return False, "artifacts tarball already exists"
    if remote_guard.get("status_exists") and remote_guard.get("runner_log_non_empty"):
        return False, "remote status and runner log already exist"
    return True, "remote runner not active and no terminal/artifact guard present"


def verify_remote_runner_started(
    gcloud_base: list[str],
    instance_name: str,
    zone: str,
    remote_run_root: str,
    remote_runner_path: str,
    remote_status_path: str,
    remote_artifact_tarball: str,
    timeout_seconds: int = 30,
) -> tuple[bool, dict[str, Any]]:
    started = time.time()
    last_guard: dict[str, Any] = {}
    while time.time() - started < timeout_seconds:
        last_guard = detect_remote_runner_state(
            gcloud_base,
            instance_name,
            zone,
            remote_run_root,
            remote_runner_path,
            remote_status_path,
            remote_artifact_tarball,
        )
        if (
            last_guard.get("status_exists")
            or last_guard.get("runner_log_non_empty")
            or (
                last_guard.get("runner_process_active")
                and last_guard.get("runner_log_exists")
            )
        ):
            return True, last_guard
        time.sleep(5)
    return False, last_guard


def instance_exists(gcloud_base: list[str], instance_name: str, zone: str) -> bool:
    result = run_command(
        gcloud_base
        + ["compute", "instances", "list", f"--filter=name={instance_name}", "--format=value(name)"],
        check=False,
    )
    return instance_name in (result.stdout or "").split()


def safe_instance_exists(gcloud_base: list[str], instance_name: str, zone: str) -> bool | None:
    try:
        return instance_exists(gcloud_base, instance_name, zone)
    except Exception:
        return None


def delete_instance(gcloud_base: list[str], instance_name: str, zone: str) -> None:
    run_command(
        gcloud_base + ["compute", "instances", "delete", instance_name, f"--zone={zone}", "--quiet"],
        capture_output=True,
    )


def create_instance(gcloud_base: list[str], args: argparse.Namespace, startup_message: str) -> None:
    command = gcloud_base + [
        "compute",
        "instances",
        "create",
        args.instance_name,
        f"--zone={args.zone}",
        f"--machine-type={args.machine_type}",
        f"--provisioning-model={args.provisioning_model}",
        f"--image-family={args.image_family}",
        f"--image-project={args.image_project}",
        f"--boot-disk-size={args.boot_disk_size}",
        "--boot-disk-type=pd-ssd",
        "--scopes=cloud-platform",
        "--metadata",
        f"strategy-engine-note={startup_message}",
    ]
    if args.provisioning_model == "SPOT":
        command.append("--instance-termination-action=STOP")
    run_command(command)


def wait_for_ssh(
    gcloud_base: list[str],
    instance_name: str,
    zone: str,
    timeout_seconds: int = DEFAULT_SSH_READY_TIMEOUT_SECONDS,
) -> None:
    started = time.time()
    while time.time() - started < timeout_seconds:
        result = run_command(
            gcloud_base + ["compute", "ssh", instance_name, f"--zone={zone}", "--command=echo ready"],
            check=False,
        )
        if "ready" in (result.stdout or ""):
            return
        time.sleep(10)
    raise TimeoutError(f"SSH not ready after {timeout_seconds} seconds.")


def ssh_command(gcloud_base: list[str], instance_name: str, zone: str, remote_command: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run_command(
        gcloud_base + ["compute", "ssh", instance_name, f"--zone={zone}", f"--command={remote_command}"],
        check=check,
    )


def scp_to_remote(gcloud_base: list[str], instance_name: str, zone: str, local_path: Path, remote_path: str) -> None:
    run_command(
        gcloud_base + ["compute", "scp", str(local_path), f"{instance_name}:{remote_path}", f"--zone={zone}"],
    )


def scp_from_remote(gcloud_base: list[str], instance_name: str, zone: str, remote_path: str, local_path: Path) -> None:
    run_command(
        gcloud_base + ["compute", "scp", f"{instance_name}:{remote_path}", str(local_path), f"--zone={zone}"],
    )


def describe_instance_status(gcloud_base: list[str], instance_name: str, zone: str) -> str:
    result = run_command(
        gcloud_base + ["compute", "instances", "describe", instance_name, f"--zone={zone}", "--format=value(status)"],
        check=False,
    )
    return (result.stdout or "").strip()


def read_remote_file(gcloud_base: list[str], instance_name: str, zone: str, remote_path: str) -> str:
    result = ssh_command(gcloud_base, instance_name, zone, f"cat {remote_path} 2>/dev/null || true", check=False)
    return (result.stdout or "").strip()


def remote_artifact_exists(gcloud_base: list[str], instance_name: str, zone: str, remote_path: str) -> bool:
    result = ssh_command(
        gcloud_base,
        instance_name,
        zone,
        f"test -s {remote_path} && echo present || true",
        check=False,
    )
    return "present" in (result.stdout or "")


def read_remote_dataset_statuses(gcloud_base: list[str], instance_name: str, zone: str, remote_run_root: str) -> list[dict[str, Any]]:
    command = (
        "python3 - <<'PY'\n"
        "import json\n"
        "from pathlib import Path\n"
        f"root = Path('{remote_run_root}') / 'repo' / 'Outputs'\n"
        "payload = []\n"
        "if root.exists():\n"
        "    for status_path in sorted(root.glob('*/status.json')):\n"
        "        try:\n"
        "            payload.append(json.loads(status_path.read_text(encoding='utf-8')))\n"
        "        except Exception:\n"
        "            pass\n"
        "print(json.dumps(payload))\n"
        "PY"
    )
    result = ssh_command(gcloud_base, instance_name, zone, command, check=False)
    text = (result.stdout or "").strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return []


def parse_status_json(text: str) -> dict[str, Any]:
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def summarize_remote_progress(remote_status: dict[str, Any], dataset_statuses: list[dict[str, Any]]) -> str:
    if dataset_statuses:
        parts = []
        for status in dataset_statuses:
            dataset = status.get("dataset", "UNKNOWN")
            family = status.get("current_family", "?")
            stage = status.get("current_stage", "?")
            pct = status.get("progress_pct", 0)
            parts.append(f"{dataset}:{family}:{stage}:{pct}%")
        return " | ".join(parts)
    stage = remote_status.get("stage", "unknown")
    message = remote_status.get("message", "")
    return f"{stage}: {message}".strip()


def extract_tarball(tarball_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball_path, "r:gz") as tar:
        tar.extractall(destination)


def mirror_artifacts_to_exports(
    *,
    run_dir: Path,
    extracted_dir: Path,
    exports_root: Path | None = None,
) -> list[Path]:
    outputs_dir = extracted_dir / "Outputs"
    if not outputs_dir.exists():
        return []

    if exports_root is None:
        exports_root = EXPORTS_DIR
    exports_root.mkdir(parents=True, exist_ok=True)
    run_id = sanitize_run_token(run_dir.name)
    mirrored_paths: list[Path] = []

    latest_dir = exports_root / "latest"
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    shutil.copytree(extracted_dir, latest_dir)
    mirrored_paths.append(latest_dir)

    latest_run_path = exports_root / LATEST_RUN_FILE_NAME
    latest_run_path.write_text(
        f"{run_id}\n{run_dir}\n{latest_dir}\n",
        encoding="utf-8",
    )
    mirrored_paths.append(latest_run_path)

    for leaderboard_name in ("master_leaderboard.csv", "master_leaderboard_bootcamp.csv"):
        master_src = outputs_dir / leaderboard_name
        if not master_src.exists():
            continue

        latest_master = exports_root / leaderboard_name
        shutil.copy2(master_src, latest_master)
        mirrored_paths.append(latest_master)

        archived_master = exports_root / f"{run_id}_{leaderboard_name}"
        shutil.copy2(master_src, archived_master)
        mirrored_paths.append(archived_master)

    tarball_src = run_dir / "artifacts.tar.gz"
    if tarball_src.exists():
        archived_tarball = exports_root / f"{run_id}_artifacts.tar.gz"
        shutil.copy2(tarball_src, archived_tarball)
        mirrored_paths.append(archived_tarball)

    return mirrored_paths


def should_sync_results_to_strategy_console(results_root: Path) -> bool:
    if os.environ.get("DISABLE_STRATEGY_CONSOLE_SYNC") == "1":
        return False

    local_console_root = (Path.home() / "strategy_console_storage").expanduser()
    local_console_runs = local_console_root / "runs"
    try:
        return results_root.resolve() != local_console_runs.resolve()
    except Exception:
        return str(results_root) != str(local_console_runs)


def sync_run_to_strategy_console_storage(
    *,
    gcloud_base: list[str],
    run_dir: Path,
    exports_root: Path | None = None,
    console_instance_name: str | None = None,
    console_zone: str | None = None,
    console_remote_root: str | None = None,
    console_remote_user: str | None = None,
) -> list[str]:
    exports_root = EXPORTS_DIR if exports_root is None else exports_root
    console_instance_name = console_instance_name or os.environ.get(
        "STRATEGY_CONSOLE_INSTANCE", DEFAULT_STRATEGY_CONSOLE_INSTANCE
    )
    console_zone = console_zone or os.environ.get("STRATEGY_CONSOLE_ZONE", DEFAULT_STRATEGY_CONSOLE_ZONE)
    console_remote_root = console_remote_root or os.environ.get(
        "STRATEGY_CONSOLE_REMOTE_ROOT", DEFAULT_STRATEGY_CONSOLE_REMOTE_ROOT
    )
    console_remote_user = console_remote_user or os.environ.get(
        "STRATEGY_CONSOLE_REMOTE_USER", DEFAULT_STRATEGY_CONSOLE_REMOTE_USER
    )

    run_id = sanitize_run_token(run_dir.name)
    remote_runs_root = f"{console_remote_root}/runs"
    remote_exports_root = f"{console_remote_root}/exports"
    remote_run_dir = f"{remote_runs_root}/{run_id}"
    remote_stage_root = f"/tmp/strategy_console_sync_{run_id}"
    synced_paths: list[str] = []

    ssh_command(
        gcloud_base,
        console_instance_name,
        console_zone,
        (
            f"rm -rf {remote_stage_root} && "
            f"mkdir -p {remote_stage_root} && "
            f"sudo -n -u {console_remote_user} mkdir -p {remote_runs_root} {remote_exports_root} && "
            f"sudo -n -u {console_remote_user} rm -rf {remote_run_dir} {remote_exports_root}/latest"
        ),
    )

    run_command(
        gcloud_base
        + [
            "compute",
            "scp",
            "--recurse",
            str(run_dir),
            f"{console_instance_name}:{remote_stage_root}",
            f"--zone={console_zone}",
        ]
    )
    ssh_command(
        gcloud_base,
        console_instance_name,
        console_zone,
        (
            f"sudo -n -u {console_remote_user} cp -R {remote_stage_root}/{run_id} {remote_runs_root}/ && "
            f"sudo -n -u {console_remote_user} chmod -R g+w {remote_run_dir}"
        ),
    )
    synced_paths.append(remote_run_dir)

    remote_runs_latest = f"{remote_runs_root}/{LATEST_RUN_FILE_NAME}"
    ssh_command(
        gcloud_base,
        console_instance_name,
        console_zone,
        (
            f"sudo -n -u {console_remote_user} python3 -c "
            f"\"from pathlib import Path; "
            f"Path({remote_runs_latest!r}).write_text({(run_id + chr(10) + remote_run_dir + chr(10))!r}, encoding='utf-8')\""
        ),
    )
    synced_paths.append(remote_runs_latest)

    latest_dir = exports_root / "latest"
    if latest_dir.exists():
        run_command(
            gcloud_base
            + [
                "compute",
                "scp",
                "--recurse",
                str(latest_dir),
                f"{console_instance_name}:{remote_stage_root}",
                f"--zone={console_zone}",
            ]
        )
        ssh_command(
            gcloud_base,
            console_instance_name,
            console_zone,
            (
                f"sudo -n -u {console_remote_user} cp -R {remote_stage_root}/latest {remote_exports_root}/ && "
                f"sudo -n -u {console_remote_user} chmod -R g+w {remote_exports_root}/latest"
            ),
        )
        synced_paths.append(f"{remote_exports_root}/latest")

    for path in sorted(exports_root.iterdir()) if exports_root.exists() else []:
        if path.is_dir():
            continue
        if not path.name.startswith(f"{run_id}_") and path.name not in {
            LATEST_RUN_FILE_NAME,
            "master_leaderboard.csv",
            "master_leaderboard_bootcamp.csv",
        }:
            continue
        run_command(
            gcloud_base
            + [
                "compute",
                "scp",
                str(path),
                f"{console_instance_name}:{remote_stage_root}/{path.name}",
                f"--zone={console_zone}",
            ]
        )
        ssh_command(
            gcloud_base,
            console_instance_name,
            console_zone,
            f"sudo -n -u {console_remote_user} cp {remote_stage_root}/{path.name} {remote_exports_root}/{path.name}",
        )
        synced_paths.append(f"{remote_exports_root}/{path.name}")

    ssh_command(
        gcloud_base,
        console_instance_name,
        console_zone,
        f"rm -rf {remote_stage_root}",
        check=False,
    )

    return synced_paths


def _detect_expected_output_files(outputs_dir: Path) -> list[str]:
    expected_files = [
        outputs_dir / "master_leaderboard.csv",
        outputs_dir / "family_summary_results.csv",
        outputs_dir / "logs" / "engine_run.log",
    ]

    discovered: list[str] = []
    for candidate in expected_files:
        if candidate.exists():
            discovered.append(str(candidate.relative_to(outputs_dir)).replace("\\", "/"))

    for dataset_dir in sorted(path for path in outputs_dir.iterdir() if path.is_dir()):
        for name in ("master_leaderboard.csv", "family_summary_results.csv", "family_leaderboard_results.csv"):
            candidate = dataset_dir / name
            if candidate.exists():
                discovered.append(str(candidate.relative_to(outputs_dir)).replace("\\", "/"))
        preserved_dir = dataset_dir / "preserved"
        if preserved_dir.exists() and any(preserved_dir.rglob("*")):
            discovered.append(str(preserved_dir.relative_to(outputs_dir)).replace("\\", "/"))

    return discovered


def download_and_extract_artifacts(
    gcloud_base: list[str],
    instance_name: str,
    zone: str,
    remote_tarball_path: str,
    tarball_local: Path,
    extracted_dir: Path,
) -> ArtifactDownloadResult:
    scp_from_remote(gcloud_base, instance_name, zone, remote_tarball_path, tarball_local)
    if not tarball_local.exists():
        raise FileNotFoundError(f"Artifacts tarball was not downloaded: {tarball_local}")

    tarball_size_bytes = tarball_local.stat().st_size
    if tarball_size_bytes <= 0:
        raise ValueError(f"Artifacts tarball is empty: {tarball_local}")

    extract_tarball(tarball_local, extracted_dir)
    return ArtifactDownloadResult(
        tarball_path=tarball_local,
        extracted_dir=extracted_dir,
        tarball_size_bytes=tarball_size_bytes,
    )


def verify_preserved_results(extracted_dir: Path, remote_state: str) -> tuple[bool, str]:
    verification = inspect_preserved_artifacts(
        tarball_path=None,
        extracted_dir=extracted_dir,
        remote_state=remote_state,
    )
    return verification.artifact_verified, verification.verification_message


def inspect_preserved_artifacts(
    *,
    tarball_path: Path | None,
    extracted_dir: Path,
    remote_state: str,
) -> ArtifactVerificationResult:
    verification = build_default_artifact_verification()
    verification.expected_files = []
    verification.effective_remote_state = infer_remote_state_from_artifacts(extracted_dir, remote_state)
    if tarball_path is not None:
        verification.tarball_exists = tarball_path.exists()
        verification.tarball_size_bytes = tarball_path.stat().st_size if tarball_path.exists() else 0
        verification.artifacts_downloaded = verification.tarball_exists and verification.tarball_size_bytes > 0
    else:
        verification.tarball_exists = True
        verification.artifacts_downloaded = True
    verification.extracted_dir_exists = extracted_dir.exists()

    required_metadata = ["run_status.json", "manifest.json", "config.yaml"]
    missing_metadata = [name for name in required_metadata if not (extracted_dir / name).exists()]
    if missing_metadata:
        verification.verification_message = f"Missing preserved metadata: {', '.join(missing_metadata)}."
        return verification

    logs_dir = extracted_dir / "logs"
    if not logs_dir.exists() or not any(logs_dir.rglob("*")):
        verification.verification_message = "Preserved logs are missing."
        return verification

    verification.extraction_verified = verification.extracted_dir_exists
    verification.expected_subdirs_present = logs_dir.exists()

    if verification.effective_remote_state == "completed":
        outputs_dir = extracted_dir / "Outputs"
        if not outputs_dir.exists():
            verification.verification_message = "Completed run did not preserve Outputs."
            return verification

        verification.expected_subdirs_present = any(
            (extracted_dir / name).exists() for name in ("Outputs", "logs", "preserved")
        )
        verification.expected_files = _detect_expected_output_files(outputs_dir)
        verification.expected_outputs_present = bool(verification.expected_files)
        verification.artifact_verified = (
            verification.artifacts_downloaded
            and verification.extraction_verified
            and verification.expected_subdirs_present
            and verification.expected_outputs_present
        )
        if verification.artifact_verified:
            verification.verification_message = (
                "Preserved outputs verified (" + ", ".join(sorted(verification.expected_files)) + ")."
            )
            return verification

        verification.verification_message = (
            "Completed run preserved Outputs, but expected result files were missing."
        )
        return verification

    verification.artifact_verified = False
    verification.verification_message = "Failure artifacts preserved."
    return verification


def can_auto_destroy(status: dict[str, Any], args: argparse.Namespace) -> tuple[bool, str]:
    if args.keep_vm:
        return False, "--keep-vm requested"
    if status.get("run_outcome") not in EXPLICIT_SUCCESS_RUN_OUTCOMES:
        return False, f"run outcome is not explicit success ({status.get('run_outcome')!r})"
    if not status.get("artifacts_downloaded"):
        return False, "artifacts were not downloaded"
    if not status.get("artifact_verified"):
        return False, "artifact verification did not pass"
    if not status.get("extraction_verified"):
        return False, "artifact extraction was not verified"
    if not status.get("expected_outputs_present"):
        return False, "expected outputs are missing locally"
    remote_state = str(status.get("remote_state") or "").strip().lower()
    if remote_state not in {"completed", "artifacts_ready"}:
        return False, f"remote state is not explicit success ({remote_state or 'unknown'})"
    return True, "verified success with local artifacts present"


def build_recovery_commands(
    *,
    instance_name: str,
    zone: str,
    remote_status_path: str,
    remote_tarball_path: str,
    local_run_dir: Path,
) -> list[str]:
    run_id = sanitize_run_token(local_run_dir.name)
    return [
        f"python run_cloud_sweep.py --recover-run {run_id}",
        f"gcloud compute ssh {instance_name} --zone={zone}",
        f"gcloud compute ssh {instance_name} --zone={zone} --command=\"cat {remote_status_path}\"",
        f"gcloud compute scp {instance_name}:{remote_tarball_path} \"{local_run_dir / 'artifacts.tar.gz'}\" --zone={zone}",
        f"gcloud compute instances delete {instance_name} --zone={zone} --quiet",
    ]


def _attempt_vm_destroy_after_recovery(
    gcloud_base: list[str],
    manifest: RunManifest,
    status_store: "LauncherStatusStore",
    args: argparse.Namespace,
) -> None:
    """Destroy the sweep VM after a successful recovery if auto-destroy is permitted."""
    instance_exists = safe_instance_exists(gcloud_base, manifest.instance_name, manifest.zone)
    if not instance_exists:
        return
    destroy_ok, destroy_reason = can_auto_destroy(status_store.current_payload(), args)
    if not destroy_ok:
        status_store.update(
            VM_OUTCOME_PRESERVED,
            "destroy_skipped",
            f"VM preserved after recovery: {destroy_reason}",
            vm_outcome=VM_OUTCOME_PRESERVED,
            destroy_allowed=False,
            destroy_reason=destroy_reason,
            instance_exists_at_end=True,
            billing_should_be_stopped=False,
            operator_action=(
                f"delete VM manually: gcloud compute instances delete "
                f"{manifest.instance_name} --zone={manifest.zone} --quiet"
            ),
        )
        print(
            f"WARNING: VM preserved after recovery ({destroy_reason}). "
            f"Delete manually: gcloud compute instances delete "
            f"{manifest.instance_name} --zone={manifest.zone} --quiet"
        )
        return
    try:
        status_store.update(
            "running",
            "destroy",
            "Destroying VM after successful recovery.",
            destroy_allowed=True,
            destroy_reason=destroy_reason,
        )
        delete_instance(gcloud_base, manifest.instance_name, manifest.zone)
        status_store.update(
            VM_OUTCOME_DESTROYED,
            "destroyed",
            "VM destroyed after recovery.",
            vm_outcome=VM_OUTCOME_DESTROYED,
            destroy_allowed=True,
            destroy_reason=destroy_reason,
            instance_exists_at_end=False,
            billing_should_be_stopped=True,
            operator_action="none",
            recovery_commands=[],
        )
        print("VM destroyed successfully after recovery.")
    except Exception as exc:
        status_store.update(
            VM_OUTCOME_PRESERVED,
            "destroy_failed",
            f"Failed to destroy VM after recovery: {exc}",
            vm_outcome=VM_OUTCOME_PRESERVED,
            destroy_allowed=False,
            destroy_reason=f"destroy failed: {exc}",
            instance_exists_at_end=True,
            billing_should_be_stopped=False,
            operator_action=(
                f"delete VM manually: gcloud compute instances delete "
                f"{manifest.instance_name} --zone={manifest.zone} --quiet"
            ),
        )
        print(
            f"WARNING: failed to destroy VM: {exc}. "
            f"Delete manually: gcloud compute instances delete "
            f"{manifest.instance_name} --zone={manifest.zone} --quiet"
        )


def recover_existing_run(
    *,
    gcloud_base: list[str],
    args: argparse.Namespace,
    run_dir: Path,
) -> int:
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Cannot recover run without manifest: {manifest_path}")

    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_payload.setdefault("created_local", manifest_payload.get("created_utc", ""))
    manifest_payload.setdefault("run_label", manifest_payload.get("run_id", run_dir.name))
    manifest = RunManifest(**manifest_payload)
    status_store = LauncherStatusStore(
        run_dir,
        run_id=manifest.run_id,
        instance_name=manifest.instance_name,
        zone=manifest.zone,
        config_path=manifest.config_path,
        local_results_dir=manifest.local_results_dir,
        remote_run_root=manifest.remote_run_root,
        created_utc=manifest.created_utc,
        created_local=manifest.created_local,
        run_label=manifest.run_label,
    )

    extracted_dir = run_dir / "artifacts"
    tarball_local = run_dir / "artifacts.tar.gz"
    remote_state = REMOTE_STATUS_UNKNOWN
    remote_status: dict[str, Any] = {}
    remote_artifact_exists_flag: bool | None = None

    if extracted_dir.exists():
        existing_verification = inspect_preserved_artifacts(
            tarball_path=tarball_local if tarball_local.exists() else None,
            extracted_dir=extracted_dir,
            remote_state="completed",
        )
        if existing_verification.artifact_verified:
            mirrored = mirror_artifacts_to_exports(
                run_dir=run_dir,
                extracted_dir=extracted_dir,
            )
            console_synced: list[str] = []
            if should_sync_results_to_strategy_console(run_dir.parent):
                try:
                    console_synced = sync_run_to_strategy_console_storage(
                        gcloud_base=gcloud_base,
                        run_dir=run_dir,
                    )
                except Exception as exc:
                    status_store.update(
                        "running",
                        "console_sync_warning",
                        f"Results verified locally but console sync failed: {exc}",
                    )
            status_store.update(
                RUN_OUTCOME_COMPLETED_VERIFIED,
                "recovered_local_artifacts",
                "Existing local artifacts verified and mirrored to exports.",
                run_outcome=RUN_OUTCOME_COMPLETED_VERIFIED,
                artifacts_downloaded=existing_verification.artifacts_downloaded,
                extraction_verified=existing_verification.extraction_verified,
                expected_outputs_present=existing_verification.expected_outputs_present,
                artifact_verified=existing_verification.artifact_verified,
                remote_state="completed",
                final_retrieval_attempted=False,
                final_retrieval_success=True,
                exports_updated=[str(path) for path in mirrored] + console_synced,
            )
            print(f"Recovered artifacts already present locally: {extracted_dir}")
            print(f"Convenience exports updated under: {EXPORTS_DIR}")
            if console_synced:
                print("Synced verified run outputs to strategy-console storage.")
            _attempt_vm_destroy_after_recovery(gcloud_base, manifest, status_store, args)
            return 0

    status_store.update(
        "running",
        "artifact_recovery",
        "Attempting recovery of preserved artifacts for existing run.",
    )

    instance_exists_now = safe_instance_exists(gcloud_base, manifest.instance_name, manifest.zone)
    if instance_exists_now:
        remote_status = parse_status_json(
            read_remote_file(gcloud_base, manifest.instance_name, manifest.zone, manifest.remote_status_path)
        )
        remote_state = str(remote_status.get("state", REMOTE_STATUS_UNKNOWN)).lower()
        try:
            remote_artifact_exists_flag = remote_artifact_exists(
                gcloud_base,
                manifest.instance_name,
                manifest.zone,
                manifest.remote_artifact_tarball,
            )
        except Exception:
            remote_artifact_exists_flag = None
    else:
        remote_state = "missing"

    if not instance_exists_now:
        status_store.update(
            RUN_OUTCOME_VM_MISSING_BEFORE_RETRIEVAL,
            "artifact_recovery_failed",
            "Recovery failed because the compute VM no longer exists.",
            run_outcome=RUN_OUTCOME_VM_MISSING_BEFORE_RETRIEVAL,
            failure_reason="vm_missing_before_retrieval",
            remote_state=remote_state,
            remote_artifact_exists=False,
            final_retrieval_attempted=True,
            final_retrieval_success=False,
        )
        return 1

    if not remote_artifact_exists_flag:
        status_store.update(
            RUN_OUTCOME_ARTIFACT_DOWNLOAD_FAILED,
            "artifact_recovery_failed",
            "Recovery failed because no preserved remote artifacts tarball is present.",
            run_outcome=RUN_OUTCOME_ARTIFACT_DOWNLOAD_FAILED,
            failure_reason="artifact_download_failed",
            remote_state=remote_state,
            remote_status=remote_status,
            remote_artifact_exists=remote_artifact_exists_flag,
            final_retrieval_attempted=True,
            final_retrieval_success=False,
        )
        return 1

    artifact_result = download_and_extract_artifacts(
        gcloud_base,
        manifest.instance_name,
        manifest.zone,
        manifest.remote_artifact_tarball,
        tarball_local,
        extracted_dir,
    )
    verification = inspect_preserved_artifacts(
        tarball_path=artifact_result.tarball_path,
        extracted_dir=artifact_result.extracted_dir,
        remote_state=remote_state,
    )
    mirrored = mirror_artifacts_to_exports(
        run_dir=run_dir,
        extracted_dir=extracted_dir,
    ) if verification.expected_outputs_present else []
    console_synced: list[str] = []
    if verification.expected_outputs_present and should_sync_results_to_strategy_console(run_dir.parent):
        try:
            console_synced = sync_run_to_strategy_console_storage(
                gcloud_base=gcloud_base,
                run_dir=run_dir,
            )
        except Exception as exc:
            status_store.update(
                "running",
                "console_sync_warning",
                f"Recovered artifacts locally but console sync failed: {exc}",
            )

    run_outcome = (
        RUN_OUTCOME_COMPLETED_VERIFIED
        if verification.artifact_verified and verification.effective_remote_state == "completed"
        else RUN_OUTCOME_ARTIFACT_VERIFICATION_FAILED
    )
    status_store.update(
        run_outcome,
        "artifact_recovery_complete",
        verification.verification_message,
        run_outcome=run_outcome,
        failure_reason=None if run_outcome == RUN_OUTCOME_COMPLETED_VERIFIED else "artifact_verification_failed",
        remote_state=verification.effective_remote_state,
        remote_status=remote_status,
        remote_artifact_exists=remote_artifact_exists_flag,
        artifacts_downloaded=verification.artifacts_downloaded,
        extraction_verified=verification.extraction_verified,
        expected_outputs_present=verification.expected_outputs_present,
        artifact_verified=verification.artifact_verified,
        final_retrieval_attempted=True,
        final_retrieval_success=verification.artifact_verified,
        exports_updated=[str(path) for path in mirrored] + console_synced,
    )
    if verification.artifact_verified:
        print(f"Recovered artifacts to: {extracted_dir}")
        print(f"Convenience exports updated under: {EXPORTS_DIR}")
        if console_synced:
            print("Synced verified run outputs to strategy-console storage.")
        _attempt_vm_destroy_after_recovery(gcloud_base, manifest, status_store, args)
        return 0
    return 1


def build_destroy_decision(
    *,
    status: dict[str, Any],
    args: argparse.Namespace,
    instance_exists_at_end: bool | None,
    remote_status_path: str,
    remote_tarball_path: str,
    local_run_dir: Path,
) -> DestroyDecision:
    destroy_allowed, destroy_reason = can_auto_destroy(status, args)
    run_outcome = str(status.get("run_outcome") or "").strip()
    remote_artifact_exists = status.get("remote_artifact_exists")
    recovery_commands = build_recovery_commands(
        instance_name=args.instance_name,
        zone=args.zone,
        remote_status_path=remote_status_path,
        remote_tarball_path=remote_tarball_path,
        local_run_dir=local_run_dir,
    )

    if destroy_allowed:
        return DestroyDecision(
            destroy_allowed=True,
            destroy_reason=destroy_reason,
            instance_exists_at_end=instance_exists_at_end,
            billing_should_be_stopped=True,
            operator_action="none",
            recovery_commands=[],
        )

    if instance_exists_at_end is False:
        return DestroyDecision(
            destroy_allowed=False,
            destroy_reason="instance already gone",
            instance_exists_at_end=False,
            billing_should_be_stopped=True,
            operator_action="check local artifacts only",
            recovery_commands=[],
        )

    if args.keep_vm:
        operator_action = "download artifacts or inspect remotely, then delete the instance manually"
    elif remote_artifact_exists:
        operator_action = "inspect VM and download artifacts manually"
    elif run_outcome == RUN_OUTCOME_VM_MISSING_BEFORE_RETRIEVAL:
        operator_action = "check local artifacts only"
    else:
        operator_action = "inspect VM and download artifacts manually"

    billing_should_be_stopped = False if instance_exists_at_end else None
    return DestroyDecision(
        destroy_allowed=False,
        destroy_reason=destroy_reason,
        instance_exists_at_end=instance_exists_at_end,
        billing_should_be_stopped=billing_should_be_stopped,
        operator_action=operator_action,
        recovery_commands=recovery_commands if instance_exists_at_end else [],
    )


def build_local_run_dir(results_root: Path, run_id: str) -> Path:
    run_dir = results_root / sanitize_run_token(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_latest_run_pointer(results_root: Path, run_dir: Path) -> Path:
    results_root.mkdir(parents=True, exist_ok=True)
    latest_path = results_root / LATEST_RUN_FILE_NAME
    latest_path.write_text(f"{run_dir.name}\n{run_dir}\n", encoding="utf-8")
    return latest_path


def print_final_run_summary(status_path: Path, local_run_dir: Path) -> None:
    status = parse_status_json(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    run_outcome = str(status.get("run_outcome", "unknown")).strip() or "unknown"
    vm_outcome = str(status.get("vm_outcome", "unknown")).strip() or "unknown"
    artifacts_downloaded = bool(status.get("artifacts_downloaded"))
    artifact_verified = bool(status.get("artifact_verified"))
    destroy_allowed = bool(status.get("destroy_allowed"))
    billing_should_be_stopped = status.get("billing_should_be_stopped")
    destroy_reason = str(status.get("destroy_reason") or "").strip()
    operator_action = str(status.get("operator_action") or "").strip()
    recovery_commands = status.get("recovery_commands") or []
    if billing_should_be_stopped is True:
        billing_message = "YES"
    elif billing_should_be_stopped is False:
        billing_message = "NO"
    else:
        billing_message = "UNKNOWN"

    outputs_dir = local_run_dir / "artifacts" / "Outputs"
    results_location = outputs_dir if outputs_dir.exists() else local_run_dir
    exports_master = EXPORTS_DIR / "master_leaderboard.csv"

    print("=============================")
    print("STRATEGY ENGINE RUN COMPLETE")
    print("=============================")
    print(f"Run ID: {status.get('run_id', local_run_dir.name)}")
    if status.get("run_label"):
        print(f"Run Label: {status['run_label']}")
    if status.get("created_local"):
        print(f"Created: {status['created_local']}")
    print(f"Local Results Path: {local_run_dir}")
    print(f"Run Outcome: {run_outcome}")
    print(f"Artifacts downloaded: {'YES' if artifacts_downloaded else 'NO'}")
    print(f"Artifacts verified: {'YES' if artifact_verified else 'NO'}")
    print(f"VM outcome: {vm_outcome}")
    print(f"Destroy allowed: {'YES' if destroy_allowed else 'NO'}")
    print(f"Destroy reason: {destroy_reason or 'unknown'}")
    print(f"Billing stopped: {billing_message}")
    print(f"Operator action: {operator_action or 'unknown'}")
    print(f"Results location: {results_location}")
    if exports_master.exists():
        print(f"Convenience export: {exports_master}")
    if status.get("failure_reason"):
        print(f"Failure reason: {status['failure_reason']}")
    if vm_outcome == VM_OUTCOME_PRESERVED:
        print("VM preserved for inspection. Destroy manually if finished.")
        if recovery_commands:
            print("Recovery options:")
            for index, command in enumerate(recovery_commands, start=1):
                print(f"{index}. {command}")
    if run_outcome not in {RUN_OUTCOME_DRY_RUN_COMPLETE, RUN_OUTCOME_COMPLETED_VERIFIED}:
        print("RUN STATUS: FAILED")
        print("Artifacts incomplete or unverified.")
        print(f"Inspect logs in: {local_run_dir}")
        print("WARNING: Run did not complete verified artifact retrieval.")
        print("VM was preserved or may have already disappeared.")
        print("Do not trust this run's outputs until checked manually.")
    print("=============================")


def create_remote_runner_file(
    run_dir: Path,
    *,
    fire_and_forget: bool = False,
    bucket_uri: str = DEFAULT_BUCKET_URI,
    compute_zone: str = DEFAULT_ZONE,
    bundle_staging_uri: str = "",
) -> Path:
    script = REMOTE_RUNNER_SCRIPT
    script = script.replace("__FIRE_AND_FORGET_ENABLED__", "1" if fire_and_forget else "0")
    script = script.replace("__BUCKET_URI__", bucket_uri)
    script = script.replace("__COMPUTE_ZONE__", compute_zone)
    script = script.replace("__BUNDLE_STAGING_URI__", bundle_staging_uri)
    runner_path = run_dir / "remote_runner.sh"
    with runner_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(script)
    return runner_path


def launch_remote_runner(
    gcloud_base: list[str],
    instance_name: str,
    zone: str,
    remote_runner_path: str,
    remote_run_root: str,
) -> subprocess.CompletedProcess[str]:
    clean_runner_path = sanitize_run_token(remote_runner_path)
    clean_run_root = sanitize_run_token(remote_run_root)
    # Wrap in a subshell + disown so the SSH connection returns immediately
    # instead of blocking for the full engine duration.
    return ssh_command(
        gcloud_base,
        instance_name,
        zone,
        (
            f"mkdir -p {clean_run_root}/logs && "
            f"chmod +x {clean_runner_path} && "
            f"( nohup sudo bash {clean_runner_path} {clean_run_root} > "
            f"{clean_run_root}/logs/runner_stdout.log 2>&1 < /dev/null & disown ) ; "
            f"echo launched"
        ),
        check=False,
    )


def monitor_run(
    *,
    gcloud_base: list[str],
    args: argparse.Namespace,
    manifest: RunManifest,
    status_store: LauncherStatusStore,
    timeout_seconds: int = DEFAULT_MONITOR_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    last_summary = ""
    restart_attempted = False
    started_at = time.time()
    ssh_disconnects = 0
    while True:
        if time.time() - started_at >= timeout_seconds:
            return {
                "state": REMOTE_STATUS_UNKNOWN,
                "stage": "monitor_timeout",
                "message": f"Monitoring exceeded {timeout_seconds} seconds.",
                "failure_reason": "monitor_timeout",
            }
        time.sleep(max(5, args.poll_seconds))
        try:
            vm_status = describe_instance_status(gcloud_base, args.instance_name, args.zone)
        except Exception:
            vm_exists = safe_instance_exists(gcloud_base, args.instance_name, args.zone)
            if vm_exists is False:
                return {
                    "state": "missing",
                    "stage": "vm_missing",
                    "message": "VM disappeared during monitoring before artifacts were retrieved.",
                    "failure_reason": RUN_OUTCOME_VM_MISSING_BEFORE_RETRIEVAL,
                }
            ssh_disconnects += 1
            if ssh_disconnects >= 3:
                return {
                    "state": REMOTE_STATUS_UNKNOWN,
                    "stage": "ssh_disconnect",
                    "message": "Lost SSH connectivity during monitoring.",
                    "failure_reason": "ssh_disconnect",
                }
            status_store.update(
                "running",
                "ssh_disconnect",
                "SSH connectivity dropped during monitoring; retrying before concluding failure.",
                failure_reason="ssh_disconnect",
            )
            continue

        if vm_status in {"STOPPED", "TERMINATED"}:
            if restart_attempted:
                return {
                    "state": REMOTE_STATUS_UNKNOWN,
                    "stage": "preempted_twice",
                    "message": f"VM entered {vm_status} twice during monitoring.",
                    "failure_reason": "spot_preempted_or_interrupted",
                }
            status_store.update("running", "preempted_vm_detected", f"VM entered {vm_status}; checking whether remote restart is actually needed.", vm_status=vm_status)
            run_command(gcloud_base + ["compute", "instances", "start", args.instance_name, f"--zone={args.zone}"])
            wait_for_ssh(gcloud_base, args.instance_name, args.zone)
            remote_guard = detect_remote_runner_state(
                gcloud_base,
                args.instance_name,
                args.zone,
                manifest.remote_run_root,
                manifest.remote_runner_path,
                manifest.remote_status_path,
                manifest.remote_artifact_tarball,
            )
            should_restart, reason = should_restart_remote_orchestration(remote_guard)
            if should_restart:
                status_store.update(
                    "running",
                    "preempted_vm_restart_remote_runner",
                    f"VM restarted after {vm_status}; relaunching remote orchestration because {reason}.",
                    vm_status=vm_status,
                    remote_restart_guard=remote_guard,
                )
                launch_remote_runner(
                    gcloud_base,
                    args.instance_name,
                    args.zone,
                    manifest.remote_runner_path,
                    manifest.remote_run_root,
                )
            else:
                status_store.update(
                    "running",
                    "preempted_vm_remote_runner_not_restarted",
                    f"VM restarted after {vm_status}; remote orchestration was not relaunched because {reason}.",
                    vm_status=vm_status,
                    remote_restart_guard=remote_guard,
                )
            restart_attempted = True
            continue

        try:
            remote_status = parse_status_json(read_remote_file(gcloud_base, args.instance_name, args.zone, manifest.remote_status_path))
            dataset_statuses = read_remote_dataset_statuses(gcloud_base, args.instance_name, args.zone, manifest.remote_run_root)
        except Exception:
            vm_exists = safe_instance_exists(gcloud_base, args.instance_name, args.zone)
            if vm_exists is False:
                return {
                    "state": "missing",
                    "stage": "vm_missing",
                    "message": "VM disappeared before remote status could be read.",
                    "failure_reason": RUN_OUTCOME_VM_MISSING_BEFORE_RETRIEVAL,
                }
            ssh_disconnects += 1
            if ssh_disconnects >= 3:
                return {
                    "state": REMOTE_STATUS_UNKNOWN,
                    "stage": "ssh_disconnect",
                    "message": "Lost SSH/log access during monitoring.",
                    "failure_reason": "ssh_disconnect",
                }
            continue

        ssh_disconnects = 0
        summary = summarize_remote_progress(remote_status, dataset_statuses)

        if summary != last_summary:
            print(f"[monitor] {summary}")
            last_summary = summary

        status_store.update(
            "running",
            "monitoring",
            summary or "Waiting for remote status.",
            vm_status=vm_status,
            remote_status=remote_status,
            dataset_statuses=dataset_statuses,
        )

        state = str(remote_status.get("state", "")).lower()
        if state in {"completed", "failed"}:
            remote_status.setdefault("vm_status", vm_status)
            return remote_status


def ensure_bucket_exists(gcloud_base: list[str], bucket_uri: str, location: str = "us-central1") -> None:
    cmd_base = [gcloud_base[0]] # Get executable (gcloud/gcloud.cmd)
    if "--project" in gcloud_base:
        idx = gcloud_base.index("--project")
        cmd_base.extend(["--project", gcloud_base[idx + 1]])

    result = run_command(cmd_base + ["storage", "buckets", "describe", bucket_uri], check=False, capture_output=True)
    if result.returncode == 0:
        return

    print(f"Creating GCS bucket: {bucket_uri} in {location}")
    run_command(cmd_base + ["storage", "buckets", "create", bucket_uri, f"--location={location}"])


def print_manifest_summary(manifest: RunManifest) -> None:
    print("=" * 60)
    print("GCP Strategy Engine Launcher")
    print("=" * 60)
    print(f"Run ID:      {manifest.run_id}")
    print(f"Run Label:   {manifest.run_label}")
    print(f"Created:     {manifest.created_local}")
    print(f"Instance:    {manifest.instance_name}")
    print(f"Zone:        {manifest.zone}")
    print(f"Machine:     {manifest.machine_type}")
    print(f"Config:      {manifest.config_path}")
    print(f"Datasets:    {len(manifest.datasets)}")
    for dataset in manifest.datasets:
        size_mb = dataset["size_bytes"] / (1024 * 1024)
        print(f"  - {dataset['market']} {dataset['timeframe']}: {dataset['file_name']} ({size_mb:.1f} MB)")
    print(f"Results Dir: {manifest.local_results_dir}")
    print("=" * 60)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv) if argv is not None else parse_args()
    config_path = absolute_repo_path(args.config)
    results_root = absolute_repo_path(args.results_root)
    preflight = run_preflight(config_path, args.project)
    print_preflight_summary(preflight)

    gcloud_base = build_gcloud_base(preflight.gcloud_bin, preflight.project_id)

    recover_run = getattr(args, "recover_run", None)
    if recover_run:
        recover_run_id = sanitize_run_token(recover_run)
        run_dir = build_local_run_dir(results_root, recover_run_id)
        print(f"Recovering existing run: {recover_run_id}")
        return recover_existing_run(
            gcloud_base=gcloud_base,
            args=args,
            run_dir=run_dir,
        )

    config = load_config(config_path)
    datasets = preflight.datasets

    # Allow YAML config to override cloud VM settings (zone, machine_type, etc.)
    cloud_cfg = config.get("cloud", {})
    if "zone" in cloud_cfg and args.zone == DEFAULT_ZONE:
        args.zone = cloud_cfg["zone"]
    if "machine_type" in cloud_cfg and args.machine_type == DEFAULT_MACHINE_TYPE:
        args.machine_type = cloud_cfg["machine_type"]
    if "provisioning_model" in cloud_cfg and args.provisioning_model == "SPOT":
        args.provisioning_model = cloud_cfg["provisioning_model"]
    if "boot_disk_size" in cloud_cfg and args.boot_disk_size == DEFAULT_BOOT_DISK_SIZE:
        args.boot_disk_size = cloud_cfg["boot_disk_size"]
    if "image_family" in cloud_cfg and args.image_family == DEFAULT_IMAGE_FAMILY:
        args.image_family = cloud_cfg["image_family"]
    if "instance_name" in cloud_cfg and args.instance_name == DEFAULT_INSTANCE_NAME:
        args.instance_name = cloud_cfg["instance_name"]
    remote_config = build_remote_config(config, datasets)
    bucket_uri = DEFAULT_BUCKET_URI

    run_id = make_run_id(args.instance_name)
    local_run_dir = build_local_run_dir(results_root, run_id)
    latest_run_path = write_latest_run_pointer(results_root, local_run_dir)
    remote = remote_paths_for_run(run_id)

    manifest = build_manifest(
        run_id=run_id,
        config_path=config_path,
        config_sha256=preflight.config_sha256,
        instance_name=args.instance_name,
        zone=args.zone,
        machine_type=args.machine_type,
        provisioning_model=args.provisioning_model,
        boot_disk_size=args.boot_disk_size,
        image_family=args.image_family,
        project_id=preflight.project_id,
        datasets=datasets,
        local_results_dir=local_run_dir,
    )
    status_store = LauncherStatusStore(
        local_run_dir,
        run_id=manifest.run_id,
        instance_name=manifest.instance_name,
        zone=manifest.zone,
        config_path=manifest.config_path,
        local_results_dir=manifest.local_results_dir,
        remote_run_root=manifest.remote_run_root,
        created_utc=manifest.created_utc,
        created_local=manifest.created_local,
        run_label=manifest.run_label,
    )

    manifest_path = local_run_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(asdict(manifest), indent=2), encoding="utf-8")
    fire_and_forget = getattr(args, "fire_and_forget", False)
    # In fire-and-forget mode the bucket is guaranteed to exist; route the large
    # input bundle through GCS so SCP only transfers small files (manifest + runner).
    # This avoids CalledProcessError from SPOT preemption during a long SCP.
    bundle_staging_uri = f"{bucket_uri}/staging/{run_id}/input_bundle.tar.gz" if fire_and_forget else ""
    runner_path = create_remote_runner_file(
        local_run_dir,
        fire_and_forget=fire_and_forget,
        bucket_uri=bucket_uri,
        compute_zone=args.zone,
        bundle_staging_uri=bundle_staging_uri,
    )
    bundle_path = local_run_dir / DEFAULT_BUNDLE_NAME

    print_manifest_summary(manifest)

    status_store.update(
        "preflight_passed",
        "preflight",
        "Preflight checks passed.",
        manifest=asdict(manifest),
        project_id=preflight.project_id,
        gcloud_bin=preflight.gcloud_bin,
        provisioning_model=manifest.provisioning_model,
        machine_type=manifest.machine_type,
        boot_disk_size=manifest.boot_disk_size,
        image_family=manifest.image_family,
    )
    create_input_bundle(
        bundle_path=bundle_path,
        repo_root=REPO_ROOT,
        manifest=manifest,
        remote_config=remote_config,
        datasets=datasets,
    )
    status_store.update(
        "prepared",
        "bundle",
        "Input bundle created.",
        bundle_path=str(bundle_path),
        bundle_size_bytes=bundle_path.stat().st_size,
    )

    if args.dry_run:
        status_store.update(
            RUN_OUTCOME_DRY_RUN_COMPLETE,
            "dry_run",
            "Dry run completed after preflight, manifest creation, and bundle creation. No VM was created.",
            run_outcome=RUN_OUTCOME_DRY_RUN_COMPLETE,
            vm_outcome="not_created",
            destroy_allowed=False,
        )
        print(f"Dry run complete. Manifest and bundle are ready in {local_run_dir}")
        print(f"Latest run pointer: {latest_run_path}")
        print_final_run_summary(status_store.latest_path, local_run_dir)
        return 0

    if fire_and_forget:
        ensure_bucket_exists(gcloud_base, bucket_uri)
        if bundle_staging_uri:
            status_store.update("running", "bundle_stage_upload", "Uploading input bundle to GCS staging (avoids SCP timeout for large bundles).")
            run_command(gcloud_base + ["storage", "cp", str(bundle_path), bundle_staging_uri])
            print(f"[bundle] Input bundle staged to GCS: {bundle_staging_uri}")

    exit_code = 0
    run_outcome: str | None = None
    failure_reason: str | None = None
    remote_status: dict[str, Any] = {}
    remote_state = REMOTE_STATUS_UNKNOWN
    artifact_verification = build_default_artifact_verification()
    artifact_verification.expected_files = []
    remote_artifact_exists_flag: bool | None = None
    final_retrieval_attempted = False
    final_retrieval_success = False
    console_synced_paths: list[str] = []
    try:
        if instance_exists(gcloud_base, args.instance_name, args.zone):
            status_store.update("running", "instance_reset", "Existing instance found; deleting it first.")
            delete_instance(gcloud_base, args.instance_name, args.zone)

        status_store.update("running", "instance_create", "Creating VM.")
        create_instance(gcloud_base, args, startup_message=f"session11:{run_id}")

        status_store.update("running", "ssh_wait", "Waiting for SSH readiness.")
        wait_for_ssh(gcloud_base, args.instance_name, args.zone)

        status_store.update("running", "remote_stage", "Creating deterministic remote staging directory.")
        ssh_command(gcloud_base, args.instance_name, args.zone, f"mkdir -p {remote['run_root']}/logs")

        if bundle_staging_uri:
            upload_desc = "Uploading manifest and runner to VM (bundle already staged to GCS)."
        else:
            upload_desc = "Uploading input bundle, manifest, and runner to VM."
        status_store.update("running", "upload", upload_desc)
        if not bundle_staging_uri:
            scp_to_remote(gcloud_base, args.instance_name, args.zone, bundle_path, remote["bundle"])
        scp_to_remote(gcloud_base, args.instance_name, args.zone, manifest_path, f"{remote['run_root']}/manifest.json")
        scp_to_remote(gcloud_base, args.instance_name, args.zone, runner_path, remote["runner"])

        status_store.update("running", "validate_remote", "Validating remote upload payloads before engine start.")
        # When bundle is staged via GCS, the runner downloads it at bootstrap time —
        # it won't be present on the VM yet, so only validate the small files.
        bundle_check = "" if bundle_staging_uri else f"test -s {remote['bundle']} && "
        ssh_command(
            gcloud_base,
            args.instance_name,
            args.zone,
            (
                f"{bundle_check}"
                f"test -s {remote['run_root']}/manifest.json && "
                f"test -s {remote['runner']}"
            ),
        )

        status_store.update("running", "remote_start", "Starting remote orchestration script.")
        launch_result = launch_remote_runner(
            gcloud_base,
            args.instance_name,
            args.zone,
            remote["runner"],
            remote["run_root"],
        )
        if launch_result.returncode != 0:
            status_store.update(
                "running",
                "remote_start_warning",
                "Remote launch command returned non-zero; verifying whether remote orchestration actually started.",
                remote_start_returncode=launch_result.returncode,
                remote_start_stderr=(launch_result.stderr or "").strip()[:1000],
            )
        runner_started, runner_guard = verify_remote_runner_started(
            gcloud_base,
            args.instance_name,
            args.zone,
            manifest.remote_run_root,
            manifest.remote_runner_path,
            manifest.remote_status_path,
            manifest.remote_artifact_tarball,
        )
        if not runner_started:
            run_outcome = RUN_OUTCOME_REMOTE_START_FAILED
            failure_reason = RUN_OUTCOME_REMOTE_START_FAILED
            status_store.update(
                RUN_OUTCOME_REMOTE_START_FAILED,
                "remote_start_integrity_failed",
                "Remote runner launch could not be confirmed. VM preserved for inspection.",
                remote_restart_guard=runner_guard,
                run_outcome=run_outcome,
                failure_reason=failure_reason,
            )
            print("Remote runner launch could not be confirmed. VM preserved for inspection.")
            exit_code = 1
        else:
            status_store.update(
                "running",
                "remote_start_verified",
                "Remote orchestration launch confirmed.",
                remote_restart_guard=runner_guard,
            )
            if fire_and_forget:
                print()
                print("FIRE-AND-FORGET MODE")
                print("====================")
                print(f"Run ID: {manifest.run_id}")
                print(f"Run Label: {manifest.run_label}")
                print(f"VM: {manifest.instance_name} ({manifest.zone}, {manifest.machine_type})")
                print()
                print("The engine is running. When it finishes, the VM will:")
                print(f"  1. Upload artifacts to GCS Bucket: {bucket_uri}")
                print("  2. Self-delete to stop billing")
                print()
                print("You can safely close this terminal.")
                print("Check results later:")
                print(f"  python download_run.py --latest")
                print(f"  python download_run.py {manifest.run_id}")
                print("====================")
                return 0
        if run_outcome is None:
            remote_status = monitor_run(
                gcloud_base=gcloud_base,
                args=args,
                manifest=manifest,
                status_store=status_store,
            )
            remote_state = str(remote_status.get("state", REMOTE_STATUS_UNKNOWN)).lower()
            failure_reason = str(remote_status.get("failure_reason", "")).strip() or None

            if remote_state == "missing":
                run_outcome = RUN_OUTCOME_VM_MISSING_BEFORE_RETRIEVAL
                failure_reason = failure_reason or RUN_OUTCOME_VM_MISSING_BEFORE_RETRIEVAL
                exit_code = 1
            elif remote_state == REMOTE_STATUS_UNKNOWN:
                exit_code = 1

        tarball_local = local_run_dir / "artifacts.tar.gz"
        extracted_dir = local_run_dir / "artifacts"
        should_attempt_download = False
        if run_outcome is None:
            should_attempt_download = True
        elif run_outcome != RUN_OUTCOME_VM_MISSING_BEFORE_RETRIEVAL:
            try:
                remote_artifact_exists_flag = remote_artifact_exists(
                    gcloud_base,
                    args.instance_name,
                    args.zone,
                    manifest.remote_artifact_tarball,
                )
                should_attempt_download = bool(remote_artifact_exists_flag)
            except Exception:
                remote_artifact_exists_flag = None
                should_attempt_download = False

        if should_attempt_download:
            status_store.update(
                "running",
                "artifact_download",
                "Downloading preserved artifact tarball.",
                remote_status=remote_status,
                remote_state=remote_state,
                remote_artifact_exists=remote_artifact_exists_flag,
            )
            try:
                artifact_result = download_and_extract_artifacts(
                    gcloud_base,
                    args.instance_name,
                    args.zone,
                    manifest.remote_artifact_tarball,
                    tarball_local,
                    extracted_dir,
                )
                artifact_verification = inspect_preserved_artifacts(
                    tarball_path=artifact_result.tarball_path,
                    extracted_dir=artifact_result.extracted_dir,
                    remote_state=remote_state,
                )
                status_store.update(
                    "running",
                    "artifact_verification",
                    artifact_verification.verification_message,
                    extracted_dir=str(extracted_dir),
                    artifacts_tarball_size_bytes=artifact_result.tarball_size_bytes,
                    artifacts_downloaded=artifact_verification.artifacts_downloaded,
                    extraction_verified=artifact_verification.extraction_verified,
                    expected_outputs_present=artifact_verification.expected_outputs_present,
                    artifact_verified=artifact_verification.artifact_verified,
                    remote_state=remote_state,
                    remote_artifact_exists=True,
                )
                if artifact_verification.expected_outputs_present:
                    mirrored_paths = mirror_artifacts_to_exports(
                        run_dir=local_run_dir,
                        extracted_dir=extracted_dir,
                    )
                    console_synced_main: list[str] = []
                    if should_sync_results_to_strategy_console(local_run_dir.parent):
                        try:
                            console_synced_main = sync_run_to_strategy_console_storage(
                                gcloud_base=gcloud_base,
                                run_dir=local_run_dir,
                            )
                        except Exception as sync_exc:
                            status_store.update(
                                "running",
                                "console_sync_warning",
                                f"Artifacts mirrored locally but console sync failed: {sync_exc}",
                            )
                    status_store.update(
                        "running",
                        "exports_sync",
                        "Mirrored latest outputs to strategy_console_storage/exports.",
                        exports_updated=[str(path) for path in mirrored_paths] + console_synced_main,
                    )
                    if console_synced_main:
                        print("Synced run outputs to strategy-console storage.")
            except Exception as exc:
                artifact_verification = build_default_artifact_verification()
                artifact_verification.expected_files = []
                artifact_verification.verification_message = f"Artifact download or extraction failed: {exc}"
                artifact_verification.tarball_exists = tarball_local.exists()
                artifact_verification.tarball_size_bytes = tarball_local.stat().st_size if tarball_local.exists() else 0
                status_store.update(
                    RUN_OUTCOME_ARTIFACT_DOWNLOAD_FAILED,
                    "artifact_download_failed",
                    artifact_verification.verification_message,
                    run_outcome=RUN_OUTCOME_ARTIFACT_DOWNLOAD_FAILED,
                    failure_reason="artifact_download_failed",
                    artifacts_downloaded=False,
                    extraction_verified=False,
                    expected_outputs_present=False,
                    artifact_verified=False,
                    remote_state=remote_state,
                    remote_artifact_exists=remote_artifact_exists_flag,
                )
                run_outcome = RUN_OUTCOME_ARTIFACT_DOWNLOAD_FAILED
                failure_reason = "artifact_download_failed"
                exit_code = 1

        if run_outcome is None:
            if remote_state == "completed" and artifact_verification.artifact_verified:
                run_outcome = RUN_OUTCOME_COMPLETED_VERIFIED
            elif remote_state == "completed":
                run_outcome = RUN_OUTCOME_ARTIFACT_VERIFICATION_FAILED
                failure_reason = failure_reason or "artifact_verification_failed"
                exit_code = 1
            elif remote_state == "failed":
                run_outcome = RUN_OUTCOME_REMOTE_RUN_FAILED
                failure_reason = failure_reason or "remote_run_failed"
                exit_code = 1
            elif artifact_verification.artifacts_downloaded:
                run_outcome = RUN_OUTCOME_COMPLETED_UNVERIFIED
                failure_reason = failure_reason or "remote_state_unknown"
                exit_code = 1
            elif remote_state == REMOTE_STATUS_UNKNOWN:
                run_outcome = RUN_OUTCOME_REMOTE_MONITOR_FAILED
                failure_reason = failure_reason or "remote_state_unknown"
                exit_code = 1

        if not args.keep_remote and safe_instance_exists(gcloud_base, args.instance_name, args.zone):
            ssh_command(gcloud_base, args.instance_name, args.zone, f"rm -rf {remote['run_root']}", check=False)

        status_store.update(
            run_outcome or RUN_OUTCOME_UNEXPECTED_LAUNCHER_FAILURE,
            "run_terminal",
            artifact_verification.verification_message or "Launcher reached terminal state.",
            run_outcome=run_outcome or RUN_OUTCOME_UNEXPECTED_LAUNCHER_FAILURE,
            failure_reason=failure_reason,
            remote_status=remote_status,
            remote_state=remote_state,
            artifacts_downloaded=artifact_verification.artifacts_downloaded,
            extraction_verified=artifact_verification.extraction_verified,
            expected_outputs_present=artifact_verification.expected_outputs_present,
            artifact_verified=artifact_verification.artifact_verified,
            remote_artifact_exists=remote_artifact_exists_flag,
        )

        if run_outcome == RUN_OUTCOME_COMPLETED_VERIFIED:
            print(f"Run complete. Preserved artifacts are in {local_run_dir}")
        elif run_outcome == RUN_OUTCOME_VM_MISSING_BEFORE_RETRIEVAL:
            print("WARNING: Results were not retrieved because the VM had already disappeared.")
        else:
            print("WARNING: Run did not complete with verified local artifacts. VM will only be destroyed if the centralized safety guard permits it.")
    except Exception as exc:
        exit_code = 1
        if run_outcome is None:
            run_outcome = RUN_OUTCOME_UNEXPECTED_LAUNCHER_FAILURE
        failure_reason = failure_reason or exc.__class__.__name__.lower()
        status_store.update(
            run_outcome,
            "launcher_exception",
            f"Launcher failed unexpectedly: {exc}",
            run_outcome=run_outcome,
            failure_reason=failure_reason,
            remote_state=remote_state,
            artifacts_downloaded=artifact_verification.artifacts_downloaded,
            extraction_verified=artifact_verification.extraction_verified,
            expected_outputs_present=artifact_verification.expected_outputs_present,
            artifact_verified=artifact_verification.artifact_verified,
            remote_artifact_exists=remote_artifact_exists_flag,
        )
    finally:
        if run_outcome is None:
            run_outcome = RUN_OUTCOME_UNEXPECTED_LAUNCHER_FAILURE
            failure_reason = failure_reason or "missing_terminal_run_outcome"
            status_store.update(
                run_outcome,
                "run_terminal_fallback",
                "Launcher reached finally without an explicit terminal outcome.",
                run_outcome=run_outcome,
                failure_reason=failure_reason,
            )

        instance_exists_at_end = safe_instance_exists(gcloud_base, args.instance_name, args.zone)
        if remote_artifact_exists_flag is None and instance_exists_at_end:
            try:
                remote_artifact_exists_flag = remote_artifact_exists(
                    gcloud_base,
                    args.instance_name,
                    args.zone,
                    manifest.remote_artifact_tarball,
                )
            except Exception:
                remote_artifact_exists_flag = None

        should_retry_retrieval = (
            instance_exists_at_end is True
            and remote_artifact_exists_flag is True
            and not artifact_verification.artifact_verified
            and run_outcome != RUN_OUTCOME_DRY_RUN_COMPLETE
        )
        if should_retry_retrieval:
            final_retrieval_attempted = True
            status_store.update(
                "running",
                "artifact_download_retry",
                "Attempting one final artifact retrieval before preserve decision.",
                run_outcome=run_outcome,
                remote_artifact_exists=remote_artifact_exists_flag,
                final_retrieval_attempted=True,
            )
            try:
                artifact_result = download_and_extract_artifacts(
                    gcloud_base,
                    args.instance_name,
                    args.zone,
                    manifest.remote_artifact_tarball,
                    local_run_dir / "artifacts.tar.gz",
                    local_run_dir / "artifacts",
                )
                artifact_verification = inspect_preserved_artifacts(
                    tarball_path=artifact_result.tarball_path,
                    extracted_dir=artifact_result.extracted_dir,
                    remote_state=remote_state,
                )
                remote_state = artifact_verification.effective_remote_state or remote_state
                final_retrieval_success = artifact_verification.artifact_verified
                if final_retrieval_success and remote_state == "completed":
                    run_outcome = RUN_OUTCOME_COMPLETED_VERIFIED
                    failure_reason = None
                    exit_code = 0
                mirrored_paths: list[Path] = []
                console_synced_retry: list[str] = []
                if artifact_verification.expected_outputs_present:
                    mirrored_paths = mirror_artifacts_to_exports(
                        run_dir=local_run_dir,
                        extracted_dir=local_run_dir / "artifacts",
                    )
                    if should_sync_results_to_strategy_console(local_run_dir.parent):
                        try:
                            console_synced_retry = sync_run_to_strategy_console_storage(
                                gcloud_base=gcloud_base,
                                run_dir=local_run_dir,
                            )
                        except Exception as sync_exc:
                            status_store.update(
                                "running",
                                "console_sync_warning",
                                f"Retry artifacts mirrored locally but console sync failed: {sync_exc}",
                            )
                status_store.update(
                    "running",
                    "artifact_verification_retry",
                    artifact_verification.verification_message,
                    run_outcome=run_outcome,
                    failure_reason=failure_reason,
                    artifacts_downloaded=artifact_verification.artifacts_downloaded,
                    extraction_verified=artifact_verification.extraction_verified,
                    expected_outputs_present=artifact_verification.expected_outputs_present,
                    artifact_verified=artifact_verification.artifact_verified,
                    remote_artifact_exists=remote_artifact_exists_flag,
                    final_retrieval_attempted=True,
                    final_retrieval_success=final_retrieval_success,
                    exports_updated=[str(path) for path in mirrored_paths] + console_synced_retry,
                )
                if console_synced_retry:
                    print("Synced retry run outputs to strategy-console storage.")
            except Exception as exc:
                final_retrieval_success = False
                status_store.update(
                    "running",
                    "artifact_download_retry_failed",
                    f"Final artifact retrieval attempt failed: {exc}",
                    run_outcome=run_outcome,
                    failure_reason=failure_reason,
                    remote_artifact_exists=remote_artifact_exists_flag,
                    final_retrieval_attempted=True,
                    final_retrieval_success=False,
                )

        status_store.update(
            "running",
            "destroy_guard_check",
            "Evaluating centralized auto-destroy guard.",
            run_outcome=run_outcome,
            failure_reason=failure_reason,
            remote_state=remote_state,
            artifacts_downloaded=artifact_verification.artifacts_downloaded,
            extraction_verified=artifact_verification.extraction_verified,
            expected_outputs_present=artifact_verification.expected_outputs_present,
            artifact_verified=artifact_verification.artifact_verified,
            instance_exists_at_end=instance_exists_at_end,
            remote_artifact_exists=remote_artifact_exists_flag,
            final_retrieval_attempted=final_retrieval_attempted,
            final_retrieval_success=final_retrieval_success,
        )
        destroy_decision = build_destroy_decision(
            status=status_store.current_payload(),
            args=args,
            instance_exists_at_end=instance_exists_at_end,
            remote_status_path=manifest.remote_status_path,
            remote_tarball_path=manifest.remote_artifact_tarball,
            local_run_dir=local_run_dir,
        )

        if destroy_decision.destroy_allowed and instance_exists_at_end:
            try:
                status_store.update(
                    "running",
                    "destroy",
                    "Destroying VM.",
                    destroy_allowed=True,
                    destroy_reason=destroy_decision.destroy_reason,
                    billing_should_be_stopped=destroy_decision.billing_should_be_stopped,
                    operator_action=destroy_decision.operator_action,
                    recovery_commands=destroy_decision.recovery_commands,
                )
                delete_instance(gcloud_base, args.instance_name, args.zone)
                status_store.update(
                    VM_OUTCOME_DESTROYED,
                    "destroyed",
                    "VM destroyed.",
                    run_outcome=run_outcome,
                    vm_outcome=VM_OUTCOME_DESTROYED,
                    destroy_allowed=True,
                    destroy_reason=destroy_decision.destroy_reason,
                    instance_exists_at_end=False,
                    billing_should_be_stopped=True,
                    operator_action="none",
                    recovery_commands=[],
                    remote_artifact_exists=remote_artifact_exists_flag,
                    final_retrieval_attempted=final_retrieval_attempted,
                    final_retrieval_success=final_retrieval_success,
                )
            except Exception as exc:
                status_store.update(
                    VM_OUTCOME_PRESERVED,
                    "destroy_failed",
                    f"Failed to destroy VM: {exc}",
                    run_outcome=run_outcome,
                    vm_outcome=VM_OUTCOME_PRESERVED,
                    destroy_allowed=False,
                    destroy_reason=f"destroy failed: {exc}",
                    failure_reason=failure_reason or "destroy_failed",
                    instance_exists_at_end=True,
                    billing_should_be_stopped=False,
                    operator_action="inspect VM and download artifacts manually",
                    recovery_commands=destroy_decision.recovery_commands,
                    remote_artifact_exists=remote_artifact_exists_flag,
                    final_retrieval_attempted=final_retrieval_attempted,
                    final_retrieval_success=final_retrieval_success,
                )
                print(f"WARNING: failed to destroy VM automatically: {exc}")
        else:
            vm_outcome = VM_OUTCOME_ALREADY_GONE if instance_exists_at_end is False else VM_OUTCOME_PRESERVED
            message = (
                "VM already gone before final cleanup."
                if vm_outcome == VM_OUTCOME_ALREADY_GONE
                else f"VM preserved for inspection. Auto-destroy blocked: {destroy_decision.destroy_reason}"
            )
            status_store.update(
                vm_outcome,
                "destroy_skipped",
                message,
                run_outcome=run_outcome,
                vm_outcome=vm_outcome,
                destroy_allowed=False,
                destroy_reason=destroy_decision.destroy_reason,
                failure_reason=failure_reason,
                instance_exists_at_end=instance_exists_at_end,
                remote_state=remote_state,
                artifacts_downloaded=artifact_verification.artifacts_downloaded,
                extraction_verified=artifact_verification.extraction_verified,
                expected_outputs_present=artifact_verification.expected_outputs_present,
                artifact_verified=artifact_verification.artifact_verified,
                billing_should_be_stopped=destroy_decision.billing_should_be_stopped,
                operator_action=destroy_decision.operator_action,
                recovery_commands=destroy_decision.recovery_commands,
                remote_artifact_exists=remote_artifact_exists_flag,
                final_retrieval_attempted=final_retrieval_attempted,
                final_retrieval_success=final_retrieval_success,
            )
            if vm_outcome == VM_OUTCOME_PRESERVED:
                print(f"VM preserved: {args.instance_name} in {args.zone}")
            else:
                print("WARNING: VM is already gone and outputs were not verified locally.")
        if artifact_verification.expected_outputs_present and should_sync_results_to_strategy_console(local_run_dir.parent):
            try:
                console_synced_paths = sync_run_to_strategy_console_storage(
                    gcloud_base=gcloud_base,
                    run_dir=local_run_dir,
                )
                status_store.update(
                    status_store.current_payload().get("state", "running"),
                    "console_sync_complete",
                    "Synced verified run outputs to strategy-console storage.",
                    exports_updated=(status_store.current_payload().get("exports_updated") or []) + console_synced_paths,
                )
            except Exception as exc:
                status_store.update(
                    status_store.current_payload().get("state", "running"),
                    "console_sync_warning",
                    f"Console sync failed after local verification: {exc}",
                    exports_updated=status_store.current_payload().get("exports_updated") or [],
                )
        print(f"Latest run pointer: {latest_run_path}")
        print_final_run_summary(status_store.latest_path, local_run_dir)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
