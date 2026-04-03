#!/usr/bin/env python3
"""
Utility to download strategy run artifacts from Google Cloud Storage.

Usage:
  python cloud/download_run.py <RUN_ID>
  python cloud/download_run.py --latest
  python cloud/download_run.py --merge <RUN_ID_A> <RUN_ID_B>
  python cloud/download_run.py --latest-pair

After downloading, the ultimate leaderboard is automatically regenerated
from all locally available runs in Outputs/runs/.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path

# Matches cloud/launch_gcp_run.py
BUCKET_NAME = "strategy-artifacts-nikolapitman"
BUCKET_URI = f"gs://{BUCKET_NAME}"
RUNS_DIR = Path("Outputs/runs")
MASTER_LEADERBOARD_NAME = "master_leaderboard.csv"
STRATEGY_RETURNS_NAME = "strategy_returns.csv"


def resolve_gcloud_binary() -> str:
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


def run_command(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def get_run_timestamp(run_id: str) -> datetime:
    """Parse timestamp from run_id (e.g. strategy-sweep-a-20260326T120000Z)."""
    try:
        parts = run_id.split("-")
        ts_str = parts[-1]
        return datetime.strptime(ts_str, "%Y%m%dT%H%M%SZ")
    except Exception:
        return datetime.min


def get_instance_prefix(run_id: str) -> str:
    """Extract everything before the timestamp suffix."""
    parts = run_id.split("-")
    # Timestamp is the last part (e.g. 20260326T120000Z)
    if parts and len(parts[-1]) >= 15 and "T" in parts[-1]:
        return "-".join(parts[:-1])
    return run_id


def list_bucket_runs() -> list[str]:
    """Return all run IDs that have artifacts.tar.gz in the bucket."""
    print(f"Checking bucket {BUCKET_URI} for runs...")
    cmd = [GCLOUD_BIN, "storage", "ls", "--json", f"{BUCKET_URI}/runs/*/artifacts.tar.gz"]
    result = run_command(cmd, check=False)
    if result.returncode != 0:
        print("Failed to list runs in bucket.")
        return []
    try:
        items = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    runs = []
    for item in items:
        path = item.get("metadata", {}).get("name", "")
        parts = path.split("/")
        if len(parts) >= 2:
            runs.append(parts[1])
    return runs


def find_latest_run() -> str | None:
    runs = list_bucket_runs()
    if not runs:
        print("No artifacts.tar.gz found in bucket.")
        return None
    runs.sort(key=get_run_timestamp, reverse=True)
    return runs[0]


def find_latest_pair() -> tuple[str, str] | None:
    """Find the two most recent runs with different instance prefixes."""
    runs = list_bucket_runs()
    if not runs:
        print("No runs found in bucket.")
        return None
    runs.sort(key=get_run_timestamp, reverse=True)

    seen_prefixes: dict[str, str] = {}
    for run_id in runs:
        prefix = get_instance_prefix(run_id)
        if prefix not in seen_prefixes:
            seen_prefixes[prefix] = run_id
        if len(seen_prefixes) >= 2:
            break

    if len(seen_prefixes) < 2:
        print(f"Could not find two runs with different prefixes. Found: {list(seen_prefixes.keys())}")
        return None

    run_ids = list(seen_prefixes.values())
    print(f"Found latest pair: {run_ids[0]} + {run_ids[1]}")
    return run_ids[0], run_ids[1]


def download_run(run_id: str) -> Path | None:
    """Download and extract a single run. Returns the local run directory or None on failure."""
    print(f"\nDownloading artifacts for run: {run_id}")
    local_dir = RUNS_DIR / run_id
    local_dir.mkdir(parents=True, exist_ok=True)

    tar_path = local_dir / "artifacts.tar.gz"
    remote_path = f"{BUCKET_URI}/runs/{run_id}/artifacts.tar.gz"

    print(f"  Source: {remote_path}")
    print(f"  Dest:   {tar_path}")

    try:
        subprocess.run([GCLOUD_BIN, "storage", "cp", remote_path, str(tar_path)], check=True)
    except subprocess.CalledProcessError:
        print(f"Error: Failed to download {remote_path}")
        return None

    print("  Extracting...")
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(local_dir)

    print(f"  Done: {local_dir}")
    return local_dir


# ---------------------------------------------------------------------------
# CSV merge helpers (no pandas dependency)
# ---------------------------------------------------------------------------

def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Return (fieldnames, rows) from a CSV file."""
    if not path.exists():
        return [], []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    return fieldnames, rows


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _merge_fieldnames(a: list[str], b: list[str]) -> list[str]:
    """Merge two fieldname lists preserving order and adding new columns."""
    seen = set(a)
    result = list(a)
    for col in b:
        if col not in seen:
            result.append(col)
            seen.add(col)
    return result


def _safe_float(val: str) -> float:
    try:
        return float(str(val).replace(",", "").replace("$", ""))
    except (ValueError, TypeError):
        return 0.0


_QUALITY_PRIORITY: dict[str, int] = {
    "ROBUST": 0,
    "STABLE": 1,
    "MARGINAL": 2,
    "EDGE_DECAYED_OOS": 3,
    "REGIME_DEPENDENT": 4,
    "BROKEN_IN_OOS": 5,
    "LOW_IS_SAMPLE": 6,
    "OOS_HEAVY": 7,
    "NO_TRADES": 8,
}


def _quality_key(row: dict[str, str]) -> int:
    flag = str(row.get("quality_flag", "")).upper().strip()
    return _QUALITY_PRIORITY.get(flag, 99)


def _rank_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Sort rows by quality, then net_pnl desc, then pf desc. Assign rank."""
    pnl_col = next((c for c in ("leader_net_pnl", "net_pnl") if any(c in r for r in rows)), None)
    pf_col = next((c for c in ("leader_pf", "profit_factor") if any(c in r for r in rows)), None)
    rows.sort(
        key=lambda r: (
            _quality_key(r),
            -_safe_float(r.get(pnl_col, "0") if pnl_col else "0"),
            -_safe_float(r.get(pf_col, "0") if pf_col else "0"),
        )
    )
    for i, row in enumerate(rows, start=1):
        row["rank"] = str(i)
    return rows


def find_leaderboard_in_dir(run_dir: Path) -> Path | None:
    """Find the master_leaderboard.csv inside a downloaded run directory."""
    # artifacts/Outputs/master_leaderboard.csv
    candidate = run_dir / "artifacts" / "Outputs" / MASTER_LEADERBOARD_NAME
    if candidate.exists():
        return candidate
    # Direct fallback — master_leaderboard.csv anywhere
    for p in run_dir.rglob(MASTER_LEADERBOARD_NAME):
        return p
    # Fallback: build a virtual master leaderboard from per-dataset family_leaderboard_results.csv
    # These always exist in run outputs even when master_leaderboard.csv is missing
    family_files = list(run_dir.rglob("family_leaderboard_results.csv"))
    if family_files:
        merged = _merge_family_leaderboards(family_files, run_dir)
        if merged:
            return merged
    return None


FAMILY_LEADERBOARD_NAME = "family_leaderboard_results.csv"


def _merge_family_leaderboards(family_files: list[Path], run_dir: Path) -> Path | None:
    """Merge per-dataset family_leaderboard_results.csv files into a single master_leaderboard.csv."""
    all_fields: list[str] = []
    all_rows: list[dict[str, str]] = []
    for fp in family_files:
        fields, rows = _read_csv(fp)
        if not rows:
            continue
        all_fields = _merge_fieldnames(all_fields, fields)
        all_rows.extend(rows)
    if not all_rows:
        return None
    # Write merged file into run directory
    out = run_dir / MASTER_LEADERBOARD_NAME
    _write_csv(out, all_fields, all_rows)
    print(f"  [auto-merge] Built {MASTER_LEADERBOARD_NAME} from {len(family_files)} dataset files ({len(all_rows)} strategies) -> {out}")
    return out


def find_strategy_returns_in_dir(run_dir: Path) -> list[Path]:
    """Find all strategy_returns.csv files inside a downloaded run directory."""
    return list(run_dir.rglob(STRATEGY_RETURNS_NAME))


def merge_runs(run_id_a: str, run_id_b: str) -> Path | None:
    """
    Download both runs, merge their leaderboards and portfolio data.
    Returns the merged output directory or None on failure.
    """
    dir_a = download_run(run_id_a)
    dir_b = download_run(run_id_b)

    if not dir_a or not dir_b:
        print("ERROR: Failed to download one or both runs.")
        return None

    # Build merged run ID
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    merged_run_id = f"merged-{ts}"
    merged_dir = RUNS_DIR / merged_run_id
    merged_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nMerging into: {merged_dir}")

    # --- Merge master leaderboards ---
    lb_a = find_leaderboard_in_dir(dir_a)
    lb_b = find_leaderboard_in_dir(dir_b)

    if not lb_a and not lb_b:
        print("WARNING: No master_leaderboard.csv found in either run.")
    else:
        fields_a, rows_a = _read_csv(lb_a) if lb_a else ([], [])
        fields_b, rows_b = _read_csv(lb_b) if lb_b else ([], [])

        for r in rows_a:
            r.setdefault("source_run_id", run_id_a)
        for r in rows_b:
            r.setdefault("source_run_id", run_id_b)

        merged_fields = _merge_fieldnames(fields_a, fields_b)
        if "source_run_id" not in merged_fields:
            merged_fields.append("source_run_id")
        if "rank" not in merged_fields:
            merged_fields.insert(0, "rank")

        all_rows = rows_a + rows_b
        all_rows = _rank_rows(all_rows)

        out_lb = merged_dir / MASTER_LEADERBOARD_NAME
        _write_csv(out_lb, merged_fields, all_rows)
        print(f"  Merged leaderboard: {len(all_rows)} strategies -> {out_lb}")

        # Also write accepted-only bootcamp leaderboard if accepted_final column exists
        accepted = [r for r in all_rows if str(r.get("accepted_final", "")).strip().lower() in ("true", "1", "yes")]
        if accepted:
            out_boot = merged_dir / "master_leaderboard_bootcamp.csv"
            _write_csv(out_boot, merged_fields, accepted)
            print(f"  Accepted strategies: {len(accepted)} -> {out_boot}")

    # --- Copy per-dataset output dirs from both runs ---
    for run_dir, run_id in [(dir_a, run_id_a), (dir_b, run_id_b)]:
        outputs_src = run_dir / "artifacts" / "Outputs"
        if outputs_src.exists():
            for dataset_dir in outputs_src.iterdir():
                if dataset_dir.is_dir():
                    dest = merged_dir / "Outputs" / dataset_dir.name
                    if not dest.exists():
                        shutil.copytree(dataset_dir, dest)
                        print(f"  Copied dataset outputs: {dataset_dir.name} (from {run_id})")
                    else:
                        print(f"  Skipped duplicate dataset dir: {dataset_dir.name}")

    # --- Write merge manifest ---
    manifest = {
        "merged_run_id": merged_run_id,
        "merged_at": ts,
        "source_runs": [run_id_a, run_id_b],
    }
    (merged_dir / "merge_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\nMerge complete: {merged_dir}")
    return merged_dir


# ---------------------------------------------------------------------------
# Ultimate leaderboard — no pandas, pure CSV
# ---------------------------------------------------------------------------

def aggregate_ultimate_leaderboard(runs_root: Path | None = None) -> None:
    """
    Scan all run directories, find master_leaderboard.csv files,
    concatenate, deduplicate, re-rank, and write ultimate_leaderboard.csv.

    Runs without pandas — pure stdlib CSV operations.
    """
    if runs_root is None:
        runs_root = RUNS_DIR

    output_path = runs_root.parent / "ultimate_leaderboard.csv"

    all_rows: list[dict[str, str]] = []
    all_fields: list[str] = []
    files_found = 0

    for run_dir in sorted(runs_root.iterdir()) if runs_root.exists() else []:
        if not run_dir.is_dir():
            continue
        lb = find_leaderboard_in_dir(run_dir)
        if not lb:
            continue
        fields, rows = _read_csv(lb)
        if not rows:
            continue
        files_found += 1
        all_fields = _merge_fieldnames(all_fields, fields)
        run_id = run_dir.name
        for r in rows:
            r.setdefault("run_id", run_id)
        all_rows.extend(rows)

    if not all_rows:
        print(f"[ultimate_leaderboard] No accepted strategies found (scanned {files_found} run dirs under {runs_root})")
        return

    # Deduplicate by (strategy_type, dataset, leader_strategy_name, best_combo_filter_class_names)
    def _sig(r: dict[str, str]) -> tuple[str, ...]:
        return (
            r.get("strategy_type", ""),
            r.get("dataset", ""),
            r.get("leader_strategy_name", ""),
            r.get("best_combo_filter_class_names", ""),
        )

    pf_col = next((c for c in ("leader_pf", "profit_factor") if any(c in r for r in all_rows)), None)

    # Sort by pf desc before dedup so we keep highest pf per signature
    if pf_col:
        all_rows.sort(key=lambda r: -_safe_float(r.get(pf_col, "0")))

    seen: set[tuple[str, ...]] = set()
    deduped: list[dict[str, str]] = []
    for r in all_rows:
        sig = _sig(r)
        if sig not in seen:
            seen.add(sig)
            deduped.append(r)

    deduped = _rank_rows(deduped)

    if "run_id" not in all_fields:
        all_fields.append("run_id")
    if "rank" not in all_fields:
        all_fields.insert(0, "rank")

    _write_csv(output_path, all_fields, deduped)
    print(f"[ultimate_leaderboard] {len(deduped)} strategies ({len(all_rows) - len(deduped)} duplicates removed) -> {output_path}")

    # --- Bootcamp ultimate leaderboard (accepted-only, bootcamp-ranked) ---
    accepted = [
        r for r in deduped
        if str(r.get("accepted_final", "")).strip().lower() in ("true", "1", "yes")
    ]

    if accepted:
        def _boot_sort_key(r: dict[str, str]) -> float:
            try:
                return -float(r.get("bootcamp_score") or r.get("leader_pf") or 0)
            except (TypeError, ValueError):
                return 0.0
        accepted.sort(key=_boot_sort_key)

        # Re-rank
        for i, r in enumerate(accepted, start=1):
            r["rank"] = str(i)

        boot_output_path = runs_root.parent / "ultimate_leaderboard_bootcamp.csv"
        _write_csv(boot_output_path, all_fields, accepted)
        print(f"[ultimate_leaderboard] Bootcamp: {len(accepted)} accepted strategies -> {boot_output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download strategy run artifacts from GCS and update ultimate leaderboard.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download a specific run
  python cloud/download_run.py strategy-sweep-a-20260326T120000Z

  # Download the most recent run
  python cloud/download_run.py --latest

  # Merge two specific runs
  python cloud/download_run.py --merge strategy-sweep-a-20260326T120000Z strategy-sweep-b-20260326T120001Z

  # Automatically find and merge the two most recent runs (parallel VM workflow)
  python cloud/download_run.py --latest-pair
""",
    )
    parser.add_argument("run_id", nargs="?", help="Run ID to download.")
    parser.add_argument("--latest", action="store_true", help="Find and download the most recent run.")
    parser.add_argument(
        "--merge",
        nargs=2,
        metavar=("RUN_ID_A", "RUN_ID_B"),
        help="Download and merge two runs.",
    )
    parser.add_argument(
        "--latest-pair",
        action="store_true",
        help="Find and merge the two most recent runs with different instance prefixes.",
    )
    parser.add_argument(
        "--no-ultimate",
        action="store_true",
        help="Skip ultimate leaderboard regeneration after download.",
    )

    args = parser.parse_args(argv)

    success = True

    if args.latest_pair:
        pair = find_latest_pair()
        if not pair:
            return 1
        result = merge_runs(pair[0], pair[1])
        success = result is not None

    elif args.merge:
        result = merge_runs(args.merge[0], args.merge[1])
        success = result is not None

    elif args.latest:
        latest_id = find_latest_run()
        if latest_id:
            result = download_run(latest_id)
            success = result is not None
        else:
            print("Could not find any runs.")
            return 1

    elif args.run_id:
        result = download_run(args.run_id)
        success = result is not None

    else:
        parser.print_help()
        return 0

    # Regenerate ultimate leaderboard from all locally available runs
    if success and not args.no_ultimate:
        print()
        try:
            aggregate_ultimate_leaderboard(RUNS_DIR)
        except Exception as exc:
            print(f"[ultimate_leaderboard] WARNING: {exc}")

    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
