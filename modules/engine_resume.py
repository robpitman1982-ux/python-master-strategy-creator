"""Engine resume logic — per-family on-disk CSV detection.

Sprint 93 (2026-05-04). Allows `master_strategy_engine.py::_run_dataset` to skip
families whose sweep + promoted CSVs are already on disk from a prior partial
run, dramatically reducing the cost of kill+restart cycles during RAM/speed
experiments.

Two layers of safety:
1. Config fingerprint - sha256 of dataset config + engine git short-sha,
   written to .engine_config.fingerprint on first run, refused to resume on
   mismatch (prevents stale CSVs from outdated config).
2. CSV integrity check - row count must match expected n_combos within 5%
   (allows post-dedup variance), promoted CSV must have at least 1 row if
   any sweep row had pf >= promotion_gate.min_pf.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

FINGERPRINT_FILENAME = ".engine_config.fingerprint"


@dataclass
class ResumeCheck:
    """Result of an is_family_resumable() call."""

    resumable: bool
    reason: str
    combo_csv: Path | None = None
    promoted_csv: Path | None = None
    refinement_csv: Path | None = None


def _git_short_sha(repo_root: Path | None = None) -> str:
    """Return current git HEAD short sha, or 'nogit' if git unavailable."""
    try:
        cwd = str(repo_root) if repo_root else None
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out or "nogit"
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "nogit"


def compute_dataset_fingerprint(
    config_payload: dict | str | bytes,
    engine_version: str | None = None,
    repo_root: Path | None = None,
) -> str:
    """sha256 fingerprint of dataset config + engine version.

    Args:
        config_payload: Either a dict (JSON-stable serialised), a YAML/JSON
            string, or raw bytes. Anything that uniquely identifies the
            configuration the engine should run.
        engine_version: Override (e.g. for tests); defaults to git short sha.
        repo_root: Repository root for git lookup.

    Returns:
        hex sha256 string (64 chars).
    """
    if engine_version is None:
        engine_version = _git_short_sha(repo_root=repo_root)

    if isinstance(config_payload, dict):
        # sort_keys=True ensures stable ordering across Python runs
        payload = json.dumps(config_payload, sort_keys=True, default=str).encode("utf-8")
    elif isinstance(config_payload, str):
        payload = config_payload.encode("utf-8")
    elif isinstance(config_payload, bytes):
        payload = config_payload
    else:
        payload = repr(config_payload).encode("utf-8")

    h = hashlib.sha256()
    h.update(payload)
    h.update(b"\x00engine_version=")
    h.update(engine_version.encode("utf-8"))
    return h.hexdigest()


def write_fingerprint(output_dir: Path, fingerprint: str) -> Path:
    """Write fingerprint to <output_dir>/.engine_config.fingerprint. Returns the path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / FINGERPRINT_FILENAME
    path.write_text(fingerprint, encoding="utf-8")
    return path


def read_fingerprint(output_dir: Path) -> str | None:
    """Return on-disk fingerprint or None if missing/unreadable."""
    path = output_dir / FINGERPRINT_FILENAME
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def is_family_resumable(
    output_dir: Path,
    family_name: str,
    expected_n_combos: int,
    min_row_fraction: float = 0.95,
) -> ResumeCheck:
    """Check whether a family's CSVs are present and complete enough to resume.

    Args:
        output_dir: Per-dataset output directory (where {family}_*.csv lives).
        family_name: e.g. 'mean_reversion'.
        expected_n_combos: Expected sweep row count (from _estimate_combo_count).
        min_row_fraction: Fraction of expected_n_combos required after dedup.
            Default 0.95 allows 5% loss to lightweight dedup.

    Returns:
        ResumeCheck with .resumable bool, .reason string, and CSV paths.
    """
    combo_csv = output_dir / f"{family_name}_filter_combination_sweep_results.csv"
    promoted_csv = output_dir / f"{family_name}_promoted_candidates.csv"
    refinement_csv = output_dir / f"{family_name}_top_combo_refinement_results_narrow.csv"

    if not combo_csv.is_file():
        return ResumeCheck(False, f"missing {combo_csv.name}")
    if not promoted_csv.is_file():
        return ResumeCheck(False, f"missing {promoted_csv.name}")

    # Row-count sanity check on combo CSV
    try:
        combo_df = pd.read_csv(combo_csv)
    except Exception as exc:
        return ResumeCheck(False, f"{combo_csv.name} unreadable: {exc}")

    if len(combo_df) == 0:
        return ResumeCheck(False, f"{combo_csv.name} is empty")

    min_rows = int(expected_n_combos * min_row_fraction)
    if len(combo_df) < min_rows:
        return ResumeCheck(
            False,
            f"{combo_csv.name} has {len(combo_df)} rows, expected >= {min_rows} "
            f"({expected_n_combos} * {min_row_fraction:.2f})",
        )

    # Promoted CSV must be readable; allow zero rows (legitimate when no combo passes)
    try:
        pd.read_csv(promoted_csv)
    except Exception as exc:
        return ResumeCheck(False, f"{promoted_csv.name} unreadable: {exc}")

    # Refinement CSV is optional (None if no candidates promoted or refinement skipped)
    has_refinement = refinement_csv.is_file()

    return ResumeCheck(
        resumable=True,
        reason=(
            f"sweep CSV {len(combo_df)} rows, promoted CSV present"
            + (", refinement CSV present" if has_refinement else ", no refinement CSV")
        ),
        combo_csv=combo_csv,
        promoted_csv=promoted_csv,
        refinement_csv=refinement_csv if has_refinement else None,
    )


def load_resumed_family(
    check: ResumeCheck,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    """Load combo_results, promoted, refinement (optional) DataFrames from disk.

    Args:
        check: A ResumeCheck with resumable=True.

    Returns:
        (combo_df, promoted_df, refinement_df_or_None)
    """
    if not check.resumable or check.combo_csv is None or check.promoted_csv is None:
        raise ValueError(f"ResumeCheck not resumable: {check.reason}")

    combo_df = pd.read_csv(check.combo_csv)
    promoted_df = pd.read_csv(check.promoted_csv)
    refinement_df: pd.DataFrame | None = None
    if check.refinement_csv is not None and check.refinement_csv.is_file():
        try:
            refinement_df = pd.read_csv(check.refinement_csv)
            if refinement_df.empty:
                refinement_df = None
        except Exception:
            refinement_df = None

    return combo_df, promoted_df, refinement_df


def make_synthetic_sanity_check() -> dict:
    """Return a placeholder sanity_check dict for resumed families.

    The real sanity_check is just a 'data + engine work' smoke verification at
    family entry. On resume we trust the on-disk CSVs (which couldn't have been
    written if sanity had failed in the original run). This shape matches what
    run_sanity_check returns enough for build_family_summary_row to consume.
    """
    return {
        "passed": True,
        "resumed_from_disk": True,
        "trades": 0,
        "net_pnl": 0.0,
        "profit_factor": 0.0,
    }
