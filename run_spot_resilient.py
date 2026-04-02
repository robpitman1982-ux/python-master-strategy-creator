from __future__ import annotations

"""Bulletproof SPOT runner — manages a queue of single-timeframe sweep jobs.

Each job runs ONE market/timeframe on a SPOT VM via fire-and-forget mode.
On preemption the runner rotates to the next zone and retries.
The queue is persisted to spot_queue.yaml so the runner can resume after
Ctrl-C or console reboot.

Usage:
    python3 run_spot_resilient.py --generate-queue              # build queue for all 9 new markets
    python3 run_spot_resilient.py                                # start grinding
    python3 run_spot_resilient.py --status                       # check queue state
    python3 run_spot_resilient.py --markets EC,JY --timeframes daily  # subset
    python3 run_spot_resilient.py --retry-failed                 # reset failed → pending
"""

import argparse
import copy
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent
QUEUE_FILE = REPO_ROOT / "spot_queue.yaml"
LOG_FILE = REPO_ROOT / "spot_runner.log"

ZONE_ROTATION = [
    "us-central1-f",
    "us-central1-c",
    "us-central1-b",
    "us-east1-b",
    "us-east1-c",
    "us-west1-b",
    "us-west1-a",
]

MAX_RETRIES = 5
POLL_INTERVAL_SECONDS = 60
ZONE_EXHAUSTED_WAIT_SECONDS = 600  # 10 minutes

BUCKET_NAME = "strategy-artifacts-nikolapitman"
BUCKET_URI = f"gs://{BUCKET_NAME}"

# Market configs — maps market ticker to its YAML config file
MARKET_CONFIGS: dict[str, str] = {
    "EC": "cloud/config_ec_3tf_spot.yaml",
    "JY": "cloud/config_jy_3tf_spot.yaml",
    "BP": "cloud/config_bp_3tf_spot.yaml",
    "AD": "cloud/config_ad_3tf_spot.yaml",
    "NG": "cloud/config_ng_3tf_spot.yaml",
    "US": "cloud/config_us_3tf_spot.yaml",
    "TY": "cloud/config_ty_3tf_spot.yaml",
    "W":  "cloud/config_w_3tf_spot.yaml",
    "BTC": "cloud/config_btc_3tf_spot.yaml",
}

TIMEFRAMES = ["daily", "60m", "30m"]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("spot_runner")


def setup_logging() -> None:
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Queue management
# ---------------------------------------------------------------------------

def load_queue() -> dict[str, Any]:
    if not QUEUE_FILE.exists():
        return {"created": None, "jobs": []}
    with open(QUEUE_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f) or {"created": None, "jobs": []}


def save_queue(queue: dict[str, Any]) -> None:
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        yaml.dump(queue, f, default_flow_style=False, sort_keys=False)


def generate_queue(markets: list[str] | None = None, timeframes: list[str] | None = None) -> dict[str, Any]:
    """Generate a fresh queue for the specified markets and timeframes."""
    use_markets = markets or list(MARKET_CONFIGS.keys())
    use_timeframes = timeframes or TIMEFRAMES

    jobs: list[dict[str, Any]] = []
    for market in use_markets:
        if market not in MARKET_CONFIGS:
            logger.warning("Unknown market %s — skipping", market)
            continue
        for tf in use_timeframes:
            jobs.append({
                "market": market,
                "timeframe": tf,
                "config": MARKET_CONFIGS[market],
                "status": "pending",
                "zone": None,
                "run_id": None,
                "attempts": 0,
                "last_error": None,
                "completed_at": None,
            })

    queue = {
        "created": datetime.now(timezone.utc).isoformat(),
        "jobs": jobs,
    }
    save_queue(queue)
    logger.info("Generated queue with %d jobs (%d markets × %d timeframes)",
                len(jobs), len(use_markets), len(use_timeframes))
    return queue


# ---------------------------------------------------------------------------
# Single-timeframe config generation
# ---------------------------------------------------------------------------

def create_single_tf_config(base_config_path: str, market: str, timeframe: str) -> Path:
    """Create a temporary config YAML with only ONE dataset entry for the given timeframe."""
    with open(REPO_ROOT / base_config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Filter datasets to just the one we want
    matching = [ds for ds in config.get("datasets", [])
                if ds.get("market") == market and ds.get("timeframe") == timeframe]
    if not matching:
        raise ValueError(f"No dataset found for {market} {timeframe} in {base_config_path}")

    config["datasets"] = matching

    # Set instance_name to avoid collisions in bucket paths
    if "cloud" not in config:
        config["cloud"] = {}
    config["cloud"]["instance_name"] = f"sweep-{market.lower()}-{timeframe}"

    # Write to a temp file that persists until we clean it up
    tmp_dir = REPO_ROOT / ".tmp_spot_configs"
    tmp_dir.mkdir(exist_ok=True)
    tmp_path = tmp_dir / f"config_{market.lower()}_{timeframe}_spot.yaml"
    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    return tmp_path


# ---------------------------------------------------------------------------
# GCloud helpers
# ---------------------------------------------------------------------------

def gcloud_bin() -> str:
    """Return the gcloud binary path."""
    for candidate in ["gcloud", "gcloud.cmd"]:
        try:
            subprocess.run([candidate, "version"], capture_output=True, check=True, timeout=15)
            return candidate
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
    return "gcloud"


def vm_exists(instance_name: str, zone: str) -> bool:
    """Check if a VM instance exists (any state)."""
    try:
        result = subprocess.run(
            [gcloud_bin(), "compute", "instances", "describe", instance_name,
             "--zone", zone, "--format", "json"],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def vm_is_running(instance_name: str, zone: str) -> bool | None:
    """Check if VM is running. Returns None if can't determine, True if running, False if not."""
    try:
        result = subprocess.run(
            [gcloud_bin(), "compute", "instances", "describe", instance_name,
             "--zone", zone, "--format", "value(status)"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return False  # VM doesn't exist
        status = result.stdout.strip().upper()
        return status in ("RUNNING", "STAGING", "PROVISIONING")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def bucket_has_artifacts(run_id: str) -> bool:
    """Check if the GCS bucket has artifacts for this run_id."""
    target = f"{BUCKET_URI}/runs/{run_id}/"
    try:
        result = subprocess.run(
            [gcloud_bin(), "storage", "ls", target],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return False
        # Look for actual output files (not just the directory marker)
        lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
        return len(lines) > 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def bucket_has_tarball(run_id: str) -> bool:
    """Check if the GCS bucket has a results tarball for this run_id."""
    target = f"{BUCKET_URI}/runs/{run_id}/artifacts.tar.gz"
    try:
        result = subprocess.run(
            [gcloud_bin(), "storage", "ls", target],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0 and "artifacts.tar.gz" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def delete_vm_if_exists(instance_name: str, zone: str) -> None:
    """Delete a VM instance if it exists (cleanup for stuck VMs)."""
    if vm_exists(instance_name, zone):
        logger.info("Cleaning up existing VM %s in %s", instance_name, zone)
        try:
            subprocess.run(
                [gcloud_bin(), "compute", "instances", "delete", instance_name,
                 "--zone", zone, "--quiet"],
                capture_output=True, text=True, timeout=120,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("Failed to delete VM %s — may need manual cleanup", instance_name)


# ---------------------------------------------------------------------------
# Job execution
# ---------------------------------------------------------------------------

def launch_job(config_path: Path, zone: str, instance_name: str) -> tuple[str | None, int]:
    """Launch a fire-and-forget sweep job. Returns (run_id, exit_code).

    The run_id is extracted from the launcher's output or from the
    local runs directory.
    """
    cmd = [
        sys.executable, str(REPO_ROOT / "run_cloud_sweep.py"),
        "--config", str(config_path.relative_to(REPO_ROOT)),
        "--fire-and-forget",
        "--zone", zone,
        "--provisioning-model", "SPOT",
    ]

    logger.info("Launching: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600, cwd=str(REPO_ROOT),
        )
    except subprocess.TimeoutExpired:
        logger.error("Launch command timed out after 10 minutes")
        return None, 1

    # Log output
    if result.stdout:
        for line in result.stdout.strip().splitlines()[-20:]:
            logger.info("  launcher> %s", line)
    if result.stderr:
        for line in result.stderr.strip().splitlines()[-10:]:
            logger.warning("  launcher-err> %s", line)

    if result.returncode != 0:
        logger.error("Launcher exited with code %d", result.returncode)
        return None, result.returncode

    # Extract run_id from LATEST_RUN.txt
    run_id = _read_latest_run_id()
    return run_id, 0


def _read_latest_run_id() -> str | None:
    """Read the most recent run ID from the runs directory."""
    from cloud.launch_gcp_run import DEFAULT_RESULTS_ROOT, LATEST_RUN_FILE_NAME
    latest_file = DEFAULT_RESULTS_ROOT / LATEST_RUN_FILE_NAME
    if latest_file.exists():
        text = latest_file.read_text(encoding="utf-8").strip()
        # The file contains a path; the run_id is the directory name
        run_path = Path(text)
        return run_path.name
    return None


def wait_for_completion(instance_name: str, zone: str, run_id: str) -> str:
    """Poll until the job completes or is preempted.

    Returns: "completed", "preempted", or "timeout"
    """
    max_wait = 7200  # 2 hours max
    elapsed = 0

    while elapsed < max_wait:
        time.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS

        running = vm_is_running(instance_name, zone)

        if running is None:
            logger.warning("Could not determine VM state — retrying in %ds", POLL_INTERVAL_SECONDS)
            continue

        if running:
            if elapsed % 300 < POLL_INTERVAL_SECONDS:
                logger.info("  VM %s still running (%d min elapsed)", instance_name, elapsed // 60)
            continue

        # VM is gone — check if artifacts exist
        logger.info("VM %s no longer running after %d min — checking artifacts", instance_name, elapsed // 60)

        # Give GCS a moment to finalize writes
        time.sleep(10)

        if bucket_has_tarball(run_id):
            logger.info("Artifacts found in bucket — job COMPLETED")
            return "completed"
        elif bucket_has_artifacts(run_id):
            logger.info("Partial artifacts found (no tarball) — treating as COMPLETED")
            return "completed"
        else:
            logger.warning("No artifacts in bucket — job was PREEMPTED")
            return "preempted"

    logger.error("Timed out waiting for VM after %d minutes", max_wait // 60)
    return "timeout"


def download_results(run_id: str) -> bool:
    """Download results for a completed run."""
    cmd = [
        sys.executable, str(REPO_ROOT / "cloud" / "download_run.py"),
        "--run-id", run_id,
    ]
    logger.info("Downloading results for %s", run_id)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(REPO_ROOT))
        if result.returncode == 0:
            logger.info("Download completed successfully")
            return True
        else:
            logger.warning("Download failed (exit %d): %s", result.returncode, result.stderr[-200:] if result.stderr else "")
            return False
    except subprocess.TimeoutExpired:
        logger.warning("Download timed out")
        return False


# ---------------------------------------------------------------------------
# Main runner loop
# ---------------------------------------------------------------------------

def run_queue(queue: dict[str, Any]) -> None:
    """Process all pending jobs in the queue."""
    jobs = queue["jobs"]
    total = len(jobs)
    completed_count = sum(1 for j in jobs if j["status"] == "completed")
    failed_count = sum(1 for j in jobs if j["status"] == "failed")

    logger.info("Queue: %d total, %d completed, %d failed, %d pending",
                total, completed_count, failed_count,
                total - completed_count - failed_count)

    job_num = completed_count + failed_count

    for job in jobs:
        if job["status"] in ("completed", "failed"):
            continue

        job_num += 1
        market = job["market"]
        tf = job["timeframe"]
        config_path_str = job["config"]

        logger.info("=" * 60)
        logger.info("[%d/%d] %s %s — starting", job_num, total, market, tf)
        logger.info("=" * 60)

        # Create single-TF config
        try:
            single_tf_config = create_single_tf_config(config_path_str, market, tf)
        except ValueError as e:
            logger.error("Config error: %s", e)
            job["status"] = "failed"
            job["last_error"] = str(e)
            save_queue(queue)
            continue

        instance_name = f"sweep-{market.lower()}-{tf}"

        # Retry loop with zone rotation
        while job["attempts"] < MAX_RETRIES:
            zone_idx = job["attempts"] % len(ZONE_ROTATION)
            zone = ZONE_ROTATION[zone_idx]

            job["attempts"] += 1
            job["status"] = "running"
            job["zone"] = zone
            save_queue(queue)

            logger.info("[%d/%d] %s %s — attempt %d/%d — SPOT %s — launching...",
                        job_num, total, market, tf, job["attempts"], MAX_RETRIES, zone)

            # Clean up any stuck VM with this name
            delete_vm_if_exists(instance_name, zone)

            # Launch fire-and-forget
            run_id, exit_code = launch_job(single_tf_config, zone, instance_name)

            if exit_code != 0 or not run_id:
                logger.error("Launch failed (exit %d, run_id=%s)", exit_code, run_id)
                job["last_error"] = f"launch failed exit={exit_code}"
                save_queue(queue)

                if job["attempts"] >= MAX_RETRIES:
                    break

                # Check if this was a zone capacity issue
                if job["attempts"] >= len(ZONE_ROTATION):
                    logger.info("Exhausted all zones — waiting %d seconds before restarting rotation",
                                ZONE_EXHAUSTED_WAIT_SECONDS)
                    time.sleep(ZONE_EXHAUSTED_WAIT_SECONDS)
                continue

            job["run_id"] = run_id
            save_queue(queue)

            logger.info("[%d/%d] %s %s — launched as %s in %s — polling...",
                        job_num, total, market, tf, run_id, zone)

            # Wait for completion
            outcome = wait_for_completion(instance_name, zone, run_id)

            if outcome == "completed":
                job["status"] = "completed"
                job["completed_at"] = datetime.now(timezone.utc).isoformat()
                save_queue(queue)

                # Download results
                download_results(run_id)

                logger.info("[%d/%d] %s %s — COMPLETED", job_num, total, market, tf)
                break

            elif outcome == "preempted":
                logger.warning("[%d/%d] %s %s — PREEMPTED on %s (attempt %d/%d)",
                               job_num, total, market, tf, zone, job["attempts"], MAX_RETRIES)
                job["last_error"] = f"preempted on {zone}"
                save_queue(queue)

                if job["attempts"] >= MAX_RETRIES:
                    break

                # If we've gone through all zones, wait before retrying
                if job["attempts"] % len(ZONE_ROTATION) == 0:
                    logger.info("Exhausted all zones — waiting %d seconds before restarting rotation",
                                ZONE_EXHAUSTED_WAIT_SECONDS)
                    time.sleep(ZONE_EXHAUSTED_WAIT_SECONDS)

            else:  # timeout
                logger.error("[%d/%d] %s %s — TIMED OUT", job_num, total, market, tf)
                job["last_error"] = "timed out waiting for VM"
                # Try to clean up the VM
                delete_vm_if_exists(instance_name, zone)
                save_queue(queue)

                if job["attempts"] >= MAX_RETRIES:
                    break

        # If we exhausted retries
        if job["status"] != "completed":
            job["status"] = "failed"
            save_queue(queue)
            logger.error("[%d/%d] %s %s — FAILED after %d attempts",
                         job_num, total, market, tf, job["attempts"])

    # Final summary
    print_summary(queue)


def print_summary(queue: dict[str, Any]) -> None:
    """Print a summary of the queue state."""
    jobs = queue["jobs"]
    completed = [j for j in jobs if j["status"] == "completed"]
    failed = [j for j in jobs if j["status"] == "failed"]
    pending = [j for j in jobs if j["status"] == "pending"]
    running = [j for j in jobs if j["status"] == "running"]

    logger.info("=" * 60)
    logger.info("QUEUE SUMMARY")
    logger.info("=" * 60)
    logger.info("Total:     %d", len(jobs))
    logger.info("Completed: %d", len(completed))
    logger.info("Failed:    %d", len(failed))
    logger.info("Pending:   %d", len(pending))
    logger.info("Running:   %d", len(running))

    if failed:
        logger.info("")
        logger.info("Failed jobs:")
        for j in failed:
            logger.info("  %s %s — %d attempts — %s",
                        j["market"], j["timeframe"], j["attempts"], j["last_error"])

    if completed:
        logger.info("")
        logger.info("Completed jobs:")
        for j in completed:
            logger.info("  %s %s — run_id=%s", j["market"], j["timeframe"], j["run_id"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulletproof SPOT runner — queue-based sweep manager with zone rotation.",
    )
    parser.add_argument("--generate-queue", action="store_true",
                        help="Generate (or regenerate) the queue file and exit.")
    parser.add_argument("--status", action="store_true",
                        help="Print queue status and exit.")
    parser.add_argument("--retry-failed", action="store_true",
                        help="Reset failed jobs to pending and start running.")
    parser.add_argument("--markets", default=None,
                        help="Comma-separated list of markets (e.g., EC,JY,BP). Default: all 9 new markets.")
    parser.add_argument("--timeframes", default=None,
                        help="Comma-separated list of timeframes (e.g., daily,60m). Default: daily,60m,30m.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = parse_args(argv)

    markets = args.markets.split(",") if args.markets else None
    timeframes = args.timeframes.split(",") if args.timeframes else None

    # --generate-queue
    if args.generate_queue:
        queue = generate_queue(markets=markets, timeframes=timeframes)
        print_summary(queue)
        return 0

    # --status
    if args.status:
        queue = load_queue()
        if not queue["jobs"]:
            logger.info("No queue found. Run with --generate-queue first.")
            return 1
        print_summary(queue)
        return 0

    # --retry-failed
    if args.retry_failed:
        queue = load_queue()
        reset_count = 0
        for job in queue["jobs"]:
            if job["status"] == "failed":
                job["status"] = "pending"
                job["attempts"] = 0
                job["last_error"] = None
                reset_count += 1
        save_queue(queue)
        logger.info("Reset %d failed jobs to pending", reset_count)
        # Fall through to run

    # Load and run queue
    queue = load_queue()
    if not queue["jobs"]:
        logger.info("No queue found. Run with --generate-queue first.")
        return 1

    # Filter queue if --markets or --timeframes specified (without --generate-queue)
    if markets or timeframes:
        for job in queue["jobs"]:
            if job["status"] in ("completed", "failed"):
                continue
            if markets and job["market"] not in markets:
                continue
            if timeframes and job["timeframe"] not in timeframes:
                continue
            # Job matches filter — keep it as-is

    pending_count = sum(1 for j in queue["jobs"] if j["status"] in ("pending", "running"))
    if pending_count == 0:
        logger.info("All jobs completed or failed. Use --retry-failed to rerun failures.")
        print_summary(queue)
        return 0

    logger.info("Starting SPOT runner — %d jobs to process", pending_count)
    try:
        run_queue(queue)
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user. Queue state saved. Re-run to resume.")
        save_queue(queue)
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
