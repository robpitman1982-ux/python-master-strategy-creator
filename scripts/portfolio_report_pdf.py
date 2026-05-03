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


PROGRAM_STEP_COUNT = {
    "bootcamp": 3,
    "high_stakes": 2,
    "hyper_growth": 1,
    "pro_growth": 1,
    "ftmo_swing_1step": 1,
    "ftmo_swing_2step": 2,
}


def detect_step_count(program_key: str, df: pd.DataFrame) -> int:
    """Resolve real n_steps from program name; fall back to df-based heuristic."""
    name = program_key.lower()
    for prefix, n in PROGRAM_STEP_COUNT.items():
        if name.startswith(prefix):
            return n
    # Fallback: count steps that have any nonzero pass rate
    n = 0
    for k in (1, 2, 3):
        col = f"step{k}_pass_rate"
        if col in df.columns and (df[col] > 0).any():
            n = k
    return n if n > 0 else 1


def render_pdf(report_csv: Path, output_pdf: Path | None = None) -> Path:
    df = pd.read_csv(report_csv)
    if df.empty:
        raise ValueError(f"empty report: {report_csv}")

    program_dir_name = report_csv.parent.name.replace("portfolio_", "", 1)
    n_steps = detect_step_count(program_dir_name, df)

    # Top 10 candidates
    rows = df.head(10).copy()

    # ---- Compose header columns ----
    headers = ["#", "Portfolio (market · timeframe · type)"]
    if n_steps == 1:
        headers.append("Pass\nrate %")
    else:
        for k in range(1, n_steps + 1):
            headers.append(f"Step {k}\npass %")
        headers.append("Final\npass %")
    headers += ["Months\nto fund", "p95 max\nDD %", "Verdict"]

    # ---- Compose body rows ----
    # One strategy per line with bullet so the count is unambiguous.
    # Includes the strategy index ("1.", "2.") to defend against any PDF
    # viewer that drops the bullet glyph.
    table_data: list[list[str]] = []
    verdict_per_row: list[str] = []
    bullet_count_per_row: list[int] = []
    for _, r in rows.iterrows():
        strategies_raw = str(r.get("strategy_names", "")).split("|")
        strategies_simple = [simplify_strategy(s.strip()) for s in strategies_raw if s.strip()]
        portfolio_cell = "\n".join(
            f"  {idx}. {name}" for idx, name in enumerate(strategies_simple, start=1)
        )
        line_count = max(1, len(strategies_simple))
        bullet_count_per_row.append(line_count)

        cells = [str(int(r.get("rank", 0))), portfolio_cell]
        if n_steps == 1:
            pr = r.get("step1_pass_rate", r.get("final_pass_rate"))
            cells.append(f"{pr*100:.1f}%" if pd.notna(pr) else "-")
        else:
            for k in range(1, n_steps + 1):
                pr = r.get(f"step{k}_pass_rate")
                cells.append(f"{pr*100:.1f}%" if pd.notna(pr) else "-")
            final = r.get("final_pass_rate")
            cells.append(f"{final*100:.1f}%" if pd.notna(final) else "-")

        months = r.get("est_months_median")
        cells.append(f"{months:.1f}" if pd.notna(months) else "-")
        p95 = r.get("p95_worst_dd_pct")
        cells.append(f"{p95*100:.2f}%" if pd.notna(p95) else "-")
        verdict = str(r.get("verdict", "")).strip()
        cells.append(verdict)
        table_data.append(cells)
        verdict_per_row.append(verdict)

    # ---- Figure + table sizing ----
    # Compute everything in inches first, then convert to axes-fraction.
    # Body fonts: portfolio 11pt, others 12pt → ~0.22 in per line incl
    # leading. Per-row inches = 0.30 padding + n_strats × 0.24 line.
    HEADER_IN = 0.50
    PORTFOLIO_LINE_IN = 0.24
    PADDING_IN = 0.30
    TITLE_BLOCK_IN = 1.40
    FOOTER_BLOCK_IN = 0.70

    row_in = [PADDING_IN + bc * PORTFOLIO_LINE_IN for bc in bullet_count_per_row]
    body_in = sum(row_in)
    fig_h = TITLE_BLOCK_IN + HEADER_IN + body_in + FOOTER_BLOCK_IN
    fig = plt.figure(figsize=(15, fig_h))

    # Title block. parse_math=False prevents underscores in the program
    # name (e.g. ftmo_swing_1step_130k) being rendered as math subscripts.
    title = f"Portfolio Selector Report — {program_dir_name}"
    fig.text(0.5, 0.955, title, ha="center", fontsize=20,
             fontweight="bold", parse_math=False)
    n_total = len(df)
    top_verdicts = ", ".join(
        f"{cnt} {v}" for v, cnt in df["verdict"].value_counts().items()
    ) if "verdict" in df.columns else ""
    subtitle = (
        f"{n_total} candidates · top 10 shown · {n_steps}-step program · "
        f"verdicts: {top_verdicts}"
    )
    fig.text(0.5, 0.915, subtitle, ha="center", fontsize=12,
             color="#555", parse_math=False)

    # Column width plan (portfolio gets ample room for strategy bullets)
    n_cols = len(headers)
    col_widths = []
    for j, h in enumerate(headers):
        if j == 0:                       # rank
            col_widths.append(0.04)
        elif j == 1:                     # portfolio
            col_widths.append(0.42)
        elif h == "Verdict":
            col_widths.append(0.11)
        elif "Months" in h:
            col_widths.append(0.08)
        elif "DD" in h:
            col_widths.append(0.08)
        else:                            # pass-rate columns
            col_widths.append(0.07)
    total_w = sum(col_widths)
    col_widths = [w / total_w for w in col_widths]

    # Build axes for the table. Position computed in figure-fractions
    # from the inch budget so layout is deterministic regardless of
    # n_strategies per row.
    title_frac = TITLE_BLOCK_IN / fig_h
    footer_frac = FOOTER_BLOCK_IN / fig_h
    axes_y = footer_frac
    axes_h = 1.0 - title_frac - footer_frac
    ax = fig.add_axes([0.02, axes_y, 0.96, axes_h])
    ax.axis("off")
    axes_h_inches = axes_h * fig_h

    table = ax.table(
        cellText=table_data,
        colLabels=headers,
        loc="upper center",
        cellLoc="left",
        colLoc="center",
        colWidths=col_widths,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(12)  # body default; per-cell overrides below

    # Convert inch heights to axes-fractions (deterministic, no overflow)
    header_h_frac = HEADER_IN / axes_h_inches
    row_h_fracs = [r / axes_h_inches for r in row_in]

    # Header style
    for j in range(n_cols):
        cell = table[0, j]
        cell.set_facecolor("#1f2937")
        cell.set_text_props(color="white", fontweight="bold", ha="center",
                            va="center", fontsize=12)
        cell.set_height(header_h_frac)
        cell.set_edgecolor("#1f2937")

    # Body style — height per row matches actual inch content of bullets
    for i, (vrow, bc) in enumerate(zip(verdict_per_row, bullet_count_per_row), start=1):
        row_h = row_h_fracs[i - 1]
        for j in range(n_cols):
            cell = table[i, j]
            cell.set_height(row_h)
            cell.set_edgecolor("#d1d5db")
            cell.set_facecolor("#f9fafb" if i % 2 == 0 else "#ffffff")
            if j == 1:
                # Portfolio bullets — slightly smaller so 3 bullets fit cleanly
                cell.set_text_props(ha="left", va="center", fontsize=11)
            else:
                cell.set_text_props(ha="center", va="center", fontsize=12)
        # Verdict highlight
        vc = table[i, n_cols - 1]
        col = VERDICT_COLOUR.get(vrow, "#9ca3af")
        vc.set_facecolor(col)
        vc.set_text_props(color="white", fontweight="bold", ha="center",
                          va="center", fontsize=11)

    # Footer — larger so it's actually readable
    footer = (
        "Pass % = MC simulation pass rate at each step.   "
        "Months to fund = median trades to first pass converted to months.   "
        "p95 max DD = 95th-percentile worst drawdown across MC sims.\n"
        "Verdicts: RECOMMENDED (green) · VIABLE (blue) · MARGINAL (grey) · "
        "INFEASIBLE_AT_ACCOUNT_SIZE (red)."
    )
    fig.text(0.5, footer_frac * 0.35, footer, ha="center", fontsize=10, color="#555")

    if output_pdf is None:
        output_pdf = report_csv.parent / "portfolio_selector_report.pdf"
    fig.savefig(output_pdf, format="pdf", bbox_inches="tight", pad_inches=0.25)
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
