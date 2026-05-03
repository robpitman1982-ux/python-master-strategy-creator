#!/usr/bin/env python3
"""Render a single-page PDF summary of a portfolio_selector_report.csv.

Output: PDF saved alongside the input CSV (same directory, name
`portfolio_selector_report.pdf`).

Each row in the PDF shows one of the top 10 candidate portfolios with:
    - rank
    - strategy bullets in simplified form (e.g. "ES 15m breakout")
    - per-step pass rates (% chance to reach next step)
    - per-step est months (time to finish each step)
    - p95 worst drawdown
    - verdict tier with colour coding

Usage:
    python scripts/portfolio_report_pdf.py /path/to/portfolio_<program>/

    # Or generate for an entire run-folder of programs at once:
    python scripts/portfolio_report_pdf.py --run-dir /tmp/portfolio_runs_2026-05-03/

    # Backfill the Drive archive:
    python scripts/portfolio_report_pdf.py --backfill-drive
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BACKUP_ROOT = Path(r"G:\My Drive\strategy-data-backup\portfolio_selector")

# Strategy-name parsing
# Examples:
#   N225_daily_RefinedBreakout_HB2_ATR0.5_COMP0.0_MOM0   -> N225 / daily / breakout
#   ES_60m_RefinedMR_HB12_ATR0.4_DIST0.4_MOM0            -> ES / 60m / mean reversion
#   YM_daily_RefinedTrend_HB1_ATR0.75_VOL0.0_MOM0        -> YM / daily / trend
#   GC_30m_RefinedMR_HB12_ATR0.4_DIST0.4_MOM0            -> GC / 30m / mean reversion
TYPE_LABEL = {
    "MR": "mean_reversion",
    "Trend": "trend",
    "Breakout": "breakout",
    "ShortTrend": "short_trend",
    "ShortBreakout": "short_breakout",
    "ShortMR": "short_mean_reversion",
    "ComboTrend": "trend",
    "ComboMR": "mean_reversion",
    "ComboBreakout": "breakout",
}

VERDICT_COLOUR = {
    "RECOMMENDED": "#22c55e",            # green
    "VIABLE": "#3b82f6",                 # blue
    "MARGINAL": "#9ca3af",               # grey
    "INFEASIBLE_AT_ACCOUNT_SIZE": "#ef4444",  # red
}


def simplify_strategy(raw: str) -> str:
    """N225_daily_RefinedBreakout_HB2_ATR0.5_COMP0.0_MOM0 -> 'N225 daily breakout'."""
    if not raw:
        return ""
    parts = raw.split("_")
    if len(parts) < 3:
        return raw
    market, timeframe = parts[0], parts[1]
    # Find the leader-source token (Refined* or Combo*)
    type_label = ""
    for tok in parts[2:]:
        m = re.match(r"^(Refined|Combo)([A-Z][A-Za-z]*)$", tok)
        if m:
            label_key = m.group(2)
            type_label = TYPE_LABEL.get(label_key, label_key.lower())
            break
    if not type_label:
        # fall through: take third token as best guess
        type_label = parts[2].lower()
    return f"{market} {timeframe} {type_label}"


def detect_step_count(df: pd.DataFrame) -> int:
    """Count the number of stepN_pass_rate columns present."""
    n = 0
    for k in (1, 2, 3):
        if f"step{k}_pass_rate" in df.columns:
            n = k
    return n if n > 0 else 1


def render_pdf(report_csv: Path, output_pdf: Path | None = None) -> Path:
    df = pd.read_csv(report_csv)
    if df.empty:
        raise ValueError(f"empty report: {report_csv}")

    program_dir_name = report_csv.parent.name.replace("portfolio_", "", 1)
    n_steps = detect_step_count(df)

    # Build display rows (top 10)
    rows = df.head(10).copy()
    headers = ["#", "Portfolio (market timeframe type)"]
    for k in range(1, n_steps + 1):
        headers.append(f"Step {k}\npass %")
        headers.append(f"Step {k}\nmonths")
    headers += ["Total\nmonths", "p95 max\nDD %", "Verdict"]

    table_data: list[list[str]] = []
    verdict_per_row: list[str] = []
    for _, r in rows.iterrows():
        strategies_raw = str(r.get("strategy_names", "")).split("|")
        strategies_simple = [simplify_strategy(s.strip()) for s in strategies_raw if s.strip()]
        portfolio_cell = "\n".join(f"• {s}" for s in strategies_simple)

        cells = [str(int(r.get("rank", 0))), portfolio_cell]
        for k in range(1, n_steps + 1):
            pr = r.get(f"step{k}_pass_rate")
            mo = r.get(f"step{k}_est_months")
            cells.append(f"{pr*100:.1f}%" if pd.notna(pr) else "-")
            cells.append(f"{mo:.1f}" if pd.notna(mo) else "-")
        total_mo = r.get("total_est_months", r.get("est_months_median", float("nan")))
        cells.append(f"{total_mo:.1f}" if pd.notna(total_mo) else "-")
        p95 = r.get("p95_worst_dd_pct")
        cells.append(f"{p95*100:.2f}%" if pd.notna(p95) else "-")
        verdict = str(r.get("verdict", "")).strip()
        cells.append(verdict)
        table_data.append(cells)
        verdict_per_row.append(verdict)

    # --- figure layout ---
    fig_h = 1.6 + 0.55 * len(table_data)  # title + per-row height
    fig = plt.figure(figsize=(16, fig_h))
    ax = fig.add_axes([0.03, 0.05, 0.94, 0.78])
    ax.axis("off")

    # Title
    title = f"Portfolio Selector Report — {program_dir_name}"
    fig.suptitle(title, fontsize=15, fontweight="bold", y=0.97)

    # Subtitle: source file + n strategies + program rules summary
    n_total = len(df)
    subtitle = (
        f"{n_total} candidates evaluated · top 10 shown · "
        f"source: {report_csv.name}"
    )
    fig.text(0.5, 0.92, subtitle, ha="center", fontsize=10, color="#444")

    table = ax.table(
        cellText=table_data,
        colLabels=headers,
        loc="center",
        cellLoc="left",
        colLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 2.0)

    # Style header
    for j in range(len(headers)):
        cell = table[0, j]
        cell.set_facecolor("#1f2937")
        cell.set_text_props(color="white", fontweight="bold")
        cell.set_height(0.06)

    # Style body cells
    for i, vrow in enumerate(verdict_per_row, start=1):
        for j in range(len(headers)):
            cell = table[i, j]
            # alternating zebra
            cell.set_facecolor("#f9fafb" if i % 2 == 0 else "#ffffff")
            cell.set_edgecolor("#d1d5db")
            cell.set_height(0.05)
            # left-align portfolio column
            if j == 1:
                cell.set_text_props(ha="left", va="center")
            else:
                cell.set_text_props(ha="center", va="center")
        # verdict column highlight
        verdict_cell = table[i, len(headers) - 1]
        col = VERDICT_COLOUR.get(vrow, "#9ca3af")
        verdict_cell.set_facecolor(col)
        verdict_cell.set_text_props(color="white", fontweight="bold", ha="center", va="center")

    # Column width tuning — give the portfolio column 4x the room
    col_widths = []
    for j, h in enumerate(headers):
        if j == 0:
            col_widths.append(0.04)
        elif j == 1:
            col_widths.append(0.34)
        elif h == "Verdict":
            col_widths.append(0.10)
        else:
            col_widths.append(0.06)
    total_w = sum(col_widths)
    col_widths = [w / total_w for w in col_widths]
    for j, w in enumerate(col_widths):
        for i in range(len(table_data) + 1):
            table[i, j].set_width(w)

    # Footer: footnotes
    footer = (
        "Pass % = MC simulation pass rate at each step. Months = median time to clear "
        "that step. p95 max DD = 95th percentile worst drawdown across MC sims. "
        "Verdict tiers: RECOMMENDED (green) / VIABLE (blue) / MARGINAL (grey) / "
        "INFEASIBLE_AT_ACCOUNT_SIZE (red)."
    )
    fig.text(0.5, 0.02, footer, ha="center", fontsize=8, color="#555", wrap=True)

    if output_pdf is None:
        output_pdf = report_csv.parent / "portfolio_selector_report.pdf"
    fig.savefig(output_pdf, format="pdf", bbox_inches="tight")
    plt.close(fig)
    return output_pdf


def render_for_run_dir(run_dir: Path) -> list[Path]:
    """Generate a PDF for every portfolio_<program> subdir in a run output."""
    out: list[Path] = []
    for child in sorted(run_dir.iterdir()):
        if not child.is_dir():
            continue
        # Drive archive uses unprefixed program names; legacy uses portfolio_*
        report = child / "portfolio_selector_report.csv"
        if report.exists():
            try:
                pdf = render_pdf(report)
                print(f"  [OK] {child.name}: {pdf.name}")
                out.append(pdf)
            except Exception as exc:
                print(f"  [--] {child.name}: {exc}")
    return out


def backfill_drive(backup_root: Path = DEFAULT_BACKUP_ROOT) -> int:
    """Walk every <run_timestamp>/<program>/ in the Drive archive and add PDFs."""
    if not backup_root.exists():
        print(f"ERROR: backup root not found: {backup_root}", file=sys.stderr)
        return 1
    n_total = 0
    for ts_dir in sorted(backup_root.iterdir()):
        if not ts_dir.is_dir():
            continue
        print(f"\nRun: {ts_dir.name}")
        produced = render_for_run_dir(ts_dir)
        n_total += len(produced)
    print(f"\nBackfill done: {n_total} PDF(s) produced")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?",
                        help="program directory containing portfolio_selector_report.csv")
    parser.add_argument("--run-dir",
                        help="parent directory containing multiple portfolio_<program>/ subdirs")
    parser.add_argument("--backfill-drive", action="store_true",
                        help="Walk the Drive archive and produce PDFs for every existing run")
    parser.add_argument("--backup-root", default=str(DEFAULT_BACKUP_ROOT),
                        help="Drive archive root for --backfill-drive")
    args = parser.parse_args()

    if args.backfill_drive:
        return backfill_drive(Path(args.backup_root))

    if args.run_dir:
        run_dir = Path(args.run_dir)
        produced = render_for_run_dir(run_dir)
        print(f"\n{len(produced)} PDF(s) produced")
        return 0

    if args.path:
        target = Path(args.path)
        if target.is_file():
            pdf = render_pdf(target)
        elif target.is_dir():
            report = target / "portfolio_selector_report.csv"
            if not report.exists():
                print(f"ERROR: {report} not found", file=sys.stderr)
                return 1
            pdf = render_pdf(report)
        else:
            print(f"ERROR: {target} not found", file=sys.stderr)
            return 1
        print(f"Wrote {pdf}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
