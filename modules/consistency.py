from __future__ import annotations


def analyse_yearly_consistency(
    trades: list,
    min_years: int = 5,
) -> dict[str, float | str]:
    """
    Analyse year-by-year PnL consistency from a list of Trade objects.

    Returns:
        pct_profitable_years: fraction of years with positive PnL
        max_consecutive_losing_years: longest streak of losing years
        consistency_flag: "CONSISTENT", "MIXED", "INCONSISTENT", or "INSUFFICIENT_DATA"
        yearly_pnls: dict of year -> total PnL
    """
    if not trades:
        return {
            "pct_profitable_years": 0.0,
            "max_consecutive_losing_years": 0,
            "consistency_flag": "INSUFFICIENT_DATA",
            "yearly_pnls": {},
        }

    yearly_pnl: dict[int, float] = {}
    for t in trades:
        year = t.exit_time.year
        yearly_pnl[year] = yearly_pnl.get(year, 0.0) + t.pnl

    years_sorted = sorted(yearly_pnl.keys())

    if len(years_sorted) < min_years:
        return {
            "pct_profitable_years": 0.0,
            "max_consecutive_losing_years": 0,
            "consistency_flag": "INSUFFICIENT_DATA",
            "yearly_pnls": yearly_pnl,
        }

    profitable_years = sum(1 for y in years_sorted if yearly_pnl[y] > 0)
    pct_profitable = profitable_years / len(years_sorted)

    # Max consecutive losing years
    max_losing_streak = 0
    current_streak = 0
    for y in years_sorted:
        if yearly_pnl[y] <= 0:
            current_streak += 1
            max_losing_streak = max(max_losing_streak, current_streak)
        else:
            current_streak = 0

    # Flag logic
    if pct_profitable < 0.40 or max_losing_streak >= 5:
        flag = "INCONSISTENT"
    elif pct_profitable >= 0.60 and max_losing_streak <= 2:
        flag = "CONSISTENT"
    else:
        flag = "MIXED"

    return {
        "pct_profitable_years": round(pct_profitable, 4),
        "max_consecutive_losing_years": max_losing_streak,
        "consistency_flag": flag,
        "yearly_pnls": yearly_pnl,
    }
