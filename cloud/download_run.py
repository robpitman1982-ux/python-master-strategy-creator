#!/usr/bin/env python3
"""
Utility to download strategy run artifacts from Google Cloud Storage.

Usage:
  python download_run.py --latest
  python download_run.py <RUN_ID>
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path

# Matches cloud/launch_gcp_run.py
BUCKET_NAME = "strategy-artifacts-robpitman"
BUCKET_URI = f"gs://{BUCKET_NAME}"
RUNS_DIR = Path("Outputs/runs")


def resolve_gcloud_binary():
    candidates = []
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


GCLOUD_BIN = resolve_gcloud_binary()

def run_command(cmd, check=True):
    return subprocess.run(cmd, text=True, capture_output=True, check=check)

def get_run_timestamp(run_id):
    # Try to parse timestamp from run_id (strategy-sweep-20260325T042617Z)
    try:
        parts = run_id.split("-")
        ts_str = parts[-1]
        return datetime.strptime(ts_str, "%Y%m%dT%H%M%SZ")
    except Exception:
        return datetime.min

def find_latest_run():
    print(f"Checking bucket {BUCKET_URI} for latest run...")
    cmd = [GCLOUD_BIN, "storage", "ls", "--json", f"{BUCKET_URI}/runs/*/artifacts.tar.gz"]
    result = run_command(cmd, check=False)
    if result.returncode != 0:
        print("Failed to list runs in bucket.")
        return None
    
    try:
        items = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("No runs found or invalid output.")
        return None

    if not items:
        print("No artifacts.tar.gz found in bucket.")
        return None

    # Items is a list of dicts. Key 'name' contains full path.
    # Format: runs/<RUN_ID>/artifacts.tar.gz
    runs = []
    for item in items:
        path = item.get("metadata", {}).get("name", "")
        parts = path.split("/")
        if len(parts) >= 2:
            run_id = parts[1]
            runs.append((run_id, get_run_timestamp(run_id)))
    
    if not runs:
        return None

    runs.sort(key=lambda x: x[1], reverse=True)
    return runs[0][0]

def download_run(run_id):
    print(f"Downloading artifacts for run: {run_id}")
    local_dir = RUNS_DIR / run_id
    local_dir.mkdir(parents=True, exist_ok=True)
    
    tar_path = local_dir / "artifacts.tar.gz"
    remote_path = f"{BUCKET_URI}/runs/{run_id}/artifacts.tar.gz"

    print(f"Source: {remote_path}")
    print(f"Dest:   {tar_path}")

    try:
        subprocess.run([GCLOUD_BIN, "storage", "cp", remote_path, str(tar_path)], check=True)
    except subprocess.CalledProcessError:
        print(f"Error: Failed to download {remote_path}")
        return

    print("Extracting artifacts...")
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(local_dir)
    
    print(f"Done. Results available in: {local_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download strategy run artifacts from GCS.")
    parser.add_argument("run_id", nargs="?", help="The Run ID to download (e.g., strategy-sweep-2026...)")
    parser.add_argument("--latest", action="store_true", help="Find and download the most recent run.")

    args = parser.parse_args()

    if args.latest:
        latest_id = find_latest_run()
        if latest_id:
            download_run(latest_id)
        else:
            print("Could not find any runs.")
    elif args.run_id:
        download_run(args.run_id)
    else:
        parser.print_help()
