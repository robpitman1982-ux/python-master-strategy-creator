# SESSION 47 TASKS — Build portfolio_selector.py (REVISED)

## Date: 2026-03-30

## Read first
Read SESSION_HANDOVER_47.md completely before starting. It contains the full
specification, data structure notes, existing API references, and context.

## Goal
Build `modules/portfolio_selector.py` — the automated portfolio selection system
that takes the full multi-market ultimate leaderboard and outputs the optimal
Bootcamp portfolio with true Pearson correlations and Monte Carlo pass rates.

---

## Step 1 — Read existing modules before writing anything

Read these files to understand what already exists:
- `modules/prop_firm_simulator.py` (789 lines — has all Bootcamp MC logic)
- `modules/portfolio_evaluator.py` (understand return loading patterns)
- `modules/ultimate_leaderboard.py` (understand leaderboard structure)
- `modules/cross_dataset_evaluator.py` (understand daily resampling pattern)
- `Outputs/ultimate_leaderboard_bootcamp.csv` (understand the data)

Do NOT reinvent what already exists in prop_firm_simulator.py.

**Pay special attention to:**
- `_scale_trade_pnl()` in prop_firm_simulator.py — it converts backtest PnL
  (on $250k source capital) to step-appropriate dollar values
- `simulate_single_step()` — the per-step simulator you'll call directly
- The daily resampling pattern in cross_dataset_evaluator.py:
  `trades_df.resample("D", on="exit_time")["net_pnl"].sum()`

---

## Step 2 — Create modules/portfolio_selector.py

Target: ~500-600 lines. Most heavy lifting is in existing modules.

### Imports to use

```python
from modules.prop_firm_simulator import (
    The5ersBootcampConfig,
    PropFirmConfig,
    simulate_single_step,
    _scale_trade_pnl,
)
```

### Stage 1: hard_filter_candidates(leaderboard_path) -> list[dict]
- Load ultimate_leaderboard_bootcamp.csv
- Filter: quality_flag in ('ROBUST', 'STABLE') only
- Filter: oos_pf > 1.4
- Filter: leader_trades >= 60 (fallback to total_trades if leader_trades missing)
- Deduplicate: if same best_refined_strategy_name in same market, keep highest bootcamp_score
  (fallback to leader_pf if bootcamp_score missing)
- **Candidate cap**: If more than 30 candidates pass, keep top 30 by bootcamp_score.
  Log warning: f"Capped candidates from {n} to 30 by bootcamp_score"
- Return filtered list of dicts (one per candidate row)

### Stage 2: build_return_matrix(candidates, runs_base_path) -> pd.DataFrame
- For each candidate, find strategy_returns.csv using run_id + dataset
  Path: {runs_base}/{run_id}/Outputs/{MARKET}_{TIMEFRAME}/strategy_returns.csv
  Where MARKET_TIMEFRAME is derived from dataset column:
  ```python
  parts = dataset.replace('_tradestation.csv', '').split('_')
  dataset_folder = f"{parts[0]}_{parts[1]}"
  ```
- Load each file. **Column name matching**: strategy_returns.csv columns are prefixed
  with run timestamp (e.g. "20260316_1355_ES_60m_RefinedMR_HB12_ATR0.5_DIST1.2_MOM0").
  Match the column by checking if `col.endswith(leader_strategy_name)`.
  If no match found, try checking if leader_strategy_name is a substring of any column.
  If still no match, log warning and skip this candidate.
- **Resample each strategy's trade returns to daily PnL buckets** before joining:
  ```python
  series = df[matched_col].copy()
  series.index = pd.to_datetime(df['exit_time'])
  daily = series.resample('D').sum().fillna(0.0)
  ```
- Outer join all daily series into a single DataFrame, fill NaN with 0.0
- Drop any candidate columns that are all zeros (failed to load)
- Log: f"Built return matrix: {n_cols} strategies x {n_rows} days"
- Return DataFrame with one column per strategy, index = date

### Stage 3: compute_correlation_matrix(return_matrix) -> pd.DataFrame
- Compute pandas .corr() on the daily return matrix
- This is the TRUE Pearson matrix based on actual daily trade P&L
- Save to Outputs/portfolio_selector_matrix.csv
- Log the matrix shape and any pairs with |corr| > 0.3
- Return the matrix

### Stage 4: sweep_combinations(candidates, corr_matrix, return_matrix, n_min=4, n_max=8) -> list[dict]
- Strategy names = columns of return_matrix (only strategies we actually loaded returns for)
- Filter candidates list to only those present in return_matrix columns
- Generate all C(n, k) combinations for k in range(n_min, n_max+1)
- **Combinatorial guard**: Before generating, compute total combinations.
  If total > 500_000, reduce n_max until total < 500_000.
  Log: f"Reduced n_max from {orig} to {n_max} to keep combinations under 500k"
- For each combination: reject if any Pearson pair > 0.4 (use abs(corr_matrix) values)
- For each survivor: compute diversity score and composite score

**Diversity score formula (explicit):**
```python
def _diversity_score(combo_candidates: list[dict]) -> float:
    n = len(combo_candidates)
    markets = set(c.get('market', '') for c in combo_candidates)
    logic_types = set(c.get('strategy_type', '') for c in combo_candidates)
    # Direction: check for short_ prefix in strategy_type
    has_long = any(not c.get('strategy_type', '').startswith('short_') for c in combo_candidates)
    has_short = any(c.get('strategy_type', '').startswith('short_') for c in combo_candidates)
    direction_mix = 1.0 if (has_long and has_short) else 0.0

    market_diversity = len(markets) / max(n, 1)
    logic_diversity = len(logic_types) / max(n, 1)

    return market_diversity * 0.4 + direction_mix * 0.3 + logic_diversity * 0.3
```

**Composite score:**
```python
avg_oos_pf = mean of oos_pf for strategies in combo
avg_corr = mean of abs(pairwise correlations) from corr_matrix for the combo
diversity = _diversity_score(combo_candidates)
score = avg_oos_pf * 30 + diversity * 20 + (1 - avg_corr) * 20
```

- Return top 50 combinations sorted by score descending
- Each result dict should contain: strategy_names (list), score, avg_oos_pf, avg_corr, diversity, n_strategies

### Stage 5: run_bootcamp_mc(combinations, return_matrix, n_sims=10000) -> list[dict]

**CRITICAL: Do NOT use monte_carlo_pass_rate() — it is single-strategy only.**

Build a new `portfolio_monte_carlo()` function:

```python
def portfolio_monte_carlo(
    strategy_trade_lists: dict[str, list[float]],
    config: PropFirmConfig,
    source_capital: float = 250_000.0,
    n_sims: int = 10_000,
    seed: int = 42,
    contract_weights: dict[str, float] | None = None,
) -> dict:
    """
    Monte Carlo for a PORTFOLIO of strategies.

    For each simulation:
    1. For each strategy, independently shuffle its trade list
    2. Interleave all shuffled trades into a single combined sequence
       (round-robin across strategies, since order is randomised anyway)
    3. Apply contract_weights scaling to each trade's PnL
    4. Run the combined trade list through simulate_challenge()

    Returns dict with:
        pass_rate, step1_pass_rate, step2_pass_rate, step3_pass_rate,
        median_worst_dd_pct, p95_worst_dd_pct, avg_trades_to_pass
    """
```

Implementation notes:
- Extract per-strategy trade lists from return_matrix: for each column,
  take non-zero values as the trade list (zeros are non-trading days)
- For each sim: shuffle each strategy's trades independently, then interleave
  by round-robin (take one from strategy A, one from B, one from C, repeat).
  This preserves the trade count per strategy while randomising sequence.
- Apply contract weights: `weighted_pnl = raw_pnl * weight` before feeding
  to simulate_challenge()
- Call `simulate_challenge(combined_trades, config, source_capital)` which
  handles PnL scaling via `_scale_trade_pnl()` internally
- Track step_pass_counts, worst DDs, trades to pass — same pattern as
  the existing `monte_carlo_pass_rate()` function
- Default contract_weights = 1.0 for all strategies

For each of the top 50 combinations from Stage 4:
- Build strategy_trade_lists from return_matrix columns
- Run portfolio_monte_carlo with n_sims=10,000
- Return results sorted by step3_pass_rate (= passed all 3 steps) descending

### Stage 6: optimise_sizing(top_portfolios, return_matrix, n_sims=1000) -> list[dict]

**NOTE: Use n_sims=1000 for sizing search (not 10,000) to keep runtime manageable.**

- For top 10 portfolios from Stage 5:
- Weights to try: [0.5, 1.0, 1.5] per strategy (3^n combinations)
- **Guard**: if 3^n > 10_000 (n > 8), skip sizing optimisation for this portfolio,
  keep default weights of 1.0, log warning
- For each weight combination:
  - Run portfolio_monte_carlo with n_sims=1000
  - Track: step3_pass_rate, p95_worst_dd_pct
- Find weights that maximise step3_pass_rate while keeping p95_worst_dd_pct < 0.045
  (leaving 0.5% margin below the 5% max loss)
- If no combo satisfies DD constraint, keep the one with lowest p95_worst_dd_pct
- Return optimised portfolios with weights, pass rates, DD stats

### Main function: run_portfolio_selection(config=None) -> dict

```python
def run_portfolio_selection(
    leaderboard_path: str = "Outputs/ultimate_leaderboard_bootcamp.csv",
    runs_base_path: str = "Outputs/runs",
    output_dir: str = "Outputs",
    n_sims_mc: int = 10_000,
    n_sims_sizing: int = 1_000,
    config: dict | None = None,
) -> dict:
```

- Orchestrate all 6 stages
- Write portfolio_selector_report.csv to output_dir with columns:
  rank, strategy_names, n_strategies, step1_pass_rate, step2_pass_rate,
  step3_pass_rate, p95_worst_dd_pct, avg_oos_pf, avg_correlation,
  diversity_score, composite_score, contract_weights, verdict
- verdict = "RECOMMENDED" if step3_pass_rate > 0.6 and p95_worst_dd_pct < 0.045
            "VIABLE" if step3_pass_rate > 0.3
            "MARGINAL" otherwise
- Write portfolio_selector_matrix.csv (the Pearson matrix)
- Print summary:
  ```
  ═══════════════════════════════════════════════════════════
  PORTFOLIO SELECTOR RESULTS
  ═══════════════════════════════════════════════════════════
  Candidates after hard filter: {n}
  Return matrix: {cols} strategies x {rows} days
  Combinations tested: {n_tested} (rejected {n_rejected} on correlation)
  Top 3 portfolios by Bootcamp pass rate:
    1. {names} — {step3_pass_rate:.1%} pass, DD {p95_dd:.1%}
    2. ...
    3. ...
  ═══════════════════════════════════════════════════════════
  ```
- Return dict with top portfolio info

---

## Step 3 — Create tests/test_portfolio_selector.py

Smoke tests with mock data (no real CSV files required):

```python
"""Tests for portfolio_selector module."""
import tempfile
from pathlib import Path
import pandas as pd
import numpy as np
import pytest
```

### test_hard_filter_removes_weak_candidates
- Create mock leaderboard DataFrame with 10 rows:
  - 3 with quality_flag='REGIME_DEPENDENT' (should be removed)
  - 2 with oos_pf=1.2 (below 1.4 threshold, should be removed)
  - 1 with leader_trades=30 (below 60 threshold, should be removed)
  - 4 valid candidates
- Write to temp CSV, call hard_filter_candidates()
- Assert len(result) == 4

### test_deduplication_keeps_best
- Create 2 candidates with same best_refined_strategy_name and same market
- One has bootcamp_score=80, other has bootcamp_score=70
- Verify only the 80-score one survives

### test_correlation_rejects_high_pairs
- Create mock return matrix with 4 strategies
- Set strategies A and B to have correlation ~0.6 (use np.random with seed)
- Call sweep_combinations with n_min=3, n_max=3
- Verify no combination containing both A and B is returned

### test_portfolio_mc_returns_valid_rate
- Create 3 mock trade lists: each 100 trades with mean +500, std 2000
- Call portfolio_monte_carlo with n_sims=100
- Assert 0.0 <= result['pass_rate'] <= 1.0
- Assert all step rates are between 0 and 1

### test_report_written
- Run full pipeline on mock data:
  - Create temp dir with mock leaderboard CSV and mock strategy_returns.csv files
  - Call run_portfolio_selection() pointing at temp dirs
- Verify portfolio_selector_report.csv exists in output dir
- Verify it has expected columns: rank, strategy_names, step3_pass_rate

---

## Step 4 — Wire into master_strategy_engine.py

At the end of master_strategy_engine.py, after the cross_dataset_evaluator call
and after the write_master_leaderboards call, add:

```python
# Portfolio selection (optional, controlled by config flag)
if not get_nested(_cfg, "pipeline", "skip_portfolio_selector", default=False):
    try:
        from modules.portfolio_selector import run_portfolio_selection
        logger.info("Running portfolio selection...")
        run_portfolio_selection(
            leaderboard_path=str(OUTPUTS_DIR / "ultimate_leaderboard_bootcamp.csv"),
            runs_base_path=str(OUTPUTS_DIR / "runs"),
            output_dir=str(OUTPUTS_DIR),
        )
    except Exception as e:
        logger.warning(f"Portfolio selection failed: {e}")
        import traceback
        traceback.print_exc()
```

Use `get_nested()` from config_loader (already imported in master_strategy_engine.py).
Mirror the exact pattern used for `skip_portfolio_evaluation`.

---

## Step 5 — Update CLAUDE.md

In the "Prop firm system" or issues section, add:
```
- [x] Portfolio selector module — Bootcamp MC pass rate, true Pearson correlation gate,
      position sizing optimiser (modules/portfolio_selector.py) (Session 47)
```

Update "Last updated" line at bottom:
```
## Last updated
2026-03-30 — Session 47: Build portfolio_selector.py (Bootcamp MC + correlation + sizing)
```

---

## Step 6 — Add to CHANGELOG_DEV.md (at the TOP)

```
## 2026-03-30 — Session 47: Portfolio selector module

**What was done**:
- Built modules/portfolio_selector.py — 6-stage portfolio selection pipeline:
  1. Hard filter gate (ROBUST/STABLE, OOS PF > 1.4, 60+ trades, dedup, cap at 30)
  2. Per-trade return extraction + daily resampling + true Pearson correlation matrix
  3. Combinatorial sweep (C(n,4..8) with 500k guard), reject pairs with |Pearson| > 0.4
  4. Portfolio Monte Carlo (10,000 sims, independent per-strategy shuffle + interleave)
  5. Position sizing optimiser (grid search weights [0.5, 1.0, 1.5], 1,000 sims)
- Portfolio MC is a NEW function — does not reuse single-strategy monte_carlo_pass_rate()
  because portfolios require independent per-strategy shuffling and interleaving
- Added tests/test_portfolio_selector.py — 5 smoke tests
- Wired into master_strategy_engine.py (skip_portfolio_selector config flag)
- Outputs: portfolio_selector_report.csv, portfolio_selector_matrix.csv

**Why this matters**:
- Closes the gap between strategy discovery (leaderboard) and portfolio decision
- First time we have ACTUAL Pearson correlations from real daily-bucketed trade P&L
- First time we have a Bootcamp Monte Carlo pass rate across portfolio combinations
- Enables fully automated "which strategies to actually run" decision

**Key design decisions**:
- Daily resampling before correlation (same pattern as cross_dataset_evaluator.py)
- Column name matching by endswith(leader_strategy_name) — handles timestamp prefixes
- Candidate cap at 30 to prevent combinatorial explosion
- Combination guard at 500k to prevent runaway sweep
- Sizing MC uses 1,000 sims (not 10,000) for speed — acceptable for relative comparison
- Diversity score: market variety 40%, direction mix 30%, logic type 30%

**Next priorities**:
1. Run portfolio_selector on ES + CL data to validate
2. Wait for NQ/GC runs to complete, rebuild leaderboard, re-run selector
3. Dashboard integration (Portfolio Selector tab)
```

---

## Step 7 — Run tests

```bash
python -m pytest tests/ -v
```

All tests must pass. Fix any failures before proceeding.

---

## Step 8 — Commit and push

```bash
git add -A
git commit -m "feat: portfolio_selector — Bootcamp MC pass rate, Pearson correlation gate, position sizing optimiser"
git push origin main
```

---

## CRITICAL IMPLEMENTATION NOTES

1. **Do NOT use monte_carlo_pass_rate() for portfolio MC.** It shuffles a single
   flat trade list. For portfolios, you need to shuffle each strategy independently
   and interleave them. Build portfolio_monte_carlo() as a new function.

2. **simulate_challenge() handles PnL scaling internally** via _scale_trade_pnl().
   It converts backtest PnL (as % of source_capital=$250k) to step-appropriate dollars.
   So pass raw backtest PnL values — do NOT pre-scale them.

3. **strategy_returns.csv column names are timestamp-prefixed.**
   e.g. "20260316_1355_ES_60m_RefinedMR_HB12_ATR0.5_DIST1.2_MOM0"
   Match by checking if col.endswith(leader_strategy_name).

4. **Resample to daily BEFORE computing correlation.** Trade-level exit times are
   sparse and misaligned across timeframes. Daily resampling makes correlation
   meaningful. Pattern: `series.resample('D').sum().fillna(0.0)`

5. **The cross_timeframe_correlation_matrix.csv files in run outputs are WRONG.**
   They show losing family representatives, not accepted strategies. IGNORE THEM.

6. **leader_win_rate column is 0.0 for all strategies.** Engine bug. Do not use.

7. **The portfolio_evaluator.py has good patterns** for loading strategy data and
   computing metrics. Study _rebuild_strategy_from_leaderboard_row() and the
   daily_returns_dict construction pattern before reimplementing.

8. **Contract weights in portfolio_monte_carlo**: multiply each trade's raw PnL
   by the weight BEFORE passing to simulate_challenge(). So a weight of 1.5
   means 1.5 contracts, and a $1000 raw trade becomes $1500.
