"""
Portfolio Selector — Automated Portfolio Selection for Prop Firm Challenges

Takes the ultimate leaderboard (multi-market, multi-timeframe) and selects
the optimal portfolio of strategies by:

1. Hard-filtering candidates (quality, OOS PF, trade count, dedup)
2. Building a daily return matrix from strategy_returns.csv files
3. Computing true Pearson correlation from daily P&L
4. Sweeping C(n, k) combinations with correlation gate
5. Running portfolio Monte Carlo through the Bootcamp 3-step cascade
6. Optimising position sizing weights

Usage:
    from modules.portfolio_selector import run_portfolio_selection
    run_portfolio_selection()
"""
from __future__ import annotations

import csv
import itertools
import logging
import os
import random
from concurrent.futures import ProcessPoolExecutor, as_completed
from math import comb
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np
import pandas as pd

from modules.prop_firm_simulator import (
    The5ersBootcampConfig,
    The5ersHighStakesConfig,
    The5ersHyperGrowthConfig,
    The5ersProGrowthConfig,
    PropFirmConfig,
    simulate_challenge,
    simulate_challenge_batch,
    _scale_trade_pnl,
)

logger = logging.getLogger(__name__)

_PROGRAM_FACTORIES = {
    "bootcamp": The5ersBootcampConfig,
    "high_stakes": The5ersHighStakesConfig,
    "hyper_growth": The5ersHyperGrowthConfig,
    "pro_growth": The5ersProGrowthConfig,
}


def _resolve_prop_config(program: str, target: float) -> PropFirmConfig:
    """Resolve a prop firm config from program name and target balance."""
    factory = _PROGRAM_FACTORIES.get(program)
    if factory is None:
        logger.warning(f"Unknown program '{program}', falling back to bootcamp")
        factory = The5ersBootcampConfig
    return factory(target)


# ============================================================================
# STAGE 1: Hard filter candidates
# ============================================================================

def hard_filter_candidates(
    leaderboard_path: str,
    oos_pf_threshold: float = 1.0,
    bootcamp_score_min: float = 40,
    candidate_cap: int = 50,
    quality_flags: list[str] | None = None,
) -> list[dict]:
    """Load ultimate_leaderboard_bootcamp.csv and apply hard filters.

    Filters:
    - quality_flag in quality_flags (default ROBUST, STABLE)
    - oos_pf > oos_pf_threshold (default 1.0)
    - bootcamp_score > bootcamp_score_min (default 40)
    - leader_trades >= 60 (fallback to total_trades)
    - Dedup: same best_refined_strategy_name + market -> keep highest bootcamp_score
    - Cap at candidate_cap candidates by bootcamp_score
    """
    df = pd.read_csv(leaderboard_path)
    n_total = len(df)
    logger.info(f"Loaded {n_total} rows from {leaderboard_path}")

    # Quality filter
    valid_flags = set(f.upper().strip() for f in (quality_flags or ["ROBUST", "STABLE"]))
    df = df[df["quality_flag"].astype(str).str.strip().str.upper().isin(valid_flags)].copy()
    logger.info(f"After quality filter ({', '.join(sorted(valid_flags))}): {len(df)}")

    # OOS PF filter
    df["oos_pf"] = pd.to_numeric(df.get("oos_pf", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    df = df[df["oos_pf"] > oos_pf_threshold].copy()
    logger.info(f"After OOS PF > {oos_pf_threshold}: {len(df)}")

    # Bootcamp score filter
    if "bootcamp_score" in df.columns:
        df["bootcamp_score"] = pd.to_numeric(df["bootcamp_score"], errors="coerce").fillna(0)
        df = df[df["bootcamp_score"] > bootcamp_score_min].copy()
        logger.info(f"After bootcamp_score > {bootcamp_score_min}: {len(df)}")

    # Trade count filter
    if "leader_trades" in df.columns:
        trades_col = pd.to_numeric(df["leader_trades"], errors="coerce").fillna(0)
    elif "total_trades" in df.columns:
        trades_col = pd.to_numeric(df["total_trades"], errors="coerce").fillna(0)
    else:
        trades_col = pd.Series(0, index=df.index)
    df = df[trades_col >= 60].copy()
    logger.info(f"After trades >= 60: {len(df)}")

    if df.empty:
        logger.warning("No candidates passed hard filters")
        return []

    # Dedup: same best_refined_strategy_name + market -> keep highest bootcamp_score
    score_col = "bootcamp_score" if "bootcamp_score" in df.columns else "leader_pf"
    df["_score"] = pd.to_numeric(df.get(score_col, pd.Series(0, index=df.index)), errors="coerce").fillna(0)

    dedup_key_col = "best_refined_strategy_name" if "best_refined_strategy_name" in df.columns else "leader_strategy_name"
    market_col = "market" if "market" in df.columns else None

    if market_col:
        df["_dedup_key"] = df[dedup_key_col].astype(str) + "|" + df[market_col].astype(str)
    else:
        df["_dedup_key"] = df[dedup_key_col].astype(str)

    df = df.sort_values("_score", ascending=False).drop_duplicates(subset="_dedup_key", keep="first")
    logger.info(f"After dedup: {len(df)}")

    # Cap at candidate_cap
    if len(df) > candidate_cap:
        n_before = len(df)
        df = df.nlargest(candidate_cap, "_score")
        logger.warning(f"Capped candidates from {n_before} to {candidate_cap} by {score_col}")

    df = df.drop(columns=["_score", "_dedup_key"], errors="ignore")
    result = df.to_dict("records")
    logger.info(f"Hard filter: {n_total} -> {len(result)} candidates")
    return result


# ============================================================================
# STAGE 2: Build return matrix
# ============================================================================

def _find_returns_file(candidate: dict, runs_base: str) -> str | None:
    """Find strategy_returns.csv for a candidate.

    First checks the candidate's own run_id directory. If not found, scans
    ALL other runs for the same market/timeframe — this handles S54 re-sweep
    runs that don't generate strategy_returns.csv but whose strategies can
    be matched against returns from earlier runs of the same dataset.
    """
    run_id = str(candidate.get("run_id", ""))
    dataset = str(candidate.get("dataset", ""))

    if not dataset:
        return None

    # Derive dataset folder: "ES_30m_2008_2026_tradestation.csv" -> "ES_30m"
    parts = dataset.replace("_tradestation.csv", "").split("_")
    if len(parts) >= 2:
        dataset_folder = f"{parts[0]}_{parts[1]}"
    else:
        dataset_folder = dataset.replace(".csv", "")

    if run_id:
        path = os.path.join(runs_base, run_id, "Outputs", dataset_folder, "strategy_returns.csv")
        if os.path.exists(path):
            return path

        # Try with artifacts/ prefix (cloud download layout)
        path2 = os.path.join(runs_base, run_id, "artifacts", "Outputs", dataset_folder, "strategy_returns.csv")
        if os.path.exists(path2):
            return path2

    # Fallback: scan ALL runs for the same market/timeframe
    try:
        for other_run in sorted(os.listdir(runs_base), reverse=True):
            if other_run == run_id:
                continue
            for sub in ("Outputs", os.path.join("artifacts", "Outputs")):
                fallback = os.path.join(runs_base, other_run, sub, dataset_folder, "strategy_returns.csv")
                if os.path.exists(fallback):
                    return fallback
    except OSError:
        pass

    return None


def _match_column(columns: list[str], leader_name: str, strategy_type: str = "") -> str | None:
    """Match a leader strategy name to a column in strategy_returns.csv."""
    leader_name = str(leader_name).strip()
    if not leader_name:
        return None

    # If strategy_type provided, try type-qualified match first
    if strategy_type:
        qualified = f"{strategy_type}_{leader_name}"
        if qualified in columns:
            return qualified
        for col in columns:
            if col.endswith(qualified):
                return col

    # Exact match
    if leader_name in columns:
        return leader_name

    # endswith match (handles timestamp prefix)
    for col in columns:
        if col.endswith(leader_name):
            return col

    # Substring match
    for col in columns:
        if leader_name in col:
            return col

    return None


def build_return_matrix(
    candidates: list[dict],
    runs_base_path: str,
) -> pd.DataFrame:
    """Build a daily return matrix from strategy_returns.csv files.

    Returns DataFrame with one column per strategy (daily PnL), index = date.
    """
    daily_series: dict[str, pd.Series] = {}
    candidate_map: dict[str, dict] = {}  # strategy_label -> candidate dict

    for cand in candidates:
        leader_name = str(cand.get("leader_strategy_name", "")).strip()
        if not leader_name:
            continue

        returns_path = _find_returns_file(cand, runs_base_path)
        if returns_path is None:
            logger.warning(f"No strategy_returns.csv found for {leader_name}")
            continue

        try:
            df = pd.read_csv(returns_path)
        except Exception as e:
            logger.warning(f"Could not read {returns_path}: {e}")
            continue

        if "exit_time" not in df.columns:
            logger.warning(f"No exit_time column in {returns_path}")
            continue

        cols = [c for c in df.columns if c != "exit_time"]
        strat_type = str(cand.get("strategy_type", "")).strip()
        matched_col = _match_column(cols, leader_name, strategy_type=strat_type)

        if matched_col is None:
            # Try best_refined_strategy_name
            refined_name = str(cand.get("best_refined_strategy_name", "")).strip()
            if refined_name:
                matched_col = _match_column(cols, refined_name, strategy_type=strat_type)

        if matched_col is None:
            # Fallback: match by strategy_type prefix only (ignoring specific refined params).
            # This handles S54 re-sweep strategies that found different refined params
            # but trade the same market/timeframe/family — returns will be correlated.
            for col in cols:
                if col.startswith(strat_type + "_Refined") or col.startswith(strat_type + "_Combo"):
                    matched_col = col
                    logger.info(f"Approx match for {leader_name}: using column {col}")
                    break

        if matched_col is None:
            logger.warning(f"No matching column for {leader_name} in {returns_path}")
            continue

        series = pd.to_numeric(df[matched_col], errors="coerce").fillna(0.0)
        series.index = pd.to_datetime(df["exit_time"], errors="coerce")
        series = series[series.index.notna()]

        # Resample to daily
        daily = series.resample("D").sum().fillna(0.0)

        # Build unique label: market_timeframe_strategyname
        market = str(cand.get("market", ""))
        timeframe = str(cand.get("timeframe", ""))
        label = f"{market}_{timeframe}_{leader_name}"

        daily_series[label] = daily
        candidate_map[label] = cand

    if not daily_series:
        logger.warning("No strategy returns loaded — return matrix is empty")
        return pd.DataFrame()

    # Outer join all daily series
    matrix = pd.DataFrame(daily_series)
    matrix = matrix.fillna(0.0)

    # Drop all-zero columns
    nonzero_cols = [c for c in matrix.columns if (matrix[c] != 0.0).any()]
    dropped = len(matrix.columns) - len(nonzero_cols)
    if dropped > 0:
        logger.warning(f"Dropped {dropped} all-zero columns from return matrix")
    matrix = matrix[nonzero_cols]

    logger.info(f"Built return matrix: {len(matrix.columns)} strategies x {len(matrix)} days")
    return matrix


def _find_trades_file(candidate: dict, runs_base: str) -> str | None:
    """Find strategy_trades.csv for a candidate (per-trade PnL)."""
    run_id = str(candidate.get("run_id", ""))
    dataset = str(candidate.get("dataset", ""))

    if not run_id or not dataset:
        return None

    parts = dataset.replace("_tradestation.csv", "").split("_")
    if len(parts) >= 2:
        dataset_folder = f"{parts[0]}_{parts[1]}"
    else:
        dataset_folder = dataset.replace(".csv", "")

    path = os.path.join(runs_base, run_id, "Outputs", dataset_folder, "strategy_trades.csv")
    if os.path.exists(path):
        return path

    path2 = os.path.join(runs_base, run_id, "artifacts", "Outputs", dataset_folder, "strategy_trades.csv")
    if os.path.exists(path2):
        return path2

    return None


def _load_raw_trade_lists(
    candidates: list[dict],
    return_matrix_columns: list[str],
    runs_base_path: str,
) -> dict[str, list[float]]:
    """Load raw per-trade PnL for each candidate present in return_matrix.

    Prefers strategy_trades.csv (one row per trade) for accurate MC simulation.
    Falls back to strategy_returns.csv (daily resampled) if trades file not found.

    Returns dict mapping strategy label -> list of individual trade PnLs.
    """
    result: dict[str, list[float]] = {}

    for cand in candidates:
        leader_name = str(cand.get("leader_strategy_name", "")).strip()
        if not leader_name:
            continue

        market = str(cand.get("market", ""))
        timeframe = str(cand.get("timeframe", ""))
        label = f"{market}_{timeframe}_{leader_name}"

        if label not in return_matrix_columns:
            continue

        strat_type = str(cand.get("strategy_type", "")).strip()
        qualified_name = f"{strat_type}_{leader_name}" if strat_type else leader_name

        # Try strategy_trades.csv first (per-trade PnL)
        trades_path = _find_trades_file(cand, runs_base_path)
        if trades_path:
            try:
                df = pd.read_csv(trades_path)
                if "strategy" in df.columns and "net_pnl" in df.columns:
                    mask = df["strategy"] == qualified_name
                    if mask.sum() == 0:
                        # Try partial match
                        mask = df["strategy"].str.contains(leader_name, na=False)
                    trades = pd.to_numeric(df.loc[mask, "net_pnl"], errors="coerce").dropna().tolist()
                    if trades:
                        result[label] = trades
                        logger.debug(f"Raw trades for {label}: {len(trades)} trades (from strategy_trades.csv)")
                        continue
            except Exception as e:
                logger.debug(f"Could not read {trades_path}: {e}")

        # Fall back to strategy_returns.csv (daily resampled)
        returns_path = _find_returns_file(cand, runs_base_path)
        if returns_path is None:
            continue

        try:
            df = pd.read_csv(returns_path)
        except Exception as e:
            logger.warning(f"Could not read {returns_path} for raw trades: {e}")
            continue

        if "exit_time" not in df.columns:
            continue

        cols = [c for c in df.columns if c != "exit_time"]
        matched_col = _match_column(cols, leader_name, strategy_type=strat_type)

        if matched_col is None:
            refined_name = str(cand.get("best_refined_strategy_name", "")).strip()
            if refined_name:
                matched_col = _match_column(cols, refined_name, strategy_type=strat_type)

        if matched_col is None:
            continue

        # Extract ALL non-zero values as individual trades (NOT resampled)
        raw_vals = pd.to_numeric(df[matched_col], errors="coerce").fillna(0.0)
        trades = [float(v) for v in raw_vals if v != 0.0]

        if trades:
            result[label] = trades
            logger.debug(f"Raw trades for {label}: {len(trades)} trades (from strategy_returns.csv fallback)")

    logger.info(f"Loaded raw trade lists for {len(result)}/{len(return_matrix_columns)} strategies")
    return result


# ============================================================================
# STAGE 3: Correlation matrix
# ============================================================================

def compute_correlation_matrix(
    return_matrix: pd.DataFrame,
    output_dir: str | None = None,
) -> pd.DataFrame:
    """Compute Pearson correlation on daily returns. Save to CSV."""
    corr = return_matrix.corr()

    if output_dir:
        out_path = os.path.join(output_dir, "portfolio_selector_matrix.csv")
        corr.to_csv(out_path)
        logger.info(f"Correlation matrix saved to {out_path}")

    # Log high-correlation pairs
    n = len(corr.columns)
    for i in range(n):
        for j in range(i + 1, n):
            val = abs(corr.iloc[i, j])
            if val > 0.3:
                logger.info(
                    f"High correlation: {corr.columns[i]} vs {corr.columns[j]}: {corr.iloc[i, j]:.3f}"
                )

    logger.info(f"Correlation matrix: {corr.shape[0]}x{corr.shape[1]}")
    return corr


def compute_multi_layer_correlation(
    return_matrix: pd.DataFrame,
    min_overlap_days: int = 30,
    stress_percentile: float = 0.10,
    output_dir: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Compute 3-layer correlation architecture for portfolio selection.

    Layer A: Active-day correlation — only days where BOTH strategies traded.
    Layer B: Drawdown-state correlation — correlate DD series, not raw PnL.
    Layer C: Tail co-loss probability — P(B losing | A in worst 10% DD).

    Returns dict with keys 'active_corr', 'dd_corr', 'tail_coloss', each a DataFrame.
    """
    cols = list(return_matrix.columns)
    n = len(cols)

    active_corr = pd.DataFrame(0.0, index=cols, columns=cols)
    dd_corr = pd.DataFrame(0.0, index=cols, columns=cols)
    tail_coloss = pd.DataFrame(0.0, index=cols, columns=cols)

    # Set diagonals to 1.0 for active_corr and dd_corr
    for c in cols:
        active_corr.loc[c, c] = 1.0
        dd_corr.loc[c, c] = 1.0
        tail_coloss.loc[c, c] = 1.0

    # Precompute equity curves and DD series for Layer B and C
    base_equity = 100_000.0
    equity_curves: dict[str, pd.Series] = {}
    dd_series: dict[str, pd.Series] = {}
    for c in cols:
        eq = base_equity + return_matrix[c].cumsum()
        equity_curves[c] = eq
        peak = eq.cummax()
        dd = eq / peak - 1.0  # negative values = drawdown
        dd_series[c] = dd

    for i in range(n):
        for j in range(i + 1, n):
            ci, cj = cols[i], cols[j]
            a = return_matrix[ci]
            b = return_matrix[cj]

            # Layer A: Active-day correlation
            both_active = (a != 0.0) & (b != 0.0)
            overlap = int(both_active.sum())
            if overlap >= min_overlap_days:
                corr_val = float(a[both_active].corr(b[both_active]))
                if np.isnan(corr_val):
                    corr_val = 0.0
            else:
                corr_val = 0.0
            active_corr.loc[ci, cj] = corr_val
            active_corr.loc[cj, ci] = corr_val

            # Layer B: Drawdown-state correlation
            dd_corr_val = float(dd_series[ci].corr(dd_series[cj]))
            if np.isnan(dd_corr_val):
                dd_corr_val = 0.0
            dd_corr.loc[ci, cj] = dd_corr_val
            dd_corr.loc[cj, ci] = dd_corr_val

            # Layer C: Tail co-loss probability
            dd_i = dd_series[ci]
            dd_j = dd_series[cj]

            # Find worst stress_percentile of A's drawdown days
            threshold_i = dd_i.quantile(stress_percentile)
            stressed_i = dd_i <= threshold_i  # worst DD days for A

            if stressed_i.sum() > 0:
                # P(B also losing | A in worst DD)
                b_losing_given_a_stressed = (dd_j[stressed_i] < 0).mean()
            else:
                b_losing_given_a_stressed = 0.0

            # Symmetric: also check B stressed → A losing
            threshold_j = dd_j.quantile(stress_percentile)
            stressed_j = dd_j <= threshold_j

            if stressed_j.sum() > 0:
                a_losing_given_b_stressed = (dd_i[stressed_j] < 0).mean()
            else:
                a_losing_given_b_stressed = 0.0

            # Take the max of both directions (conservative)
            tail_val = max(float(b_losing_given_a_stressed), float(a_losing_given_b_stressed))
            tail_coloss.loc[ci, cj] = tail_val
            tail_coloss.loc[cj, ci] = tail_val

    if output_dir:
        active_corr.to_csv(os.path.join(output_dir, "portfolio_selector_active_corr.csv"))
        dd_corr.to_csv(os.path.join(output_dir, "portfolio_selector_dd_corr.csv"))
        tail_coloss.to_csv(os.path.join(output_dir, "portfolio_selector_tail_coloss.csv"))

    # Log high values
    for i in range(n):
        for j in range(i + 1, n):
            ci, cj = cols[i], cols[j]
            ac = abs(active_corr.loc[ci, cj])
            dc = abs(dd_corr.loc[ci, cj])
            tc = tail_coloss.loc[ci, cj]
            if ac > 0.3 or dc > 0.3 or tc > 0.3:
                logger.info(
                    f"Multi-layer corr {ci} vs {cj}: active={ac:.3f}, dd={dc:.3f}, tail={tc:.3f}"
                )

    logger.info(f"Multi-layer correlation: {n}x{n}, 3 layers computed")
    return {"active_corr": active_corr, "dd_corr": dd_corr, "tail_coloss": tail_coloss}


# ============================================================================
# STAGE 3b: Pre-sweep correlation dedup
# ============================================================================

def correlation_dedup(
    candidates: list[dict],
    corr_matrix: pd.DataFrame,
    return_matrix: pd.DataFrame,
    threshold: float = 0.6,
) -> list[dict]:
    """Remove near-duplicate strategies before combinatorial sweep.

    If two strategies have |Pearson| > threshold, keep the one with
    higher bootcamp_score. This reduces n before C(n,k) explosion.

    Uses a greedy approach: build graph of high-correlation edges,
    then for each connected component keep only the highest-scoring node.
    """
    # Build label -> candidate mapping (only those in return matrix)
    cand_by_label: dict[str, dict] = {}
    for cand in candidates:
        leader_name = str(cand.get("leader_strategy_name", "")).strip()
        market = str(cand.get("market", ""))
        timeframe = str(cand.get("timeframe", ""))
        label = f"{market}_{timeframe}_{leader_name}"
        if label in return_matrix.columns:
            cand_by_label[label] = cand

    labels = list(cand_by_label.keys())
    if len(labels) < 2:
        return candidates

    # Build adjacency list of high-correlation pairs
    adj: dict[str, set[str]] = {l: set() for l in labels}
    abs_corr = corr_matrix.abs()

    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            li, lj = labels[i], labels[j]
            if li in abs_corr.columns and lj in abs_corr.columns:
                val = float(abs_corr.loc[li, lj])
                if val > threshold:
                    adj[li].add(lj)
                    adj[lj].add(li)

    # Find connected components via BFS
    visited: set[str] = set()
    to_remove: set[str] = set()

    for label in labels:
        if label in visited:
            continue
        if not adj[label]:
            visited.add(label)
            continue

        # BFS to find component
        component: list[str] = []
        queue = [label]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            for neighbor in adj[node]:
                if neighbor not in visited:
                    queue.append(neighbor)

        if len(component) <= 1:
            continue

        # Keep only the highest-scoring member
        def _score(l: str) -> float:
            c = cand_by_label[l]
            return float(c.get("bootcamp_score", c.get("leader_pf", 0)))

        component.sort(key=_score, reverse=True)
        keeper = component[0]
        for removed in component[1:]:
            to_remove.add(removed)
            logger.info(
                f"Dedup: removing {removed} (score={_score(removed):.1f}), "
                f"correlated with {keeper} (score={_score(keeper):.1f})"
            )

    if not to_remove:
        logger.info("Correlation dedup: no duplicates found")
        return candidates

    # Remove candidates whose label is in to_remove
    kept: list[dict] = []
    for cand in candidates:
        leader_name = str(cand.get("leader_strategy_name", "")).strip()
        market = str(cand.get("market", ""))
        timeframe = str(cand.get("timeframe", ""))
        label = f"{market}_{timeframe}_{leader_name}"
        if label not in to_remove:
            kept.append(cand)

    logger.info(f"Correlation dedup: {len(candidates)} -> {len(kept)} candidates (removed {len(to_remove)})")
    return kept


# ============================================================================
# STAGE 4: Sweep combinations
# ============================================================================

def _diversity_score(combo_candidates: list[dict]) -> float:
    """Compute diversity score for a portfolio combination."""
    n = len(combo_candidates)
    markets = set(c.get("market", "") for c in combo_candidates)
    logic_types = set(c.get("strategy_type", "") for c in combo_candidates)

    has_long = any(not str(c.get("strategy_type", "")).startswith("short_") for c in combo_candidates)
    has_short = any(str(c.get("strategy_type", "")).startswith("short_") for c in combo_candidates)
    direction_mix = 1.0 if (has_long and has_short) else 0.0

    market_diversity = len(markets) / max(n, 1)
    logic_diversity = len(logic_types) / max(n, 1)

    return market_diversity * 0.4 + direction_mix * 0.3 + logic_diversity * 0.3


def _pre_mc_score(
    combo_candidates: list[dict],
    combo_names: list[str],
    return_matrix: pd.DataFrame,
    pair_corrs: list[float],
    max_dd_overlap: float = 0.0,
) -> float:
    """Calmar-based pre-MC score for ranking portfolio combinations.

    Components:
    - avg_oos_pf (25%)
    - calmar_proxy: avg annual return / worst individual max DD (20%)
    - recent_pf: mean of recent_12m_pf (15%)
    - market diversity (10%)
    - direction diversity (10%)
    - logic diversity (10%)
    - tail overlap penalty (-25% of max DD overlap)
    """
    n = len(combo_candidates)

    # OOS PF
    avg_oos_pf = mean(float(c.get("oos_pf", 1.0)) for c in combo_candidates)

    # Calmar proxy
    total_annual_return = 0.0
    worst_dd = 0.0
    for c in combo_candidates:
        net_pnl = float(c.get("leader_net_pnl", 0))
        trades = float(c.get("leader_trades", 0))
        tpy = float(c.get("leader_trades_per_year", 0))
        if tpy > 0 and trades > 0:
            years = trades / tpy
        else:
            years = 18.0  # approximate data span
        annual_ret = net_pnl / years if years > 0 else 0
        total_annual_return += annual_ret

        dd = float(c.get("max_drawdown", 0)) or float(c.get("mc_max_dd_99", 0))
        if dd <= 0:
            # Estimate from return matrix
            label = None
            for name in combo_names:
                lname = str(c.get("leader_strategy_name", ""))
                if lname and lname in name and name in return_matrix.columns:
                    label = name
                    break
            if label and label in return_matrix.columns:
                equity = return_matrix[label].cumsum()
                dd = float((equity.cummax() - equity).max())
        worst_dd = max(worst_dd, dd)

    calmar_proxy = total_annual_return / worst_dd if worst_dd > 0 else 0
    # Normalize calmar to 0-10 range (typical good calmar is 1-5)
    calmar_norm = min(calmar_proxy / 5.0, 1.0) * 10.0

    # Recent performance
    recent_pf = mean(float(c.get("recent_12m_pf", 1.0)) for c in combo_candidates)

    # Diversity components
    markets = set(c.get("market", "") for c in combo_candidates)
    logic_types = set(c.get("strategy_type", "") for c in combo_candidates)
    has_long = any(not str(c.get("strategy_type", "")).startswith("short_") for c in combo_candidates)
    has_short = any(str(c.get("strategy_type", "")).startswith("short_") for c in combo_candidates)

    market_div = len(markets) / max(n, 1) * 10
    direction_div = 10.0 if (has_long and has_short) else 0.0
    logic_div = len(logic_types) / max(n, 1) * 10

    # Tail overlap penalty
    dd_overlap_penalty = max_dd_overlap * 10

    score = (
        0.25 * avg_oos_pf
        + 0.20 * calmar_norm
        + 0.15 * recent_pf
        + 0.10 * market_div
        + 0.10 * direction_div
        + 0.10 * logic_div
        - 0.25 * dd_overlap_penalty
    )
    return score


_EQUITY_INDEX_MARKETS = {"ES", "NQ", "RTY", "YM"}
_METALS_MARKETS = {"GC", "SI", "HG"}


def _compute_dd_overlap(return_matrix: pd.DataFrame, col_a: str, col_b: str, dd_threshold: float = 0.02) -> float | None:
    """Compute drawdown overlap ratio between two strategies.
    Returns fraction of overlapping days both are in drawdown > threshold.
    Returns None if overlap period is too short (< 252 days).
    """
    if col_a not in return_matrix.columns or col_b not in return_matrix.columns:
        return None
    a = return_matrix[col_a].fillna(0.0)
    b = return_matrix[col_b].fillna(0.0)
    # Only consider calendar days where BOTH strategies are active.
    active = (a != 0.0) & (b != 0.0)
    if active.sum() < 252:
        return None
    # strategy_returns.csv stores daily PnL, not fractional returns, so
    # build a cumulative equity curve off a fixed capital base rather
    # than compounding raw dollar values.
    base_equity = 100_000.0
    a_active = a[active]
    b_active = b[active]
    eq_a = base_equity + a_active.cumsum()
    eq_b = base_equity + b_active.cumsum()
    dd_a = eq_a / eq_a.cummax() - 1
    dd_b = eq_b / eq_b.cummax() - 1
    # Binary: 1 if drawdown exceeds threshold
    in_dd_a = (dd_a < -dd_threshold).astype(float)
    in_dd_b = (dd_b < -dd_threshold).astype(float)
    overlap = (in_dd_a * in_dd_b).sum()
    n_active = len(a_active)
    return float(overlap / n_active) if n_active > 0 else 0.0


def _compute_ecd(
    return_matrix: pd.DataFrame,
    col_a: str,
    col_b: str,
    stress_percentile: float = 0.10,
) -> float | None:
    """Compute Expected Conditional Drawdown between two strategies.

    Measures: "How much does B hurt when A is already stressed?"

    1. Build equity curves and DD series for both A and B.
    2. Find worst stress_percentile of A's drawdown days.
    3. On those calendar days, measure B's average drawdown.
    4. Return max of both directions (A stressed→B DD, B stressed→A DD).

    Returns None if insufficient data (< 252 days with both active).
    """
    if col_a not in return_matrix.columns or col_b not in return_matrix.columns:
        return None

    a = return_matrix[col_a].fillna(0.0)
    b = return_matrix[col_b].fillna(0.0)

    # Build equity curves
    base_equity = 100_000.0
    eq_a = base_equity + a.cumsum()
    eq_b = base_equity + b.cumsum()

    # DD series (fractional, negative = drawdown)
    dd_a = eq_a / eq_a.cummax() - 1.0
    dd_b = eq_b / eq_b.cummax() - 1.0

    if len(dd_a) < 252:
        return None

    # A stressed → B's average DD
    threshold_a = dd_a.quantile(stress_percentile)
    stressed_a = dd_a <= threshold_a
    if stressed_a.sum() > 0:
        ecd_b_given_a = abs(float(dd_b[stressed_a].mean()))
    else:
        ecd_b_given_a = 0.0

    # B stressed → A's average DD
    threshold_b = dd_b.quantile(stress_percentile)
    stressed_b = dd_b <= threshold_b
    if stressed_b.sum() > 0:
        ecd_a_given_b = abs(float(dd_a[stressed_b].mean()))
    else:
        ecd_a_given_b = 0.0

    return max(ecd_b_given_a, ecd_a_given_b)


def _sweep_worker_init(
    abs_corr_arr: np.ndarray,
    col_index: dict[str, int],
    cand_list: list[dict],
    cand_name_to_idx: dict[str, int],
    ml_active_arr: np.ndarray | None,
    ml_dd_arr: np.ndarray | None,
    ml_tail_arr: np.ndarray | None,
    eq_curves: dict[str, np.ndarray],
    eq_peaks: dict[str, np.ndarray],
    sweep_params: dict,
) -> None:
    """Initializer for sweep worker processes — shared data via globals."""
    global _sw_abs_corr, _sw_col_idx, _sw_cands, _sw_cand_idx
    global _sw_ml_active, _sw_ml_dd, _sw_ml_tail
    global _sw_eq_curves, _sw_eq_peaks, _sw_params
    _sw_abs_corr = abs_corr_arr
    _sw_col_idx = col_index
    _sw_cands = cand_list
    _sw_cand_idx = cand_name_to_idx
    _sw_ml_active = ml_active_arr
    _sw_ml_dd = ml_dd_arr
    _sw_ml_tail = ml_tail_arr
    _sw_eq_curves = eq_curves
    _sw_eq_peaks = eq_peaks
    _sw_params = sweep_params


def _sweep_chunk(chunk: list[tuple[str, ...]], k: int) -> list[dict]:
    """Process a chunk of combinations in a worker process."""
    params = _sw_params
    active_thresh = params["active_corr_threshold"]
    dd_thresh = params["dd_corr_threshold"]
    tail_thresh = params["tail_coloss_threshold"]
    use_ecd = params["use_ecd"]
    max_ecd = params["max_ecd"]
    max_dd_overlap = params["max_dd_overlap"]
    max_per_market = params["max_per_market"]
    max_equity_index = params["max_equity_index"]
    equity_markets = {"ES", "NQ", "RTY", "YM"}
    use_ml = _sw_ml_active is not None

    results: list[dict] = []

    for combo in chunk:
        rejected = False
        pair_corrs: list[float] = []

        # Correlation gate
        for i in range(len(combo)):
            for j in range(i + 1, len(combo)):
                ci_idx = _sw_col_idx.get(combo[i])
                cj_idx = _sw_col_idx.get(combo[j])
                if ci_idx is None or cj_idx is None:
                    pair_corrs.append(0.0)
                    continue

                if use_ml:
                    ac = abs(float(_sw_ml_active[ci_idx, cj_idx]))
                    dc = abs(float(_sw_ml_dd[ci_idx, cj_idx]))
                    tc = float(_sw_ml_tail[ci_idx, cj_idx])
                    pair_corrs.append(ac)
                    if ac > active_thresh or dc > dd_thresh or tc > tail_thresh:
                        rejected = True
                        break
                else:
                    val = float(_sw_abs_corr[ci_idx, cj_idx])
                    pair_corrs.append(val)
                    if val > 0.4:
                        rejected = True
                        break
            if rejected:
                break

        if rejected:
            continue

        # Market concentration check
        combo_cands = [_sw_cands[_sw_cand_idx[s]] for s in combo]
        market_counts: dict[str, int] = {}
        for c in combo_cands:
            m = str(c.get("market", "")).upper()
            market_counts[m] = market_counts.get(m, 0) + 1
        if any(v > max_per_market for v in market_counts.values()):
            continue
        equity_count = sum(market_counts.get(m, 0) for m in equity_markets)
        if equity_count > max_equity_index:
            continue

        # ECD / DD overlap check using precomputed equity curves
        if use_ecd:
            ecd_rejected = False
            for ci in range(len(combo)):
                for cj in range(ci + 1, len(combo)):
                    ecd_val = _fast_ecd(combo[ci], combo[cj])
                    if ecd_val is not None and ecd_val > max_ecd:
                        ecd_rejected = True
                        break
                if ecd_rejected:
                    break
            if ecd_rejected:
                continue
        elif max_dd_overlap < 1.0:
            dd_rejected = False
            for ci in range(len(combo)):
                for cj in range(ci + 1, len(combo)):
                    dd_ov = _fast_dd_overlap(combo[ci], combo[cj])
                    if dd_ov is not None and dd_ov > max_dd_overlap:
                        dd_rejected = True
                        break
                if dd_rejected:
                    break
            if dd_rejected:
                continue

        # Score
        n = len(combo_cands)
        avg_oos_pf = sum(float(c.get("oos_pf", 1.0)) for c in combo_cands) / n

        # Diversity
        markets = set(c.get("market", "") for c in combo_cands)
        logic_types = set(c.get("strategy_type", "") for c in combo_cands)
        has_long = any(not str(c.get("strategy_type", "")).startswith("short_") for c in combo_cands)
        has_short = any(str(c.get("strategy_type", "")).startswith("short_") for c in combo_cands)
        market_div = len(markets) / max(n, 1)
        direction_mix = 1.0 if (has_long and has_short) else 0.0
        logic_div = len(logic_types) / max(n, 1)
        diversity = market_div * 0.4 + direction_mix * 0.3 + logic_div * 0.3

        avg_corr = sum(pair_corrs) / len(pair_corrs) if pair_corrs else 0.0

        # Compute max ECD/DD overlap for scoring
        combo_max_dd_overlap = 0.0
        if use_ecd:
            for ci in range(len(combo)):
                for cj in range(ci + 1, len(combo)):
                    ecd_val = _fast_ecd(combo[ci], combo[cj])
                    if ecd_val is not None:
                        combo_max_dd_overlap = max(combo_max_dd_overlap, ecd_val)
        elif max_dd_overlap < 1.0:
            for ci in range(len(combo)):
                for cj in range(ci + 1, len(combo)):
                    dd_ov = _fast_dd_overlap(combo[ci], combo[cj])
                    if dd_ov is not None:
                        combo_max_dd_overlap = max(combo_max_dd_overlap, dd_ov)

        # Simplified pre-MC score (avoid return_matrix access in worker)
        recent_pf = sum(float(c.get("recent_12m_pf", 1.0)) for c in combo_cands) / n
        # Calmar proxy
        total_annual_return = 0.0
        worst_dd = 0.0
        for c in combo_cands:
            net_pnl = float(c.get("leader_net_pnl", 0))
            trades = float(c.get("leader_trades", 0))
            tpy = float(c.get("leader_trades_per_year", 0))
            years = trades / tpy if tpy > 0 and trades > 0 else 18.0
            total_annual_return += net_pnl / years if years > 0 else 0
            dd = float(c.get("max_drawdown", 0)) or float(c.get("mc_max_dd_99", 0))
            worst_dd = max(worst_dd, dd)
        calmar_proxy = total_annual_return / worst_dd if worst_dd > 0 else 0
        calmar_norm = min(calmar_proxy / 5.0, 1.0) * 10.0

        dd_overlap_penalty = combo_max_dd_overlap * 10
        score = (
            0.25 * avg_oos_pf
            + 0.20 * calmar_norm
            + 0.15 * recent_pf
            + 0.10 * (market_div * 10)
            + 0.10 * (10.0 if (has_long and has_short) else 0.0)
            + 0.10 * (logic_div * 10)
            - 0.25 * dd_overlap_penalty
        )

        results.append({
            "strategy_names": list(combo),
            "score": score,
            "avg_oos_pf": avg_oos_pf,
            "avg_corr": avg_corr,
            "diversity": diversity,
            "n_strategies": k,
        })

    return results


def _fast_ecd(col_a: str, col_b: str, stress_percentile: float = 0.10) -> float | None:
    """Fast ECD using precomputed equity curves in worker globals."""
    eq_a = _sw_eq_curves.get(col_a)
    eq_b = _sw_eq_curves.get(col_b)
    if eq_a is None or eq_b is None or len(eq_a) < 252:
        return None

    peak_a = _sw_eq_peaks.get(col_a)
    peak_b = _sw_eq_peaks.get(col_b)
    dd_a = eq_a / peak_a - 1.0
    dd_b = eq_b / peak_b - 1.0

    threshold_a = np.quantile(dd_a, stress_percentile)
    stressed_a = dd_a <= threshold_a
    ecd_b = abs(float(dd_b[stressed_a].mean())) if stressed_a.sum() > 0 else 0.0

    threshold_b = np.quantile(dd_b, stress_percentile)
    stressed_b = dd_b <= threshold_b
    ecd_a = abs(float(dd_a[stressed_b].mean())) if stressed_b.sum() > 0 else 0.0

    return max(ecd_a, ecd_b)


def _fast_dd_overlap(col_a: str, col_b: str, dd_threshold: float = 0.02) -> float | None:
    """Fast DD overlap using precomputed equity curves in worker globals."""
    eq_a = _sw_eq_curves.get(col_a)
    eq_b = _sw_eq_curves.get(col_b)
    if eq_a is None or eq_b is None or len(eq_a) < 252:
        return None

    peak_a = _sw_eq_peaks.get(col_a)
    peak_b = _sw_eq_peaks.get(col_b)
    dd_a = eq_a / peak_a - 1.0
    dd_b = eq_b / peak_b - 1.0

    in_dd_a = (dd_a < -dd_threshold).astype(float)
    in_dd_b = (dd_b < -dd_threshold).astype(float)
    overlap = float((in_dd_a * in_dd_b).sum())
    return overlap / len(eq_a) if len(eq_a) > 0 else 0.0


def sweep_combinations(
    candidates: list[dict],
    corr_matrix: pd.DataFrame,
    return_matrix: pd.DataFrame,
    n_min: int = 4,
    n_max: int = 8,
    max_per_market: int = 2,
    max_equity_index: int = 3,
    max_dd_overlap: float = 0.30,
    multi_layer_corr: dict[str, pd.DataFrame] | None = None,
    active_corr_threshold: float = 0.50,
    dd_corr_threshold: float = 0.40,
    tail_coloss_threshold: float = 0.30,
    use_ecd: bool = True,
    max_ecd: float = 0.03,
    candidate_cap: int = 50,
    max_combinations: int = 10_000_000_000,
) -> list[dict]:
    """Sweep all C(n,k) combinations with parallel ProcessPoolExecutor."""
    # Only use candidates that are in the return matrix
    available_names = set(return_matrix.columns)
    cand_by_name: dict[str, dict] = {}

    for cand in candidates:
        leader_name = str(cand.get("leader_strategy_name", "")).strip()
        market = str(cand.get("market", ""))
        timeframe = str(cand.get("timeframe", ""))
        label = f"{market}_{timeframe}_{leader_name}"
        if label in available_names:
            cand_by_name[label] = cand

    strategy_names = list(cand_by_name.keys())
    n = len(strategy_names)

    if n < n_min:
        logger.warning(f"Only {n} strategies available, need at least {n_min}")
        return []

    n_max = min(n_max, n)

    # Adaptive n_max: auto-reduce if sweep would take too long
    n_cores = min(os.cpu_count() or 4, 8)
    target_sweep_seconds = 300  # 5 minutes max
    us_per_combo = 1.0  # microseconds per combo (conservative)
    orig_n_max = n_max
    for test_max in range(n_max, n_min - 1, -1):
        total = sum(comb(n, k) for k in range(n_min, test_max + 1))
        if total <= max_combinations:
            wall_secs = total * us_per_combo / 1_000_000 / n_cores
            if wall_secs <= target_sweep_seconds:
                n_max = test_max
                break
        n_max = test_max - 1
    else:
        n_max = n_min
    if n_max != orig_n_max:
        logger.warning(f"Adaptive n_max: reduced from {orig_n_max} to {n_max} based on {n} candidates, {n_cores} cores")

    total_combos = sum(comb(n, k) for k in range(n_min, n_max + 1))
    logger.info(f"Sweeping {total_combos:,} combinations (n={n}, k={n_min}..{n_max}, cores={n_cores})")

    # Precompute numpy arrays for fast worker access
    abs_corr_arr = corr_matrix.abs().values
    col_names = list(corr_matrix.columns)
    col_index = {c: i for i, c in enumerate(col_names)}

    ml_active_arr = multi_layer_corr["active_corr"].abs().values if multi_layer_corr else None
    ml_dd_arr = multi_layer_corr["dd_corr"].abs().values if multi_layer_corr else None
    ml_tail_arr = multi_layer_corr["tail_coloss"].values if multi_layer_corr else None

    # Precompute equity curves for ECD/DD overlap
    base_equity = 100_000.0
    eq_curves: dict[str, np.ndarray] = {}
    eq_peaks: dict[str, np.ndarray] = {}
    for s in strategy_names:
        if s in return_matrix.columns:
            eq = base_equity + return_matrix[s].values.cumsum()
            eq_curves[s] = eq
            eq_peaks[s] = np.maximum.accumulate(eq)

    # Prepare candidate data for workers (list + index)
    cand_list = [cand_by_name[s] for s in strategy_names]
    cand_name_to_idx = {s: i for i, s in enumerate(strategy_names)}

    sweep_params = {
        "active_corr_threshold": active_corr_threshold,
        "dd_corr_threshold": dd_corr_threshold,
        "tail_coloss_threshold": tail_coloss_threshold,
        "use_ecd": use_ecd,
        "max_ecd": max_ecd,
        "max_dd_overlap": max_dd_overlap,
        "max_per_market": max_per_market,
        "max_equity_index": max_equity_index,
    }

    # For small problems, run single-threaded (avoid process overhead)
    if total_combos < 10_000 or n_cores <= 1:
        # Single-threaded sweep
        _sweep_worker_init(
            abs_corr_arr, col_index, cand_list, cand_name_to_idx,
            ml_active_arr, ml_dd_arr, ml_tail_arr,
            eq_curves, eq_peaks, sweep_params,
        )
        all_results: list[dict] = []
        for k in range(n_min, n_max + 1):
            combos = list(itertools.combinations(strategy_names, k))
            all_results.extend(_sweep_chunk(combos, k))
    else:
        # Parallel sweep across cores
        all_results = []
        for k in range(n_min, n_max + 1):
            combos = list(itertools.combinations(strategy_names, k))
            if not combos:
                continue
            chunk_size = max(1, len(combos) // n_cores)
            chunks = [combos[i:i + chunk_size] for i in range(0, len(combos), chunk_size)]

            with ProcessPoolExecutor(
                max_workers=n_cores,
                initializer=_sweep_worker_init,
                initargs=(
                    abs_corr_arr, col_index, cand_list, cand_name_to_idx,
                    ml_active_arr, ml_dd_arr, ml_tail_arr,
                    eq_curves, eq_peaks, sweep_params,
                ),
            ) as executor:
                futures = [executor.submit(_sweep_chunk, chunk, k) for chunk in chunks]
                for f in as_completed(futures):
                    all_results.extend(f.result())

            logger.info(f"  k={k}: {len(combos):,} combos, {comb(n, k):,} total")

    # Sort by score descending, keep top candidate_cap
    all_results.sort(key=lambda r: r["score"], reverse=True)
    results = all_results[:candidate_cap]

    logger.info(f"Sweep complete: {len(results)} survivors from {total_combos:,} combos")
    return results


# ============================================================================
# STAGE 5: Portfolio Monte Carlo
# ============================================================================

def _build_shuffled_interleave_matrix(
    strategy_trade_lists: dict[str, list[float]],
    contract_weights: dict[str, float],
    n_sims: int,
    seed: int,
) -> np.ndarray:
    """Build (n_sims, n_trades) matrix of shuffled+interleaved portfolio trades."""
    rng = random.Random(seed)
    strategy_names = list(strategy_trade_lists.keys())
    trade_lists = {s: list(strategy_trade_lists[s]) for s in strategy_names}
    max_len = max(len(trade_lists[s]) for s in strategy_names) if strategy_names else 0
    n_trades_per_sim = max_len * len(strategy_names)

    matrix = np.zeros((n_sims, n_trades_per_sim))
    for sim in range(n_sims):
        shuffled: dict[str, list[float]] = {}
        for s in strategy_names:
            t = trade_lists[s].copy()
            rng.shuffle(t)
            shuffled[s] = t

        idx = 0
        for trade_idx in range(max_len):
            for s in strategy_names:
                if trade_idx < len(shuffled[s]):
                    w = contract_weights.get(s, 1.0)
                    matrix[sim, idx] = shuffled[s][trade_idx] * w
                    idx += 1

    return matrix


def portfolio_monte_carlo(
    strategy_trade_lists: dict[str, list[float]],
    config: PropFirmConfig,
    source_capital: float = 250_000.0,
    n_sims: int = 10_000,
    seed: int = 42,
    contract_weights: dict[str, float] | None = None,
) -> dict:
    """Monte Carlo for a PORTFOLIO of strategies.

    For each simulation:
    1. For each strategy, independently shuffle its trade list
    2. Interleave all shuffled trades into a single combined sequence
    3. Apply contract_weights scaling to each trade's PnL
    4. Run through vectorized simulate_challenge_batch()

    Returns dict with pass_rate, step pass rates, DD stats, avg_trades_to_pass.
    """
    if contract_weights is None:
        contract_weights = {s: 1.0 for s in strategy_trade_lists}

    trade_matrix = _build_shuffled_interleave_matrix(
        strategy_trade_lists, contract_weights, n_sims, seed,
    )

    return simulate_challenge_batch(trade_matrix, config, source_capital)


def _build_block_bootstrap_matrix(
    daily_returns: np.ndarray,
    n_sims: int,
    n_days: int,
    block_sizes: list[int],
    seed: int,
) -> np.ndarray:
    """Build (n_sims, n_trades) matrix from block-sampled daily returns.

    For each sim, sample consecutive blocks of days (with replacement)
    until we have >= n_days returns, then extract non-zero as trades.
    Returns a ragged-padded matrix where each row is that sim's trade sequence.
    """
    rng = random.Random(seed)
    # First pass: build all sim return series, track max trade count
    all_trades: list[list[float]] = []
    for _ in range(n_sims):
        sim_returns: list[float] = []
        while len(sim_returns) < n_days:
            block_size = rng.choice(block_sizes)
            start = rng.randint(0, n_days - 1)
            end = min(start + block_size, n_days)
            sim_returns.extend(daily_returns[start:end])
        sim_returns = sim_returns[:n_days]
        trades = [r for r in sim_returns if r != 0.0]
        all_trades.append(trades)

    max_trades = max(len(t) for t in all_trades) if all_trades else 1
    matrix = np.zeros((n_sims, max_trades))
    for i, trades in enumerate(all_trades):
        if trades:
            matrix[i, :len(trades)] = trades

    return matrix


def portfolio_monte_carlo_block_bootstrap(
    return_matrix: pd.DataFrame,
    strategy_names: list[str],
    config: PropFirmConfig,
    source_capital: float = 250_000.0,
    n_sims: int = 5_000,
    seed: int = 42,
    contract_weights: dict[str, float] | None = None,
    block_sizes: list[int] | None = None,
) -> dict:
    """Block bootstrap Monte Carlo for a PORTFOLIO of strategies.

    Instead of shuffling individual trade lists (which destroys crisis clustering),
    this samples blocks of consecutive days from the daily portfolio return series.

    This preserves: crisis clustering, cross-strategy DD correlation,
    volatility regime persistence, serial correlation in returns.
    """
    if block_sizes is None:
        block_sizes = [5, 10, 20]
    if contract_weights is None:
        contract_weights = {s: 1.0 for s in strategy_names}

    # Build daily portfolio return series
    available = [s for s in strategy_names if s in return_matrix.columns]
    if not available:
        return {"pass_rate": 0.0, "final_pass_rate": 0.0}

    weighted_returns = pd.Series(0.0, index=return_matrix.index)
    for s in available:
        w = contract_weights.get(s, 1.0)
        weighted_returns += return_matrix[s] * w

    daily_returns = weighted_returns.values.copy()
    n_days = len(daily_returns)

    if n_days < 30:
        return {"pass_rate": 0.0, "final_pass_rate": 0.0}

    # Build trade matrix via block bootstrap
    trade_matrix = _build_block_bootstrap_matrix(
        daily_returns, n_sims, n_days, block_sizes, seed,
    )

    # Run vectorized batch simulation
    return simulate_challenge_batch(trade_matrix, config, source_capital)


_mc_shared: dict = {}


def _mc_worker_init(
    return_matrix_vals: np.ndarray,
    return_matrix_cols: list[str],
    return_matrix_idx: list,
    raw_trade_lists: dict[str, list[float]] | None,
) -> None:
    """Initialize per-worker shared data for MC workers."""
    _mc_shared["return_matrix"] = pd.DataFrame(
        return_matrix_vals, columns=return_matrix_cols, index=return_matrix_idx,
    )
    _mc_shared["raw_trade_lists"] = raw_trade_lists


def _mc_worker(args: tuple) -> dict | None:
    """Worker function for parallel MC across combinations."""
    combo, n_sims, mc_method, config_dict = args
    names = combo["strategy_names"]

    # Reconstruct config from dict (PropFirmConfig is a dataclass)
    config = PropFirmConfig(**config_dict)
    return_matrix = _mc_shared["return_matrix"]
    raw_trade_lists = _mc_shared.get("raw_trade_lists")

    if mc_method == "block_bootstrap":
        mc = portfolio_monte_carlo_block_bootstrap(
            return_matrix, names, config, n_sims=n_sims,
        )
    else:
        trade_lists: dict[str, list[float]] = {}
        for name in names:
            if raw_trade_lists and name in raw_trade_lists:
                trade_lists[name] = raw_trade_lists[name]
            elif name in return_matrix.columns:
                vals = return_matrix[name].values
                trades = [float(v) for v in vals if v != 0.0]
                if trades:
                    trade_lists[name] = trades
        if not trade_lists:
            return None
        mc = portfolio_monte_carlo(trade_lists, config, n_sims=n_sims)

    return {**combo, **mc}


def run_bootcamp_mc(
    combinations: list[dict],
    return_matrix: pd.DataFrame,
    n_sims: int = 10_000,
    raw_trade_lists: dict[str, list[float]] | None = None,
    prop_config: PropFirmConfig | None = None,
    mc_method: str = "block_bootstrap",
) -> list[dict]:
    """Run portfolio Monte Carlo for top combinations from sweep.

    Uses ProcessPoolExecutor to parallelize across combinations.

    Args:
        raw_trade_lists: If provided, use raw per-trade PnL instead of
            extracting from the daily return matrix.
        prop_config: Prop firm config to simulate against. Defaults to Bootcamp $250K.
        mc_method: "block_bootstrap" (default) or "shuffle_interleave".

    Returns combinations enriched with MC results, sorted by final step pass rate.
    """
    config = prop_config or The5ersBootcampConfig()
    n_workers = min(len(combinations), os.cpu_count() or 4)

    # Serialize config to dict for pickling
    from dataclasses import asdict
    config_dict = asdict(config)

    args_list = [
        (combo, n_sims, mc_method, config_dict)
        for combo in combinations
    ]

    logger.info(
        f"Portfolio MC: {len(combinations)} combos × {n_sims} sims ({mc_method}), "
        f"{n_workers} workers"
    )

    results: list[dict] = []
    if n_workers <= 1 or len(combinations) <= 2:
        # Single-threaded for small jobs
        _mc_worker_init(
            return_matrix.values, list(return_matrix.columns),
            list(return_matrix.index), raw_trade_lists,
        )
        for i, args in enumerate(args_list):
            result = _mc_worker(args)
            if result is not None:
                results.append(result)
            logger.info(f"  Portfolio MC {i + 1}/{len(combinations)} complete")
    else:
        with ProcessPoolExecutor(
            max_workers=n_workers,
            initializer=_mc_worker_init,
            initargs=(
                return_matrix.values, list(return_matrix.columns),
                list(return_matrix.index), raw_trade_lists,
            ),
        ) as executor:
            futures = {executor.submit(_mc_worker, args): i for i, args in enumerate(args_list)}
            for future in as_completed(futures):
                idx = futures[future]
                result = future.result()
                if result is not None:
                    results.append(result)
                logger.info(f"  Portfolio MC {idx + 1}/{len(combinations)} complete")

    # Sort by final step pass rate
    final_step_key = f"step{config.n_steps}_pass_rate"
    results.sort(key=lambda r: r.get(final_step_key, r.get("pass_rate", 0.0)), reverse=True)
    logger.info(f"MC complete for {len(results)} portfolios ({config.program_name})")
    return results


# ============================================================================
# STAGE 4b: Regime survival gate
# ============================================================================

_DEFAULT_REGIME_WINDOWS = [
    ("2022", "2022-01-01", "2022-12-31"),  # inflation/rate hike
    ("2023", "2023-01-01", "2023-12-31"),  # recovery
    ("2024-2025", "2024-01-01", "2025-12-31"),  # AI/metals trend
]


def regime_survival_gate(
    combinations: list[dict],
    return_matrix: pd.DataFrame,
    min_regime_pf: float = 0.8,
    regime_windows: list[tuple[str, str, str]] | None = None,
) -> list[dict]:
    """Filter portfolio combinations that fail in specific market regimes.

    For each surviving combo, compute portfolio PnL in regime windows.
    Reject combo if any regime window has PF < min_regime_pf.

    Args:
        combinations: Output from sweep_combinations.
        return_matrix: Daily return matrix (index must be DatetimeIndex).
        min_regime_pf: Minimum PF per regime window (default 0.8).
        regime_windows: List of (name, start_date, end_date) tuples.

    Returns filtered list of combinations.
    """
    if regime_windows is None:
        regime_windows = _DEFAULT_REGIME_WINDOWS

    # Ensure datetime index
    if not isinstance(return_matrix.index, pd.DatetimeIndex):
        try:
            return_matrix = return_matrix.copy()
            return_matrix.index = pd.to_datetime(return_matrix.index)
        except Exception:
            logger.warning("Cannot convert return matrix index to datetime; skipping regime gate")
            return combinations

    survivors: list[dict] = []
    n_rejected = 0

    for combo in combinations:
        names = combo["strategy_names"]
        available = [n for n in names if n in return_matrix.columns]
        if not available:
            survivors.append(combo)
            continue

        rejected = False
        for regime_name, start, end in regime_windows:
            mask = (return_matrix.index >= start) & (return_matrix.index <= end)
            window = return_matrix.loc[mask, available]

            if window.empty or len(window) < 20:
                continue

            # Sum daily PnL across all strategies in the combo
            portfolio_pnl = window.sum(axis=1)
            gross_profit = float(portfolio_pnl[portfolio_pnl > 0].sum())
            gross_loss = abs(float(portfolio_pnl[portfolio_pnl < 0].sum()))

            if gross_loss > 0:
                pf = gross_profit / gross_loss
            elif gross_profit > 0:
                pf = 10.0  # no losses
            else:
                pf = 0.0  # no trades

            if pf < min_regime_pf:
                logger.info(
                    f"Regime gate REJECT: {len(names)} strats, "
                    f"regime={regime_name}, PF={pf:.2f} < {min_regime_pf}"
                )
                rejected = True
                break

        if rejected:
            n_rejected += 1
        else:
            survivors.append(combo)

    logger.info(f"Regime gate: {len(combinations)} -> {len(survivors)} combos ({n_rejected} rejected)")
    return survivors


# ============================================================================
# STAGE 6: Optimise sizing
# ============================================================================

def _compute_inverse_dd_weights(
    trade_lists: dict[str, list[float]],
    candidates_by_label: dict[str, dict],
    weight_options: list[float],
) -> dict[str, float]:
    """Compute inverse-DD weights and snap to nearest grid value.

    For each strategy, weight is inversely proportional to its max drawdown,
    so each contributes roughly equal risk to the portfolio.
    """
    raw_weights: dict[str, float] = {}

    for label in trade_lists:
        # Try to get max_drawdown from leaderboard data
        cand = candidates_by_label.get(label, {})
        max_dd = float(cand.get("max_drawdown", 0)) or float(cand.get("mc_max_dd_99", 0))

        if max_dd <= 0:
            # Estimate from trade list: simulate equity curve, compute max DD
            trades = trade_lists[label]
            if trades:
                equity = np.cumsum(trades)
                running_max = np.maximum.accumulate(equity)
                drawdowns = running_max - equity
                max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0

        raw_weights[label] = 1.0 / max_dd if max_dd > 0 else 1.0

    # Normalize
    total = sum(raw_weights.values())
    if total <= 0:
        return {s: weight_options[0] for s in trade_lists}

    normalized = {s: w / total for s, w in raw_weights.items()}

    # Snap to nearest grid value (scale so max normalized weight maps to max grid)
    max_norm = max(normalized.values()) if normalized else 1.0
    scale = max(weight_options) / max_norm if max_norm > 0 else 1.0

    snapped: dict[str, float] = {}
    for s, w in normalized.items():
        scaled = w * scale
        snapped[s] = min(weight_options, key=lambda opt: abs(opt - scaled))

    return snapped


def optimise_sizing(
    top_portfolios: list[dict],
    return_matrix: pd.DataFrame,
    n_sims: int = 1_000,
    final_n_sims: int = 10_000,
    raw_trade_lists: dict[str, list[float]] | None = None,
    min_pass_rate: float = 0.40,
    prop_config: PropFirmConfig | None = None,
    dd_p95_limit_pct: float = 0.70,
    dd_p99_limit_pct: float = 0.90,
    candidates_by_label: dict[str, dict] | None = None,
) -> list[dict]:
    """Grid-search contract weights for top portfolios.

    Uses n_sims=1000 for speed during grid search. After finding best weights,
    runs a final 10k-sim MC for accurate step rates.

    Objective: minimize median_trades_to_pass subject to:
      - pass_rate >= min_pass_rate (default 0.40)
      - p95_dd <= dd_p95_limit_pct * program_dd_limit (hard constraint)
      - p99_dd <= dd_p99_limit_pct * program_dd_limit (hard constraint)

    If no weight combo passes DD constraints, falls back to lowest p95_dd combo.
    """
    config = prop_config or The5ersBootcampConfig()
    weight_options = [0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
    n_weight_opts = len(weight_options)
    results: list[dict] = []
    max_weight_samples = 250

    for i, portfolio in enumerate(top_portfolios[:10]):
        names = portfolio["strategy_names"]
        n_strats = len(names)

        # Cap the brute-force sizing search so large portfolios don't stall
        # the whole selector or test suite.
        total_weight_combos = n_weight_opts ** n_strats

        # Use raw trade lists if available, else fall back to return matrix
        trade_lists: dict[str, list[float]] = {}
        for name in names:
            if raw_trade_lists and name in raw_trade_lists:
                trade_lists[name] = raw_trade_lists[name]
            elif name in return_matrix.columns:
                vals = return_matrix[name].values
                trades = [float(v) for v in vals if v != 0.0]
                if trades:
                    trade_lists[name] = trades

        if not trade_lists:
            portfolio["micro_multiplier"] = {s: 0.1 for s in names}
            portfolio["sizing_optimised"] = False
            results.append(portfolio)
            continue

        strat_names_in_matrix = list(trade_lists.keys())
        best_weights: dict[str, float] | None = None
        best_trades: float | None = None
        best_pass_rate = -1.0
        best_dd = 1.0

        # DD constraint thresholds
        dd_limit = config.max_drawdown_pct
        p95_ceiling = dd_p95_limit_pct * dd_limit
        p99_ceiling = dd_p99_limit_pct * dd_limit

        # Fallback tracking: lowest p95_dd combo if nothing passes DD constraints
        fallback_weights: dict[str, float] | None = None
        fallback_dd = 1.0

        logger.info(
            f"Sizing optimisation {i + 1}: {n_strats} strategies, "
            f"{n_weight_opts**len(strat_names_in_matrix)} weight combos x {n_sims} sims"
        )

        combo_width = len(strat_names_in_matrix)
        if total_weight_combos > max_weight_samples:
            sampled_indices = sorted(random.Random(42 + i).sample(range(total_weight_combos), max_weight_samples))
            logger.info(
                f"Sizing optimisation {i + 1}: sampling {max_weight_samples}/{total_weight_combos} weight combos"
            )

            weight_combo_iter = []
            for combo_index in sampled_indices:
                idx = combo_index
                combo: list[float] = []
                for _ in range(combo_width):
                    combo.append(weight_options[idx % n_weight_opts])
                    idx //= n_weight_opts
                weight_combo_iter.append(tuple(combo))
        else:
            weight_combo_iter = list(itertools.product(weight_options, repeat=combo_width))

        # Prepend inverse-DD weights as a guaranteed candidate
        inv_dd_weights = _compute_inverse_dd_weights(
            trade_lists, candidates_by_label or {}, weight_options,
        )
        inv_dd_combo = tuple(inv_dd_weights.get(s, weight_options[0]) for s in strat_names_in_matrix)
        if isinstance(weight_combo_iter, list):
            if inv_dd_combo not in weight_combo_iter:
                weight_combo_iter.insert(0, inv_dd_combo)
        else:
            weight_combo_iter = itertools.chain([inv_dd_combo], weight_combo_iter)
        logger.info(f"  Inverse-DD seed weights: {dict(zip(strat_names_in_matrix, inv_dd_combo))}")

        for weight_combo in weight_combo_iter:
            weights = dict(zip(strat_names_in_matrix, weight_combo))

            mc = portfolio_monte_carlo(
                trade_lists, config,
                n_sims=n_sims,
                contract_weights=weights,
            )

            final_step_key = f"step{config.n_steps}_pass_rate"
            pass_rate = mc.get(final_step_key, mc.get("pass_rate", 0.0))
            p95_dd = mc["p95_worst_dd_pct"]
            p99_dd = mc.get("p99_worst_dd_pct", p95_dd)
            trades = mc["median_trades_to_pass"]

            # Track fallback: lowest p95_dd regardless of constraints
            if p95_dd < fallback_dd:
                fallback_dd = p95_dd
                fallback_weights = weights.copy()

            # Hard DD constraints
            if p95_dd > p95_ceiling:
                continue
            if p99_dd > p99_ceiling:
                continue

            # Minimize trades-to-pass subject to pass_rate >= min_pass_rate
            if pass_rate >= min_pass_rate:
                if trades > 0 and (best_trades is None or trades < best_trades):
                    best_trades = trades
                    best_pass_rate = pass_rate
                    best_dd = p95_dd
                    best_weights = weights.copy()
            elif best_weights is None:
                # No combo meets minimum yet; track best pass rate as fallback
                if pass_rate > best_pass_rate:
                    best_pass_rate = pass_rate
                    best_weights = weights.copy()
                    best_dd = p95_dd

        if best_weights is None:
            if fallback_weights is not None:
                best_weights = fallback_weights
                logger.warning(
                    f"  No weight combo passed DD constraints (p95 ceiling={p95_ceiling:.1%}). "
                    f"Using lowest-DD fallback (p95_dd={fallback_dd:.1%})"
                )
            else:
                best_weights = {s: 0.1 for s in strat_names_in_matrix}

        # Final MC at the requested final sim count — all step rates
        # from the SAME experiment so they're comparable.
        final_mc = portfolio_monte_carlo(
            trade_lists, config,
            n_sims=final_n_sims,
            contract_weights=best_weights,
            seed=99,
        )
        portfolio["micro_multiplier"] = best_weights
        portfolio["sizing_optimised"] = True
        for step_i in range(1, config.n_steps + 1):
            key = f"step{step_i}_pass_rate"
            portfolio[f"opt_{key}"] = final_mc.get(key, 0.0)
        portfolio["opt_final_pass_rate"] = final_mc.get("final_pass_rate", 0.0)
        portfolio["opt_p95_dd"] = final_mc["p95_worst_dd_pct"]
        portfolio["opt_avg_trades_to_pass"] = final_mc["avg_trades_to_pass"]
        portfolio["median_trades_to_pass"] = final_mc["median_trades_to_pass"]
        portfolio["p75_trades_to_pass"] = final_mc["p75_trades_to_pass"]
        portfolio["step_median_trades"] = final_mc["step_median_trades"]
        results.append(portfolio)

        final_step_key = f"step{config.n_steps}_pass_rate"
        logger.info(
            f"  Best weights: {best_weights} -> pass={final_mc.get(final_step_key, 0.0):.1%}, DD={final_mc['p95_worst_dd_pct']:.1%}"
        )

    return results


# ============================================================================
# STAGE 6b: Portfolio robustness test
# ============================================================================

def portfolio_robustness_test(
    portfolios: list[dict],
    return_matrix: pd.DataFrame,
    raw_trade_lists: dict[str, list[float]] | None = None,
    prop_config: PropFirmConfig | None = None,
    n_sims: int = 1_000,
) -> list[dict]:
    """Test portfolio stability via weight perturbation and remove-one analysis.

    For each portfolio:
    1. Perturb each strategy weight by ±0.1, run quick MC, measure pass_rate change
    2. Remove each strategy one at a time, run quick MC, measure pass_rate change
    3. Compute robustness_score from stability metrics
    """
    config = prop_config or The5ersBootcampConfig()
    final_step_key = f"step{config.n_steps}_pass_rate"
    weight_options = [0.1, 0.2, 0.3, 0.5, 0.7, 1.0]

    for portfolio in portfolios[:10]:
        names = portfolio["strategy_names"]
        weights = portfolio.get("micro_multiplier", {s: 0.3 for s in names})

        # Build trade lists
        trade_lists: dict[str, list[float]] = {}
        for name in names:
            if raw_trade_lists and name in raw_trade_lists:
                trade_lists[name] = raw_trade_lists[name]
            elif name in return_matrix.columns:
                vals = return_matrix[name].values
                trades = [float(v) for v in vals if v != 0.0]
                if trades:
                    trade_lists[name] = trades

        if not trade_lists:
            portfolio["robustness_score"] = 0.0
            continue

        # Baseline pass rate
        baseline_mc = portfolio_monte_carlo(
            trade_lists, config, n_sims=n_sims,
            contract_weights=weights,
        )
        baseline_rate = baseline_mc.get(final_step_key, baseline_mc.get("pass_rate", 0.0))

        # 1. Weight perturbation: ±0.1 for each strategy
        weight_changes: list[float] = []
        for strat in list(trade_lists.keys()):
            orig_w = weights.get(strat, 0.3)
            for delta in [-0.1, 0.1]:
                new_w = orig_w + delta
                # Snap to nearest valid weight
                new_w = min(weight_options, key=lambda opt: abs(opt - new_w))
                if new_w == orig_w:
                    continue
                perturbed = {**weights, strat: new_w}
                mc = portfolio_monte_carlo(
                    trade_lists, config, n_sims=n_sims,
                    contract_weights=perturbed,
                )
                rate = mc.get(final_step_key, mc.get("pass_rate", 0.0))
                weight_changes.append(abs(rate - baseline_rate))

        # 2. Remove-one test
        remove_changes: list[float] = []
        if len(trade_lists) > 1:
            for strat in list(trade_lists.keys()):
                reduced_lists = {s: t for s, t in trade_lists.items() if s != strat}
                reduced_weights = {s: w for s, w in weights.items() if s != strat}
                if not reduced_lists:
                    continue
                mc = portfolio_monte_carlo(
                    reduced_lists, config, n_sims=n_sims,
                    contract_weights=reduced_weights,
                )
                rate = mc.get(final_step_key, mc.get("pass_rate", 0.0))
                remove_changes.append(abs(rate - baseline_rate))

        # 3. Compute robustness score
        weight_stability = 1.0 - max(weight_changes) if weight_changes else 1.0
        remove_stability = 1.0 - max(remove_changes) if remove_changes else 1.0
        robustness_score = weight_stability * 0.5 + remove_stability * 0.5
        robustness_score = max(0.0, min(1.0, robustness_score))

        portfolio["robustness_score"] = round(robustness_score, 4)
        portfolio["weight_stability"] = round(weight_stability, 4)
        portfolio["remove_stability"] = round(remove_stability, 4)

        if robustness_score < 0.5:
            logger.warning(
                f"Fragile portfolio (robustness={robustness_score:.2f}): "
                f"{', '.join(names[:3])}..."
            )
        else:
            logger.info(f"Robust portfolio (robustness={robustness_score:.2f}): {len(names)} strategies")

    return portfolios


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

def run_portfolio_selection(
    leaderboard_path: str = "Outputs/ultimate_leaderboard_bootcamp.csv",
    runs_base_path: str = "Outputs/runs",
    output_dir: str = "Outputs",
    n_sims_mc: int | None = None,
    n_sims_sizing: int | None = None,
    n_sims_final: int | None = None,
    config: dict | None = None,
) -> dict:
    """Run the full 6-stage portfolio selection pipeline.

    Returns dict with top portfolio info.
    """
    logger.info("=" * 60)
    logger.info("PORTFOLIO SELECTOR — Starting")
    logger.info("=" * 60)

    # Read config overrides
    if config is None:
        try:
            from modules.config_loader import load_config
            config = load_config()
        except Exception:
            config = {}
    ps_cfg = config.get("pipeline", {}).get("portfolio_selector", {}) if config else {}
    if n_sims_mc is None:
        n_sims_mc = int(ps_cfg.get("n_sims_mc", 10_000))
    if n_sims_sizing is None:
        n_sims_sizing = int(ps_cfg.get("n_sims_sizing", 1_000))
    if n_sims_final is None:
        n_sims_final = int(ps_cfg.get("n_sims_final", n_sims_mc))

    # Resolve prop firm program
    program = str(ps_cfg.get("prop_firm_program", "bootcamp"))
    target = float(ps_cfg.get("prop_firm_target", 250_000))
    prop_config = _resolve_prop_config(program, target)
    logger.info(f"Prop firm: {prop_config.firm_name} {prop_config.program_name} "
                f"(${prop_config.target_balance:,.0f}, {prop_config.n_steps} steps)")

    # Stage 1: Hard filter
    quality_flags_cfg = ps_cfg.get("quality_flags", ["ROBUST", "STABLE"])
    if isinstance(quality_flags_cfg, str):
        quality_flags_cfg = [quality_flags_cfg]
    candidates = hard_filter_candidates(
        leaderboard_path,
        oos_pf_threshold=float(ps_cfg.get("oos_pf_threshold", 1.0)),
        bootcamp_score_min=float(ps_cfg.get("bootcamp_score_min", 40)),
        candidate_cap=int(ps_cfg.get("candidate_cap", 60)),
        quality_flags=quality_flags_cfg,
    )
    if not candidates:
        logger.warning("No candidates passed hard filter. Aborting.")
        return {"status": "no_candidates"}

    # Stage 2: Build return matrix
    return_matrix = build_return_matrix(candidates, runs_base_path)
    if return_matrix.empty:
        logger.warning("Return matrix is empty. Aborting.")
        return {"status": "no_returns"}

    # Stage 2b: Load raw per-trade PnL for MC (preserves individual trades)
    raw_trades = _load_raw_trade_lists(
        candidates, list(return_matrix.columns), runs_base_path,
    )

    # Stage 3: Correlation matrix (uses daily return matrix — correct for corr)
    corr_matrix = compute_correlation_matrix(return_matrix, output_dir=output_dir)

    # Stage 3a: Multi-layer correlation (if enabled)
    use_multi_layer = bool(ps_cfg.get("use_multi_layer_correlation", True))
    multi_layer_corr: dict[str, pd.DataFrame] | None = None
    if use_multi_layer:
        multi_layer_corr = compute_multi_layer_correlation(
            return_matrix, output_dir=output_dir,
        )

    # Stage 3b: Pre-sweep correlation dedup
    candidates = correlation_dedup(candidates, corr_matrix, return_matrix)

    # Stage 4: Sweep combinations
    combinations = sweep_combinations(
        candidates, corr_matrix, return_matrix,
        n_min=int(ps_cfg.get("n_min", 3)),
        n_max=int(ps_cfg.get("n_max", 8)),
        max_per_market=int(ps_cfg.get("max_strategies_per_market", 2)),
        max_equity_index=int(ps_cfg.get("max_equity_index_strategies", 3)),
        max_dd_overlap=float(ps_cfg.get("max_dd_overlap", 0.30)),
        multi_layer_corr=multi_layer_corr,
        active_corr_threshold=float(ps_cfg.get("active_corr_threshold", 0.50)),
        dd_corr_threshold=float(ps_cfg.get("dd_corr_threshold", 0.40)),
        tail_coloss_threshold=float(ps_cfg.get("tail_coloss_threshold", 0.30)),
        use_ecd=bool(ps_cfg.get("use_ecd", True)),
        max_ecd=float(ps_cfg.get("max_ecd", 0.03)),
        candidate_cap=int(ps_cfg.get("sweep_top_n", 50)),
        max_combinations=int(ps_cfg.get("max_combinations", 10_000_000_000)),
    )
    if not combinations:
        logger.warning("No valid combinations found. Aborting.")
        return {"status": "no_combinations"}

    # Stage 4b: Regime survival gate
    use_regime_gate = bool(ps_cfg.get("use_regime_gate", True))
    if use_regime_gate:
        combinations = regime_survival_gate(
            combinations, return_matrix,
            min_regime_pf=float(ps_cfg.get("min_regime_pf", 0.8)),
        )
        if not combinations:
            logger.warning("No combinations survived regime gate. Aborting.")
            return {"status": "no_combinations_after_regime_gate"}

    n_tested = len(combinations)

    # Stage 5: Prop firm MC (uses raw trades if available)
    mc_method = str(ps_cfg.get("mc_method", "block_bootstrap"))
    mc_results = run_bootcamp_mc(
        combinations, return_matrix, n_sims=n_sims_mc,
        raw_trade_lists=raw_trades if raw_trades else None,
        prop_config=prop_config,
        mc_method=mc_method,
    )
    if not mc_results:
        logger.warning("No MC results. Aborting.")
        return {"status": "no_mc_results"}

    # Stage 6: Optimise sizing (uses raw trades if available)
    min_pass_rate = 0.40
    if config:
        ps_cfg = config.get("pipeline", {}).get("portfolio_selector", {})
        min_pass_rate = float(ps_cfg.get("min_pass_rate", min_pass_rate))

    dd_p95_limit = float(ps_cfg.get("dd_p95_limit_pct", 0.70))
    dd_p99_limit = float(ps_cfg.get("dd_p99_limit_pct", 0.90))

    # Build candidates_by_label for inverse-DD sizing initialization
    cand_by_label: dict[str, dict] = {}
    for cand in candidates:
        leader_name = str(cand.get("leader_strategy_name", "")).strip()
        market = str(cand.get("market", ""))
        timeframe = str(cand.get("timeframe", ""))
        label = f"{market}_{timeframe}_{leader_name}"
        cand_by_label[label] = cand

    optimised = optimise_sizing(
        mc_results, return_matrix, n_sims=n_sims_sizing,
        final_n_sims=n_sims_final,
        raw_trade_lists=raw_trades if raw_trades else None,
        min_pass_rate=min_pass_rate,
        prop_config=prop_config,
        dd_p95_limit_pct=dd_p95_limit,
        dd_p99_limit_pct=dd_p99_limit,
        candidates_by_label=cand_by_label,
    )

    # Write report (pass candidates for trade frequency estimation)
    # Stage 6b: Robustness test
    optimised = portfolio_robustness_test(
        optimised, return_matrix,
        raw_trade_lists=raw_trades if raw_trades else None,
        prop_config=prop_config,
        n_sims=n_sims_sizing,
    )

    _write_report(optimised, output_dir, candidates, prop_config=prop_config)

    # Print summary
    _print_summary(candidates, return_matrix, combinations, optimised)

    return {
        "status": "success",
        "n_candidates": len(candidates),
        "n_strategies_in_matrix": len(return_matrix.columns),
        "n_combinations_tested": n_tested,
        "top_portfolio": optimised[0] if optimised else None,
    }


def _write_report(
    portfolios: list[dict],
    output_dir: str,
    candidates: list[dict] | None = None,
    prop_config: PropFirmConfig | None = None,
) -> None:
    """Write portfolio_selector_report.csv with time-to-fund estimates."""
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "portfolio_selector_report.csv")

    # Build lookup: strategy label -> candidate dict for trade frequency
    cand_by_label: dict[str, dict] = {}
    if candidates:
        for cand in candidates:
            leader_name = str(cand.get("leader_strategy_name", "")).strip()
            market = str(cand.get("market", ""))
            timeframe = str(cand.get("timeframe", ""))
            label = f"{market}_{timeframe}_{leader_name}"
            cand_by_label[label] = cand

    rows: list[dict] = []
    for rank, p in enumerate(portfolios, 1):
        cfg = prop_config or The5ersBootcampConfig()
        n_steps = cfg.n_steps
        # Get final step pass rate dynamically
        final_rate = p.get(f"opt_step{n_steps}_pass_rate",
                          p.get(f"step{n_steps}_pass_rate",
                                p.get("opt_final_pass_rate",
                                      p.get("final_pass_rate", 0.0))))
        p95_dd = p.get("opt_p95_dd", p.get("p95_worst_dd_pct", 0.0))
        dd_limit = cfg.max_drawdown_pct

        # Count unique markets in portfolio
        strat_names = p.get("strategy_names", [])
        markets = set(n.split("_")[0] for n in strat_names if "_" in n)
        n_markets = len(markets)

        if final_rate > 0.6 and p95_dd < dd_limit * 0.9 and n_markets >= 3:
            verdict = "RECOMMENDED"
        elif final_rate > 0.3 and n_markets >= 2:
            verdict = "VIABLE"
        else:
            verdict = "MARGINAL"

        weights = p.get("micro_multiplier", p.get("contract_weights", {}))

        # Display weights as micro contract counts (weight * 10 = micros)
        micro_display = "|".join(
            f"{k}={int(round(v * 10))} micros" for k, v in weights.items()
        ) if weights else ""

        # Estimate time-to-fund from trade frequency
        median_trades = p.get("median_trades_to_pass", 0.0)
        p75_trades = p.get("p75_trades_to_pass", 0.0)

        total_trades_per_year = 0.0
        for name in strat_names:
            cand = cand_by_label.get(name, {})
            tpy = float(cand.get("leader_trades_per_year", 0))
            if tpy == 0:
                # Fallback: leader_trades / 18 years (approx data span)
                lt = float(cand.get("leader_trades", cand.get("total_trades", 0)))
                tpy = lt / 18 if lt > 0 else 0
            total_trades_per_year += tpy

        trades_per_month = total_trades_per_year / 12 if total_trades_per_year > 0 else 0
        est_months_median = median_trades / trades_per_month if trades_per_month > 0 else 0
        est_months_p75 = p75_trades / trades_per_month if trades_per_month > 0 else 0

        row: dict = {
            "rank": rank,
            "strategy_names": "|".join(strat_names),
            "n_strategies": p.get("n_strategies", 0),
        }
        for si in range(1, max(n_steps, 3) + 1):
            rate = p.get(f"opt_step{si}_pass_rate", p.get(f"step{si}_pass_rate", 0.0))
            row[f"step{si}_pass_rate"] = round(rate, 4)
        row.update({
            "final_pass_rate": round(final_rate, 4),
            "p95_worst_dd_pct": round(p95_dd, 4),
            "avg_oos_pf": round(p.get("avg_oos_pf", 0.0), 4),
            "avg_correlation": round(p.get("avg_corr", 0.0), 4),
            "diversity_score": round(p.get("diversity", 0.0), 4),
            "composite_score": round(p.get("score", 0.0), 4),
            "micro_contracts": micro_display,
            "median_trades_to_fund": round(median_trades, 0),
            "p75_trades_to_fund": round(p75_trades, 0),
            "est_months_median": round(est_months_median, 1),
            "est_months_p75": round(est_months_p75, 1),
            "robustness_score": round(p.get("robustness_score", 0.0), 4),
            "worst_rolling_20_p95": round(p.get("worst_rolling_20_p95", 0.0), 2),
            "max_losing_streak_p95": int(p.get("max_losing_streak_p95", 0)),
            "max_recovery_trades_p95": int(p.get("max_recovery_trades_p95", 0)),
            "verdict": verdict,
        })
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)
    logger.info(f"Report written to {out_path}")


def _print_summary(
    candidates: list[dict],
    return_matrix: pd.DataFrame,
    combinations: list[dict],
    optimised: list[dict],
) -> None:
    """Print human-readable summary."""
    n_rejected = 0  # We track this in sweep but can approximate
    print()
    print("=" * 59)
    print("PORTFOLIO SELECTOR RESULTS")
    print("=" * 59)
    print(f"  Candidates after hard filter: {len(candidates)}")
    print(f"  Return matrix: {len(return_matrix.columns)} strategies x {len(return_matrix)} days")
    print(f"  Combinations tested: {len(combinations)}")

    top3 = optimised[:3]
    if top3:
        print("  Top 3 portfolios by pass rate:")
        for i, p in enumerate(top3, 1):
            names = p.get("strategy_names", [])
            final_rate = p.get("opt_final_pass_rate", p.get("final_pass_rate", 0.0))
            p95_dd = p.get("opt_p95_dd", p.get("p95_worst_dd_pct", 0.0))
            # Names are "MARKET_TIMEFRAME_STRATEGYNAME" — show "MARKET TF TYPE" for readability
            short_names = []
            for n in names:
                parts = n.split("_", 2)  # max 3 parts: market, timeframe, rest
                if len(parts) >= 3:
                    market, tf = parts[0], parts[1]
                    # Extract strategy type from the rest (e.g. "mean_reversion_vol_dip_Refined..." -> "MR")
                    rest = parts[2]
                    if rest.startswith("mean_reversion"):
                        stype = "MR"
                    elif rest.startswith("short_mean_reversion"):
                        stype = "ShortMR"
                    elif rest.startswith("short_breakout"):
                        stype = "ShortBO"
                    elif rest.startswith("short_trend"):
                        stype = "ShortTr"
                    elif rest.startswith("breakout"):
                        stype = "BO"
                    elif rest.startswith("trend"):
                        stype = "Trend"
                    else:
                        stype = rest.split("_")[0][:8]
                    short_names.append(f"{market} {tf} {stype}")
                else:
                    short_names.append(n[:25])
            print(f"    {i}. {', '.join(short_names)} -- {final_rate:.1%} pass, DD {p95_dd:.1%}")

    print("=" * 59)
