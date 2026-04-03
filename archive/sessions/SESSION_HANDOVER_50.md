# SESSION HANDOVER — Session 50
## Date: 2026-03-31
## For: Claude Code (unattended execution)

---

## WHAT THIS SESSION DOES

Code-only fixes to `portfolio_selector.py` — no full re-run of the selector
until all markets (GC, RTY, YM) are in. Smoke tests only.

### 8 tasks in order:

1. **Fix step rate reporting** — report mixes step rates from different MC runs
   (initial=10k sims uniform weights vs sizing=1k sims optimised weights).
   After sizing optimisation, run ONE final MC at 10k sims with best weights
   and report all 3 step rates from that single run.

2. **Use raw per-trade returns for MC** — MC currently uses daily-resampled
   values from return_matrix (multiple same-day trades summed). Need to load
   raw per-trade PnL for accurate MC. Keep daily matrix for correlation only.

3. **Pre-sweep correlation dedup** — remove near-duplicate strategies (|r|>0.6)
   before combinatorial sweep to reduce C(n,k) explosion.

4a. **Rebalance scoring** — increase diversity weight from 20→30, decrease
   OOS PF weight from 30→20. Add minimum market count for VIABLE verdict.

4b. **Reframe sizing as micro contracts** — change weight grid from
   [0.5, 1.0, 1.5] to [0.1, 0.2, 0.3, 0.4, 0.5] = 1-5 micro contracts.
   Rob trades micros (MES, MNQ, MCL etc.) on The5ers. Backtest uses full
   contracts from TradeStation. Rename contract_weights → micro_multiplier.

5. **Add estimated time-to-fund** — track trades-to-pass per step in MC,
   convert to estimated months using strategy trade frequency.

6. **Update tests** — step monotonicity, time-to-fund fields, dedup.

7. **Update docs** — CLAUDE.md and CHANGELOG_DEV.md.

### Key files to modify:
- `modules/portfolio_selector.py` — main target (all code tasks)
- `modules/prop_firm_simulator.py` — micro contract config if needed
- `tests/test_portfolio_selector.py` — new tests
- `CLAUDE.md` — project state update
- `CHANGELOG_DEV.md` — session log

### Key files to READ (do not modify):
- `modules/prop_firm_simulator.py` — `simulate_challenge()`, `_scale_trade_pnl()`
- `generate_returns.py` — how raw returns are built
- `Outputs/portfolio_selector_report.csv` — current (buggy) output to compare against

---

## ROOT CAUSE DETAILS

### Step 3 > Step 2 bug
In `_write_report()` line ~695:
```python
step3 = p.get("opt_step3_pass_rate", p.get("step3_pass_rate", 0.0))
```
But step1 and step2 come from the initial MC, not the sizing optimiser.
The sizing optimiser runs 1,000 sims with grid-searched weights — a completely
different experiment from the initial 10,000-sim MC with uniform weights.

### Daily resampling distortion
`generate_returns.py` writes daily-resampled PnL (line 106):
```python
daily_pnl = trades_df.resample("D", on="exit_time")["net_pnl"].sum()
```
Then `run_bootcamp_mc()` extracts "trades" as non-zero daily values (line 497):
```python
trades = [float(v) for v in vals if v != 0.0]
```
So a day with 3 trades (+$500, -$200, +$100) becomes one "$400 trade".
For intraday strategies (15m, 30m) this is especially distorting — they may
have 5-10 trades per day that get collapsed into one value.

### Near-duplicate strategies
From the correlation matrix:
- ES_daily_MR_HB5_ATR0.4_DIST0.4 vs ES_daily_MR_HB5_ATR0.5_DIST0.4: r=0.949
- ES_30m_MR_HB20_ATR1.0_DIST0.0 vs ES_30m_MR_HB20_ATR1.0_DIST0.4: r=0.792
- SI Breakout PriorRange vs RangeBreakout variants: r=0.842
These are essentially the same strategy with slightly different parameters.

---

## WHAT GOOD LOOKS LIKE

After these fixes:
- Step rates should be monotonically decreasing: Step1 >= Step2 >= Step3
- Trade counts in MC should match actual strategy trade counts (not daily buckets)
- Fewer candidates after correlation dedup (maybe 20-22 from 30)
- More market diversity in top portfolios (3+ markets for VIABLE)
- Report includes `est_months_median` and `est_months_p75` columns
- All existing tests still pass + new tests for monotonicity and time-to-fund

---

## CLAUDE CODE LAUNCH COMMAND

```
claude --dangerously-skip-permissions -p "Read SESSION_50_TASKS.md and execute
tasks in order. For each task, make the code changes, then run the smoke tests
to verify nothing broke. Commit after each task. Do NOT re-run the full
portfolio selector — these are code-only changes. Run: python -m pytest tests/
-x -v after all changes."
```
