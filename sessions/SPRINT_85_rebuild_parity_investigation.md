# SPRINT_85 - Rebuild parity investigation (refined-leader bug class)

**Sprint number:** 85
**Date opened:** 2026-05-03
**Date closed:** ___
**Operator:** Rob
**Author:** Claude Code on Latitude
**Branch:** `feat/rebuild-parity-fix` (TBD)
**Depends on:** Sprint 84 (provides the parity check that surfaced this finding)

---

## 1. Sprint goal

Find and fix the root cause of `_rebuild_strategy_from_leaderboard_row()` producing trades that diverge massively from the original sweep's `leader_net_pnl`. Sprint 84's parity check showed near-100% PARITY_FAILED across the validation run (ES/NQ, 6 datasets, ~75 accepted strategies). This means the post-ultimate gate currently fails-closes nearly the entire pool, leaving the selector with no candidates.

The original sweep is the source of truth (live EAs trade on it, with sensible PnL). The rebuild is the buggy path.

## 2. Empirical evidence (from Sprint 84 validation backfill, 2026-05-03)

Sample: 6 datasets x ~12-15 accepted strategies = ~75 strategies. ALL PARITY_FAILED.

Pattern across every dataset:

| Strategy (refined leader) | Rebuilt trades | Rebuilt PnL | Leader PnL |
|---|---|---|---|
| trend_slope_recovery_RefinedTrend_HB24_ATR0.75_VOL0.0_MOM0 | 9580 | -$7.58M | +$3.46M |
| mean_reversion_trend_pullback_RefinedMR_HB16_ATR0.4_DIST0.4_MOM0 | 13738 | -$26.54M | +$5.48M |
| breakout_compression_squeeze_RefinedBreakout_HB16_ATR0.5_COMP0.0_MOM0 | 4341 | -$6.73M | +$2.85M |
| short_trend_RefinedTrend_HB10_ATR0.75_VOL0.0_MOM0 | 16480 | -$12.83M | +$1.10M |
| ... | ... | ... | ... |

Pattern signatures:
- Trade counts way too high (5000-20000 on 141k-bar 30m datasets, vs leader_trades typically 200-1500)
- All rebuilds produce massive losses; all leaderboards show profits
- Affects refined leaders AND combo leaders (`trend_ComboTrend_RecoveryTrigger_*` failed too)
- Affects every strategy family (trend, MR, breakout, short_*)

This is NOT noise. The rebuild produces ~5-10x the original trade count and inverted-sign PnL. Position-sizing or filter-application is broken in the rebuild path specifically.

## 3. Hypotheses (ranked)

### H1: stop_distance_atr unit confusion (HIGH)
The leaderboard column `leader_stop_distance_atr` stores an ATR multiplier (0.4, 0.75, etc).
`portfolio_evaluator.py:232-234` reads it into a variable called `stop_distance_points`:
```python
stop_distance_points = _safe_float(
    row.get("leader_stop_distance_points", row.get("leader_stop_distance_atr", 0.0)), 0.0
)
```
Then passes it to `build_candidate_specific_strategy(... stop_distance_points, ...)`.
The strategy class (e.g. `mean_reversion_strategy_type.py:321`) maps `stop_distance_points -> stop_distance_atr` correctly:
```python
return _InlineMeanReversionStrategy(... stop_distance_atr=stop_distance_points ...)
```
Engine (`engine.py:577-578`) then prefers `strategy.stop_distance_atr` if truthy. So the path SHOULD be ATR-based. But the rebuild trade counts suggest tight stops fire instantly.

**Test:** Add diagnostic logging in `_rebuild_strategy_from_leaderboard_row` to print final `(stop_distance_atr, stop_distance_points)` actually used by vectorized_backtest.

### H2: Filter-class round-trip loses information (HIGH)
`_parse_filter_classes_from_combo_row` may not perfectly reproduce the original filter list when refined leaders are involved. Specifically, refined leaders may have parameters ON THE FILTERS that aren't carried in the leaderboard's `best_combo_filter_class_names`. The rebuild then uses default filter parameters, which may be looser than the original.

**Test:** Compare a known-good strategy's original filter parameters (from `{family}_promoted_candidates.csv`) vs the rebuilt strategy's filter parameters. Look for parameter drift.

### H3: Refined leader exit configuration not propagated (MEDIUM)
`portfolio_evaluator.py:274-277` passes `trailing_stop_atr`, `profit_target_atr`, `signal_exit_reference` from the leaderboard row, but does NOT pass `break_even_atr` or `early_exit_bars`. If the original refined leader used break_even or early_exit, the rebuild loses those exits and trades stay open longer (or not — could go either way). But this doesn't explain 5x trade counts.

**Test:** Check whether any of the refined leaders in the validation run actually used break_even or early_exit.

### H4: Universal filters added to combo class list silently (MEDIUM)
Session 42 added 7 universal filters (InsideBar, OutsideBar, GapUp/Down, ATRPercentile, HigherHigh, LowerLow). If the original sweep included these in the filter combo but the rebuild's `_parse_filter_classes_from_combo_row` doesn't recognize them or applies them with different defaults, the rebuilt strategy has weaker filters.

**Test:** Inspect the combo-name -> filter-class lookup for every universal filter.

### H5: Per-bar signal mask mismatch (LOWER)
The vectorized engine uses `precomputed_signals` (a boolean mask). The rebuild may compute this differently than the original sweep, e.g. due to feature-precompute order or NaN handling differences. But Session 61's vectorized parity tests cover this.

**Test:** For one strategy, run BOTH the rebuild AND the original sweep code path side-by-side on identical input. Assert signal_mask equality.

### H6: ATR computation differs in rebuild (LOWER)
`add_precomputed_features` is called inside the rebuilder (`portfolio_evaluator.py:259-264`) with strategy-specific lookbacks. The rebuilt feature columns may overwrite or differ from what the original sweep computed (which used a UNION of all family lookbacks). If atr_20 differs, stops differ, position sizing differs.

**Test:** After rebuild add_precomputed_features call, compare atr_20 column with what the original sweep would have had.

## 4. Investigation plan

Phase A - Diagnostic (1-2 hours):
1. On c240, pick ONE strategy from the validation run that's PARITY_FAILED.
2. Add diagnostic logging to `_rebuild_strategy_from_leaderboard_row` that prints:
   - The exact filter classes resolved (names + constructor args)
   - The strategy's final stop_distance_atr / stop_distance_points / hold_bars
   - The strategy's exit_config (every field)
   - First 5 entry timestamps and first 5 exit timestamps
3. Run both the original sweep (resume from cached promoted_candidates) and the rebuild for that ONE strategy.
4. Diff the two trade lists and the strategy parameters.

Phase B - Fix (depends on Phase A finding):
- If H1: explicitly pass `stop_distance_atr=...` to `build_candidate_specific_strategy` (rename param) and to `MasterStrategyEngine.run(stop_distance_atr=...)`.
- If H2: pull filter parameters from `{family}_promoted_candidates.csv` rows, not just class names.
- If H3: extend `portfolio_evaluator.py:274-277` to pass `break_even_atr` and `early_exit_bars`.
- If H4: audit `_parse_filter_classes_from_combo_row` for missing universal filters.
- If H5/H6: feature/signal mask comparison.

Phase C - Verify (1-2 hours):
1. Re-run Sprint 84 backfill on validation run.
2. Expect >= 90% PARITY_OK, < 10% PARITY_FAILED.
3. Check the live EAs' strategies (NQ Daily MR, YM Daily Short Trend, GC Daily MR, NQ 15m MR) all rebuild correctly. These are the highest-stakes since they're trading real money.

## 5. Verdict definitions

| Verdict | Condition |
|---------|-----------|
| **CANDIDATES** | After fix, validation backfill achieves >= 90% PARITY_OK rate. Live EA strategies all rebuild with PARITY_OK. Promote to Sprint 86 (selector cost-overlay wiring). |
| **PARTIAL** | Fix repairs the dominant bug class (e.g. H1) but a minority of strategies still fail. Document remaining classes; treat as known limitation. |
| **NO EDGE** | n/a - this is a bug fix, no hypothesis to reject. |
| **BLOCKED** | Cannot reproduce the failure locally / cannot determine cause / fix violates parity-tested vectorized engine. |

## 6. Why this matters operationally

Until this is fixed:
- The post-ultimate gate fails-closes nearly all strategies on the gated leaderboard.
- The selector has no candidate pool to work with.
- The full pipeline (Sprint 86+: cost overlay, walk-forward, regime windows, candidate-bucket pool, etc.) is blocked because there are no strategies to run them on.

The four live EAs are NOT affected because they're not driven by the rebuild path. They were set up earlier with explicit parameters from the original sweep.

## 7. Pre-registration checklist

- [x] Sprint 84 shipped and produced empirical evidence
- [ ] Branch `feat/rebuild-parity-fix` cut from main
- [ ] Pick one strategy for diagnostic (suggestion: ES_daily mean_reversion leader since simplest)
- [ ] Add diagnostic logging committed BEFORE running diagnostic (so log output is reproducible)
- [ ] Run validation backfill in baseline and post-fix mode

## 8. Result (filled in at sprint close)

TBD

---

## Append to LOG.md after sprint close

Single LOG.md entry: date, sprint name, verdict, the root cause identified, fix summary, parity-pass-rate before vs after.
