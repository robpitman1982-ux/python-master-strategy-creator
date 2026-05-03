#!/usr/bin/env python3
"""24-month printable projection for FTMO Swing 1-Step 130K.

Numbers derived from the 2026-05-03 selector run (rank 3 portfolio,
4-strategy: N225 breakout + N225 mean reversion + CAC breakout + YM trend).
Backtest median time-to-fund = 2.0 months at 100% MC pass rate.

Three scenarios shown:
  1. Single $130K account, no scaling
  2. Single $130K account WITH FTMO scaling (+25% every 4 funded months)
  3. Three $130K accounts in parallel (FTMO trader cap is ~$400K combined)

Usage:
    python scripts/ftmo_130k_projection_pdf.py \
        --output Outputs/projections/ftmo_130k_projection_24mo.pdf
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

USD_TO_AUD = 1.55

ACCOUNT_SIZE = 130_000
PROFIT_TARGET_PCT = 0.10
PROFIT_SPLIT = 0.90
ENTRY_FEE = 5_400

PASS_MONTHS = 2
MONTHLY_PCT = 0.05
TOTAL_MONTHS = 24

SCALING_PCT = 0.25
SCALING_INTERVAL_MONTHS = 4
SCALING_BALANCE_CAP = 400_000  # FTMO trader-wide cap


def fmt_usd(v):
    if v == 0:
        return "-"
    sign = "-" if v < 0 else "+"
    if abs(v) < 1000:
        return f"{sign}${abs(v):,.0f}"
    return f"{sign}${abs(v):,.0f}"


def fmt_aud(v):
    if v == 0:
        return "-"
    sign = "-" if v < 0 else "+"
    return f"{sign}A${abs(v) * USD_TO_AUD:,.0f}"


def fmt_cum_aud(v):
    sign = "-" if v < 0 else ""
    return f"{sign}A${abs(v) * USD_TO_AUD:,.0f}"


def build_no_scaling_schedule():
    """Compact 24-month schedule, no FTMO scaling."""
    monthly_take = ACCOUNT_SIZE * MONTHLY_PCT * PROFIT_SPLIT  # $5,850
    pass_payout = ACCOUNT_SIZE * PROFIT_TARGET_PCT * PROFIT_SPLIT + ENTRY_FEE  # $17,100

    rows = []
    cum = 0.0
    cum -= ENTRY_FEE
    rows.append({"period": "Month 0", "what": "Pay entry fee",
                 "delta": -ENTRY_FEE, "cum": cum})
    rows.append({"period": "Month 1", "what": "Trading evaluation",
                 "delta": 0, "cum": cum})
    cum += pass_payout
    rows.append({"period": "Month 2", "what": "PASS - eval payout + fee refund",
                 "delta": pass_payout, "cum": cum, "highlight": True})
    # Group remaining 22 months into 4-month blocks (5x4mo + 2 extra months)
    blocks = [
        ("Months 3-6",   4),
        ("Months 7-10",  4),
        ("Months 11-14", 4),
        ("Months 15-18", 4),
        ("Months 19-22", 4),
        ("Months 23-24", 2),
    ]
    for label, n in blocks:
        delta = monthly_take * n
        cum += delta
        rows.append({
            "period": label,
            "what":   f"Funded payouts ({n} x $5,850/mo)",
            "delta":  delta,
            "cum":    cum,
        })
    return rows


def build_scaling_schedule():
    """Schedule with FTMO scaling: +25% every 4 funded months, capped at $400K."""
    rows = []
    cum = -ENTRY_FEE
    rows.append({"period": "Month 0", "what": "Pay entry fee",
                 "size": ACCOUNT_SIZE, "delta": -ENTRY_FEE, "cum": cum})
    rows.append({"period": "Month 1", "what": "Trading evaluation",
                 "size": ACCOUNT_SIZE, "delta": 0, "cum": cum})
    pass_payout = ACCOUNT_SIZE * PROFIT_TARGET_PCT * PROFIT_SPLIT + ENTRY_FEE
    cum += pass_payout
    rows.append({"period": "Month 2",
                 "what": "PASS - eval payout + fee refund",
                 "size": ACCOUNT_SIZE,
                 "delta": pass_payout, "cum": cum, "highlight": True})

    current_size = ACCOUNT_SIZE
    # Funded months start at month 3. Scale every 4 funded months at end of
    # months 6, 10, 14, 18, 22 (i.e. new size effective months 7, 11, 15, ...).
    # Loop month-by-month from 3 to 24, group by 4.
    funded_blocks = [
        ("Months 3-6",   3, 6),    # First 4 funded months at $130K
        ("Months 7-10",  7, 10),   # After scale 1
        ("Months 11-14", 11, 14),  # After scale 2
        ("Months 15-18", 15, 18),  # After scale 3
        ("Months 19-22", 19, 22),  # After scale 4
        ("Months 23-24", 23, 24),  # 2 months at last size
    ]
    for i, (label, m0, m1) in enumerate(funded_blocks):
        if i > 0:
            new_size = min(current_size * (1 + SCALING_PCT), SCALING_BALANCE_CAP)
            current_size = new_size
        n = m1 - m0 + 1
        monthly_take = current_size * MONTHLY_PCT * PROFIT_SPLIT
        delta = monthly_take * n
        cum += delta
        size_label = f"${current_size/1000:.1f}K"
        rows.append({
            "period": label,
            "what":   f"Funded ({n}x ${monthly_take:,.0f}/mo)",
            "size":   current_size,
            "size_label": size_label,
            "delta":  delta,
            "cum":    cum,
        })
    return rows


def render_pdf(output_path: Path):
    no_scale = build_no_scaling_schedule()
    scale    = build_scaling_schedule()

    final_no_scale = no_scale[-1]["cum"]
    final_scale    = scale[-1]["cum"]
    final_3acct    = final_no_scale * 3

    fig = plt.figure(figsize=(11.5, 16.0))
    fig.patch.set_facecolor("white")

    # === TITLE ===
    fig.text(0.5, 0.975, "FTMO Swing 1-Step $130,000",
             ha="center", fontsize=24, fontweight="bold", parse_math=False)
    fig.text(0.5, 0.955, "24-Month Projected Earnings",
             ha="center", fontsize=15, color="#444", parse_math=False)
    fig.text(0.5, 0.937,
             "Based on the 4-strategy CFD portfolio - 100% pass rate, 2 months to fund",
             ha="center", fontsize=10.5, color="#777",
             style="italic", parse_math=False)

    # === SETUP BOX ===
    setup_box = FancyBboxPatch(
        (0.05, 0.835), 0.90, 0.085,
        boxstyle="round,pad=0.012",
        transform=fig.transFigure,
        facecolor="#f4f7fb", edgecolor="#cfd9e6", linewidth=1.2,
    )
    fig.add_artist(setup_box)
    setup_lines = [
        ("Account size",        "$130,000 USD"),
        ("Profit target",       "$13,000  (10%)"),
        ("Your share",          "90%  (Australian Swing - max payout)"),
        ("Entry fee",           "$5,400  (refunded with first payout)"),
        ("Max drawdown",        "10% trailing  ($13,000 buffer)"),
        ("Backtest worst case", "7.95%  (well inside the 10% limit)"),
        ("Pass rate",           "100%  (10,000 stress simulations)"),
        ("Median time to fund", "2 months"),
    ]
    for i, (k, v) in enumerate(setup_lines):
        col = i % 2
        row = i // 2
        x = 0.08 if col == 0 else 0.52
        y = 0.905 - row * 0.018
        fig.text(x, y, k, fontsize=10.5, color="#444",
                 fontweight="bold", parse_math=False)
        fig.text(x + 0.20, y, v, fontsize=10.5, color="#111",
                 parse_math=False)

    # === STRATEGIES ===
    fig.text(0.05, 0.815, "What it trades  -  4 daily-bar strategies, ~5 min/day to monitor",
             fontsize=11.5, fontweight="bold", parse_math=False)
    strats = [
        "1.  Nikkei 225  -  long breakouts",
        "2.  Nikkei 225  -  mean reversion bounces",
        "3.  CAC 40  -  long breakouts (compression squeeze)",
        "4.  Dow Jones  -  short trend continuation",
    ]
    for i, s in enumerate(strats):
        col = i % 2
        row = i // 2
        x = 0.08 if col == 0 else 0.52
        y = 0.798 - row * 0.018
        fig.text(x, y, s, fontsize=10.5, parse_math=False)

    # === HEADLINE THREE-SCENARIO BLOCK ===
    fig.text(0.5, 0.745, "End-of-month-24 totals  -  three scenarios",
             ha="center", fontsize=14, fontweight="bold", parse_math=False)

    scenario_panels = [
        {
            "title": "1 ACCOUNT",
            "subtitle": "no scaling",
            "usd": final_no_scale,
            "color_bg": "#eaf3fb",
            "color_edge": "#3f6b9d",
            "color_text": "#1f4773",
        },
        {
            "title": "1 ACCOUNT",
            "subtitle": "with FTMO scaling",
            "usd": final_scale,
            "color_bg": "#fff5e6",
            "color_edge": "#c98e3b",
            "color_text": "#7a531e",
        },
        {
            "title": "3 ACCOUNTS",
            "subtitle": "in parallel, no scaling",
            "usd": final_3acct,
            "color_bg": "#eaf6ee",
            "color_edge": "#0a7d3a",
            "color_text": "#0a7d3a",
        },
    ]
    panel_w = 0.27
    panel_gap = 0.025
    total_w = 3 * panel_w + 2 * panel_gap
    panel_x0 = (1.0 - total_w) / 2
    for i, p in enumerate(scenario_panels):
        x = panel_x0 + i * (panel_w + panel_gap)
        box = FancyBboxPatch(
            (x, 0.640), panel_w, 0.090,
            boxstyle="round,pad=0.008",
            transform=fig.transFigure,
            facecolor=p["color_bg"], edgecolor=p["color_edge"], linewidth=1.5,
        )
        fig.add_artist(box)
        cx = x + panel_w / 2
        fig.text(cx, 0.715, p["title"], ha="center", fontsize=12,
                 fontweight="bold", color=p["color_text"], parse_math=False)
        fig.text(cx, 0.700, p["subtitle"], ha="center", fontsize=9.5,
                 color=p["color_text"], style="italic", parse_math=False)
        fig.text(cx, 0.675, f"${p['usd']:,.0f}", ha="center", fontsize=18,
                 fontweight="bold", color=p["color_text"], parse_math=False)
        fig.text(cx, 0.652, f"A${p['usd'] * USD_TO_AUD:,.0f}",
                 ha="center", fontsize=12,
                 color=p["color_text"], parse_math=False)

    # === DETAILED TABLES ===
    def render_compact_table(rows, x_left, x_right, top_y, title, banner_color,
                             show_size=False):
        # Banner
        banner = FancyBboxPatch(
            (x_left, top_y), x_right - x_left, 0.024,
            boxstyle="round,pad=0.005",
            transform=fig.transFigure,
            facecolor=banner_color, edgecolor=banner_color,
        )
        fig.add_artist(banner)
        fig.text((x_left + x_right) / 2, top_y + 0.011, title,
                 ha="center", va="center", fontsize=11, color="white",
                 fontweight="bold", parse_math=False)
        # Headers
        col_y = top_y - 0.020
        if show_size:
            col_xs = [
                x_left + 0.012,            # Period
                x_left + 0.078,            # Size
                x_left + 0.110,            # What
                x_right - 0.085,           # Period delta USD
                x_right - 0.005,           # Cumulative AUD
            ]
            headers = ["Period", "Size", "What", "Period $", "Cum. AUD"]
            aligns = ["left", "left", "left", "right", "right"]
        else:
            col_xs = [
                x_left + 0.012,
                x_left + 0.078,
                x_right - 0.085,
                x_right - 0.005,
            ]
            headers = ["Period", "What", "Period $", "Cum. AUD"]
            aligns = ["left", "left", "right", "right"]
        for cx, h, a in zip(col_xs, headers, aligns):
            fig.text(cx, col_y, h, fontsize=9.5, color="#555",
                     fontweight="bold", ha=a, parse_math=False)
        # Rows
        row_h = 0.020
        for i, r in enumerate(rows):
            ry = col_y - 0.018 - i * row_h
            if i % 2 == 0:
                bg = FancyBboxPatch(
                    (x_left, ry - 0.007), x_right - x_left, row_h,
                    boxstyle="square,pad=0",
                    transform=fig.transFigure,
                    facecolor="#fafafa", edgecolor="none",
                )
                fig.add_artist(bg)
            color = "#111"
            weight = "normal"
            if r.get("highlight"):
                color = "#0a7d3a"
                weight = "bold"
            elif r.get("delta", 0) < 0:
                color = "#a33"
            if show_size:
                cells = [
                    r["period"],
                    r.get("size_label", f"${r.get('size', ACCOUNT_SIZE)/1000:.0f}K"),
                    r["what"],
                    fmt_usd(r["delta"]) if r["delta"] != 0 else "-",
                    fmt_cum_aud(r["cum"]),
                ]
            else:
                cells = [
                    r["period"],
                    r["what"],
                    fmt_usd(r["delta"]) if r["delta"] != 0 else "-",
                    fmt_cum_aud(r["cum"]),
                ]
            for cx, val, a in zip(col_xs, cells, aligns):
                fig.text(cx, ry, val, fontsize=9.5, color=color,
                         fontweight=weight, ha=a, parse_math=False)
        # Final total banner
        total_y = col_y - 0.018 - len(rows) * row_h - 0.012
        total_box = FancyBboxPatch(
            (x_left, total_y - 0.005),
            x_right - x_left, 0.030,
            boxstyle="round,pad=0.004",
            transform=fig.transFigure,
            facecolor="#eef6ee", edgecolor="#0a7d3a", linewidth=1.0,
        )
        fig.add_artist(total_box)
        final_usd = rows[-1]["cum"]
        final_aud = final_usd * USD_TO_AUD
        fig.text(x_left + 0.012, total_y + 0.010,
                 "24-month total",
                 fontsize=10.5, color="#0a7d3a", fontweight="bold",
                 parse_math=False)
        fig.text(x_right - 0.005, total_y + 0.010,
                 f"${final_usd:,.0f}  /  A${final_aud:,.0f}",
                 fontsize=10.5, color="#0a7d3a", fontweight="bold",
                 ha="right", parse_math=False)
        return total_y

    # Two tables stacked vertically
    render_compact_table(
        no_scale, 0.05, 0.95, 0.610,
        "DETAIL  -  1 Account, no scaling",
        "#3f6b9d", show_size=False,
    )
    render_compact_table(
        scale, 0.05, 0.95, 0.395,
        "DETAIL  -  1 Account, WITH FTMO scaling (+25% every 4 funded months)",
        "#c98e3b", show_size=True,
    )

    # === MULTI-ACCOUNT NOTE ===
    multi_y = 0.165
    multi_box = FancyBboxPatch(
        (0.05, multi_y - 0.020), 0.90, 0.060,
        boxstyle="round,pad=0.010",
        transform=fig.transFigure,
        facecolor="#eaf6ee", edgecolor="#0a7d3a", linewidth=1.2,
    )
    fig.add_artist(multi_box)
    fig.text(0.07, multi_y + 0.025, "Running 3 accounts in parallel",
             fontsize=12, fontweight="bold", color="#0a7d3a", parse_math=False)
    fig.text(0.07, multi_y + 0.005,
             "FTMO allows up to ~$400K combined per trader. 3 x $130K = $390K is just under the cap.",
             fontsize=10, color="#222", parse_math=False)
    fig.text(0.07, multi_y - 0.013,
             "Same EA, same strategies, same monitoring effort. Numbers triple linearly:",
             fontsize=10, color="#222", parse_math=False)
    fig.text(0.93, multi_y + 0.005,
             f"24-month total:  ${final_3acct:,.0f}  /  A${final_3acct * USD_TO_AUD:,.0f}",
             fontsize=11, color="#0a7d3a", fontweight="bold",
             ha="right", parse_math=False)

    # === NOTES ===
    notes_y = 0.090
    fig.text(0.05, notes_y, "Notes",
             fontsize=11, fontweight="bold", parse_math=False)
    notes = [
        f"AUD shown at USD/AUD = {USD_TO_AUD:.2f} (rough current rate; actual converts at the day's exchange rate).",
        "FTMO scaling: +25% every 4 funded months IF 10% profit hit. We project 5%/mo, so 20%+ per period - easily clears the bar.",
        "Conservative view: if strategies trade at half their backtested pace, halve every figure on this page.",
        "These are model projections, not guarantees. Live trading has slippage and news events the backtest doesn't fully see.",
        "All three scenarios assume the same 4-strategy portfolio survives unchanged for 24 months. We re-evaluate quarterly.",
    ]
    for i, n in enumerate(notes):
        fig.text(0.07, notes_y - 0.014 - i * 0.013,
                 f"-  {n}", fontsize=8.8, color="#444", parse_math=False)

    # === FOOTER ===
    fig.text(0.5, 0.010,
             "Generated 2026-05-04  -  Selector run 2026-05-03  -  "
             "python-master-strategy-creator",
             ha="center", fontsize=8, color="#888", parse_math=False)

    fig.savefig(output_path, format="pdf", bbox_inches=None,
                facecolor="white")
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    args = p.parse_args()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    render_pdf(out)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
