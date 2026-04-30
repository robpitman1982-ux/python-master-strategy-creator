#!/usr/bin/env python3
"""Local sweep runner — runs the strategy engine directly on local hardware.

Replaces cloud runners (GCP SPOT, DigitalOcean). No Docker, no GCS, no VM
provisioning. Reads a sweep config YAML and calls master_strategy_engine.py.

Usage:
    # Run a single-market sweep
    python run_local_sweep.py --config configs/local_sweeps/ES_all_timeframes.yaml

    # Dry run — show what would be swept without running
    python run_local_sweep.py --config configs/local_sweeps/ES_all_timeframes.yaml --dry-run

    # Override data directory
    python run_local_sweep.py --config my_config.yaml --data-dir /data/market_data/dukascopy/
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

from modules.instrument_universe import InstrumentUniverseError, validate_sweep_config


def load_sweep_config(config_path: str) -> dict:
    """Load and validate a sweep config YAML."""
    path = Path(config_path)
    if not path.exists():
        print(f"ERROR: Config not found: {path}")
        sys.exit(1)
    with open(path) as f:
        cfg = yaml.safe_load(f)
    return cfg


def build_engine_config(sweep_cfg: dict, data_dir: str | None = None) -> dict:
    """Build an engine-compatible config dict from the sweep config.

    The sweep config may have a 'sweep' section with metadata (name, dirs)
    that we strip out, passing only engine-relevant keys through.
    """
    engine_cfg: dict = {}

    # Datasets
    datasets = sweep_cfg.get("datasets", [])
    if data_dir:
        # Override data directory for all dataset paths
        for ds in datasets:
            filename = Path(ds["path"]).name
            ds["path"] = str(Path(data_dir) / filename)
    engine_cfg["datasets"] = datasets

    # Strategy types
    engine_cfg["strategy_types"] = sweep_cfg.get("strategy_types", "all")

    # Engine settings
    if "engine" in sweep_cfg:
        engine_cfg["engine"] = sweep_cfg["engine"]

    # Pipeline settings
    if "pipeline" in sweep_cfg:
        engine_cfg["pipeline"] = sweep_cfg["pipeline"]

    # Promotion gate
    if "promotion_gate" in sweep_cfg:
        engine_cfg["promotion_gate"] = sweep_cfg["promotion_gate"]

    # Leaderboard
    if "leaderboard" in sweep_cfg:
        engine_cfg["leaderboard"] = sweep_cfg["leaderboard"]

    # Output directory
    sweep_meta = sweep_cfg.get("sweep", {})
    output_dir = sweep_meta.get("output_dir") or sweep_cfg.get("output_dir", "Outputs")
    run_name = sweep_meta.get("name", "")
    if run_name:
        engine_cfg["output_dir"] = str(Path(output_dir) / run_name)
    else:
        engine_cfg["output_dir"] = output_dir

    return engine_cfg


def run_sweep(config_path: str, data_dir: str | None = None, dry_run: bool = False) -> int:
    """Run the strategy engine with the given sweep config.

    Returns the engine exit code (0 = success).
    """
    sweep_cfg = load_sweep_config(config_path)
    engine_cfg = build_engine_config(sweep_cfg, data_dir)

    sweep_meta = sweep_cfg.get("sweep", {})
    run_name = sweep_meta.get("name", Path(config_path).stem)

    # Summary
    datasets = engine_cfg.get("datasets", [])
    strategy_types = engine_cfg.get("strategy_types", "all")
    output_dir = engine_cfg.get("output_dir", "Outputs")
    pipeline = engine_cfg.get("pipeline", {})
    max_workers = pipeline.get("max_workers_sweep", "default")

    print("=" * 60)
    print(f"LOCAL SWEEP: {run_name}")
    print(f"  Config:     {config_path}")
    print(f"  Output:     {output_dir}")
    print(f"  Workers:    {max_workers}")
    print(f"  Strategies: {strategy_types}")
    print(f"  Datasets:   {len(datasets)}")
    for ds in datasets:
        print(f"    - {ds.get('market', '?')} {ds.get('timeframe', '?')}: {ds['path']}")
    print("=" * 60)

    try:
        universe = validate_sweep_config(
            engine_cfg,
            data_dir=None,
            require_existing_data=not dry_run,
        )
        print(f"  Universe:   {universe}")
    except InstrumentUniverseError as exc:
        print(f"\nERROR: Instrument universe preflight failed:\n  {exc}")
        return 1

    if dry_run:
        print("\n[DRY RUN] Would run engine with the above config. Exiting.")
        return 0

    # Validate data files exist
    missing = []
    for ds in datasets:
        p = Path(ds["path"])
        if not p.exists():
            # Try relative to repo root
            repo_root = Path(__file__).resolve().parent
            if not (repo_root / p).exists():
                missing.append(str(p))
    if missing:
        print(f"\nERROR: Missing data files:")
        for m in missing:
            print(f"  {m}")
        print("\nRun the converter first: python scripts/convert_tds_to_engine.py")
        return 1

    # Write temporary engine config
    tmp_config = Path(output_dir) / f".sweep_config_{run_name}.yaml"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    with open(tmp_config, "w") as f:
        yaml.dump(engine_cfg, f, default_flow_style=False)

    # Run the engine
    start_time = time.time()
    print(f"\nStarting engine at {datetime.now().strftime('%H:%M:%S')}...")

    repo_root = Path(__file__).resolve().parent
    engine_script = repo_root / "master_strategy_engine.py"

    cmd = [sys.executable, str(engine_script), "--config", str(tmp_config)]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(cmd, env=env, cwd=str(repo_root))

    elapsed = time.time() - start_time
    hours = int(elapsed // 3600)
    mins = int((elapsed % 3600) // 60)
    secs = int(elapsed % 60)

    print(f"\n{'=' * 60}")
    if result.returncode == 0:
        print(f"SWEEP COMPLETE: {run_name}")
    else:
        print(f"SWEEP FAILED: {run_name} (exit code {result.returncode})")
    print(f"  Elapsed: {hours}h {mins}m {secs}s")
    print(f"  Output:  {output_dir}")
    print(f"{'=' * 60}")

    # Clean up temp config
    try:
        tmp_config.unlink()
    except OSError:
        pass

    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run strategy sweep on local hardware"
    )
    parser.add_argument("--config", type=str, required=True,
                        help="Path to sweep config YAML")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="Override data directory for all dataset paths")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be swept without running")
    args = parser.parse_args()

    exit_code = run_sweep(args.config, args.data_dir, args.dry_run)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
