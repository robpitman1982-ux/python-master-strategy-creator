"""
Cross-Dataset Portfolio Evaluator

Runs after all per-dataset evaluations complete. Collects all accepted
strategies from all datasets in a single run, normalises their trade
returns to a common daily PnL series, and produces cross-timeframe
correlation, MC drawdowns, and yearly stats.

Called from master_strategy_engine.py after the dataset loop completes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from modules.data_loader import load_tradestation_csv
from modules.portfolio_evaluator import (
    _rebuild_strategy_from_leaderboard_row,
    run_monte_carlo_stats,
)


def evaluate_cross_dataset_portfolio(
    outputs_root: Path,
    datasets: list[dict],
    oos_split_date: str = "2019-01-01",
) -> None:
    """Collect all accepted strategies across datasets, normalise to daily PnL,
    and write cross-timeframe correlation, portfolio review, and yearly stats.

    Parameters
    ----------
    outputs_root:
        Top-level Outputs directory (e.g. Path("Outputs")).
    datasets:
        List of dataset dicts from config — each has ``path``, ``market``,
        ``timeframe``.
    oos_split_date:
        Same IS/OOS split date used by the individual evaluators.
    """
    outputs_root = Path(outputs_root)

    # ------------------------------------------------------------------
    # A) Collect all accepted strategy rows across all datasets
    # ------------------------------------------------------------------
    all_accepted: list[pd.DataFrame] = []

    for ds in datasets:
        ds_market = str(ds.get("market", "UNKNOWN"))
        ds_timeframe = str(ds.get("timeframe", "unknown"))
        ds_path = str(ds.get("path", ""))

        leaderboard_csv = outputs_root / f"{ds_market}_{ds_timeframe}" / "family_leaderboard_results.csv"
        if not leaderboard_csv.exists():
            print(f"  [cross-eval] No leaderboard found for {ds_market}_{ds_timeframe}, skipping.")
            continue

        try:
            df = pd.read_csv(leaderboard_csv)
        except Exception as e:
            print(f"  [cross-eval] Could not read {leaderboard_csv}: {e}")
            continue

        if "accepted_final" not in df.columns:
            continue

        accepted_mask = df["accepted_final"].astype(str).str.strip().str.lower() == "true"
        df = df[accepted_mask].copy()
        if df.empty:
            continue

        df["source_market"] = ds_market
        df["source_timeframe"] = ds_timeframe
        df["source_data_path"] = ds_path
        all_accepted.append(df)

    if not all_accepted:
        print("  [cross-eval] No accepted strategies found across any dataset. Skipping cross-dataset evaluation.")
        return

    all_accepted_df = pd.concat(all_accepted, ignore_index=True)

    if len(all_accepted_df) < 2:
        print(f"  [cross-eval] Only {len(all_accepted_df)} accepted strategy found — need >= 2 for correlation. Skipping.")
        return

    print(f"  [cross-eval] Collected {len(all_accepted_df)} accepted strategies across {len(all_accepted)} datasets.")

    # ------------------------------------------------------------------
    # B) Reconstruct trade histories — cache data files to avoid re-loading
    # ------------------------------------------------------------------
    data_cache: dict[str, pd.DataFrame] = {}
    trades_by_label: dict[str, pd.DataFrame] = {}
    meta_by_label: dict[str, dict[str, Any]] = {}

    for _, row in all_accepted_df.iterrows():
        ds_market = str(row["source_market"])
        ds_timeframe = str(row["source_timeframe"])
        ds_path = str(row["source_data_path"])
        strategy_type = str(row.get("strategy_type", "unknown"))
        strategy_name = str(row.get("leader_strategy_name", "UNKNOWN")).strip()

        if not ds_path or not Path(ds_path).exists():
            print(f"  [cross-eval] Data file not found: {ds_path} — skipping {strategy_name}")
            continue

        label = f"{ds_timeframe}_{strategy_type}_{strategy_name[-20:]}"

        # Load data (cached)
        if ds_path not in data_cache:
            try:
                data_cache[ds_path] = load_tradestation_csv(ds_path)
            except Exception as e:
                print(f"  [cross-eval] Could not load data {ds_path}: {e}")
                continue

        data = data_cache[ds_path]
        outputs_dir = outputs_root / f"{ds_market}_{ds_timeframe}"

        try:
            trades_df, _filters_str, _cfg = _rebuild_strategy_from_leaderboard_row(
                row=row,
                data=data,
                outputs_dir=outputs_dir,
                market_symbol=ds_market,
                timeframe=ds_timeframe,
            )
        except Exception as e:
            print(f"  [cross-eval] Rebuild failed for {label}: {e}")
            continue

        if trades_df is None or trades_df.empty:
            print(f"  [cross-eval] No trades reconstructed for {label}, skipping.")
            continue

        trades_df["exit_time"] = pd.to_datetime(trades_df["exit_time"], errors="coerce")
        trades_df["net_pnl"] = pd.to_numeric(trades_df["net_pnl"], errors="coerce").fillna(0.0)
        trades_df = trades_df.dropna(subset=["exit_time"])

        trades_by_label[label] = trades_df
        meta_by_label[label] = {
            "source_timeframe": ds_timeframe,
            "strategy_type": strategy_type,
            "quality_flag": str(row.get("quality_flag", "UNKNOWN")),
            "total_trades": len(trades_df),
            "net_pnl": float(trades_df["net_pnl"].sum()),
            "max_drawdown": _compute_max_drawdown(trades_df),
        }

    if len(trades_by_label) < 2:
        print(f"  [cross-eval] Only {len(trades_by_label)} strategies reconstructed — need >= 2. Skipping correlation.")
        return

    print(f"  [cross-eval] Reconstructed {len(trades_by_label)} strategies successfully.")

    # ------------------------------------------------------------------
    # C) Normalise each strategy to a daily PnL series
    # ------------------------------------------------------------------
    daily_series: dict[str, pd.Series] = {}
    for label, trades_df in trades_by_label.items():
        daily = (
            trades_df.set_index("exit_time")["net_pnl"]
            .resample("D")
            .sum()
        )
        daily_series[label] = daily

    # ------------------------------------------------------------------
    # D) Cross-timeframe correlation matrix
    # ------------------------------------------------------------------
    if len(daily_series) >= 2:
        aligned = pd.DataFrame(daily_series).fillna(0.0)
        corr_matrix = aligned.corr()
        corr_out = outputs_root / "cross_timeframe_correlation_matrix.csv"
        corr_matrix.to_csv(corr_out)
        print(f"\n  Cross-timeframe correlation matrix ({corr_matrix.shape[0]}×{corr_matrix.shape[1]}):")
        print(corr_matrix.round(2).to_string())
        print(f"\n  Saved to {corr_out}")

    # ------------------------------------------------------------------
    # E) Monte Carlo and stress tests per strategy
    # ------------------------------------------------------------------
    portfolio_rows: list[dict[str, Any]] = []

    for label, trades_df in trades_by_label.items():
        meta = meta_by_label[label]
        mc = run_monte_carlo_stats(trades_df, iterations=10000)

        portfolio_rows.append({
            "strategy_label": label,
            "source_timeframe": meta["source_timeframe"],
            "strategy_type": meta["strategy_type"],
            "quality_flag": meta["quality_flag"],
            "total_trades": meta["total_trades"],
            "net_pnl": round(meta["net_pnl"], 2),
            "max_drawdown": round(meta["max_drawdown"], 2),
            "mc_max_dd_95": round(mc["mc_dd_95"], 2),
            "mc_max_dd_99": round(mc["mc_dd_99"], 2),
            "mc_pnl_50": round(mc["mc_pnl_50"], 2),
            "shock_drop_10pct_pnl": round(mc["shock_drop_10_pct_pnl"], 2),
        })

    review_df = pd.DataFrame(portfolio_rows)
    review_out = outputs_root / "cross_timeframe_portfolio_review.csv"
    review_df.to_csv(review_out, index=False)
    print(f"\n  Portfolio review saved to {review_out}")

    # ------------------------------------------------------------------
    # F) Yearly PnL breakdown
    # ------------------------------------------------------------------
    yearly_rows: list[dict[str, Any]] = []

    for label, trades_df in trades_by_label.items():
        df_y = trades_df.copy()
        df_y["year"] = df_y["exit_time"].dt.year

        for y, group in df_y.groupby("year"):
            g_prof = group.loc[group["net_pnl"] > 0, "net_pnl"].sum()
            g_loss = abs(group.loc[group["net_pnl"] < 0, "net_pnl"].sum())
            pf = (g_prof / g_loss) if g_loss > 0 else (float(g_prof) if g_prof > 0 else 0.0)
            yearly_rows.append({
                "strategy_label": label,
                "year": y,
                "trades": len(group),
                "net_pnl": round(float(group["net_pnl"].sum()), 2),
                "profit_factor": round(float(pf), 2),
            })

    yearly_df = pd.DataFrame(yearly_rows)
    yearly_out = outputs_root / "cross_timeframe_yearly_stats.csv"
    yearly_df.to_csv(yearly_out, index=False)
    print(f"  Yearly stats saved to {yearly_out}")

    # ------------------------------------------------------------------
    # G) Print summary
    # ------------------------------------------------------------------
    print(f"\n{'─' * 72}")
    print("CROSS-DATASET PORTFOLIO SUMMARY")
    print(f"{'─' * 72}")
    print(f"  {'Label':<40}  {'TF':<8}  {'Trades':>6}  {'NetPnL':>10}  {'MC DD99':>10}")
    print(f"  {'─' * 40}  {'─' * 8}  {'─' * 6}  {'─' * 10}  {'─' * 10}")
    for row in sorted(portfolio_rows, key=lambda r: r["net_pnl"], reverse=True):
        print(
            f"  {row['strategy_label']:<40}  {row['source_timeframe']:<8}  "
            f"{row['total_trades']:>6}  {row['net_pnl']:>10,.0f}  {row['mc_max_dd_99']:>10,.0f}"
        )
    print(f"{'─' * 72}")


def _compute_max_drawdown(trades_df: pd.DataFrame) -> float:
    """Compute max drawdown from a trades DataFrame with net_pnl column."""
    if trades_df.empty or "net_pnl" not in trades_df.columns:
        return 0.0
    cum_pnl = trades_df["net_pnl"].cumsum()
    if cum_pnl.empty:
        return 0.0
    return float((cum_pnl.cummax() - cum_pnl).max())
