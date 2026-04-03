#!/bin/bash
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
exit "$ENGINE_EXIT"
