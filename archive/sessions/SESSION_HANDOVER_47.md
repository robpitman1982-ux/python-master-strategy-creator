# SESSION HANDOVER — Session 47
## Date: 2026-03-30
## For: Claude Opus 4.6 (new chat)

---

## WHAT YOU ARE BUILDING

Automated futures strategy discovery engine targeting The5ers $250K Bootcamp prop firm challenge.
The engine sweeps filter combinations across futures markets to find robust algorithmic strategies.
Goal: build `modules/portfolio_selector.py` — the missing link between strategy discovery and
portfolio decision-making.

**Repo**: `robpitman1982-ux/python-master-strategy-creator` (public GitHub)
**Infra**: GCP n2-highcpu-96 on-demand VMs, strategy-console e2-micro (always-on), GCS bucket `strategy-artifacts-robpitman`
**Dashboard**: Streamlit at `http://35.232.131.181:8501`

---

## CURRENT STATE

### Overnight runs (as of 2026-03-30)

A full 7-market rerun ran overnight via `run_full_rerun.sh` on strategy-console:
ES → CL → NQ → SI → HG → RTY → YM (sequential, STANDARD provisioning, fixed position sizing)

**ES and CL results are downloaded and analysed. NQ and others may still be running or complete.**

Check status:
```bash
# SSH to strategy-console
gcloud compute ssh strategy-console --zone us-central1-c
tail -50 /home/robpitman1982/python-master-strategy-creator/full_rerun.log
gcloud compute instances list --filter="name=strategy-sweep"
gcloud storage ls gs://strategy-artifacts-robpitman/runs/ | grep 20260329
```

Download any remaining market results:
```powershell
cd "C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator"
python cloud/download_run.py --latest
```

### Why these runs exist

Session 45 fixed a CRITICAL position sizing bug: the engine used `self.current_capital`
(compounding) instead of `self.initial_capital` (fixed). Over 18 years with PF 8.0 on NQ,
this produced $20 BILLION PnL on a $250k account. All previous dollar figures were meaningless.
The fix is in commit `80d3fbc`. PF, quality flags, and trade counts are unaffected (ratio-based).
Only dollar metrics changed. All old runs were moved to `Outputs/runs_old_compounded/`.

### ES + CL leaderboard summary (clean data, correct dollar figures)

74 strategies accepted. 15 ROBUST, 11 STABLE.
Key findings from Session 47 analysis:

| Rank | Mkt | TF | Type | PF | OOS PF | Trades | Max DD | BCS |
|------|-----|----|------|----|--------|--------|--------|-----|
| 1 | ES | 30m | MR mom_exhaustion | 2.35 | 2.77 | 100 | $25.6k | 86.4 |
| 2 | ES | 30m | trend | 1.93 | 2.15 | 94 | $16.9k | 82.5 |
| 3 | CL | 60m | breakout | 1.85 | 2.09 | 60 | $22.5k | 78.7 |
| 4 | CL | daily | MR trend_pullback | 1.51 | 1.82 | 293 | $25.7k | 75.3 |
| 5 | CL | daily | short_trend | 1.82 | 1.41 | 182 | $23.3k | 75.0 |
| 6 | CL | 30m | short_breakout | 1.63 | 1.55 | 121 | $5.6k | 66.2 |
| 7 | CL | 15m | MR trend_pullback | 1.47 | 1.85 | 197 | $6.3k | 71.7 |

ES daily MR vol_dip has BCS 88.2 but max DD $145k (58% of $250k) — disqualified on DD.
All 15 ROBUST strategies show OOS PF > IS PF — genuine edge, not overfit.

### The5ers $250K Bootcamp rules (CONFIRMED from screenshot)

CRITICAL corrections from previous analysis:
- **Leverage: 1:30** (not 1:7.5 as previously assumed)
- **Time limit: UNLIMITED** (no 12-week deadline)
- Step 1: $100k balance, +6% target (+$6k), -5% max loss (-$5k)
- Step 2: $150k balance, +6% target (+$9k), -5% max loss (-$7.5k)
- Step 3: $200k balance, +6% target (+$12k), -5% max loss (-$10k)
- Funded: $250k, +5% target, -4% max loss, **-3% daily pause (-$7,500/day)**

Unlimited time means the ONLY constraint is never hitting the max loss line.
With PF > 1.0, you WILL eventually reach the profit target. Drawdown management is everything.

---

## THE TASK FOR THIS SESSION

### Build `modules/portfolio_selector.py`

This is the most important piece missing from the engine. Right now there is a gap between
"strategy discovery" (the leaderboard) and "portfolio decision" (which strategies to actually run).
This module closes that gap.

**What exists already that you can use:**
- `modules/prop_firm_simulator.py` — has `monte_carlo_pass_rate()`, `simulate_challenge()`,
  and `The5ersBootcampConfig` fully implemented. 789 lines. USE THIS.
- `modules/portfolio_evaluator.py` — reads `strategy_returns.csv`, computes correlations. USE THIS.
- `modules/ultimate_leaderboard.py` — leaderboard aggregation. USE THIS.
- `Outputs/runs/strategy-sweep-20260329T072342Z/Outputs/ES_*/strategy_returns.csv` — per-trade
  returns for ES strategies (exists on Rob's Windows machine in the run directories)
- `Outputs/runs/strategy-sweep-20260329T101235Z/Outputs/CL_*/strategy_returns.csv` — per-trade
  returns for CL strategies

**What to build:**

```
modules/portfolio_selector.py
```

**Stage 1 — Hard filter gate**
- Load `ultimate_leaderboard_bootcamp.csv` (merged across all markets when NQ etc. land)
- Filter: ROBUST or STABLE quality only, OOS PF > 1.4, total_trades >= 60
- Deduplicate: same `best_refined_strategy_name` in same market → keep highest BCS only
- Output: filtered candidate list (~30-50 strategies after all markets)

**Stage 2 — Per-trade return extraction + true Pearson correlation**
- For each candidate, find their `strategy_returns.csv` in the run output directories
  Path pattern: `Outputs/runs/{run_id}/Outputs/{MARKET}_{TIMEFRAME}/strategy_returns.csv`
  The run_id is in the `run_id` column of the leaderboard CSV
- Align returns by exit_time to daily buckets
- Compute pandas `.corr()` on daily P&L series → true Pearson matrix
- This replaces the structural proxy used in Session 47 analysis

**Stage 3 — Combinatorial portfolio search**
- Sweep all C(n, 4) through C(n, 8) combinations from filtered candidates
- Reject any combination where any Pearson pair > 0.4
- Score survivors: avg OOS PF + market diversity + direction mix + logic type diversity
- Output: top 50 portfolio combinations

**Stage 4 — Bootcamp Monte Carlo (use existing prop_firm_simulator)**
- For each top-50 combination, run 10,000 simulations through the 3-step cascade
- Use `monte_carlo_pass_rate()` from `prop_firm_simulator.py` — it already exists
- Simulate portfolio by combining per-trade returns across all strategies in combination
- Apply The5ers rules: Step 1 ($100k, -$5k), Step 2 ($150k, -$7.5k), Step 3 ($200k, -$10k)
- Also run funded stage: -$10k max loss + -$7,500 daily pause
- Output: Step 1 pass rate, Step 2 conditional pass rate, Step 3 conditional pass rate

**Stage 5 — Position sizing optimiser**
- For top 10 portfolio combinations, grid search contract weights [0.5, 1.0, 1.5, 2.0] per strategy
- Maximise 3-step pass rate while keeping portfolio DD under each step limit
- Output: optimal weights per strategy

**Output files:**
- `portfolio_selector_report.csv` — top 10 portfolios with pass rates, weights, verdict
- `portfolio_selector_matrix.csv` — true Pearson matrix for the filtered candidates
- Both written to `Outputs/` directory

**Config flag:** add `skip_portfolio_selector: false` to YAML (so it can be disabled)

**Tests:** `tests/test_portfolio_selector.py` — smoke test with 5 mock strategies

---

## DATA STRUCTURE NOTES (important for implementation)

### What the leaderboard CSV contains

The `ultimate_leaderboard_bootcamp.csv` has 74 rows (ES + CL). Key columns:
- `run_id` — e.g., `strategy-sweep-20260329T072342Z` (tells you which run folder)
- `market` — ES or CL
- `timeframe` — daily, 60m, 30m, 15m
- `dataset` — e.g., `ES_30m_2008_2026_tradestation.csv`
- `leader_strategy_name` — the refined strategy name
- `leader_max_drawdown` — negative dollar figure (e.g., -25615.0)
- `leader_pf`, `is_pf`, `oos_pf` — profit factors
- `quality_flag` — ROBUST, STABLE, ROBUST_BORDERLINE, etc.
- `bootcamp_score` (BCS) — composite score

### Where strategy_returns.csv files live

Each run creates per-dataset subfolders. For example:
```
Outputs/runs/strategy-sweep-20260329T072342Z/Outputs/
  ES_30m/
    mean_reversion_mom_exhaustion_promoted_candidates.csv
    strategy_returns.csv   ← THIS IS WHAT YOU NEED
    ...
  ES_daily/
    strategy_returns.csv
  ...
```

The `strategy_returns.csv` has columns:
- `exit_time` — datetime
- One column per strategy, named by strategy name, values = trade P&L in dollars

**Critical data gap:** The `cross_timeframe_correlation_matrix.csv` files in the run outputs
are NOT what you want. They show family representatives (not the refined accepted strategies)
and all show negative PnL. Ignore those files entirely. Only use `strategy_returns.csv`
inside each dataset subfolder.

**Win rate bug:** `leader_win_rate` is 0.0 for ALL strategies — this column is not exporting
correctly from the engine. Do not use it for any calculations.

---

## KEY LEARNINGS FROM SESSION 47 ANALYSIS

### What other LLMs said (context for you)

**ChatGPT:** Said old cross-TF portfolio outputs shouldn't be trusted due to "timeframe fix bug".
Actually wrong — the cross_timeframe files are wrong because they show FAMILY REPS not accepted
strategies. The leaderboard IS the correct source. ChatGPT also proposed a 5-strategy ES-heavy
basket (4 of 5 are ES MR). That's concentration risk, not diversification.

**Gemini:** Good principles (calmar ratio as primary metric, correlation < 0.3, filter on DD).
But only had headers + last row of the CSV, couldn't actually analyse anything. Mentioned
MES/MNQ/MGC/MBT (micros) — wrong, Rob's challenge uses ES/CL full-size contracts.

### Provisional portfolio (ES + CL only, NQ not yet available)

From the Session 47 structural correlation analysis, the best 7-strategy portfolio is:
Ranks [2, 4, 6, 7, 8, 13, 18] from the bootcamp leaderboard:

| Strategy | Market | TF | PF | OOS | Max DD | Role |
|----------|--------|----|----|-----|--------|------|
| MR mom_exhaustion | ES | 30m | 2.35 | 2.77 | $25.6k | Primary |
| Trend | ES | 30m | 1.93 | 2.15 | $16.9k | Diversity |
| MR signal_exit | CL | 30m | 1.73 | 3.98 | $6.0k | Low DD anchor |
| MR trend_pullback | CL | daily | 1.51 | 1.82 | $25.7k | Trade volume |
| Short trend | CL | daily | 1.82 | 1.41 | $23.3k | Short hedge |
| MR trend_pullback | CL | 15m | 1.47 | 1.85 | $6.3k | Low DD anchor |
| Short breakout | CL | 30m | 1.63 | 1.55 | $5.6k | Short hedge |

Average structural correlation: -0.045 (effectively zero)
Portfolio DD estimate (mid): ~$9,700 (max_dd / √7)
This is provisionally SAFE for Step 3 and Funded but RISKY for Step 1 ($5k limit)

**Step 1 mitigation:** Start with only the 3 lowest-DD strategies first:
CL 30m MR ($6k DD), CL 30m Short_BO ($5.6k DD), CL 15m MR ($6.3k DD).
Build balance above target as buffer, then add higher-earning strategies.

**NQ will change this picture significantly** — pre-fix NQ had 14 ROBUST strategies at PF 8.04.
Once NQ results land, the portfolio selection needs to be redone with the full leaderboard.

---

## INFRASTRUCTURE & OPERATIONS

### Console VM commands
```bash
# SSH (always use sudo -u robpitman1982 for runs)
gcloud compute ssh strategy-console --zone us-central1-c
sudo -u robpitman1982 bash -c 'cd /home/robpitman1982/python-master-strategy-creator && ...'

# Check run status
tail -50 /home/robpitman1982/python-master-strategy-creator/full_rerun.log
gcloud compute instances list --filter="name=strategy-sweep"
gcloud storage ls gs://strategy-artifacts-robpitman/runs/

# Download results (from Windows)
cd "C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator"
python cloud/download_run.py --latest
```

### Claude Code (unattended execution)
```bash
claude --dangerously-skip-permissions -p "Read SESSION_47_TASKS.md and execute all steps..."
```

### Key paths on Windows
```
C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator\
  Outputs\runs\strategy-sweep-20260329T072342Z\   ← ES run
  Outputs\runs\strategy-sweep-20260329T101235Z\   ← CL run
  Data\  ← all TradeStation CSVs (ES, CL, NQ, GC, SI, HG, RTY, YM all present)
```

---

## SESSION 47 TASKS FILE

Create `SESSION_47_TASKS.md` with the following content and execute it:

```
# SESSION 47 TASKS — Build portfolio_selector.py

## Goal
Build modules/portfolio_selector.py — the automated portfolio selection system
that takes the full multi-market leaderboard and outputs the optimal Bootcamp portfolio.

## Steps

### Step 1 — Create modules/portfolio_selector.py
Implement the 5-stage pipeline described in SESSION_HANDOVER_47.md.
Key imports to use: prop_firm_simulator.The5ersBootcampConfig, monte_carlo_pass_rate
portfolio_evaluator for return loading patterns.

### Step 2 — Create tests/test_portfolio_selector.py
Smoke test with 5 mock strategies covering:
- Stage 1 filter gate (removes REGIME_DEPENDENT, thin trade count)
- Stage 3 correlation rejection (rejects pair with Pearson > 0.4)
- Stage 4 MC produces pass_rate between 0 and 1
- Output CSV is created and has expected columns

### Step 3 — Wire into master_strategy_engine.py
After the cross_dataset_evaluator call at the end of the pipeline,
add an optional call to portfolio_selector if skip_portfolio_selector != true.
Mirror the pattern used for skip_portfolio_evaluation.

### Step 4 — Update CLAUDE.md issues list
Mark portfolio_selector as complete in the prop firm system section.
Add: "- [x] Portfolio selector module — MC Bootcamp pass rate, correlation gate, sizing optimiser"

### Step 5 — Update CHANGELOG_DEV.md
Add Session 47 entry at the TOP.

### Step 6 — Run tests
python -m pytest tests/ -v
All tests must pass.

### Step 7 — Commit and push
git add -A
git commit -m "feat: portfolio_selector — Bootcamp MC pass rate, correlation gate, position sizing"
git push origin main
```

---

## EXISTING MODULE REFERENCE (what portfolio_selector.py should use)

### prop_firm_simulator.py key APIs

```python
from modules.prop_firm_simulator import (
    The5ersBootcampConfig,
    simulate_challenge,
    monte_carlo_pass_rate,
)

# Config (CORRECT — matches The5ers screenshot)
config = The5ersBootcampConfig()
# step_balances = [100_000, 150_000, 200_000]
# profit_target_pct = 0.06
# max_drawdown_pct = 0.05
# max_daily_drawdown_pct = None  (no daily DD during eval steps)
# max_calendar_days = None  (UNLIMITED TIME)
# funded_max_drawdown_pct = 0.04
# funded_daily_pause_pct = 0.03  (THIS IS THE FUNDED STAGE TRAP)

# Single simulation
result = simulate_challenge(trade_pnl_list, config=config)
# result.passed = True/False
# result.steps_completed = 0, 1, 2, or 3
# result.final_balance
# result.max_drawdown_hit

# Monte Carlo
stats = monte_carlo_pass_rate(trade_pnl_list, config=config, n_sims=10000)
# stats['pass_rate'] = 0.0 to 1.0
# stats['step1_pass_rate'], stats['step2_pass_rate'], stats['step3_pass_rate']
# stats['median_steps_completed']
```

### portfolio_evaluator.py — return loading pattern

```python
# The evaluator already knows how to load strategy_returns.csv files.
# Mirror its pattern for Stage 2 of portfolio_selector.
# Key: strategy_returns.csv has exit_time + one column per strategy name
# Column names are the strategy names (e.g. "RefinedMR_HB20_ATR1.0_DIST0.0_MOM0")
```

### Finding strategy_returns.csv for a leaderboard row

```python
import os

def find_returns_file(leaderboard_row: dict, runs_base: str) -> str | None:
    """
    Given a leaderboard row, find the strategy_returns.csv for its dataset.
    runs_base = "Outputs/runs" (or the equivalent GCS download path)
    """
    run_id = leaderboard_row['run_id']  # e.g. "strategy-sweep-20260329T072342Z"
    dataset = leaderboard_row['dataset']  # e.g. "ES_30m_2008_2026_tradestation.csv"
    
    # Derive dataset folder name: "ES_30m_2008_2026_tradestation.csv" -> "ES_30m"
    parts = dataset.replace('_tradestation.csv', '').split('_')
    # parts = ['ES', '30m', '2008', '2026']  -> folder = "ES_30m"
    dataset_folder = f"{parts[0]}_{parts[1]}"
    
    path = os.path.join(runs_base, run_id, "Outputs", dataset_folder, "strategy_returns.csv")
    return path if os.path.exists(path) else None
```

---

## IMPORTANT CONTEXT: WHAT DATA IS AVAILABLE RIGHT NOW

### Data files on Rob's Windows machine
```
C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator\Data\
  ES_daily_2008_2026_tradestation.csv   ✅
  ES_60m_2008_2026_tradestation.csv     ✅
  ES_30m_2008_2026_tradestation.csv     ✅
  ES_15m_2008_2026_tradestation.csv     ✅
  CL_daily_2008_2026_tradestation.csv   ✅
  CL_60m_2008_2026_tradestation.csv     ✅
  CL_30m_2008_2026_tradestation.csv     ✅
  CL_15m_2008_2026_tradestation.csv     ✅
  NQ_daily_2008_2026_tradestation.csv   ✅ (ready for when NQ run lands)
  NQ_60m_2008_2026_tradestation.csv     ✅
  NQ_30m_2008_2026_tradestation.csv     ✅
  NQ_15m_2008_2026_tradestation.csv     ✅
  GC, SI, HG, RTY, YM all present       ✅
```

### Runs currently downloaded
```
Outputs/runs/strategy-sweep-20260329T072342Z/  ← ES run (complete)
Outputs/runs/strategy-sweep-20260329T101235Z/  ← CL run (complete)
```
NQ, SI, HG, RTY, YM runs — check GCS bucket, may be complete

---

## AFTER THE MODULE IS BUILT — NEXT PRIORITIES

Once `portfolio_selector.py` exists and tests pass:

1. **Wait for all market runs to complete and download**
   - NQ is critical — historically 14 ROBUST strategies, highest PF in all markets
   - Once all 7 markets are in, rebuild the ultimate leaderboard and run selector

2. **Run portfolio selector on full leaderboard**
   ```python
   # from project root
   python -c "from modules.portfolio_selector import run_portfolio_selection; run_portfolio_selection()"
   ```

3. **Upload results for final portfolio decision**
   - Upload `Outputs/portfolio_selector_report.csv` and `portfolio_selector_matrix.csv`
   - Final portfolio decision requires human review of the MC pass rates

4. **Dashboard integration** (future session)
   - Add "Portfolio Selector" tab to dashboard.py
   - Show top 10 portfolios with pass rates, correlation heatmap, sizing weights

5. **Consider BTC futures** (deferred — verify contract specs first)

---

## KEY PRINCIPLES TO PRESERVE

- **Unlimited time = drawdown is the only constraint.** With PF > 1.0 and unlimited time,
  you will always reach 6% eventually. Never hit -5% is the only rule that matters.

- **Step 1 is the danger point.** $5k max loss on $100k. Start with lowest-DD strategies only.
  Build buffer, then add higher-earning strategies once above the target.

- **Funded stage daily pause is new.** -3% of $250k = -$7,500/day. CL daily strategies can
  move $7k+ in a single high-volatility day (CPI, OPEC). Pause CL daily positions on
  known volatility events when funded.

- **NQ will change the portfolio.** Pre-fix NQ had PF 8.04 ROBUST with 411 trades.
  ES MR strategies may be replaced by superior NQ alternatives once that data lands.

- **Cross-timeframe correlation files are WRONG.** The engine's `cross_timeframe_correlation_matrix.csv`
  shows losing family representatives, not accepted strategies. Only use `strategy_returns.csv`
  inside each dataset subfolder for true correlation calculation.

- **Win rate column is bugged.** All 0.0 across the board. Don't use it.

---

## FILE REFERENCE

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Auto-read by Claude Code — project context and issues list |
| `CHANGELOG_DEV.md` | Session-by-session history |
| `SESSION_HANDOVER_47.md` | This file |
| `SESSION_47_TASKS.md` | Task file for Claude Code execution |
| `modules/prop_firm_simulator.py` | Existing Bootcamp MC simulator (use this) |
| `modules/portfolio_evaluator.py` | Existing portfolio metrics + return loading |
| `modules/ultimate_leaderboard.py` | Ultimate leaderboard aggregation |
| `run_full_rerun.sh` | 7-market overnight runner (may still be running) |
| `Outputs/runs/strategy-sweep-20260329T072342Z/` | ES run outputs |
| `Outputs/runs/strategy-sweep-20260329T101235Z/` | CL run outputs |
| `Outputs/ultimate_leaderboard_bootcamp.csv` | Current ES+CL leaderboard |
