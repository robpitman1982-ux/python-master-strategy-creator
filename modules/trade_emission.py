"""Canonical per-trade artifact emission for accepted strategies.

Sprint 84 - bakes strategy_trades.csv and strategy_returns.csv into the canonical
sweep finalize path. Runs unconditionally on every accepted strategy regardless
of skip_portfolio_evaluation, so post_ultimate_gate concentration check and
selector cost-aware MC always have real per-trade data to consume.

Schema of strategy_trades.csv matches generate_returns.py output exactly so
downstream consumers (post_ultimate_gate, portfolio_selector) need no changes.

Parity check: rebuilt net_pnl sum must be within 1% of leader_net_pnl from
family leaderboard, OR within $100 absolute when leader_net_pnl is small. If
parity fails the strategy gets trade_artifact_status = PARITY_FAILED, and the
post_ultimate_gate fails it closed.
"""
from __future__ import annotations

import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from modules.portfolio_evaluator import _rebuild_strategy_from_leaderboard_row


PARITY_REL_TOLERANCE = 0.01    # rebuilt within 1% of leader_net_pnl
PARITY_ABS_TOLERANCE = 100.0   # ... or $100 absolute, whichever is looser


@dataclass(frozen=True)
class StrategyEmissionResult:
    """Result of emitting per-trade artifacts for a single strategy."""

    strategy_key: str            # "{strategy_type}_{leader_strategy_name}"
    status: str                  # OK | PARITY_FAILED | REBUILD_FAILED | NO_TRADES
    n_trades: int
    rebuilt_net_pnl: float
    leader_net_pnl: float
    parity_ratio: float          # rebuilt / leader, NaN if leader == 0


def _parity_status(rebuilt: float, leader: float) -> tuple[str, float]:
    """Return (status, parity_ratio) for a rebuilt vs leader net_pnl pair."""
    if not pd.notna(leader):
        # Leaderboard didn't report a comparison value - accept rebuild as-is.
        return "OK", float("nan")

    abs_diff = abs(rebuilt - leader)
    if abs_diff <= PARITY_ABS_TOLERANCE:
        ratio = (rebuilt / leader) if abs(leader) > 1e-9 else float("nan")
        return "OK", ratio

    if abs(leader) < 1e-9:
        # Leader near-zero, abs_diff above absolute tolerance => fail.
        return "PARITY_FAILED", float("nan")

    rel_diff = abs_diff / abs(leader)
    if rel_diff <= PARITY_REL_TOLERANCE:
        return "OK", rebuilt / leader
    return "PARITY_FAILED", rebuilt / leader


def _strategy_key(row: pd.Series) -> str:
    """Build the canonical strategy column key."""
    strategy_type = str(row.get("strategy_type", "")).strip()
    leader_name = str(row.get("leader_strategy_name", "")).strip()
    return f"{strategy_type}_{leader_name}" if strategy_type else leader_name


def _emit_one(
    row: pd.Series,
    data: pd.DataFrame,
    outputs_dir: Path,
    market: str,
    timeframe: str,
) -> tuple[StrategyEmissionResult, list[dict[str, Any]], pd.Series | None]:
    """Rebuild a single strategy and return (result, per_trade_rows, daily_pnl).

    per_trade_rows matches the schema expected by generate_returns.py:
        exit_time, strategy, net_pnl, entry_time, direction, entry_price,
        exit_price, bars_held
    """
    strategy_key = _strategy_key(row)
    leader_net_pnl = float(row.get("leader_net_pnl", 0.0) or 0.0)

    if not strategy_key or strategy_key in {"_", "NONE_NONE"}:
        return (
            StrategyEmissionResult(
                strategy_key=strategy_key or "UNKNOWN",
                status="REBUILD_FAILED",
                n_trades=0,
                rebuilt_net_pnl=0.0,
                leader_net_pnl=leader_net_pnl,
                parity_ratio=float("nan"),
            ),
            [],
            None,
        )

    try:
        trades_df, _filters_str, _cfg = _rebuild_strategy_from_leaderboard_row(
            row=row,
            data=data,
            outputs_dir=outputs_dir,
            market_symbol=market,
            timeframe=timeframe,
        )
    except Exception as exc:
        print(f"    [trade_emission] REBUILD FAILED for {strategy_key}: {exc}")
        traceback.print_exc()
        return (
            StrategyEmissionResult(
                strategy_key=strategy_key,
                status="REBUILD_FAILED",
                n_trades=0,
                rebuilt_net_pnl=0.0,
                leader_net_pnl=leader_net_pnl,
                parity_ratio=float("nan"),
            ),
            [],
            None,
        )

    if trades_df is None or trades_df.empty:
        return (
            StrategyEmissionResult(
                strategy_key=strategy_key,
                status="NO_TRADES",
                n_trades=0,
                rebuilt_net_pnl=0.0,
                leader_net_pnl=leader_net_pnl,
                parity_ratio=float("nan"),
            ),
            [],
            None,
        )

    trades_df = trades_df.copy()
    trades_df["exit_time"] = pd.to_datetime(trades_df["exit_time"])
    trades_df["net_pnl"] = pd.to_numeric(trades_df["net_pnl"], errors="coerce").fillna(0.0)

    rebuilt_net_pnl = float(trades_df["net_pnl"].sum())
    daily_pnl = trades_df.resample("D", on="exit_time")["net_pnl"].sum().fillna(0.0)

    per_trade_rows: list[dict[str, Any]] = []
    optional_cols = ("entry_time", "direction", "entry_price", "exit_price", "bars_held")
    for _, trade in trades_df.iterrows():
        out_row: dict[str, Any] = {
            "exit_time": str(trade["exit_time"]),
            "strategy": strategy_key,
            "net_pnl": float(trade["net_pnl"]),
        }
        for col in optional_cols:
            if col in trade.index and pd.notna(trade[col]):
                out_row[col] = trade[col]
        per_trade_rows.append(out_row)

    status, parity_ratio = _parity_status(rebuilt_net_pnl, leader_net_pnl)

    return (
        StrategyEmissionResult(
            strategy_key=strategy_key,
            status=status,
            n_trades=int(len(trades_df)),
            rebuilt_net_pnl=rebuilt_net_pnl,
            leader_net_pnl=leader_net_pnl,
            parity_ratio=parity_ratio,
        ),
        per_trade_rows,
        daily_pnl,
    )


def emit_trade_artifacts(
    leaderboard_csv: Path,
    data: pd.DataFrame,
    output_dir: Path,
    market: str,
    timeframe: str,
) -> dict[str, StrategyEmissionResult]:
    """Emit strategy_trades.csv and strategy_returns.csv for all accepted rows.

    Args:
        leaderboard_csv: Path to family_leaderboard_results.csv. Must already exist.
        data: Pre-loaded market OHLC DataFrame (engine-ready).
        output_dir: Where to write strategy_trades.csv and strategy_returns.csv.
            Typically the same directory as leaderboard_csv.
        market: Market symbol (e.g. ES). Used for EngineConfig.
        timeframe: Timeframe string (e.g. 60m). Used for feature precompute.

    Returns:
        Dict mapping strategy_key -> StrategyEmissionResult with parity status.
        Caller is expected to merge this into family_leaderboard_results.csv
        via apply_parity_status().
    """
    leaderboard_csv = Path(leaderboard_csv)
    output_dir = Path(output_dir)

    if not leaderboard_csv.exists():
        return {}

    leaderboard_df = pd.read_csv(leaderboard_csv)
    if leaderboard_df.empty or "accepted_final" not in leaderboard_df.columns:
        return {}

    accepted = leaderboard_df[
        leaderboard_df["accepted_final"].astype(str).str.strip().str.lower() == "true"
    ].copy()
    if accepted.empty:
        return {}

    # Honour the alias used by generate_returns.py for stop-distance column
    if (
        "leader_stop_distance_atr" in accepted.columns
        and "leader_stop_distance_points" not in accepted.columns
    ):
        accepted["leader_stop_distance_points"] = accepted["leader_stop_distance_atr"]

    print(
        f"[trade_emission] Emitting trade artifacts for {len(accepted)} accepted strategies"
        f" ({market} {timeframe})"
    )

    results: dict[str, StrategyEmissionResult] = {}
    daily_returns: dict[str, pd.Series] = {}
    all_trade_rows: list[dict[str, Any]] = []

    for _, row in accepted.iterrows():
        result, per_trade_rows, daily_pnl = _emit_one(
            row=row,
            data=data,
            outputs_dir=leaderboard_csv.parent,
            market=market,
            timeframe=timeframe,
        )
        results[result.strategy_key] = result
        if per_trade_rows and daily_pnl is not None:
            all_trade_rows.extend(per_trade_rows)
            daily_returns[result.strategy_key] = daily_pnl
            tag = "OK" if result.status == "OK" else result.status
            print(
                f"    [trade_emission] {result.strategy_key}: {result.n_trades} trades, "
                f"rebuilt=${result.rebuilt_net_pnl:,.2f} leader=${result.leader_net_pnl:,.2f} "
                f"[{tag}]"
            )
        else:
            print(
                f"    [trade_emission] {result.strategy_key}: {result.status} "
                f"(no trades emitted)"
            )

    if not all_trade_rows:
        print("[trade_emission] No trades emitted - nothing to write.")
        return results

    output_dir.mkdir(parents=True, exist_ok=True)

    trades_df_out = pd.DataFrame(all_trade_rows).sort_values("exit_time")
    trades_path = output_dir / "strategy_trades.csv"
    trades_df_out.to_csv(trades_path, index=False)
    print(
        f"[trade_emission] Wrote {trades_path} ({len(trades_df_out)} trade rows, "
        f"{len(daily_returns)} strategies)"
    )

    returns_df_out = pd.DataFrame(daily_returns).fillna(0.0)
    returns_df_out.index.name = "exit_time"
    returns_path = output_dir / "strategy_returns.csv"
    returns_df_out.to_csv(returns_path)
    print(
        f"[trade_emission] Wrote {returns_path} ({len(returns_df_out)} days, "
        f"{len(returns_df_out.columns)} strategies)"
    )

    return results


def apply_parity_status(
    leaderboard_csv: Path, results: dict[str, StrategyEmissionResult]
) -> None:
    """Patch family_leaderboard_results.csv with a trade_artifact_status column.

    Adds (or replaces):
        trade_artifact_status:  OK | PARITY_FAILED | REBUILD_FAILED | NO_TRADES | SKIPPED
        trade_artifact_n_trades: integer
        trade_artifact_rebuilt_net_pnl: float
        trade_artifact_parity_ratio: float (rebuilt / leader; nan if leader was 0)

    Rows whose strategy_key is not in results (or whose accepted_final is False)
    are marked SKIPPED.
    """
    leaderboard_csv = Path(leaderboard_csv)
    if not leaderboard_csv.exists():
        return

    try:
        df = pd.read_csv(leaderboard_csv)
    except pd.errors.EmptyDataError:
        return
    if df.empty:
        return

    def _row_key(row: pd.Series) -> str:
        return _strategy_key(row)

    keys = df.apply(_row_key, axis=1)
    accepted_mask = (
        df.get("accepted_final", pd.Series([False] * len(df)))
        .astype(str)
        .str.strip()
        .str.lower()
        == "true"
    )

    statuses: list[str] = []
    n_trades: list[int] = []
    rebuilt: list[float] = []
    ratios: list[float] = []

    for key, accepted in zip(keys, accepted_mask):
        if not accepted:
            statuses.append("SKIPPED")
            n_trades.append(0)
            rebuilt.append(0.0)
            ratios.append(float("nan"))
            continue

        result = results.get(key)
        if result is None:
            statuses.append("REBUILD_FAILED")
            n_trades.append(0)
            rebuilt.append(0.0)
            ratios.append(float("nan"))
            continue

        statuses.append(result.status)
        n_trades.append(result.n_trades)
        rebuilt.append(result.rebuilt_net_pnl)
        ratios.append(result.parity_ratio)

    df["trade_artifact_status"] = statuses
    df["trade_artifact_n_trades"] = n_trades
    df["trade_artifact_rebuilt_net_pnl"] = rebuilt
    df["trade_artifact_parity_ratio"] = ratios

    df.to_csv(leaderboard_csv, index=False)
    n_ok = sum(1 for s in statuses if s == "OK")
    n_failed = sum(1 for s in statuses if s in {"PARITY_FAILED", "REBUILD_FAILED", "NO_TRADES"})
    print(
        f"[trade_emission] Patched {leaderboard_csv.name}: "
        f"{n_ok} OK, {n_failed} failed, "
        f"{len(statuses) - n_ok - n_failed} SKIPPED"
    )
