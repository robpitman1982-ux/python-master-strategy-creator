# QUICK FIX: accepted_final bug + cloud prep

Read CLAUDE.md first for project context.

## BUG FIX: accepted_final = False when it should be True

The MR strategy RefinedMR_HB12_ATR0.5_DIST1.2_MOM0 has:
- PF: 1.71 (above min 1.00)
- OOS PF: 1.80 (above min 1.00) 
- Total trades: 61 (above min 60)
- Net PnL: $83,878 (above min 0.0)
- Quality flag: ROBUST

But accepted_final = False in the leaderboard. The portfolio evaluator then skips it
with "No strategies passed final leaderboard acceptance gate."

### Debug steps:

1. Read `master_strategy_engine.py` and find the function `_choose_family_leader()` 
   and the final acceptance gate logic. Look for where `accepted_final` is set.

2. Check if any of these are causing the rejection:
   - String matching on quality_flag that doesn't handle new BORDERLINE suffixes
     (e.g., `== "ROBUST"` failing on "ROBUST_BORDERLINE")
   - A minimum OOS trades threshold that's rejecting 19 OOS trades
   - A minimum IS trades threshold
   - The `accepted_final` logic comparing against FINAL_MIN_* constants
   - Any new fields from Session 2 (consistency_flag, quality_score) being checked

3. Fix the issue. The acceptance gate should use these thresholds from config:
   - min_net_pnl: 0.0
   - min_pf: 1.00
   - min_oos_pf: 1.00
   - min_total_trades: 60
   
   If there are additional checks beyond these 4, they need to be reviewed.
   Quality flag checks should use `.startswith()` not `==`.

4. Also check `portfolio_evaluator.py` — it reads the leaderboard CSV and filters
   on `accepted_final`. Make sure it reads the boolean correctly (could be string
   "False" vs boolean False from CSV parsing).

5. After fixing, run a quick test:
   ```
   python master_strategy_engine.py
   ```
   Config should still be set to strategy_types: "mean_reversion" for fast testing.
   The MR strategy should now show accepted_final = True and portfolio evaluation
   should run successfully.

6. Git commit: `fix: accepted_final gate rejecting valid strategies`

## CLOUD PREP: Update region to Sydney

Find all occurrences of `sgp1` in any cloud scripts or config files and replace
with `syd1`. Sydney is closest to Melbourne (user's location).

If no cloud scripts exist yet, skip this step.

Git commit: `config: use Sydney (syd1) region for cloud deployment`

## Update docs

Update CLAUDE.md — add to known issues:
- [x] accepted_final bug — valid strategies rejected at final gate (FIXED)

Update CHANGELOG_DEV.md at the TOP.

Git commit: `docs: update after accepted_final fix`
