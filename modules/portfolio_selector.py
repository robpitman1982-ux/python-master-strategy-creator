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
) -> list[dict]:
    """Load ultimate_leaderboard_bootcamp.csv and apply hard filters.

    Filters:
    - quality_flag in (ROBUST, STABLE)
    - oos_pf > oos_pf_threshold (default 1.0)
    - bootcamp_score > bootcamp_score_min (default 40)
    - leader_trades >= 60 (fallback to total_trades)
    - Dedup: same best_refined_strategy_name + market -> keep highest bootcamp_score
    - Cap at candidate_cap (default 50) candidates by bootcamp_score
    """
    df = pd.read_csv(leaderboard_path)
    n_total = len(df)
    logger.info(f"Loaded {n_total} rows from {leaderboard_path}")

    # Quality filter
    valid_flags = {"ROBUST", "STABLE"}
    df = df[df["quality_flag"].astype(str).str.strip().str.upper().isin(valid_flags)].copy()
    logger.info(f"After quality filter (ROBUST/STABLE): {len(df)}")

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
    """Find strategy_returns.csv for a candidate."""
    run_id = str(candidate.get("run_id", ""))
    dataset = str(candidate.get("dataset", ""))

    if not run_id or not dataset:
        return None

    # Derive dataset folder: "ES_30m_2008_2026_tradestation.csv" -> "ES_30m"
    parts = dataset.replace("_tradestation.csv", "").split("_")
    if len(parts) >= 2:
        dataset_folder = f"{parts[0]}_{parts[1]}"
    else:
        dataset_folder = dataset.replace(".csv", "")

    path = os.path.join(runs_base, run_id, "Outputs", dataset_folder, "strategy_returns.csv")
    if os.path.exists(path):
        return path

    # Try with artifacts/ prefix (cloud download layout)
    path2 = os.path.join(runs_base, run_id, "artifacts", "Outputs", dataset_folder, "strategy_returns.csv")
    if os.path.exists(path2):
        return path2

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


def sweep_combinations(
    candidates: list[dict],
    corr_matrix: pd.DataFrame,
    return_matrix: pd.DataFrame,
    n_min: int = 4,
    n_max: int = 8,
) -> list[dict]:
    """Sweep all C(n,k) combinations, reject high-correlation pairs, score survivors."""
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

    # Combinatorial guard
    from math import comb
    orig_n_max = n_max
    total = sum(comb(n, k) for k in range(n_min, n_max + 1))
    while total > 500_000 and n_max > n_min:
        n_max -= 1
        total = sum(comb(n, k) for k in range(n_min, n_max + 1))
    if n_max != orig_n_max:
        logger.warning(f"Reduced n_max from {orig_n_max} to {n_max} to keep combinations under 500k")

    total_combos = sum(comb(n, k) for k in range(n_min, n_max + 1))
    logger.info(f"Sweeping {total_combos} combinations (n={n}, k={n_min}..{n_max})")

    abs_corr = corr_matrix.abs()
    results: list[dict] = []
    n_rejected = 0

    for k in range(n_min, n_max + 1):
        for combo in itertools.combinations(strategy_names, k):
            # Reject if any pair > 0.4
            rejected = False
            pair_corrs: list[float] = []
            for i in range(len(combo)):
                for j in range(i + 1, len(combo)):
                    c_i, c_j = combo[i], combo[j]
                    if c_i in abs_corr.columns and c_j in abs_corr.columns:
                        val = float(abs_corr.loc[c_i, c_j])
                    else:
                        val = 0.0
                    pair_corrs.append(val)
                    if val > 0.4:
                        rejected = True
                        break
                if rejected:
                    break

            if rejected:
                n_rejected += 1
                continue

            # Compute scores
            combo_cands = [cand_by_name[s] for s in combo]
            avg_oos_pf = mean(
                float(c.get("oos_pf", 1.0)) for c in combo_cands
            )
            avg_corr = mean(pair_corrs) if pair_corrs else 0.0
            diversity = _diversity_score(combo_cands)
            score = avg_oos_pf * 20 + diversity * 30 + (1 - avg_corr) * 20

            results.append({
                "strategy_names": list(combo),
                "score": score,
                "avg_oos_pf": avg_oos_pf,
                "avg_corr": avg_corr,
                "diversity": diversity,
                "n_strategies": k,
            })

    # Sort by score descending, keep top 50
    results.sort(key=lambda r: r["score"], reverse=True)
    results = results[:50]

    logger.info(f"Sweep complete: {len(results)} survivors, {n_rejected} rejected on correlation")
    return results


# ============================================================================
# STAGE 5: Portfolio Monte Carlo
# ============================================================================

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
       (round-robin across strategies)
    3. Apply contract_weights scaling to each trade's PnL
    4. Run the combined trade list through simulate_challenge()

    Returns dict with pass_rate, step pass rates, DD stats, avg_trades_to_pass.
    """
    if contract_weights is None:
        contract_weights = {s: 1.0 for s in strategy_trade_lists}

    rng = random.Random(seed)
    strategy_names = list(strategy_trade_lists.keys())
    trade_lists = {s: list(strategy_trade_lists[s]) for s in strategy_names}

    pass_count = 0
    step_pass_counts = [0] * config.n_steps
    worst_dds: list[float] = []
    trades_to_pass: list[int] = []
    step_trades_list: list[list[int]] = []  # per-sim [step1_trades, step2_trades, ...]

    for _ in range(n_sims):
        # 1. Independently shuffle each strategy's trades
        shuffled: dict[str, list[float]] = {}
        for s in strategy_names:
            t = trade_lists[s].copy()
            rng.shuffle(t)
            shuffled[s] = t

        # 2. Interleave by round-robin with weight scaling
        combined: list[float] = []
        max_len = max(len(shuffled[s]) for s in strategy_names) if strategy_names else 0

        for idx in range(max_len):
            for s in strategy_names:
                if idx < len(shuffled[s]):
                    w = contract_weights.get(s, 1.0)
                    combined.append(shuffled[s][idx] * w)

        # 3. Run through simulate_challenge
        result = simulate_challenge(combined, config, source_capital)
        worst_dds.append(result.worst_drawdown_pct)

        for step in result.steps:
            if step.passed:
                step_pass_counts[step.step_number - 1] += 1
            else:
                break  # Don't count later steps if this one failed

        if result.passed_all_steps:
            pass_count += 1
            trades_to_pass.append(result.total_trades_used)
            step_trades_list.append([s.trades_taken for s in result.steps])

    worst_dd_arr = np.array(worst_dds)
    step_pass_rates = [c / n_sims for c in step_pass_counts]

    # Per-step trade medians for passing sims
    step_median_trades: list[float] = []
    if step_trades_list:
        for i in range(config.n_steps):
            vals = [st[i] for st in step_trades_list if i < len(st)]
            step_median_trades.append(float(np.median(vals)) if vals else 0.0)

    return {
        "pass_rate": pass_count / n_sims,
        "step1_pass_rate": step_pass_rates[0] if len(step_pass_rates) > 0 else 0.0,
        "step2_pass_rate": step_pass_rates[1] if len(step_pass_rates) > 1 else 0.0,
        "step3_pass_rate": step_pass_rates[2] if len(step_pass_rates) > 2 else 0.0,
        "median_worst_dd_pct": float(np.median(worst_dd_arr)),
        "p95_worst_dd_pct": float(np.percentile(worst_dd_arr, 95)),
        "avg_trades_to_pass": float(np.mean(trades_to_pass)) if trades_to_pass else 0.0,
        "median_trades_to_pass": float(np.median(trades_to_pass)) if trades_to_pass else 0.0,
        "p75_trades_to_pass": float(np.percentile(trades_to_pass, 75)) if trades_to_pass else 0.0,
        "step_median_trades": step_median_trades,
    }


def run_bootcamp_mc(
    combinations: list[dict],
    return_matrix: pd.DataFrame,
    n_sims: int = 10_000,
    raw_trade_lists: dict[str, list[float]] | None = None,
    prop_config: PropFirmConfig | None = None,
) -> list[dict]:
    """Run portfolio Monte Carlo for top combinations from sweep.

    Args:
        raw_trade_lists: If provided, use raw per-trade PnL instead of
            extracting from the daily return matrix. This preserves
            individual trades that would otherwise be summed on the same day.
        prop_config: Prop firm config to simulate against. Defaults to Bootcamp $250K.

    Returns combinations enriched with MC results, sorted by final step pass rate.
    """
    config = prop_config or The5ersBootcampConfig()
    results: list[dict] = []

    for i, combo in enumerate(combinations):
        names = combo["strategy_names"]
        logger.info(f"Portfolio MC {i + 1}/{len(combinations)}: {len(names)} strategies, {n_sims} sims")

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
            logger.warning(f"No trade data for combination {i + 1}, skipping")
            continue

        mc = portfolio_monte_carlo(trade_lists, config, n_sims=n_sims)

        result = {**combo, **mc}
        results.append(result)

    # Sort by final step pass rate (step3 for bootcamp, step2 for high stakes, etc.)
    final_step_key = f"step{config.n_steps}_pass_rate"
    results.sort(key=lambda r: r.get(final_step_key, r.get("pass_rate", 0.0)), reverse=True)
    logger.info(f"MC complete for {len(results)} portfolios ({config.program_name})")
    return results


# ============================================================================
# STAGE 6: Optimise sizing
# ============================================================================

def optimise_sizing(
    top_portfolios: list[dict],
    return_matrix: pd.DataFrame,
    n_sims: int = 1_000,
    raw_trade_lists: dict[str, list[float]] | None = None,
    min_pass_rate: float = 0.40,
    prop_config: PropFirmConfig | None = None,
) -> list[dict]:
    """Grid-search contract weights for top portfolios.

    Uses n_sims=1000 for speed during grid search. After finding best weights,
    runs a final 10k-sim MC for accurate step rates.

    Objective: minimize median_trades_to_pass subject to pass_rate >= min_pass_rate.
    This finds the fastest path to funding rather than the safest.
    """
    config = prop_config or The5ersBootcampConfig()
    weight_options = [0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
    n_weight_opts = len(weight_options)
    results: list[dict] = []

    for i, portfolio in enumerate(top_portfolios[:10]):
        names = portfolio["strategy_names"]
        n_strats = len(names)

        # Guard: n_weight_opts^n > 10,000 -> skip sizing
        total_weight_combos = n_weight_opts ** n_strats
        if total_weight_combos > 10_000:
            logger.warning(
                f"Portfolio {i + 1}: {n_weight_opts}^{n_strats} = {total_weight_combos} weight combos — "
                f"skipping sizing, using default weights"
            )
            portfolio["micro_multiplier"] = {s: 0.1 for s in names}
            portfolio["sizing_optimised"] = False
            results.append(portfolio)
            continue

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

        logger.info(
            f"Sizing optimisation {i + 1}: {n_strats} strategies, "
            f"{n_weight_opts**len(strat_names_in_matrix)} weight combos x {n_sims} sims"
        )

        for weight_combo in itertools.product(weight_options, repeat=len(strat_names_in_matrix)):
            weights = dict(zip(strat_names_in_matrix, weight_combo))

            mc = portfolio_monte_carlo(
                trade_lists, config,
                n_sims=n_sims,
                contract_weights=weights,
            )

            final_step_key = f"step{config.n_steps}_pass_rate"
            pass_rate = mc.get(final_step_key, mc.get("pass_rate", 0.0))
            dd = mc["p95_worst_dd_pct"]
            trades = mc["median_trades_to_pass"]

            # Minimize trades-to-pass subject to pass_rate >= min_pass_rate
            if pass_rate >= min_pass_rate:
                if trades > 0 and (best_trades is None or trades < best_trades):
                    best_trades = trades
                    best_pass_rate = pass_rate
                    best_dd = dd
                    best_weights = weights.copy()
            elif best_weights is None:
                # No combo meets minimum yet; track best pass rate as fallback
                if pass_rate > best_pass_rate:
                    best_pass_rate = pass_rate
                    best_weights = weights.copy()
                    best_dd = dd

        if best_weights is None:
            best_weights = {s: 0.1 for s in strat_names_in_matrix}

        # Final MC at full sim count with optimised weights — all step rates
        # from the SAME experiment so they're comparable
        final_mc = portfolio_monte_carlo(
            trade_lists, config,
            n_sims=10_000,
            contract_weights=best_weights,
            seed=99,
        )
        portfolio["micro_multiplier"] = best_weights
        portfolio["sizing_optimised"] = True
        for step_i in range(1, config.n_steps + 1):
            key = f"step{step_i}_pass_rate"
            portfolio[f"opt_{key}"] = final_mc.get(key, 0.0)
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
# MAIN ORCHESTRATOR
# ============================================================================

def run_portfolio_selection(
    leaderboard_path: str = "Outputs/ultimate_leaderboard_bootcamp.csv",
    runs_base_path: str = "Outputs/runs",
    output_dir: str = "Outputs",
    n_sims_mc: int = 10_000,
    n_sims_sizing: int = 1_000,
    config: dict | None = None,
) -> dict:
    """Run the full 6-stage portfolio selection pipeline.

    Returns dict with top portfolio info.
    """
    logger.info("=" * 60)
    logger.info("PORTFOLIO SELECTOR — Starting")
    logger.info("=" * 60)

    # Read config overrides
    ps_cfg = config.get("pipeline", {}).get("portfolio_selector", {}) if config else {}
    n_sims_mc = int(ps_cfg.get("n_sims_mc", n_sims_mc))
    n_sims_sizing = int(ps_cfg.get("n_sims_sizing", n_sims_sizing))

    # Resolve prop firm program
    program = str(ps_cfg.get("prop_firm_program", "bootcamp"))
    target = float(ps_cfg.get("prop_firm_target", 250_000))
    prop_config = _resolve_prop_config(program, target)
    logger.info(f"Prop firm: {prop_config.firm_name} {prop_config.program_name} "
                f"(${prop_config.target_balance:,.0f}, {prop_config.n_steps} steps)")

    # Stage 1: Hard filter
    candidates = hard_filter_candidates(
        leaderboard_path,
        oos_pf_threshold=float(ps_cfg.get("oos_pf_threshold", 1.0)),
        bootcamp_score_min=float(ps_cfg.get("bootcamp_score_min", 40)),
        candidate_cap=int(ps_cfg.get("candidate_cap", 50)),
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

    # Stage 3b: Pre-sweep correlation dedup
    candidates = correlation_dedup(candidates, corr_matrix, return_matrix)

    # Stage 4: Sweep combinations
    combinations = sweep_combinations(candidates, corr_matrix, return_matrix)
    if not combinations:
        logger.warning("No valid combinations found. Aborting.")
        return {"status": "no_combinations"}

    n_tested = len(combinations)

    # Stage 5: Prop firm MC (uses raw trades if available)
    mc_results = run_bootcamp_mc(
        combinations, return_matrix, n_sims=n_sims_mc,
        raw_trade_lists=raw_trades if raw_trades else None,
        prop_config=prop_config,
    )
    if not mc_results:
        logger.warning("No MC results. Aborting.")
        return {"status": "no_mc_results"}

    # Stage 6: Optimise sizing (uses raw trades if available)
    min_pass_rate = 0.40
    if config:
        ps_cfg = config.get("pipeline", {}).get("portfolio_selector", {})
        min_pass_rate = float(ps_cfg.get("min_pass_rate", min_pass_rate))

    optimised = optimise_sizing(
        mc_results, return_matrix, n_sims=n_sims_sizing,
        raw_trade_lists=raw_trades if raw_trades else None,
        min_pass_rate=min_pass_rate,
        prop_config=prop_config,
    )

    # Write report (pass candidates for trade frequency estimation)
    _write_report(optimised, output_dir, candidates)

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
        step1 = p.get("opt_step1_pass_rate", p.get("step1_pass_rate", 0.0))
        step2 = p.get("opt_step2_pass_rate", p.get("step2_pass_rate", 0.0))
        step3 = p.get("opt_step3_pass_rate", p.get("step3_pass_rate", 0.0))
        p95_dd = p.get("opt_p95_dd", p.get("p95_worst_dd_pct", 0.0))

        # Count unique markets in portfolio
        strat_names = p.get("strategy_names", [])
        markets = set(n.split("_")[0] for n in strat_names if "_" in n)
        n_markets = len(markets)

        if step3 > 0.6 and p95_dd < 0.045 and n_markets >= 3:
            verdict = "RECOMMENDED"
        elif step3 > 0.3 and n_markets >= 2:
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

        rows.append({
            "rank": rank,
            "strategy_names": "|".join(strat_names),
            "n_strategies": p.get("n_strategies", 0),
            "step1_pass_rate": round(step1, 4),
            "step2_pass_rate": round(step2, 4),
            "step3_pass_rate": round(step3, 4),
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
            "verdict": verdict,
        })

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
        print("  Top 3 portfolios by Bootcamp pass rate:")
        for i, p in enumerate(top3, 1):
            names = p.get("strategy_names", [])
            step3 = p.get("opt_step3_pass_rate", p.get("step3_pass_rate", 0.0))
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
            print(f"    {i}. {', '.join(short_names)} -- {step3:.1%} pass, DD {p95_dd:.1%}")

    print("=" * 59)
