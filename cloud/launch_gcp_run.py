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


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_ROOT = REPO_ROOT / "cloud_results"
DEFAULT_CONFIG = REPO_ROOT / "cloud" / "config_es_all_timeframes_gcp96.yaml"
DEFAULT_ZONE = "australia-southeast2-a"
DEFAULT_MACHINE_TYPE = "n2-highcpu-96"
DEFAULT_INSTANCE_NAME = "strategy-sweep"
DEFAULT_BOOT_DISK_SIZE = "120GB"
DEFAULT_IMAGE_FAMILY = "ubuntu-2404-lts-amd64"
DEFAULT_IMAGE_PROJECT = "ubuntu-os-cloud"
DEFAULT_BUNDLE_NAME = "input_bundle.tar.gz"
LATEST_RUN_FILE_NAME = "LATEST_RUN.txt"


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
            "local_results_dir": local_results_dir,
            "remote_run_root": remote_run_root,
            "bundle_size_bytes": None,
            "run_outcome": None,
            "vm_outcome": None,
        }

    def update(self, state: str, stage: str, message: str, **extra: Any) -> None:
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
    parser.add_argument("--results-root", default=str(DEFAULT_RESULTS_ROOT.relative_to(REPO_ROOT)))
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--boot-disk-size", default=DEFAULT_BOOT_DISK_SIZE)
    parser.add_argument("--image-family", default=DEFAULT_IMAGE_FAMILY)
    parser.add_argument("--image-project", default=DEFAULT_IMAGE_PROJECT)
    parser.add_argument("--dry-run", action="store_true", help="Run preflight, manifest, and bundle creation only.")
    parser.add_argument("--keep-vm", action="store_true", help="Do not destroy the VM at the end.")
    parser.add_argument("--keep-remote", action="store_true", help="Do not delete remote staging before exit.")
    parser.add_argument(
        "--provisioning-model",
        default="SPOT",
        choices=["SPOT", "STANDARD"],
        help="GCP provisioning model.",
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
    write_status "failed" "bootstrap" "Input bundle missing" 1
    preserve_outputs
    exit 1
fi

if ! sudo apt-get update -qq || ! sudo apt-get install -y -qq python3 python3-pip python3-venv tar >/dev/null 2>&1; then
    write_status "failed" "bootstrap" "Failed installing system packages" 1
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

write_status "running" "validated" "Inputs validated; creating virtual environment"
rm -rf "$RUN_ROOT/venv"
if ! python3 -m venv "$RUN_ROOT/venv"; then
    write_status "failed" "venv" "Failed creating virtual environment" 1
    preserve_outputs
    exit 1
fi
source "$RUN_ROOT/venv/bin/activate"

PIP_EXIT=0
if [ -f "$REPO_DIR/requirements.txt" ]; then
    pip install --quiet -r "$REPO_DIR/requirements.txt" || PIP_EXIT=$?
else
    pip install --quiet numpy pandas pyyaml pytest || PIP_EXIT=$?
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
exit "$ENGINE_EXIT"
"""


def resolve_required_datasets(config: dict[str, Any], repo_root: Path) -> list[DatasetSpec]:
    datasets = config.get("datasets", [])
    if not datasets:
        raise ValueError("Config does not define any datasets.")

    resolved: list[DatasetSpec] = []
    for entry in datasets:
        local_path = Path(str(entry.get("path", "")))
        if not local_path.is_absolute():
            local_path = (repo_root / local_path).resolve()
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
    return RunManifest(
        run_id=run_id,
        created_utc=datetime.now(UTC).isoformat(timespec="seconds"),
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
        "--metadata",
        f"strategy-engine-note={startup_message}",
    ]
    if args.provisioning_model == "SPOT":
        command.append("--instance-termination-action=STOP")
    run_command(command)


def wait_for_ssh(gcloud_base: list[str], instance_name: str, zone: str, timeout_seconds: int = 420) -> None:
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
    required_metadata = ["run_status.json", "manifest.json", "config.yaml"]
    missing_metadata = [name for name in required_metadata if not (extracted_dir / name).exists()]
    if missing_metadata:
        return False, f"Missing preserved metadata: {', '.join(missing_metadata)}."

    logs_dir = extracted_dir / "logs"
    if not logs_dir.exists() or not any(logs_dir.rglob("*")):
        return False, "Preserved logs are missing."

    if remote_state == "completed":
        outputs_dir = extracted_dir / "Outputs"
        if not outputs_dir.exists():
            return False, "Completed run did not preserve Outputs."

        root_result_files = [path.name for path in outputs_dir.iterdir() if path.is_file() and path.name in MEANINGFUL_OUTPUT_FILE_NAMES]
        dataset_dirs = [path for path in outputs_dir.iterdir() if path.is_dir()]
        dataset_result_dirs = []
        for dataset_dir in dataset_dirs:
            has_status = (dataset_dir / "status.json").exists()
            has_result = any((dataset_dir / name).exists() for name in MEANINGFUL_OUTPUT_FILE_NAMES if name != "master_leaderboard.csv")
            if has_status and has_result:
                dataset_result_dirs.append(dataset_dir.name)

        if root_result_files or dataset_result_dirs:
            detail = []
            if root_result_files:
                detail.append(f"root files: {', '.join(sorted(root_result_files))}")
            if dataset_result_dirs:
                detail.append(f"dataset outputs: {', '.join(sorted(dataset_result_dirs))}")
            return True, "Preserved outputs verified (" + "; ".join(detail) + ")."

        return False, "Completed run preserved Outputs, but no meaningful result files were found."

    return True, "Failure artifacts preserved."


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
    verification_passed = run_outcome == "run_completed_verified"
    billing_message = (
        "Billing should now be stopped."
        if vm_outcome == "vm_destroyed" or run_outcome == "dry_run_complete"
        else "Billing may still be active."
    )

    print("=" * 60)
    print("Final Run Summary")
    print("=" * 60)
    print(f"Run ID:              {status.get('run_id', local_run_dir.name)}")
    print(f"Local Results Path:  {local_run_dir}")
    print(f"Run Outcome:         {run_outcome}")
    print(f"VM Outcome:          {vm_outcome}")
    print(f"Verification Passed: {'yes' if verification_passed else 'no'}")
    print(billing_message)
    print("=" * 60)


def create_remote_runner_file(run_dir: Path) -> Path:
    runner_path = run_dir / "remote_runner.sh"
    with runner_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(REMOTE_RUNNER_SCRIPT)
    return runner_path


def launch_remote_runner(
    gcloud_base: list[str],
    instance_name: str,
    zone: str,
    remote_runner_path: str,
    remote_run_root: str,
) -> None:
    clean_runner_path = sanitize_run_token(remote_runner_path)
    clean_run_root = sanitize_run_token(remote_run_root)
    ssh_command(
        gcloud_base,
        instance_name,
        zone,
        f"chmod +x {clean_runner_path} && nohup sudo bash {clean_runner_path} {clean_run_root} > {clean_run_root}/logs/runner_stdout.log 2>&1 < /dev/null &",
    )


def monitor_run(
    *,
    gcloud_base: list[str],
    args: argparse.Namespace,
    manifest: RunManifest,
    status_store: LauncherStatusStore,
) -> dict[str, Any]:
    last_summary = ""
    restart_attempted = False
    while True:
        time.sleep(max(5, args.poll_seconds))
        vm_status = describe_instance_status(gcloud_base, args.instance_name, args.zone)

        if vm_status in {"STOPPED", "TERMINATED"}:
            if restart_attempted:
                raise RuntimeError(f"VM entered {vm_status} twice; leaving instance intact for inspection.")
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

        remote_status = parse_status_json(read_remote_file(gcloud_base, args.instance_name, args.zone, manifest.remote_status_path))
        dataset_statuses = read_remote_dataset_statuses(gcloud_base, args.instance_name, args.zone, manifest.remote_run_root)
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
            return remote_status


def print_manifest_summary(manifest: RunManifest) -> None:
    print("=" * 60)
    print("GCP Strategy Engine Launcher")
    print("=" * 60)
    print(f"Run ID:      {manifest.run_id}")
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
    args = parse_args(argv)
    config_path = absolute_repo_path(args.config)
    results_root = absolute_repo_path(args.results_root)
    preflight = run_preflight(config_path, args.project)
    print_preflight_summary(preflight)

    gcloud_base = build_gcloud_base(preflight.gcloud_bin, preflight.project_id)
    config = load_config(config_path)
    datasets = preflight.datasets
    remote_config = build_remote_config(config, datasets)

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
    )

    manifest_path = local_run_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(asdict(manifest), indent=2), encoding="utf-8")
    runner_path = create_remote_runner_file(local_run_dir)
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
            "dry_run_complete",
            "dry_run",
            "Dry run completed after preflight, manifest creation, and bundle creation. No VM was created.",
            run_outcome="dry_run_complete",
        )
        print(f"Dry run complete. Manifest and bundle are ready in {local_run_dir}")
        print(f"Latest run pointer: {latest_run_path}")
        print_final_run_summary(status_store.latest_path, local_run_dir)
        return 0

    destroy_allowed = not args.keep_vm
    exit_code = 0
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

        status_store.update("running", "upload", "Uploading input bundle and manifest.")
        scp_to_remote(gcloud_base, args.instance_name, args.zone, bundle_path, remote["bundle"])
        scp_to_remote(gcloud_base, args.instance_name, args.zone, manifest_path, f"{remote['run_root']}/manifest.json")
        scp_to_remote(gcloud_base, args.instance_name, args.zone, runner_path, remote["runner"])

        status_store.update("running", "validate_remote", "Validating remote upload payloads before engine start.")
        ssh_command(
            gcloud_base,
            args.instance_name,
            args.zone,
            (
                f"test -s {remote['bundle']} && "
                f"test -s {remote['run_root']}/manifest.json && "
                f"test -s {remote['runner']}"
            ),
        )

        status_store.update("running", "remote_start", "Starting remote orchestration script.")
        launch_remote_runner(
            gcloud_base,
            args.instance_name,
            args.zone,
            remote["runner"],
            remote["run_root"],
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
            destroy_allowed = False
            status_store.update(
                "vm_preserved_for_inspection",
                "remote_start_integrity_failed",
                "Remote runner launch could not be confirmed. VM preserved for inspection.",
                remote_restart_guard=runner_guard,
                vm_outcome="vm_preserved_for_inspection",
            )
            print("Remote runner launch could not be confirmed. VM preserved for inspection.")
            return 1
        status_store.update(
            "running",
            "remote_start_verified",
            "Remote orchestration launch confirmed.",
            remote_restart_guard=runner_guard,
        )

        remote_status = monitor_run(
            gcloud_base=gcloud_base,
            args=args,
            manifest=manifest,
            status_store=status_store,
        )

        remote_state = str(remote_status.get("state", "failed")).lower()
        status_store.update("running", "download", "Downloading preserved artifact tarball.", remote_status=remote_status)

        tarball_local = local_run_dir / "artifacts.tar.gz"
        extracted_dir = local_run_dir / "artifacts"
        try:
            artifact_result = download_and_extract_artifacts(
                gcloud_base,
                args.instance_name,
                args.zone,
                manifest.remote_artifact_tarball,
                tarball_local,
                extracted_dir,
            )
        except Exception as exc:
            destroy_allowed = False
            status_store.update(
                "vm_preserved_for_inspection",
                "artifact_download_failed",
                f"Artifact download or extraction failed: {exc}",
                vm_outcome="vm_preserved_for_inspection",
            )
            print(f"Artifact download or extraction failed. VM preserved for inspection: {exc}")
            return 1
        verified, verification_message = verify_preserved_results(extracted_dir, remote_state)
        if verified and remote_state == "completed":
            status_store.update(
                "run_completed_verified",
                "verification_passed",
                verification_message,
                extracted_dir=str(extracted_dir),
                artifacts_tarball_size_bytes=artifact_result.tarball_size_bytes,
                run_outcome="run_completed_verified",
            )
        elif verified:
            status_store.update(
                "remote_failed_artifacts_preserved",
                "verification_passed_remote_failed",
                verification_message,
                extracted_dir=str(extracted_dir),
                artifacts_tarball_size_bytes=artifact_result.tarball_size_bytes,
                run_outcome="remote_failed_artifacts_preserved",
            )
        else:
            status_store.update(
                "run_completed_unverified",
                "verification_failed",
                verification_message,
                extracted_dir=str(extracted_dir),
                artifacts_tarball_size_bytes=artifact_result.tarball_size_bytes,
                run_outcome="run_completed_unverified",
            )

        if not verified:
            destroy_allowed = False

        if not args.keep_remote:
            ssh_command(gcloud_base, args.instance_name, args.zone, f"rm -rf {remote['run_root']}", check=False)

        if remote_state != "completed":
            print("Remote run finished with a failure state. Preserved artifacts were downloaded for inspection.")
            exit_code = 1
            destroy_allowed = False
        else:
            print(f"Run complete. Preserved artifacts are in {local_run_dir}")
    finally:
        if destroy_allowed:
            try:
                status_store.update("running", "destroy", "Destroying VM.")
                delete_instance(gcloud_base, args.instance_name, args.zone)
                status_store.update("vm_destroyed", "destroyed", "VM destroyed.", vm_outcome="vm_destroyed")
            except Exception as exc:
                status_store.update("vm_preserved_for_inspection", "destroy_failed", f"Failed to destroy VM: {exc}", vm_outcome="vm_preserved_for_inspection")
                print(f"WARNING: failed to destroy VM automatically: {exc}")
        else:
            status_store.update("vm_preserved_for_inspection", "destroy_skipped", "VM preserved for inspection.", vm_outcome="vm_preserved_for_inspection")
            print(f"VM preserved: {args.instance_name} in {args.zone}")
        print(f"Latest run pointer: {latest_run_path}")
        print_final_run_summary(status_store.latest_path, local_run_dir)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
