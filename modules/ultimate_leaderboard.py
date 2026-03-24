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

# ---------------------------------------------------------------------------
# Quality-flag priority for ranking
# ---------------------------------------------------------------------------

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


def _quality_sort_key(flag: Any) -> int:
    return _QUALITY_PRIORITY.get(str(flag).upper().strip(), 99)


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
        output_path = storage_root / "ultimate_leaderboard.csv"

    discovered_at = datetime.now(UTC).isoformat(timespec="seconds")

    # ------------------------------------------------------------------
    # 1. Collect all leaderboard rows
    # ------------------------------------------------------------------
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

        # Filter to accepted only
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

    combined = pd.concat(all_frames, ignore_index=True)
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
    combined["_quality_sort"] = combined.get("quality_flag", pd.Series("", index=combined.index)).apply(_quality_sort_key)

    pnl_col = "leader_net_pnl" if "leader_net_pnl" in combined.columns else (
        "net_pnl" if "net_pnl" in combined.columns else None
    )
    pnl_series = pd.to_numeric(combined[pnl_col], errors="coerce").fillna(0) if pnl_col else pd.Series(0, index=combined.index)
    pf_series = pd.to_numeric(combined[pf_col], errors="coerce").fillna(0) if pf_col else pd.Series(0, index=combined.index)

    combined = combined.assign(_pnl_sort=pnl_series, _pf_sort2=pf_series)
    combined = combined.sort_values(
        ["_quality_sort", "_pnl_sort", "_pf_sort2"],
        ascending=[True, False, False],
    )
    combined = combined.reset_index(drop=True)
    if "rank" in combined.columns:
        combined = combined.drop(columns=["rank"])
    combined.insert(0, "rank", combined.index + 1)

    # Drop internal sort columns
    combined = combined.drop(columns=[c for c in combined.columns if c.startswith("_")])

    # ------------------------------------------------------------------
    # 4. Write
    # ------------------------------------------------------------------
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output_path, index=False)

    if verbose:
        print(
            f"\nUltimate leaderboard: {len(combined)} strategies "
            f"({duplicates_removed} duplicates removed from {total_raw} raw rows)"
        )
        print(f"Written to: {output_path}")
        cols_preview = ["rank", "strategy_type", "dataset", "quality_flag", pf_col or "—", "run_id"]
        preview_cols = [c for c in cols_preview if c in combined.columns]
        if preview_cols:
            print(combined[preview_cols].head(10).to_string(index=False))

    return combined


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate accepted strategies from all runs into ultimate_leaderboard.csv"
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
