from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.errors import EmptyDataError


def _safe_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _best_quality_flag(group: pd.DataFrame) -> str:
    if "quality_flag" not in group.columns or group.empty:
        return ""
    ranked = group.sort_values(
        by=["profit_factor", "net_pnl", "total_trades"],
        ascending=[False, False, False],
    )
    return str(ranked.iloc[0].get("quality_flag", ""))


def load_refinement_results(outputs_dir: str | Path) -> pd.DataFrame:
    outputs_path = Path(outputs_dir)
    csv_files = sorted(outputs_path.glob("*/*_top_combo_refinement_results_narrow.csv"))

    frames: list[pd.DataFrame] = []
    for csv_path in csv_files:
        try:
            df = pd.read_csv(csv_path)
        except EmptyDataError:
            continue
        if df.empty:
            continue

        df = df.copy()
        df["dataset"] = csv_path.parent.name
        if "strategy_type" not in df.columns:
            stem = csv_path.stem
            df["strategy_type"] = stem.replace("_top_combo_refinement_results_narrow", "")
        if "exit_type" not in df.columns:
            df["exit_type"] = "time_stop"
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    for col in ["profit_factor", "net_pnl", "total_trades"]:
        if col in combined.columns:
            combined[col] = pd.to_numeric(combined[col], errors="coerce")
    return combined


def build_exit_validation_summary(refinement_df: pd.DataFrame) -> pd.DataFrame:
    if refinement_df.empty:
        return pd.DataFrame(
            columns=[
                "dataset",
                "strategy_type",
                "exit_type",
                "rows",
                "best_pf",
                "median_pf",
                "best_net_pnl",
                "median_net_pnl",
                "best_quality_flag",
                "best_strategy_name",
                "avg_trades",
                "median_trades",
            ]
        )

    records: list[dict[str, Any]] = []
    grouped = refinement_df.groupby(["dataset", "strategy_type", "exit_type"], dropna=False)

    for (dataset, strategy_type, exit_type), group in grouped:
        ranked = group.sort_values(
            by=["profit_factor", "net_pnl", "total_trades"],
            ascending=[False, False, False],
        )
        best_row = ranked.iloc[0]
        records.append(
            {
                "dataset": str(dataset),
                "strategy_type": str(strategy_type),
                "exit_type": str(exit_type),
                "rows": int(len(group)),
                "best_pf": float(group["profit_factor"].max()),
                "median_pf": float(group["profit_factor"].median()),
                "best_net_pnl": float(group["net_pnl"].max()),
                "median_net_pnl": float(group["net_pnl"].median()),
                "best_quality_flag": _best_quality_flag(group),
                "best_strategy_name": str(best_row.get("strategy_name", "")),
                "avg_trades": float(group["total_trades"].mean()) if "total_trades" in group.columns else 0.0,
                "median_trades": float(group["total_trades"].median()) if "total_trades" in group.columns else 0.0,
            }
        )

    summary_df = pd.DataFrame(records)
    return summary_df.sort_values(
        by=["dataset", "strategy_type", "best_pf", "best_net_pnl"],
        ascending=[True, True, False, False],
    ).reset_index(drop=True)


def _build_console_lines(summary_df: pd.DataFrame) -> list[str]:
    if summary_df.empty:
        return ["No refinement CSVs found for exit validation."]

    lines = ["Exit validation winners by dataset/family:"]
    for (dataset, strategy_type), group in summary_df.groupby(["dataset", "strategy_type"], sort=True):
        ranked = group.sort_values(by=["best_pf", "best_net_pnl"], ascending=[False, False]).reset_index(drop=True)
        winner = ranked.iloc[0]
        baseline = ranked[ranked["exit_type"] == "time_stop"]

        baseline_pf = _safe_float(baseline.iloc[0]["best_pf"]) if not baseline.empty else None
        baseline_pnl = _safe_float(baseline.iloc[0]["best_net_pnl"]) if not baseline.empty else None
        delta_bits: list[str] = []
        if baseline_pf is not None:
            delta_bits.append(f"PF vs time_stop {float(winner['best_pf']) - baseline_pf:+.2f}")
        if baseline_pnl is not None:
            delta_bits.append(f"PnL vs time_stop {float(winner['best_net_pnl']) - baseline_pnl:+.2f}")

        delta_suffix = f" ({', '.join(delta_bits)})" if delta_bits else ""
        lines.append(
            f"- {dataset} | {strategy_type}: {winner['exit_type']} "
            f"(best_pf={winner['best_pf']:.2f}, best_net_pnl={winner['best_net_pnl']:.2f}){delta_suffix}"
        )

    return lines


def generate_exit_validation_report(
    outputs_dir: str | Path,
    output_file: str | Path | None = None,
) -> pd.DataFrame:
    outputs_path = Path(outputs_dir)
    summary_path = Path(output_file) if output_file else outputs_path / "exit_validation_summary.csv"

    refinement_df = load_refinement_results(outputs_path)
    summary_df = build_exit_validation_summary(refinement_df)
    summary_df.to_csv(summary_path, index=False)

    for line in _build_console_lines(summary_df):
        print(line)

    print(f"\nSaved exit validation summary to {summary_path}")
    return summary_df


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize exit-type performance from refinement result CSVs.")
    parser.add_argument("--outputs-dir", default="Outputs", help="Root Outputs directory containing per-dataset result folders.")
    parser.add_argument("--output-file", default=None, help="Optional CSV path for the generated summary.")
    args = parser.parse_args(argv)

    generate_exit_validation_report(outputs_dir=args.outputs_dir, output_file=args.output_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
