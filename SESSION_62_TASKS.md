# SESSION 62 — Sweep Speed Optimizations + Portfolio Selector Bug Fixes

## Context
- Vectorized trade engine (Session 60) works at the per-combo level (1.06s → 0.083s) but the full sweep pipeline didn't speed up because overhead OUTSIDE the trade loop dominates
- ES daily took 176s with vectorization vs 191s without — basically no improvement
- Portfolio selector has multiple bugs producing incorrect results
- Sources: Codex analysis, Gemini analysis, Claude review of portfolio_selector.py

## IMPORTANT RULES
- One commit per task step
- Run `python -m pytest tests/ -x -q` after each change to confirm no regressions
- Do NOT change any strategy logic, filter logic, or backtest correctness
- All cloud config YAMLs are in `cloud/` directory (55 files)

---

## PART A: SWEEP SPEED OPTIMIZATIONS

### Task 1: Add BLAS/OpenMP thread caps at process startup
**Why:** Without these, each of the 90+ Python worker processes spawns its own BLAS threads for numpy operations. On a 96-core VM with 94 workers, this creates 750+ threads fighting for 96 cores — catastrophic cache thrashing and context switching.

**Files to edit:**
- `master_strategy_engine.py` — add at very top, before any imports:
```python
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
```
- `cloud/gcp_startup.sh` — add the same 4 exports before the python command

**Commit:** `perf: add BLAS/OMP thread caps to prevent worker thread explosion`

---

### Task 2: Reduce default sweep workers from 90 to 48 in all cloud configs
**Why:** 94 workers on a 96-core VM is too aggressive for Python+pandas+numpy. Memory-bandwidth bound at that point. 48 workers leaves headroom for OS, I/O, and avoids L3 cache thrashing.

**Files to edit:** All `cloud/config_*.yaml` files
- Change `max_workers_sweep: 90` → `max_workers_sweep: 48`
- Change `max_workers_refinement: 90` → `max_workers_refinement: 48`
- Do NOT change any other config values

**Commit:** `perf: reduce cloud sweep workers from 90 to 48 to avoid oversubscription`

---

### Task 3: Remove per-combo print statements from strategy type sweep methods
**Why:** All three family sweep methods print every combo result (e.g., `Combo 3095/16473 | ...`). On 45K+ combos this creates massive stdout I/O and main-process coordination overhead. Keep only 10% progress updates.

**Files to edit:**
- `modules/strategy_types/mean_reversion_strategy_type.py`
- `modules/strategy_types/trend_strategy_type.py`
- `modules/strategy_types/breakout_strategy_type.py`

**What to do:** Find the per-combo print line in each file's sweep function (looks like `print(f"  Combo {idx+1}/{len(combinations)} | ...")`). Replace with progress printing every 10% only:
```python
if (idx + 1) % max(1, len(combinations) // 10) == 0 or idx == len(combinations) - 1:
    print(f"  Progress: {idx+1}/{len(combinations)} ({100*(idx+1)/len(combinations):.0f}%)")
```

**Commit:** `perf: reduce per-combo logging to 10% progress updates only`

---

### Task 4: Add `copy_data=False` path to engine and use in sweep workers
**Why:** `MasterStrategyEngine.__init__` does `self.data = data.copy()` for every combo. The 60m precomputed dataset is ~13.9MB. With 48 workers, that's 670MB of pure copy overhead per family sweep. The engine does NOT mutate the DataFrame in the vectorized path.

**Files to edit:**
- `modules/engine.py` — In `MasterStrategyEngine.__init__`, change:
```python
# Before:
self.data = data.copy()

# After:
self.data = data if not copy_data else data.copy()
```
Add `copy_data: bool = True` parameter to `__init__`.

- `modules/strategy_types/mean_reversion_strategy_type.py` — In the sweep worker function, pass `copy_data=False` when constructing the engine
- `modules/strategy_types/trend_strategy_type.py` — Same
- `modules/strategy_types/breakout_strategy_type.py` — Same
- `modules/refiner.py` — In the refinement worker, pass `copy_data=False`

**Commit:** `perf: add copy_data=False to engine init, skip DataFrame copy in sweep workers`

---

### Task 5: Fix vectorized run_vectorized() equity_curve / max drawdown bug
**Why:** `run_vectorized()` never builds `equity_curve`, but `results()` calculates max drawdown from it. This means drawdown is wrong on vectorized runs, which distorts leaderboard rankings and portfolio selection.

**Files to edit:**
- `modules/engine.py` — In `run_vectorized()`, after computing trades, build the equity curve from cumulative PnL of executed trades (same as the scalar path does). Ensure `self.equity_curve` is populated so `results()` computes drawdown correctly.

**How to verify:** Run the existing parity tests in `tests/test_engine_parity.py`. They should now pass with matching drawdown values between scalar and vectorized paths. If there's a test that was previously skipped or marked xfail for drawdown, fix it.

**Commit:** `fix: build equity_curve in vectorized path so drawdown is correct`

---

### Task 6: Ensure skip_portfolio_evaluation=true in all cloud sweep configs
**Why:** Some cloud configs still have `skip_portfolio_evaluation: false`. Portfolio evaluation should be done locally after download, not on the expensive cloud VM.

**Files to edit:** Check all `cloud/config_*.yaml` files. Any that have `skip_portfolio_evaluation: false` or are missing the key entirely should be set to `skip_portfolio_evaluation: true`.

**Commit:** `chore: ensure all cloud configs skip portfolio evaluation`

---

## PART B: PORTFOLIO SELECTOR BUG FIXES

### Task 7: Re-sort optimised portfolios by pass rate after sizing optimization
**Why:** The screen prints "Top 3 portfolios by pass rate" but the list uses pre-sizing ordering. Portfolio #4 in the report has 85.2% pass rate but is shown below portfolio #1 at 42.3%. The real best portfolio is hidden from the user.

**File to edit:** `modules/portfolio_selector.py`

**What to do:** In `run_portfolio_selection()`, after the `optimise_sizing()` call and before `portfolio_robustness_test()`, add:
```python
optimised.sort(key=lambda p: p.get("opt_final_pass_rate", p.get("final_pass_rate", 0.0)), reverse=True)
```

Also do the same after `portfolio_robustness_test()` in case it modifies pass rates.

**Commit:** `fix: re-sort portfolios by pass rate after sizing optimization`

---

### Task 8: Loosen DD p95 constraint in sizing optimizer
**Why:** Current `dd_p95_limit_pct: 0.70` means p95 DD must stay below 70% × 5% = 3.5% for Bootcamp. This forces every portfolio to weight 0.1 (1 micro each), making trades too small to reach 6% profit targets. Portfolios that exceed this constraint fall back to minimum weights and get crushed on pass rate. The constraint was designed to be conservative but is so tight it prevents the optimizer from finding viable sizing.

**File to edit:** `config.yaml` — Change:
```yaml
dd_p95_limit_pct: 0.90    # was 0.70 — way too tight, forced all weights to minimum
dd_p99_limit_pct: 0.95    # was 0.90
```

**Commit:** `fix: loosen DD p95/p99 limits in sizing optimizer to allow viable weights`

---

### Task 9: Fix pairwise ALL-must-pass correlation gate bias against larger portfolios
**Why:** The sweep requires ALL C(k,2) pairs to pass correlation thresholds. For k=8, that's 28 pairs — even with 90% per-pair pass rate, P(all pass) = 4%. Result: 9 out of 10 portfolios have exactly 3 strategies regardless of n_max=8 setting.

**File to edit:** `modules/portfolio_selector.py` — In `_sweep_chunk()`, change the correlation gate logic.

**What to change:** Instead of rejecting a combo if ANY pair exceeds the threshold, use this logic:
- Compute the AVERAGE pairwise correlation across all pairs
- Reject if average > threshold (use active_corr_threshold for average)
- ALSO reject if any SINGLE pair exceeds a higher "hard cap" threshold of 0.85 (to prevent any two near-identical strategies)

Replace the correlation gate block (the nested for loop with `if ac > active_thresh or dc > dd_thresh or tc > tail_thresh: rejected = True`) with:
```python
# Compute average pairwise correlations
all_ac, all_dc, all_tc = [], [], []
hard_cap_breach = False
for i in range(len(combo)):
    for j in range(i + 1, len(combo)):
        ci_idx = _sw_col_idx.get(combo[i])
        cj_idx = _sw_col_idx.get(combo[j])
        if ci_idx is None or cj_idx is None:
            continue
        if use_ml:
            ac = abs(float(_sw_ml_active[ci_idx, cj_idx]))
            dc = abs(float(_sw_ml_dd[ci_idx, cj_idx]))
            tc = float(_sw_ml_tail[ci_idx, cj_idx])
            all_ac.append(ac)
            all_dc.append(dc)
            all_tc.append(tc)
            # Hard cap: no single pair above 0.85 active correlation
            if ac > 0.85:
                hard_cap_breach = True
                break
        else:
            val = float(_sw_abs_corr[ci_idx, cj_idx])
            all_ac.append(val)
            if val > 0.85:
                hard_cap_breach = True
                break
    if hard_cap_breach:
        break

if hard_cap_breach:
    continue

# Average correlation gate
avg_ac = sum(all_ac) / len(all_ac) if all_ac else 0.0
if avg_ac > active_thresh:
    continue
if use_ml and all_dc:
    avg_dc = sum(all_dc) / len(all_dc)
    if avg_dc > dd_thresh:
        continue
```

**Commit:** `fix: use average correlation gate instead of all-pairs-must-pass to allow larger portfolios`

---

### Task 10: Expand weight options in sizing optimizer
**Why:** Current grid `[0.1, 0.2, 0.3, 0.5, 0.7, 1.0]` caps at 1.0 (10 micros). With leverage 1:30 on a $100K Step 1 balance, the account can support more than 10 micros. Larger weights allow the optimizer to find sizing that actually reaches profit targets.

**File to edit:** `modules/portfolio_selector.py` — In `optimise_sizing()`, change:
```python
# Before:
weight_options = [0.1, 0.2, 0.3, 0.5, 0.7, 1.0]

# After:
weight_options = [0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0]
```

Also increase `max_weight_samples` from 250 to 500 to compensate for the larger search space.

**Commit:** `fix: expand sizing weight grid to allow larger positions`

---

## PART C: VERIFICATION

### Task 11: Run full test suite and local portfolio selector test
1. Run `python -m pytest tests/ -x -q` — all tests must pass
2. Run `python run_portfolio_all_programs.py --programs bootcamp_250k` locally
3. Verify output shows:
   - Portfolios sorted by descending pass rate (highest first)
   - At least some portfolios with 4+ strategies
   - Top portfolio pass rate should be meaningfully different from the old 42.3% (either higher due to better sizing, or different composition)
4. Print the top 5 from the portfolio_selector_report.csv to the console

**Commit:** `chore: session 62 verification complete`

---

## EXECUTION ORDER
Run tasks 1-11 in order. Each task is independent except:
- Task 5 depends on Task 4 (engine changes)
- Task 11 depends on all previous tasks

## GIT
- Branch: main
- Push after all tasks complete: `git push origin main`
