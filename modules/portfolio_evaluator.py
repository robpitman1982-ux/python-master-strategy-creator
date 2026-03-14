"""
Portfolio Evaluator
Reads the family leaderboard, reconstructs the selected winning strategies,
runs In-Sample / Out-Of-Sample regime splits, calculates Monte Carlo metrics,
runs slippage & trade drop robustness tests, and builds Combined Portfolio metrics.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import modules.filters as filters_module
from modules.data_loader import load_tradestation_csv
from modules.engine import EngineConfig, MasterStrategyEngine
from modules.feature_builder import add_precomputed_features
from modules.strategy_types import get_strategy_type

OOS_SPLIT_DATE = "2019-01-01"


def generate_run_id(market: str, timeframe: str) -> tuple[str, str]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    return f"{timestamp}_{market}_{timeframe}", timestamp


def run_monte_carlo_stats(trades_df: pd.DataFrame, iterations: int = 10000) -> dict[str, float]:
    if trades_df.empty or "net_pnl" not in trades_df.columns:
        return {
            "mc_dd_95": 0.0,
            "mc_dd_99": 0.0,
            "mc_pnl_50": 0.0,
            "shock_drop_10_pct_pnl": 0.0,
        }

    trades_arr = trades_df["net_pnl"].astype(float).values
    n_trades = len(trades_arr)

    max_drawdowns = np.zeros(iterations)
    net_pnls = np.zeros(iterations)
    shock_pnls = np.zeros(iterations)

    for i in range(iterations):
        simulated_trades = np.random.choice(trades_arr, size=n_trades, replace=True)
        cum_equity = np.cumsum(simulated_trades)
        running_max = np.maximum.accumulate(cum_equity)
        drawdowns = running_max - cum_equity

        max_drawdowns[i] = np.max(drawdowns) if len(drawdowns) > 0 else 0.0
        net_pnls[i] = cum_equity[-1] if len(cum_equity) > 0 else 0.0

        mask = np.random.rand(n_trades) > 0.10
        shock_trades = simulated_trades[mask]
        shock_pnls[i] = np.sum(shock_trades) if len(shock_trades) > 0 else 0.0

    return {
        "mc_dd_95": float(np.percentile(max_drawdowns, 95)),
        "mc_dd_99": float(np.percentile(max_drawdowns, 99)),
        "mc_pnl_50": float(np.percentile(net_pnls, 50)),
        "shock_drop_10_pct_pnl": float(np.percentile(shock_pnls, 50)),
    }


def calculate_metrics_split(trades_df: pd.DataFrame) -> dict[str, float]:
    if trades_df.empty or "exit_time" not in trades_df.columns or "net_pnl" not in trades_df.columns:
        return {
            "full_pf": 0.0,
            "full_net": 0.0,
            "max_dd": 0.0,
            "recent_pf": 0.0,
            "is_pf": 0.0,
            "oos_pf": 0.0,
            "is_trades": 0,
            "oos_trades": 0,
            "recent_12m_trades": 0,
        }

    df = trades_df.copy()
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df["net_pnl"] = pd.to_numeric(df["net_pnl"], errors="coerce").fillna(0.0)

    def _get_pf(df_slice: pd.DataFrame) -> float:
        if df_slice.empty:
            return 0.0
        g_prof = df_slice.loc[df_slice["net_pnl"] > 0, "net_pnl"].sum()
        g_loss = abs(df_slice.loc[df_slice["net_pnl"] < 0, "net_pnl"].sum())
        if g_loss > 0:
            return float(g_prof / g_loss)
        if g_prof > 0:
            return float(g_prof)
        return 0.0

    full_pf = _get_pf(df)
    full_net = float(df["net_pnl"].sum())
    cum_pnl = df["net_pnl"].cumsum()
    max_dd = float((cum_pnl.cummax() - cum_pnl).max()) if not cum_pnl.empty else 0.0

    max_date = df["exit_time"].max()
    recent_trades = df[df["exit_time"] >= (max_date - timedelta(days=365))]
    is_trades = df[df["exit_time"] < pd.to_datetime(OOS_SPLIT_DATE)]
    oos_trades = df[df["exit_time"] >= pd.to_datetime(OOS_SPLIT_DATE)]

    return {
        "full_pf": full_pf,
        "full_net": full_net,
        "max_dd": max_dd,
        "recent_pf": _get_pf(recent_trades),
        "is_pf": _get_pf(is_trades),
        "oos_pf": _get_pf(oos_trades),
        "is_trades": len(is_trades),
        "oos_trades": len(oos_trades),
        "recent_12m_trades": len(recent_trades),
    }


def calculate_slippage_shock(trades_df: pd.DataFrame, tick_value: float = 12.50) -> float:
    if trades_df.empty or "net_pnl" not in trades_df.columns:
        return 0.0
    extra_friction_per_trade = 4 * tick_value
    shocked_pnl = trades_df["net_pnl"].astype(float) - extra_friction_per_trade
    return float(shocked_pnl.sum())


def _normalize_trade_columns(trades_df: pd.DataFrame) -> pd.DataFrame:
    if trades_df.empty:
        return trades_df

    rename_map = {}
    for col in trades_df.columns:
        c = col.lower().strip()
        if c in ["pnl", "net_pnl", "net pnl"]:
            rename_map[col] = "net_pnl"
        elif c in ["exit_time", "exit time", "exit date"]:
            rename_map[col] = "exit_time"
    return trades_df.rename(columns=rename_map)


def _load_combo_reference_row(outputs_dir: Path, strategy_type_name: str, combo_name: str) -> dict[str, Any] | None:
    promoted_csv = outputs_dir / f"{strategy_type_name}_promoted_candidates.csv"
    if not promoted_csv.exists():
        return None

    promoted_df = pd.read_csv(promoted_csv)
    if promoted_df.empty or "strategy_name" not in promoted_df.columns:
        return None

    match_df = promoted_df[promoted_df["strategy_name"] == combo_name]
    if match_df.empty:
        return None

    return match_df.iloc[0].to_dict()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _parse_filter_classes_from_combo_row(combo_row: dict[str, Any]) -> list[type]:
    filters_str = str(combo_row.get("filters", "")).strip()
    if not filters_str:
        return []

    combo_classes: list[type] = []
    for f in filters_str.split(","):
        f_name = f.strip()
        if not f_name:
            continue
        if not f_name.endswith("Filter"):
            f_name = f"{f_name}Filter"
        if hasattr(filters_module, f_name):
            combo_classes.append(getattr(filters_module, f_name))

    return combo_classes


def _rebuild_strategy_from_leaderboard_row(
    row: pd.Series,
    data: pd.DataFrame,
    outputs_dir: Path,
    market_symbol: str,
) -> tuple[pd.DataFrame, str, EngineConfig]:
    strategy_type_name = str(row["strategy_type"]).strip()
    leader_source = str(row.get("leader_source", "")).strip().lower()

    combo_name = str(row.get("best_combo_strategy_name", ""))
    combo_row = _load_combo_reference_row(outputs_dir, strategy_type_name, combo_name)
    if not combo_row:
        return pd.DataFrame(), "", EngineConfig(symbol=market_symbol)

    combo_classes = _parse_filter_classes_from_combo_row(combo_row)
    if not combo_classes:
        return pd.DataFrame(), "", EngineConfig(symbol=market_symbol)

    strategy_type_inst = get_strategy_type(strategy_type_name)

    hold_bars = _safe_int(row.get("leader_hold_bars", 0), 0)
    stop_distance_points = _safe_float(row.get("leader_stop_distance_points", 0.0), 0.0)
    min_avg_range = _safe_float(row.get("leader_min_avg_range", 0.0), 0.0)
    momentum_lookback = _safe_int(row.get("leader_momentum_lookback", 0), 0)

    # If combo leader was selected, use family defaults.
    if leader_source == "combo":
        hold_bars = int(getattr(strategy_type_inst, "default_hold_bars", 3))
        stop_distance_points = float(getattr(strategy_type_inst, "default_stop_distance_points", 1.0))
        min_avg_range = 0.0
        momentum_lookback = 0

    eval_data = add_precomputed_features(
        data.copy(),
        sma_lengths=strategy_type_inst.get_required_sma_lengths(),
        avg_range_lookbacks=strategy_type_inst.get_required_avg_range_lookbacks(),
        momentum_lookbacks=strategy_type_inst.get_required_momentum_lookbacks(),
    )

    strategy = strategy_type_inst.build_candidate_specific_strategy(
        combo_classes,
        hold_bars,
        stop_distance_points,
        min_avg_range,
        momentum_lookback,
    )

    cfg = EngineConfig(
        initial_capital=250_000.0,
        risk_per_trade=0.01,
        symbol=market_symbol,
    )

    engine = MasterStrategyEngine(data=eval_data, config=cfg)
    engine.run(strategy=strategy)

    trades_df = _normalize_trade_columns(engine.trades_dataframe())
    return trades_df, str(combo_row.get("filters", "")), cfg


def evaluate_portfolio(
    leaderboard_csv: Path,
    data_csv: Path,
    market_name: str,
    timeframe: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    leaderboard_csv = Path(leaderboard_csv)
    data_csv = Path(data_csv)

    if not leaderboard_csv.exists():
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    leaderboard_df = pd.read_csv(leaderboard_csv)
    if leaderboard_df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    print(f"\nLoading market data from: {data_csv} for evaluation...")
    data = load_tradestation_csv(data_csv)

    run_id, _timestamp = generate_run_id(market_name, timeframe)

    results_list: list[dict[str, Any]] = []
    daily_returns_dict: dict[str, pd.Series] = {}
    yearly_stats_list: list[dict[str, Any]] = []
    all_trades_list: list[pd.DataFrame] = []

    last_cfg = EngineConfig(symbol=market_name)

    # Only evaluate families that actually had promoted candidates.
    leaderboard_df = leaderboard_df[leaderboard_df["promotion_status"] == "PROMOTED"].copy()

    print(f"\nEvaluating {len(leaderboard_df)} strategies from Leaderboard...")

    for _, row in leaderboard_df.iterrows():
        strategy_name = str(row.get("leader_strategy_name", "UNKNOWN"))
        print(f"\n  Evaluating: {row['strategy_type']} -> {strategy_name}")

        try:
            trades_df, filters_str, cfg = _rebuild_strategy_from_leaderboard_row(
                row=row,
                data=data,
                outputs_dir=leaderboard_csv.parent,
                market_symbol=market_name,
            )

            if trades_df.empty:
                print(f"    [Warning] Skipping. Could not rebuild trades for {strategy_name}.")
                continue

            last_cfg = cfg

            trades_df["exit_time"] = pd.to_datetime(trades_df["exit_time"])
            trades_df["net_pnl"] = pd.to_numeric(trades_df["net_pnl"], errors="coerce").fillna(0.0)

            all_trades_list.append(trades_df)

            daily_returns_dict[f"{run_id}_{strategy_name}"] = (
                trades_df.resample("D", on="exit_time")["net_pnl"].sum().fillna(0)
            )

            stats = calculate_metrics_split(trades_df)
            mc = run_monte_carlo_stats(trades_df, iterations=10000)
            shock_pnl = calculate_slippage_shock(trades_df, tick_value=cfg.tick_value)

            df_year = trades_df.copy()
            df_year["year"] = df_year["exit_time"].dt.year

            strat_yearly = []
            for y, group in df_year.groupby("year"):
                g_prof = group.loc[group["net_pnl"] > 0, "net_pnl"].sum()
                g_loss = abs(group.loc[group["net_pnl"] < 0, "net_pnl"].sum())
                pf = (g_prof / g_loss) if g_loss > 0 else (float(g_prof) if g_prof > 0 else 0.0)

                strat_yearly.append(
                    {
                        "strategy_name": strategy_name,
                        "filters": filters_str,
                        "year": y,
                        "trades": len(group),
                        "net_pnl": round(float(group["net_pnl"].sum()), 2),
                        "profit_factor": round(float(pf), 2),
                    }
                )

            yearly_df = pd.DataFrame(strat_yearly).sort_values("year")
            if not yearly_df.empty:
                yearly_df["rolling_3y_pnl"] = yearly_df["net_pnl"].rolling(3).sum()
                yearly_stats_list.extend(yearly_df.to_dict("records"))

            results_list.append(
                {
                    "strategy_family": row["strategy_type"],
                    "strategy_name": strategy_name,
                    "quality_flag": row.get("quality_flag", "UNKNOWN"),
                    "total_trades": len(trades_df),
                    "is_trades": stats["is_trades"],
                    "oos_trades": stats["oos_trades"],
                    "full_pf": round(stats["full_pf"], 2),
                    "is_pf_pre_2019": round(stats["is_pf"], 2),
                    "oos_pf_post_2019": round(stats["oos_pf"], 2),
                    "recent_12m_pf": round(stats["recent_pf"], 2),
                    "net_pnl": round(stats["full_net"], 2),
                    "max_drawdown": round(stats["max_dd"], 2),
                    "mc_max_dd_99": round(mc["mc_dd_99"], 2),
                    "shock_drop_10pct_pnl": round(mc["shock_drop_10_pct_pnl"], 2),
                    "shock_extra_slip_pnl": round(shock_pnl, 2),
                }
            )

        except Exception as e:
            print(f"    [Warning] Could not reconstruct trade history: {e}")

    if len(all_trades_list) > 1:
        print("\n  Evaluating: COMBINED PORTFOLIO (All Winning Strategies Merged)")
        combo_df = pd.concat(all_trades_list, ignore_index=True)
        combo_df = combo_df.sort_values("exit_time").reset_index(drop=True)

        stats = calculate_metrics_split(combo_df)
        mc = run_monte_carlo_stats(combo_df, iterations=10000)
        shock_pnl = calculate_slippage_shock(combo_df, tick_value=last_cfg.tick_value)

        results_list.append(
            {
                "strategy_family": "PORTFOLIO",
                "strategy_name": "Combined_All_Strategies",
                "quality_flag": "AGGREGATE",
                "total_trades": len(combo_df),
                "is_trades": stats["is_trades"],
                "oos_trades": stats["oos_trades"],
                "full_pf": round(stats["full_pf"], 2),
                "is_pf_pre_2019": round(stats["is_pf"], 2),
                "oos_pf_post_2019": round(stats["oos_pf"], 2),
                "recent_12m_pf": round(stats["recent_pf"], 2),
                "net_pnl": round(stats["full_net"], 2),
                "max_drawdown": round(stats["max_dd"], 2),
                "mc_max_dd_99": round(mc["mc_dd_99"], 2),
                "shock_drop_10pct_pnl": round(mc["shock_drop_10_pct_pnl"], 2),
                "shock_extra_slip_pnl": round(shock_pnl, 2),
            }
        )

    returns_df = pd.DataFrame(daily_returns_dict).fillna(0)
    corr_df = returns_df.corr() if not returns_df.empty else pd.DataFrame()
    yearly_df = pd.DataFrame(yearly_stats_list)

    return pd.DataFrame(results_list), returns_df, corr_df, yearly_df