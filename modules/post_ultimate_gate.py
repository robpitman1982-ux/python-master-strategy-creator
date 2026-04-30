from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from modules.leaderboard_ranking import sort_aggregate_leaderboard
from modules.ultimate_leaderboard import (
    CFD_ULTIMATE_FILENAME,
    FUTURES_ULTIMATE_FILENAME,
    LEGACY_ULTIMATE_FILENAME,
    collect_accepted_ultimate_rows,
)

POST_GATE_AUDIT_SUFFIX = "_post_gate_audit.csv"
POST_GATE_GATED_SUFFIX = "_gated.csv"


def _parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _numeric(value: Any, default: float = math.nan) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dataset_folder_from_name(dataset: str) -> str:
    text = str(dataset or "").replace("_tradestation.csv", "").replace(".csv", "")
    parts = text.split("_")
    if len(parts) >= 2:
        return f"{parts[0]}_{parts[1]}"
    return text


def _find_trades_file(row: pd.Series, runs_root: Path) -> Path | None:
    run_id = str(row.get("run_id", "")).strip()
    dataset = str(row.get("dataset", "")).strip()
    if not run_id or not dataset:
        return None

    dataset_folder = _dataset_folder_from_name(dataset)
    candidates = [
        runs_root / run_id / "Outputs" / dataset_folder / "strategy_trades.csv",
        runs_root / run_id / "artifacts" / "Outputs" / dataset_folder / "strategy_trades.csv",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _match_trade_strategy_column(df: pd.DataFrame, row: pd.Series) -> pd.Series:
    if "strategy" not in df.columns or "net_pnl" not in df.columns:
        return pd.Series(dtype=float)

    leader_name = str(row.get("leader_strategy_name", "")).strip()
    strategy_type = str(row.get("strategy_type", "")).strip()
    qualified_name = f"{strategy_type}_{leader_name}" if strategy_type else leader_name

    mask = df["strategy"].astype(str) == qualified_name
    if int(mask.sum()) == 0 and leader_name:
        mask = df["strategy"].astype(str).str.contains(leader_name, na=False)
    return pd.to_numeric(df.loc[mask, "net_pnl"], errors="coerce").dropna()


def _gini(values: list[float]) -> float:
    if not values:
        return math.nan
    arr = np.asarray(sorted(v for v in values if math.isfinite(v) and v > 0.0), dtype=float)
    if arr.size == 0:
        return math.nan
    total = float(arr.sum())
    if total <= 0.0:
        return math.nan
    n = arr.size
    index = np.arange(1, n + 1, dtype=float)
    return float((2.0 * np.sum(index * arr)) / (n * total) - (n + 1) / n)


def _equity_flat_time_pct(trades: list[float]) -> float:
    if not trades:
        return math.nan
    equity = 0.0
    peak = 0.0
    underwater = 0
    for trade in trades:
        equity += float(trade)
        peak = max(peak, equity)
        if equity < peak:
            underwater += 1
    return underwater / len(trades)


def _concentration_metrics(trades: list[float]) -> dict[str, float]:
    if not trades:
        return {
            "trade_pnl_gini": math.nan,
            "top_5pct_profit_contribution": math.nan,
            "equity_flat_time_pct": math.nan,
            "loaded_trade_count": 0.0,
        }

    winners = sorted((float(t) for t in trades if float(t) > 0.0), reverse=True)
    net_profit = float(sum(trades))
    top_n = max(1, int(math.ceil(len(trades) * 0.05)))
    top_profit = float(sum(winners[:top_n])) if winners else 0.0

    if net_profit > 0.0:
        top_contrib = top_profit / net_profit
    elif top_profit > 0.0:
        top_contrib = float("inf")
    else:
        top_contrib = math.nan

    return {
        "trade_pnl_gini": _gini(winners),
        "top_5pct_profit_contribution": top_contrib,
        "equity_flat_time_pct": _equity_flat_time_pct(trades),
        "loaded_trade_count": float(len(trades)),
    }


def _same_signature_mask(raw_pool: pd.DataFrame, row: pd.Series) -> pd.Series:
    mask = pd.Series(True, index=raw_pool.index)
    for col in ("dataset", "strategy_type", "best_combo_filter_class_names", "leader_exit_type"):
        if col in raw_pool.columns:
            mask &= raw_pool[col].astype(str) == str(row.get(col, ""))
    return mask


def _neighbor_mask(raw_pool: pd.DataFrame, row: pd.Series) -> pd.Series:
    mask = _same_signature_mask(raw_pool, row)
    if "leader_strategy_name" in raw_pool.columns:
        mask &= raw_pool["leader_strategy_name"].astype(str) != str(row.get("leader_strategy_name", ""))

    thresholds = {
        "leader_hold_bars": 1.0,
        "leader_stop_distance_atr": 0.25,
        "leader_profit_target_atr": 0.25,
        "leader_trailing_stop_atr": 0.25,
        "leader_min_avg_range": 0.25,
        "leader_momentum_lookback": 1.0,
    }

    any_diff = pd.Series(False, index=raw_pool.index)
    compared = False
    for col, threshold in thresholds.items():
        if col not in raw_pool.columns:
            continue
        current = _numeric(row.get(col), default=math.nan)
        if not math.isfinite(current):
            continue
        pool_vals = pd.to_numeric(raw_pool[col], errors="coerce")
        close = (pool_vals - current).abs() <= threshold
        same = (pool_vals - current).abs() < 1e-12
        mask &= close.fillna(False)
        any_diff |= (~same.fillna(False)) & close.fillna(False)
        compared = True

    if compared:
        mask &= any_diff
    return mask


def _fragility_metrics(raw_pool: pd.DataFrame, row: pd.Series) -> dict[str, Any]:
    if raw_pool.empty:
        return {
            "neighbor_count": 0,
            "neighbor_median_oos_pf": math.nan,
            "neighbor_median_oos_pf_ratio": math.nan,
            "neighbor_weak_frac": math.nan,
            "fragility_status": "NO_RAW_POOL",
        }

    neighbors = raw_pool[_neighbor_mask(raw_pool, row)].copy()
    if neighbors.empty or "oos_pf" not in neighbors.columns:
        return {
            "neighbor_count": 0,
            "neighbor_median_oos_pf": math.nan,
            "neighbor_median_oos_pf_ratio": math.nan,
            "neighbor_weak_frac": math.nan,
            "fragility_status": "INSUFFICIENT_NEIGHBORS",
        }

    oos_vals = pd.to_numeric(neighbors["oos_pf"], errors="coerce").dropna()
    if oos_vals.empty:
        return {
            "neighbor_count": 0,
            "neighbor_median_oos_pf": math.nan,
            "neighbor_median_oos_pf_ratio": math.nan,
            "neighbor_weak_frac": math.nan,
            "fragility_status": "INSUFFICIENT_NEIGHBORS",
        }

    current_oos = max(_numeric(row.get("oos_pf"), default=0.0), 1e-9)
    weak_frac = float((oos_vals < 1.0).mean())
    median_oos = float(oos_vals.median())
    return {
        "neighbor_count": int(len(oos_vals)),
        "neighbor_median_oos_pf": median_oos,
        "neighbor_median_oos_pf_ratio": median_oos / current_oos,
        "neighbor_weak_frac": weak_frac,
        "fragility_status": "EVIDENCED",
    }


def _post_gate_pass(row: pd.Series) -> bool:
    concentration_pass = _parse_bool(row.get("gate_concentration_pass", False))
    fragility_state = str(row.get("gate_fragility_status", ""))
    fragility_pass = _parse_bool(row.get("gate_fragility_pass", False))
    if not concentration_pass:
        return False
    if fragility_state == "EVIDENCED" and not fragility_pass:
        return False
    return True


def sort_post_gated_leaderboard(df: pd.DataFrame) -> pd.DataFrame:
    ranked = df.copy()
    ranked["_post_gate_pass"] = ranked.get("post_gate_pass", pd.Series(False, index=ranked.index)).astype(bool)
    ranked["_concentration_pass"] = ranked.get("gate_concentration_pass", pd.Series(False, index=ranked.index)).astype(bool)
    ranked["_fragility_evidenced"] = ranked.get("gate_fragility_status", pd.Series("", index=ranked.index)).astype(str).eq("EVIDENCED")
    ranked["_fragility_pass"] = ranked.get("gate_fragility_pass", pd.Series(False, index=ranked.index)).astype(bool)
    ranked["_neighbor_ratio"] = pd.to_numeric(ranked.get("gate_neighbor_median_oos_pf_ratio", pd.Series(dtype=float)), errors="coerce").fillna(-1.0)
    ranked["_top5"] = pd.to_numeric(ranked.get("gate_top_5pct_profit_contribution", pd.Series(dtype=float)), errors="coerce").fillna(float("inf"))
    ranked["_flat"] = pd.to_numeric(ranked.get("gate_equity_flat_time_pct", pd.Series(dtype=float)), errors="coerce").fillna(float("inf"))
    ranked["_gini"] = pd.to_numeric(ranked.get("gate_trade_pnl_gini", pd.Series(dtype=float)), errors="coerce").fillna(float("inf"))
    ranked["_accepted"] = ranked.get("accepted_final", pd.Series(True, index=ranked.index)).apply(_parse_bool)
    ranked["_quality"] = ranked.get("quality_flag", pd.Series("", index=ranked.index)).map(
        lambda v: {"ROBUST": 0, "ROBUST_BORDERLINE": 1, "STABLE": 2, "STABLE_BORDERLINE": 3}.get(str(v).upper().strip(), 99)
    )
    ranked["_oos_pf"] = pd.to_numeric(ranked.get("oos_pf", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    ranked["_recent_pf"] = pd.to_numeric(ranked.get("recent_12m_pf", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    ranked["_calmar"] = pd.to_numeric(ranked.get("calmar_ratio", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    ranked["_dsr"] = pd.to_numeric(ranked.get("deflated_sharpe_ratio", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    ranked["_leader_pf"] = pd.to_numeric(ranked.get("leader_pf", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    ranked["_max_dd"] = pd.to_numeric(ranked.get("leader_max_drawdown", pd.Series(dtype=float)), errors="coerce").fillna(float("inf")).abs()
    ranked["_net_pnl"] = pd.to_numeric(ranked.get("leader_net_pnl", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    ranked["_tpy"] = pd.to_numeric(ranked.get("leader_trades_per_year", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    ranked = ranked.sort_values(
        by=[
            "_post_gate_pass",
            "_concentration_pass",
            "_fragility_evidenced",
            "_fragility_pass",
            "_neighbor_ratio",
            "_top5",
            "_flat",
            "_gini",
            "_accepted",
            "_quality",
            "_oos_pf",
            "_recent_pf",
            "_calmar",
            "_dsr",
            "_leader_pf",
            "_max_dd",
            "_net_pnl",
            "_tpy",
        ],
        ascending=[False, False, False, False, False, True, True, True, False, True, False, False, False, False, False, True, False, False],
        kind="mergesort",
    )
    ranked = ranked.drop(columns=[c for c in ranked.columns if c.startswith("_")], errors="ignore").reset_index(drop=True)
    if "rank" in ranked.columns:
        ranked = ranked.drop(columns=["rank"])
    ranked.insert(0, "rank", ranked.index + 1)
    return ranked


def _gated_output_paths(base_output: Path) -> tuple[Path, Path, list[Path]]:
    audit_path = base_output.with_name(f"{base_output.stem}{POST_GATE_AUDIT_SUFFIX}")
    gated_path = base_output.with_name(f"{base_output.stem}{POST_GATE_GATED_SUFFIX}")
    aliases: list[Path] = []
    if base_output.name == FUTURES_ULTIMATE_FILENAME:
        aliases = [
            base_output.parent / f"{Path(LEGACY_ULTIMATE_FILENAME).stem}{POST_GATE_AUDIT_SUFFIX}",
            base_output.parent / f"{Path(LEGACY_ULTIMATE_FILENAME).stem}{POST_GATE_GATED_SUFFIX}",
        ]
    return audit_path, gated_path, aliases


def build_post_ultimate_gate(
    *,
    storage_root: Path,
    source_path: Path,
    output_dir: Path | None = None,
    max_profit_gini: float = 0.60,
    max_top_5pct_profit_contribution: float = 0.40,
    max_equity_flat_time_pct: float = 0.40,
    min_neighbor_count: int = 3,
    min_neighbor_median_ratio: float = 0.70,
    max_neighbor_weak_frac: float = 0.20,
) -> dict[str, Any]:
    storage_root = Path(storage_root)
    source_path = Path(source_path)
    output_dir = output_dir or source_path.parent
    runs_root = storage_root / "runs"

    audit_path, gated_path, alias_paths = _gated_output_paths(output_dir / source_path.name)

    if not source_path.exists():
        return {
            "audit_path": str(audit_path),
            "gated_path": str(gated_path),
            "audit_rows": 0,
            "gated_rows": 0,
        }

    df = pd.read_csv(source_path)
    if df.empty:
        df.to_csv(audit_path, index=False)
        df.to_csv(gated_path, index=False)
        for alias in alias_paths:
            df.to_csv(alias, index=False)
        return {
            "audit_path": str(audit_path),
            "gated_path": str(gated_path),
            "audit_rows": 0,
            "gated_rows": 0,
        }

    raw_pool = collect_accepted_ultimate_rows(storage_root=storage_root, verbose=False)

    enriched_rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        row_dict = row.to_dict()

        trades_path = _find_trades_file(row, runs_root)
        trade_metrics = {
            "trade_pnl_gini": math.nan,
            "top_5pct_profit_contribution": math.nan,
            "equity_flat_time_pct": math.nan,
            "loaded_trade_count": 0.0,
        }
        if trades_path is not None:
            try:
                trades_df = pd.read_csv(trades_path)
                trade_series = _match_trade_strategy_column(trades_df, row)
                trade_metrics = _concentration_metrics(trade_series.tolist())
            except Exception:
                pass

        fragility = _fragility_metrics(raw_pool, row)
        concentration_pass = True
        if math.isfinite(trade_metrics["trade_pnl_gini"]):
            concentration_pass &= trade_metrics["trade_pnl_gini"] <= max_profit_gini
        if math.isfinite(trade_metrics["top_5pct_profit_contribution"]):
            concentration_pass &= trade_metrics["top_5pct_profit_contribution"] <= max_top_5pct_profit_contribution
        if math.isfinite(trade_metrics["equity_flat_time_pct"]):
            concentration_pass &= trade_metrics["equity_flat_time_pct"] <= max_equity_flat_time_pct

        fragility_pass = True
        if fragility["fragility_status"] == "EVIDENCED":
            fragility_pass = (
                fragility["neighbor_count"] >= min_neighbor_count
                and fragility["neighbor_median_oos_pf_ratio"] >= min_neighbor_median_ratio
                and fragility["neighbor_weak_frac"] <= max_neighbor_weak_frac
            )

        row_dict["gate_trade_pnl_gini"] = trade_metrics["trade_pnl_gini"]
        row_dict["gate_top_5pct_profit_contribution"] = trade_metrics["top_5pct_profit_contribution"]
        row_dict["gate_equity_flat_time_pct"] = trade_metrics["equity_flat_time_pct"]
        row_dict["gate_loaded_trade_count"] = int(trade_metrics["loaded_trade_count"])
        row_dict["gate_concentration_pass"] = concentration_pass

        row_dict["gate_neighbor_count"] = fragility["neighbor_count"]
        row_dict["gate_neighbor_median_oos_pf"] = fragility["neighbor_median_oos_pf"]
        row_dict["gate_neighbor_median_oos_pf_ratio"] = fragility["neighbor_median_oos_pf_ratio"]
        row_dict["gate_neighbor_weak_frac"] = fragility["neighbor_weak_frac"]
        row_dict["gate_fragility_status"] = fragility["fragility_status"]
        row_dict["gate_fragility_pass"] = fragility_pass
        row_dict["post_gate_pass"] = _post_gate_pass(pd.Series(row_dict))
        enriched_rows.append(row_dict)

    audit_df = pd.DataFrame(enriched_rows)
    audit_df = sort_post_gated_leaderboard(audit_df)
    gated_df = sort_post_gated_leaderboard(audit_df[audit_df["post_gate_pass"].astype(bool)].copy())

    audit_df.to_csv(audit_path, index=False)
    gated_df.to_csv(gated_path, index=False)
    for alias in alias_paths:
        if alias.name.endswith(POST_GATE_AUDIT_SUFFIX):
            audit_df.to_csv(alias, index=False)
        elif alias.name.endswith(POST_GATE_GATED_SUFFIX):
            gated_df.to_csv(alias, index=False)

    if source_path.name == CFD_ULTIMATE_FILENAME:
        # No extra alias needed, but make the intent explicit in the result payload.
        alias_written = []
    else:
        alias_written = [str(path) for path in alias_paths]

    return {
        "audit_path": str(audit_path),
        "gated_path": str(gated_path),
        "alias_paths": alias_written,
        "audit_rows": int(len(audit_df)),
        "gated_rows": int(len(gated_df)),
    }
