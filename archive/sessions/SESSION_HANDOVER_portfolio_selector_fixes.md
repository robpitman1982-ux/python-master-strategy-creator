# Portfolio Selector Fixes — Session Handover
**Date:** 6 April 2026, ~4:20 AM AEST
**Repo:** robpitman1982-ux/python-master-strategy-creator
**Local:** C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator\

---

## CURRENT STATE — RUN IN PROGRESS

A new portfolio selector run is currently executing in PowerShell.
**PID: 12720** — running as of 4:19 AM, no results written yet.

This is the first run with all fixes applied (see below).
Expected runtime: 2-3 hours per program × 4 programs = 8-12 hours total.

To check status:
```powershell
Get-Process -Id 12720 -ErrorAction SilentlyContinue | Select-Object Id, CPU
Get-ChildItem 'C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator\Outputs' -Filter 'portfolio_selector_report.csv' -Recurse | Select-Object FullName, LastWriteTime
```

---

## WHAT WAS FIXED THIS SESSION

### Fix 1 — Pre-screen MC replaces blind top-50 truncation (CRITICAL)
**Problem:** After the sweep produced 3.2M combinations, a proxy score selected
the top 50 to send to MC. This meant 99.998% of viable combinations never got
evaluated by any MC at all.

**Fix:** `sweep_combinations()` now returns ALL combinations that pass the
correlation gate. A new Stage 4c runs a fast 200-sim MC on all of them, sorts
by actual pass rate, and sends the top 200 to the full 10,000-sim MC.

**Files changed:** `modules/portfolio_selector.py`
- `sweep_combinations()`: removed `all_results[:candidate_cap]` truncation
- `run_portfolio_selection()`: added Stage 4c fast pre-screen block
- `sweep_combinations()` call: `candidate_cap=999_999_999` (no truncation)

**Config:** `fast_mc_sims: 200`, `sweep_top_n: 200`

---

### Fix 2 — Regime gate disabled (HIGH)
**Problem:** The regime gate used in-sample data (2022/2023/2024-2025 windows)
to filter combinations before MC. It was silently killing good combinations based
on endogenous regime detection with no logging of how many it rejected.
Also used raw dollar PnL (not scaled) so contract-size differences distorted the PF calc.

**Fix:** `use_regime_gate: false` in config. The function remains in code for
future re-evaluation but is not called.

---

### Fix 3 — Sizing optimizer objective fixed (HIGH)
**Problem:** The sizing optimizer used hard DD constraints (p95 must be < 90%
of challenge max DD). These constraints were ALWAYS binding — the log showed
"No weight combo passed DD constraints. Using lowest-DD fallback" for EVERY
portfolio. Result: all portfolios ended up with minimum weights (0.1 micro each),
making the entire sizing stage useless.

**Fix:** Removed all hard DD constraints from `optimise_sizing()`. New objective:
**maximise pass_rate directly**. Ties broken by lowest DD. No fallback needed.

**Code changed in `optimise_sizing()`:**
- Removed `best_trades`, `fallback_weights`, `fallback_dd` variables
- Removed `p95_ceiling`, `p99_ceiling` calculations
- Removed the `if p95_dd > p95_ceiling: continue` hard blocks
- New logic: if `pass_rate > best_pass_rate` → update best (or tie-break by DD)

---

### Fix 4 — Correlation thresholds loosened to allow k=4,5 portfolios
**Problem:** Mean pairwise `active_corr_threshold: 0.60` was rejecting diversified
k=4/k=5 portfolios because adding more strategies statistically raises the chance
of one pair exceeding the mean. k=3 always won by default, not by merit.

**Fix:** Thresholds raised so only near-duplicate pairs are rejected — the fast
pre-screen MC now correctly evaluates whether a k=5 portfolio genuinely
diversifies better than a k=3.

**Config:** `active_corr_threshold: 0.85`, `dd_corr_threshold: 0.95`

---

### Fix 5 — Excluded markets updated for The5ers
**Config:** `excluded_markets: ["BTC", "RTY", "HG"]`
- **BTC**: risk-sizing invalid (1000x price appreciation since 2009 inflates
  ATR-based position sizes, producing fake $34M-$73M net PnL per strategy)
- **RTY**: Russell 2000 — not available on The5ers CFD platform (no US2000 symbol)
- **HG**: Copper — not available on The5ers CFD platform (no copper symbol)

RTY and HG are valid for other platforms (Darwinex, FTMO) — only exclude
for The5ers-specific runs.

---

## WHY ONLY 2 PORTFOLIOS APPEARED IN PREVIOUS RUNS

The old run (BTC excluded but fixes not yet applied) produced only 2 portfolios
across all 4 programs — the same 2 combinations in different rank order.

Root causes:
1. Pre-MC truncation to top 50 by proxy score — most viable combinations never reached MC
2. Regime gate silently killing most of those 50 before MC
3. Sizing always falling back to minimum weights — every portfolio looked identical
4. Correlation thresholds structurally preventing k>3 portfolios

The identical results across programs (Hyper Growth = Pro Growth exactly) is
actually CORRECT — both are 1-step, 10% target, 6% DD. Same rules = same results.
The percentage-based scaling makes the simulation dimensionless — capital size
does not change which portfolio is optimal, only the challenge structure does.

---

## WHAT TO EXPECT FROM CURRENT RUN

- 10-30 portfolios per program instead of 2
- Genuine k=4 and k=5 portfolios alongside k=3
- Realistic pass rates (75-95% range for Bootcamp, higher for simpler programs)
- Sizing will actually find meaningful weights (not all 0.1 micros)
- Composite score ranking: pass_rate × (12/est_months)^0.5 — faster funding ranks higher

---

## NEXT SESSION PRIORITIES (after reviewing results)

### 1. BTC 4-year window implementation
Instead of permanently excluding BTC, implement per-market data cutoff:
```yaml
market_data_cutoff:
  BTC: "2022-01-01"  # 4 years = full halving cycle
```
BTC from 2022 onwards behaves as a risk asset correlated to NQ — useful
diversification info without the 1000x fake-sizing issue.
Implementation: clip `build_return_matrix()` per-market before daily resampling.

### 2. Fix source_capital scaling for smaller programs
`source_capital` is hardcoded at $250K throughout the MC simulator.
For $5K Hyper Growth / Pro Growth programs, strategies are sized for $250K
but evaluated against $5K challenge rules. The percentage-based scaling
`trade_pnl / source_capital × step_balance` handles this correctly in the
simulator, but position sizing in the engine itself assumes $250K.
Assess whether this actually affects results or is handled by the scaling.

### 3. Gemini/ChatGPT review of portfolio_selector_review.md
Full code review document is at:
`C:\Users\Rob\Documents\portfolio_selector_review.md`
Contains 16 numbered issues, severity rankings, and 5 questions for reviewers.
Key questions: is block bootstrap appropriate for path-dependent sequential
challenge? Should sizing be co-optimised with selection rather than sequential?

### 4. Push all changes to GitHub
Nothing was committed this session. All changes are local only.

---

## KEY FILES CHANGED THIS SESSION

| File | Changes |
|------|---------|
| `modules/portfolio_selector.py` | Fix 1 (pre-screen MC), Fix 2 (regime gate default off), Fix 3 (sizing objective) |
| `config.yaml` | Fix 1 (fast_mc_sims, sweep_top_n), Fix 2 (use_regime_gate: false), Fix 4 (corr thresholds), Fix 5 (excluded_markets) |

---

## CURRENT CONFIG STATE (portfolio_selector section)

```yaml
portfolio_selector:
  candidate_cap: 60
  max_candidates_per_market: 8
  excluded_markets: ["BTC", "RTY", "HG"]
  n_min: 3
  n_max: 5
  n_sims_mc: 10000
  n_sims_sizing: 1000
  fast_mc_sims: 200
  sweep_top_n: 200
  quality_flags: ["ROBUST", "ROBUST_BORDERLINE", "STABLE"]
  active_corr_threshold: 0.85   # loosened — only reject near-duplicates
  dd_corr_threshold: 0.95       # effectively disabled — MC handles this
  tail_coloss_threshold: 1.01   # disabled
  use_ecd: false                # disabled
  use_multi_layer_correlation: true
  use_regime_gate: false        # DISABLED
  dd_p95_limit_pct: 0.90        # no longer used as hard constraint
  dd_p99_limit_pct: 0.95        # no longer used as hard constraint
  max_strategies_per_market: 3
  max_equity_index_strategies: 5
  speed_target_months: 12.0
  speed_weight: 0.5
```

---

## PROP FIRM CONTEXT

**Primary target:** The5ers (active account 26213568, FivePercentOnline-Real MT5)
- Tradeable: SP500 (ES), NAS100 (NQ), US30 (YM), XAUUSD (GC), XAGUSD (SI), XTIUSD (CL)
- NOT available: RTY (no US2000), HG (no copper)

**Programs in selector:**
- Bootcamp $250K: 3-step, 6% profit each step, 6% max DD, most restrictive
- High Stakes $100K: 2-step, 8%/5% profit, 6% max DD
- Hyper Growth $5K: 1-step, 10% profit, 6% max DD
- Pro Growth $5K: 1-step, 10% profit, 6% max DD (identical to Hyper Growth)

**Live deployment:**
- Portfolio #1 EA live on Contabo VPS 89.117.72.49, The5ers account 26213568
- First live trade: Strategy 2 (YM Daily Short Trend), ticket 532066267

---

## KNOWN REMAINING ISSUES (not fixed this session)

1. **n_max: 5** — k=6 causes OOM crash locally (22.9M combos exceed RAM).
   Would need chunked sweep or cloud execution for k=6.

2. **Dashboard Live Monitor** — engine log and promoted candidates sections
   show stale/empty state during active runs. Deferred.

3. **Strategy_returns vs strategy_trades fallback** — if `strategy_trades.csv`
   is missing, MC uses daily-aggregated PnL as trade-level data, underestimating
   variance. Check coverage across all 53 candidates.
