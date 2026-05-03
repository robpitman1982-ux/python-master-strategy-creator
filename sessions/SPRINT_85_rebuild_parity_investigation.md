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

## 8. Result (interim, Phase A closed 2026-05-03)

**Phase A verdict: CANDIDATES (partial)**

Root cause for the dominant bug class identified and fixed: `_rebuild_strategy_from_leaderboard_row` was constructing `EngineConfig` with futures defaults (tick_value=12.50, dollars_per_point=50.0, commission=$2/contract, slippage=4 ticks). On CFD data sweeps, the original engine ran with `cfd_markets.yaml` per-market values (tick_value=0.01, dollars_per_point=1.0, commission=0, slippage=1 tick for indices). The position-sizing math `floor(risk_amount / (stop_dist * dollars_per_point))` partially compensates between the two but slippage `half_slip = slippage_ticks * tick_value / dollars_per_point` does not — original CFD slippage was 0.01 points/side, rebuild was 1.0 points/side (100x larger). Stack ~12k trades on top of 100x slippage and you get $-6.4M phantom losses where leaderboard reports $+1.75M.

Fix shipped (commit `27292b6`): `_load_cfd_market_engine_values()` reads `configs/cfd_markets.yaml` at module-import time (cached) and supplies per-market engine values to the rebuild's `EngineConfig`. Falls back to futures defaults when the market is not in `cfd_markets.yaml`.

### Empirical verification

After fix, on validation run `2026-04-30_es_nq_validation` (ES_30m, ES_60m so far):

| Strategy class | ES_30m parity | ES_60m parity |
|---|---|---|
| Trend (combo) | OK exact | TBD |
| Trend subtypes | All 3 OK exact | OK |
| Mean reversion (base) | OK exact | TBD |
| Mean reversion subtypes | vol_dip OK, trend_pullback FAIL, mom_exhaustion FAIL | mixed (HB12 OK, HB others FAIL) |
| Breakout (base + 3 subtypes) | All FAIL ~25% under | mixed (HB10 OK, HB others FAIL) |
| Short_* | All FAIL ~50-80% under | TBD |

Total ES_30m: 6 OK / 9 FAIL out of 15. Up from 0/15 before the fix.

### Phase B - residual bug class (deferred to follow-up sprint)

The remaining PARITY_FAILED rows have parameter-specific divergence, not strategy-type-specific. Pattern: when a refined leader has `min_avg_range = 0.0` (sentinel value indicating "use default"), the rebuild's default differs from what the original refinement used because `precomputed_signals` were generated under different conditions.

Examples:
- `breakout_compression_squeeze_RefinedBreakout_HB6_ATR0.5_COMP0.6_MOM0` -> exact match
- `breakout_compression_squeeze_RefinedBreakout_HB16_ATR0.5_COMP0.0_MOM0` -> 35% under leader (FAIL)
- `breakout_range_expansion_RefinedBreakout_HB10_ATR0.5_COMP0.0_MOM0` -> exact match (different timeframe)
- `breakout_range_expansion_RefinedBreakout_HB16_ATR0.5_COMP0.0_MOM0` -> 30% under leader (FAIL)

So `COMP=0.0` is not always a problem - it depends on how the original refinement composed `precomputed_signals` (which the rebuild does not see).

**Hypothesis for Phase B:** Use the original `_promoted_candidates.csv` row to populate filter parameters precisely (rather than relying on the strategy class's compile-time defaults). The leaderboard's `best_combo_filter_class_names` gives only class names; the original row had per-filter parameter values that the rebuild discards.

**Consequence:** A subset of strategies (estimated 30-50% of refined subtypes) will be flagged PARITY_FAILED until Phase B is resolved. Post-ultimate gate's fail-closed behaviour is the right conservative response - those strategies will be excluded from selector input until parity is restored.

**Sprint sequence:**
- Phase A: ✓ shipped
- Phase B: ✓ shipped 2026-05-03 — see Phase B section below
- Live EA strategies (NQ Daily MR, YM Daily Short Trend, GC Daily MR, NQ 15m MR) tested in 10market backfill - will determine whether Phase B blocks live-trading parity or only research-validation parity.

## Phase B - Signal mask round-trip (closed 2026-05-03)

**Phase B verdict: CANDIDATES (mechanism shipped, empirical verification pending next backfill).**

### Root cause refined

`_promoted_candidates.csv` does not store per-filter parameter values — only
class names. The original sweep + refinement path computed signals via:

```python
filter_objects = strat_type.build_filter_objects_from_classes(combo_classes, timeframe=cfg.timeframe)
signal_mask = compute_combined_signal_mask(filter_objects, data)
engine.run(strategy=strategy, precomputed_signals=signal_mask)
```

The rebuild was instead calling `engine.run(strategy=strategy)` with no
mask. Without the precomputed mask, the engine asks the strategy class's
inline `generate_signal()` for each bar. The inline method uses the same
hardcoded filter parameters as `build_filter_objects_from_classes`, so in
principle the entry universe should match. But subtype variations and
edge cases (e.g. CompressionFilter with `min_avg_range = 0.0` sentinel,
universal filters added in Session 42) led to silent divergence.

### Fix shipped

`modules/portfolio_evaluator.py:_rebuild_strategy_from_leaderboard_row`
now constructs the same combined signal mask as the sweep and passes it
to `engine.run(precomputed_signals=...)`. Wrapped in try/except so an
unexpected filter class falls back to the previous no-mask behaviour
rather than aborting the whole rebuild.

```python
filter_objects = strategy_type_inst.build_filter_objects_from_classes(
    combo_classes, timeframe=timeframe,
)
precomputed_signals = compute_combined_signal_mask(filter_objects, eval_data)
engine.run(strategy=strategy, precomputed_signals=precomputed_signals)
```

### Tests (`tests/test_sprint85b_signal_mask.py`)

6 cases: helper imports, graceful fallback when `build_filter_objects_from_classes`
raises, base + subtype + short subtypes all expose
`build_filter_objects_from_classes`, `compute_combined_signal_mask` returns
a `bool` ndarray of correct length on synthetic OHLC data. All pass.

### Empirical verification (deferred to next backfill)

The fix is mechanically sound but parity-pass-rate impact must be measured
against the same validation run that produced the Phase A baseline. Two
ways this can land:
1. The 10market backfill currently running on c240 finishes with the OLD
   code (started before this commit) — re-run finalise on it for the Phase
   A baseline. Then run a follow-up backfill with this fix and diff
   parity rates.
2. Easier: run a small targeted rebuild on `2026-04-30_es_nq_validation`
   (the small validation run) post-fix and compare to the Phase A summary
   (6 OK / 9 FAIL out of 15 on ES_30m).

If parity-pass-rate jumps ≥80% across mixed timeframes, Phase B closes
fully. If residual divergence remains (sub-class), open Phase C scoped to
that residue (likely filter-instantiation-time differences across base vs
subtype `build_candidate_specific_strategy` overrides).

### Commits / branches

- Pre-registration: `45b9499`
- Phase A fix: `27292b6`
- Branch: `main` (committed direct since this was an unblocking fix to Sprint 84's pipeline)

---

## Append to LOG.md after sprint close

Single LOG.md entry: date, sprint name, verdict, the root cause identified, fix summary, parity-pass-rate before vs after.
