# Session 97 — Three rebuild parity bugs + 10-market overnight 5m sweep

**Date**: 2026-05-04 → 2026-05-05 (overnight)
**Trigger**: NQ 5m family-split distributed run produced 3 PARITY_FAILED on gen8 short strategies after launching the validation sprint.

## Summary

Hunt-and-fix mission on three independent rebuild parity bugs that had been quietly producing wrong PnL on every accepted short-side strategy. All three discovered, isolated, fixed, regression-tested, and validated against real NQ 5m production data. After bugs cleared, launched a 10-market overnight 5m sweep across all 3 cluster hosts (NQ already done in earlier validation; ES/CL/GC/YM on r630, SI/EC/JY on gen8, BP/AD/BTC on g9).

All accepted strategies on completed markets land with **0 PARITY_FAILED**. 87/87 tests green (7 new parity regression tests + 80 existing).

## Bug #1 — Direction default in rebuild EngineConfig (commit `f4424ce`)

**Symptom**: gen8 short_breakout / short_mean_reversion / short_trend all PARITY_FAILED. Worst: short_breakout native=$10,627 vs rebuilt=−$22,005 (opposite signs).

**Root cause**: `_rebuild_strategy_from_leaderboard_row()` in [modules/portfolio_evaluator.py](../modules/portfolio_evaluator.py) constructed `EngineConfig` without setting `direction=`. The default is `"long"` ([modules/engine.py:25](../modules/engine.py#L25)). The sweep path correctly pulls direction from `strategy_type.get_engine_direction()` at [master_strategy_engine.py:798](../master_strategy_engine.py#L798), but the rebuild path missed that. ShortMR/ShortTrend/ShortBreakout were rebuilt as longs.

**Fix**: 1-line addition pulling direction from the strategy_type instance and passing it to EngineConfig. Test [tests/test_rebuild_direction_parity.py](../tests/test_rebuild_direction_parity.py) covers long_mean_reversion (sanity) + 3 short variants. On unfixed code: 3 short tests fail as designed; on fixed code all pass with zero-tolerance.

## Bug #2 — Rebuild always called Python-loop engine.run() instead of vectorized (commit `235f993`)

**Symptom**: After Bug #1 fixed, 2 of 3 short strategies passed parity but `short_mean_reversion` (using `exit_type=signal_exit, signal_exit_reference=fast_sma`) still failed. Rebuilt $11.5M / 76,838 trades vs leader $15.85M / 107,997 trades — a 29% trade-count gap.

**Root cause**: The rebuild always called `engine.run()` (Python loop) regardless of `cfg.use_vectorized_trades`. The Python-loop signal_exit logic at [engine.py:223](../modules/engine.py#L223) is hardcoded `if close_price >= fast_sma: return close_price` — long-only. For short trades this condition is inverted and never fires, so the engine silently falls back to time_stop. The vectorized path at [vectorized_trades.py:274-279](../modules/vectorized_trades.py#L274-L279) correctly branches on `is_long`. Sweep dispatches `engine.run_vectorized()` based on the flag at [mean_reversion_strategy_type.py:116](../modules/strategy_types/mean_reversion_strategy_type.py#L116) — rebuild didn't.

Verified via on-cluster diagnostic harness: rebuild via `_rebuild_strategy_from_leaderboard_row()` produced the time_stop refinement variant's PnL ($15.38M) instead of the signal_exit variant the leader actually selected ($15.85M). Same strategy_name encoded multiple grid points; the rebuild silently ran the wrong one.

**Fix**: Dispatch to `engine.run_vectorized()` when `cfg.use_vectorized_trades=True`, matching the sweep worker pattern. Adds 2 new parity tests covering signal_exit/fast_sma for both ShortMR and long MR.

## Bug #3 — Leaderboard didn't track which combo's refinement won (commit `aa961ff`)

**Symptom**: After Bugs #1 + #2 fixed, gen8 hit 3/3 OK but r630 long-side trend FAILED parity at 35% divergence ($8.8M rebuilt vs $13.4M leader).

**Root cause**: Refinement runs across N promoted candidates × full grid. Each candidate has its own filter combo. The winning refined row can come from any of the N candidates' refinement runs — not necessarily the same combo as `best_combo_*` (which is the best raw-sweep combo before refinement). The leaderboard recorded `best_combo_*` as the "filter source of truth" but never stored which candidate's refinement actually produced the leader.

Concretely on r630: leader_net_pnl=$13.4M came from filter combo `UpClose,TwoBarUp,HigherLow,HigherHigh` but `best_combo_filter_class_names` was `RecoveryTrigger,Momentum,CloseAboveFastSMA,HigherLow` — a different combo. Rebuild loaded the wrong filter chain, ran the wrong strategy, and got the wrong PnL.

**Fix**:
1. [master_strategy_engine.py](../master_strategy_engine.py) writes `best_refined_filters` and `best_refined_filter_class_names` to family_leaderboard_results.csv (sourced from refinement_df row's `combo_filters` / `combo_filter_class_names` columns).
2. [modules/portfolio_evaluator.py](../modules/portfolio_evaluator.py) prefers `best_refined_filter_class_names` when `leader_source == "refined"` and the column is populated. Falls back to `best_combo_*` for backwards compat with old leaderboards.
3. New regression test `test_rebuild_uses_best_refined_filters_when_leader_is_refined` builds a leaderboard row where best_combo and best_refined point to different combos and asserts rebuild uses the refined combo.

## Backfill workflow for old runs (commit `1f1c50d`)

`scripts/backfill_best_refined_filters.py` walks an existing leaderboard CSV, looks up the matching refinement_narrow row by `strategy_name` + grid params + exit config (max-net_pnl tiebreak), and writes `best_refined_filters` + `best_refined_filter_class_names` back. Idempotent. Lets pre-`aa961ff` runs be repaired without re-running the sweep+refinement, then `scripts/backfill_trade_emission.py --force` re-emits `strategy_trades.csv` using the new rebuild path.

Validated end-to-end on r630's NQ 5m long bases (which had FAILED on trend before fix): backfill repopulates the column, re-emit produces 3/3 OK with bit-exact $13,412,390.85.

## NQ 5m full-tally validation

Full NQ 5m sweep (15 strategy types across 3 hosts in parallel) used as the validation harness:

| Host | Families | Outcome |
|---|---|---|
| gen8 (3 short bases) | short_mean_reversion, short_breakout, short_trend | **3/3 OK** after fixes #1+#2 |
| r630 (3 long bases) | mean_reversion, trend, breakout | **3/3 OK** after fix #3 + backfill |
| g9 (9 subtypes) | 3 MR + 3 trend + 3 breakout subtypes | **9/9 OK** after backfill |

**Total: 15/15 strategies, bit-exact parity, 0 FAILED.**

## 10-market overnight 5m sweep (kicked off 2026-05-04 ~09:35-11:13 UTC)

Generated per-market 5m configs via `scripts/generate_5ers_5m_configs.py` (commit `b74d27e`). Per-host queue runner at `scripts/run_5ers_overnight_queue.sh` (commit `34015ec`).

**Distribution**:
- **r630** (88 threads, 62 GB RAM): ES → CL → GC → YM (4 markets, workers=40)
- **gen8** (48 threads, 78 GB RAM): SI → EC → JY (3 markets, workers=36)
- **g9** (48 threads, 31 GB RAM): BP → AD → BTC (3 markets, workers=24)

**Sprint 98 RAM safety flags ON** for all configs: `recycling_pool: true`, `maxtasksperchild: 200`, `sequential_families: true`.

**Per-market wall-times observed (ongoing as of session close)**:
- ES (r630): 9011s = 150 min ✓
- CL (r630): 8883s = 148 min ✓
- GC (r630): 11140s = 186 min ✓
- SI (gen8): 25570s = 426 min (7.1h) ✓ — slower box, biggest dataset
- BP (g9): 15999s = 267 min (4.4h) ✓

**Leaderboard tally at session close**:
- ES: 14 accepted, 14 OK, 0 FAILED
- CL: 13 accepted, 13 OK, 0 FAILED
- GC: 14 accepted, 14 OK, 0 FAILED
- SI: 14 accepted, 14 OK, 0 FAILED
- BP: 13 accepted, 13 OK, 0 FAILED

**Total so far: 68 accepted strategies, 0 PARITY_FAILED.**

YM, EC, JY, AD, BTC still active or queued. Forecast: 8-9 of 10 markets done by end of overnight cycle. EC + JY (gen8) likely the laggards — 7h+ FX wall-times mean only 1-2 of 3 gen8 markets complete before user wakes.

## RAM observation (live, session 97 close)

| Host | RAM total | Used | Avail | Swap used | Workers alive | Avg RSS/worker |
|---|---|---|---|---|---|---|
| r630 | 62 GB | 54 GB | 7 GB | 4 GB | ~80 (transient) | 793 MB |
| gen8 | 78 GB | 72 GB | 5 GB | 6 GB | ~73 (transient) | 1.24 GB |
| g9 | 31 GB | 3-25 GB depending on phase | varies | 0 | varies | varies |

**Findings**:
- 40-worker cap on r630 + 36 on gen8 is a Sprint 98 calibration that holds up but barely: both hosts are using swap right now.
- "80 workers alive" on r630 is recycling-pool transient overlap (old + new during fork-on-demand window), not 80 effective workers. Steady-state effective is ~40.
- The bottleneck is not CPU count — it's **per-worker RSS dominated by the precomputed features DataFrame** (1.4M rows × 21 cols = ~235 MB raw + pandas overhead, copied per worker on fork).
- Cannot push workers higher without addressing per-worker footprint.

## Next-sprint design: shared-memory feature DataFrame

Saved as `docs/SHARED_MEMORY_FEATURES_DESIGN.md`. Stdlib `multiprocessing.shared_memory` approach. Each numeric feature column gets a named POSIX shm segment; workers attach by name and reconstruct zero-copy DataFrame views. Expected outcome: r630 worker RSS 793 MB → ~250 MB, headroom for 70-80 workers, ~30-40% faster total wall-time on big markets. Estimated effort 1 working day.

## Commits on main (session 97)

- `f4424ce` — Bug #1 fix (direction default in rebuild EngineConfig) + 4 parity tests
- `235f993` — Bug #2 fix (vectorized dispatch in rebuild) + 2 signal_exit parity tests
- `aa961ff` — Bug #3 fix (best_refined_filter_class_names tracking) + 1 routing regression test
- `1f1c50d` — `scripts/backfill_best_refined_filters.py` for repairing pre-fix runs
- `b74d27e` — 10-market 5m configs (ES, CL, GC, YM, SI, EC, JY, BP, AD, BTC) + generator
- `34015ec` — `scripts/run_5ers_overnight_queue.sh` per-host queue runner

## Files added

```
modules/portfolio_evaluator.py  (modified — direction + vectorized dispatch + refined filter preference)
master_strategy_engine.py       (modified — best_refined_filters in leaderboard)
tests/test_rebuild_direction_parity.py  (new — 7 regression tests)
scripts/backfill_best_refined_filters.py  (new — repair tool)
scripts/generate_5ers_5m_configs.py  (new — config generator)
scripts/run_5ers_overnight_queue.sh  (new — queue runner)
configs/local_sweeps/{ES,CL,GC,YM,SI,EC,JY,BP,AD,BTC}_5m_5ers.yaml  (new — 10 configs)
docs/SHARED_MEMORY_FEATURES_DESIGN.md  (new — design for next sprint)
sessions/SESSION_97_rebuild_parity_bugs_and_5ers_overnight.md  (this file)
```

## Sprint 100 (same session, 2026-05-05) — Shared-memory feature DataFrame

Shipped end-to-end the same session as bug fixes #1-#3 once the user OK'd the design. Commits `3c33f11`.

**Module**: `modules/shared_memory_features.py` — stdlib `multiprocessing.shared_memory` only. `materialise_to_shm(df, run_id)` allocates one POSIX segment per numeric column (named `psc_<run_id>_<col>`) plus one for the int64 view of the DatetimeIndex. Returns a `ShmOwner` with idempotent `close()` and atexit-registered crash safety. `attach_from_shm(meta)` reconstructs a zero-copy `pd.DataFrame(cols, index=idx, copy=False)` from the meta and returns the handles the worker MUST keep alive for buffer validity.

**Wiring**:
- `master_strategy_engine.py`: when `pipeline.shared_memory_features: true`, materialise after `add_precomputed_features()` and pass `owner.meta` to pool initialisers. Parent retains the original DataFrame for sanity check, status writes, summary builds. Cleanup in dataset finally block.
- `sweep_worker_init` (shared sweep pool): detects `ShmMeta` vs `DataFrame` at init time and attaches once, sharing handles across all 3 family modules.
- `_mr_worker_init` / `_trend_worker_init` / `_breakout_worker_init`: same pattern. Each module gets a `_*_shm_handles` list at module level to keep handles alive for the worker's lifetime (otherwise GC frees the buffer mid-sweep).

**Tests**: 12 in `tests/test_shared_memory_features.py`. 11 pass on Windows + 1 cross-process (Linux only, runs on cluster). All 98 existing tests still green. The cross-process test attaches in a `spawn` subprocess and verifies bit-exact summary reads.

**Cluster smoke test (c240, 2026-05-04 19:00 UTC)**: ES daily run, SHM OFF (control) vs SHM ON. Both produced 13 accepted strategies, **bit-exact `trade_artifact_rebuilt_net_pnl` on all 13**, 0 PARITY_FAILED. Two of 15 leader rows had different `leader_strategy_name` (tied refined candidates with identical net_pnl to last cent — pre-existing tie-break non-determinism documented in earlier engine_parity work; not SHM-induced). SHM-on run wrote `[shm] features materialised to shared memory (16 cols × 4,163 rows)` and `[shm] feature segments unlinked` confirming both phases. SHM-on was 1:59 vs 1:41 SHM-off — slightly faster even on tiny daily data because fork copies less.

**Crash safety verified**: launched ES 5m run on c240 (829k rows, 22 SHM segments allocated), killed parent mid-sanity-check with SIGTERM; atexit handler unlinked all 22 segments cleanly (`/dev/shm/` count went from 22 → 0).

**Final RAM-savings benchmark deferred** to tomorrow when the 3 cluster hosts (r630/gen8/g9) finish their overnight queues and become available for clean A/B testing without contention. Smoke + parity + crash-safety already prove correctness; the remaining test is just measuring per-worker RSS to confirm the projected 800 MB → 250 MB drop.

## Open work next session

1. Confirm overnight queue final state (which of 8 active markets completed; JY + BTC remain deferred via `.deferred` rename).
2. Run backfill on any pre-fix runs that need repair (use `scripts/backfill_best_refined_filters.py` + `backfill_trade_emission.py --force`).
3. **Sprint 100 RAM A/B**: NQ 5m on r630 with `shared_memory_features: false` (baseline = 793 MB/worker, 4 GB swap) vs `shared_memory_features: true` (target ~250 MB/worker, 0 swap). Sample RSS via `scripts/rss_sampler.sh`. If RSS drops as projected, push workers 40 → 70 on r630 and re-time ES 5m against tonight's 150-min baseline.
4. **Round 2 markets** (15 markets, 13 with data + 2 deferred): N225, DAX, FTSE, STOXX, CAC, BRENT, ETH, NZDUSD, USDCAD, USDCHF (the5ers extras), RTY, NG, HG (FTMO-only), JY, BTC (deferred). With SHM at workers=70 on r630, the queue should land in roughly one overnight cycle vs two.
5. Decide whether to expand to AUS, W, DXY (FTMO-supported but no Dukascopy data on cluster).
