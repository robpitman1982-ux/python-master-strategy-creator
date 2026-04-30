"""
Ultimate Leaderboard — Cross-Run Strategy Aggregator

Scans all run directories under strategy_console_storage/runs/,
extracts accepted strategies, deduplicates by parameter signature,
and maintains one cumulative leaderboard file.

Usage:
    python -m modules.ultimate_leaderboard [--storage-root PATH] [--output PATH]
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from modules.leaderboard_ranking import sort_aggregate_leaderboard

FUTURES_ULTIMATE_FILENAME = "ultimate_leaderboard_FUTURES.csv"
LEGACY_ULTIMATE_FILENAME = "ultimate_leaderboard.csv"
CFD_ULTIMATE_FILENAME = "ultimate_leaderboard_cfd.csv"


def _find_leaderboard_files(runs_root: Path, *, verbose: bool = False) -> list[tuple[str, Path]]:
    """Return (run_id, csv_path) pairs for all leaderboard CSVs under runs_root."""
    pairs: list[tuple[str, Path]] = []

    if not runs_root.exists():
        return pairs

    for run_dir in runs_root.iterdir():
        if not run_dir.is_dir():
            continue
        run_id = run_dir.name

        # Preferred: master_leaderboard.csv directly under artifacts/Outputs
        master = run_dir / "artifacts" / "Outputs" / "master_leaderboard.csv"
        if master.exists():
            if verbose:
                print(f"  [master] {run_id}: {master}")
            pairs.append((run_id, master))
            continue

        # Fall back: per-dataset family_leaderboard_results.csv files
        fallback_files = list((run_dir / "artifacts" / "Outputs").glob("*/family_leaderboard_results.csv")) if (
            run_dir / "artifacts" / "Outputs"
        ).exists() else []

        for fb in fallback_files:
            if verbose:
                print(f"  [family] {run_id}: {fb}")
            pairs.append((run_id, fb))

    return pairs


def _build_signature(row: "Any") -> tuple[str, ...]:
    """Build a deduplication key from strategy-identifying columns."""
    def _get(col: str) -> str:
        val = row.get(col, "") if isinstance(row, dict) else getattr(row, col, "")
        return str(val or "").strip()

    return (
        _get("strategy_type"),
        _get("dataset"),
        _get("leader_strategy_name"),
        _get("best_combo_filter_class_names"),
    )


def _looks_like_cfd_row(row: "Any") -> bool:
    dataset = str(row.get("dataset", "") if isinstance(row, dict) else getattr(row, "dataset", ""))
    source_file = str(row.get("source_file", "") if isinstance(row, dict) else getattr(row, "source_file", ""))
    text = f"{dataset} {source_file}".lower()
    return "dukascopy" in text or "/cfds/" in text or "\\cfds\\" in text


def aggregate_ultimate_leaderboard(
    storage_root: Path | None = None,
    output_path: Path | None = None,
    *,
    verbose: bool = False,
) -> "Any":
    """Scan all runs, extract accepted strategies, deduplicate, rank, and write CSV.

    Returns a pandas DataFrame (empty if no accepted strategies found).
    """
    import pandas as pd

    from paths import CONSOLE_STORAGE_ROOT

    if storage_root is None:
        storage_root = CONSOLE_STORAGE_ROOT.expanduser()

    runs_root = storage_root / "runs"

    if output_path is None:
        output_path = storage_root / FUTURES_ULTIMATE_FILENAME

    discovered_at = datetime.now(UTC).isoformat(timespec="seconds")

    combined = collect_accepted_ultimate_rows(
        storage_root=storage_root,
        discovered_at=discovered_at,
        verbose=verbose,
    )
    if combined.empty:
        if verbose:
            print(f"No accepted strategies found across {runs_root}")
        return pd.DataFrame()
    total_raw = len(combined)

    # ------------------------------------------------------------------
    # 2. Deduplicate — keep highest leader_pf per signature
    # ------------------------------------------------------------------
    combined["_sig"] = combined.apply(_build_signature, axis=1).apply(str)

    pf_col = "leader_pf" if "leader_pf" in combined.columns else (
        "profit_factor" if "profit_factor" in combined.columns else None
    )

    if pf_col:
        combined["_pf_sort"] = pd.to_numeric(combined[pf_col], errors="coerce").fillna(0)
        combined = combined.sort_values("_pf_sort", ascending=False)

    combined = combined.drop_duplicates(subset="_sig", keep="first")
    duplicates_removed = total_raw - len(combined)

    # ------------------------------------------------------------------
    # 3. Rank
    # ------------------------------------------------------------------
    combined = sort_aggregate_leaderboard(combined)
    combined = combined.reset_index(drop=True)
    if "rank" in combined.columns:
        combined = combined.drop(columns=["rank"])
    combined.insert(0, "rank", combined.index + 1)

    # ------------------------------------------------------------------
    # 4. Write
    # ------------------------------------------------------------------
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_targets: list[Path] = [output_path]
    if output_path.name == FUTURES_ULTIMATE_FILENAME:
        output_targets.append(output_path.parent / LEGACY_ULTIMATE_FILENAME)
    elif output_path.name == LEGACY_ULTIMATE_FILENAME:
        output_targets.append(output_path.parent / FUTURES_ULTIMATE_FILENAME)

    written_paths: list[Path] = []
    seen: set[Path] = set()
    for target in output_targets:
        if target in seen:
            continue
        seen.add(target)
        combined.to_csv(target, index=False)
        written_paths.append(target)

    if combined.apply(_looks_like_cfd_row, axis=1).all():
        cfd_output_path = output_path.parent / CFD_ULTIMATE_FILENAME
        combined.to_csv(cfd_output_path, index=False)
        if verbose:
            print(f"CFD ultimate leaderboard: {len(combined)} strategies -> {cfd_output_path}")

    if verbose:
        print(
            f"\nUltimate leaderboard: {len(combined)} strategies "
            f"({duplicates_removed} duplicates removed from {total_raw} raw rows)"
        )
        print(f"Written to: {written_paths[0]}")
        if len(written_paths) > 1:
            print("Alias copies:")
            for alias_path in written_paths[1:]:
                print(f"  {alias_path}")
        cols_preview = ["rank", "strategy_type", "dataset", "quality_flag", pf_col or "—", "run_id"]
        preview_cols = [c for c in cols_preview if c in combined.columns]
        if preview_cols:
            print(combined[preview_cols].head(10).to_string(index=False))

    return combined


def collect_accepted_ultimate_rows(
    storage_root: Path | None = None,
    *,
    discovered_at: str | None = None,
    verbose: bool = False,
) -> "Any":
    """Collect raw accepted rows from all run leaderboards before dedupe/ranking."""
    import pandas as pd

    from paths import CONSOLE_STORAGE_ROOT

    if storage_root is None:
        storage_root = CONSOLE_STORAGE_ROOT.expanduser()

    runs_root = storage_root / "runs"
    discovered_at = discovered_at or datetime.now(UTC).isoformat(timespec="seconds")

    all_frames: list[pd.DataFrame] = []
    files_found = 0

    for run_id, csv_path in _find_leaderboard_files(runs_root, verbose=verbose):
        try:
            df = pd.read_csv(csv_path)
        except Exception as exc:
            if verbose:
                print(f"  [skip] {csv_path}: {exc}")
            continue

        files_found += 1

        if "accepted_final" in df.columns:
            accepted_mask = df["accepted_final"].apply(
                lambda v: str(v).strip().lower() in ("true", "1", "yes")
            )
            df = df[accepted_mask]

        if df.empty:
            continue

        df = df.copy()
        df["run_id"] = run_id
        df["source_file"] = str(csv_path)
        df["discovered_at"] = discovered_at
        all_frames.append(df)

    if not all_frames:
        if verbose:
            print(f"No accepted strategies found (scanned {files_found} files across {runs_root})")
        return pd.DataFrame()

    return pd.concat(all_frames, ignore_index=True)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate accepted strategies from all runs into the canonical ultimate leaderboard CSV"
    )
    parser.add_argument("--storage-root", type=Path, default=None, help="Override storage root path")
    parser.add_argument("--output", type=Path, default=None, help="Override output CSV path")
    parser.add_argument("--verbose", action="store_true", help="Print detailed scan info")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = aggregate_ultimate_leaderboard(
        storage_root=args.storage_root,
        output_path=args.output,
        verbose=True if args.verbose else True,  # always verbose in CLI mode
    )
    import pandas as pd
    if isinstance(result, pd.DataFrame) and result.empty:
        print("No accepted strategies found.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
