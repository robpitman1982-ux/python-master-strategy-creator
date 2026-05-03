# LLM Consultation — 5m Sweep RAM Crisis + Speed Win Hunt

**Last refreshed:** 2026-05-04 (after Sprints 84-92 shipped + post-incident profiling)
**Goal:** stop the 5m sweep cluster from collapsing under RAM pressure AND find the highest-leverage speed wins, given that the previous binding bottleneck (trade artifact emission) is now fixed.
**Owner:** Rob Pitman. Cross-LLM consultation (ChatGPT-5 / Gemini 2.5 Pro). Reply with concrete code-level changes, not generic advice.

---

## 1. What was already shipped (do NOT propose redoing these)

These all landed in 2026-05-03 sprint cycle. The engine + selector pipeline is materially different from the prior `EXTERNAL_LLM_BRIEFING.md` (last refreshed 2026-05-03 pre-sprint-84):

| Sprint | Shipped | Commit |
|--------|---------|--------|
| **84** | **Canonical per-trade artifact emission.** `strategy_trades.csv` + `strategy_returns.csv` now mandatory on every accepted strategy from every sweep run, regardless of `skip_portfolio_evaluation`. Post-ultimate gate fail-closed on missing/parity-failed artifacts. Empirical: gated pass rate 96.4% → 4.5% on validation, 22 real strategies surviving. | `7acd6ec` |
| **85A** | CFD config plumbing fix. `_rebuild_strategy_from_leaderboard_row` no longer uses futures `EngineConfig` defaults on CFD data (was 100x slippage + inverted PnL). | `82c10a7` |
| **85B** | Rebuild signal-mask round-trip — `compute_combined_signal_mask` output now passed to `engine.run`, eliminates entry-bar drift in refined-subtype rebuilds. | `43e04d7` |
| **87** | The5ers MT5 cost overlay. `configs/the5ers_mt5_specs.yaml` populated with asymmetric long/short swap + commission, custom triple-day rules (CL Friday=10×, BTC daily-no-triple). Selector consumes via `use_the5ers_overlay` toggle. | `f76ff8b` |
| **88** | Account-aware deployability check. Selector flags `INFEASIBLE_AT_ACCOUNT_SIZE` when any portfolio weight scales below MT5 `min_lot=0.01` for the configured account size. | `21b8dbe` |
| **89** | **Cost-aware MC vectorised.** Triple-nested Python loop replaced by numpy batch operations. **Measured speedup: 6,513×** (158s → 24ms at 3 strats × 100 trades × 200 sims). | `1eb15ae` |
| **92** | FTMO firm overlay + multi-firm support. `configs/ftmo_mt5_specs.yaml` populated. Selector auto-selects per-firm overlay from `prop_config.firm_name`. End-to-end: same top portfolio (N225 daily Breakout + CAC daily Breakout + YM daily Trend) wins ALL 7 program tracks (4× The5ers + 3× FTMO) with 99.8-100% pass rate, 6.14-6.54% p95 DD. | `06736a4` |

**Tests:** 108/108 green across all sprint suites. Top portfolio empirically validated against real FTMO swap data.

**Implication for any LLM advice on this consultation:** "ship direct trade emission first" is wrong — already done. "Wire cost overlays into MC" is wrong — already done. "Fail-closed when artifacts missing" is wrong — already done. Recommendations must address what's still open.

## 2. What is still open

Three categories:

### 2a. The 5m sweep RAM crisis (today's incident — root cause unknown)

When 5m sweeps run on the cluster, hosts go offline (network-layer unresponsive) once the engine progresses to the subtype phase (~6 families deep). Pattern observed today:

1. Engine launches with ~80 worker processes via `ProcessPoolExecutor`.
2. As later families need additional precomputed features (different lookbacks for SMA/ATR/momentum), per-worker RSS climbs from ~300 MB → 500 MB+.
3. On `g9` (31 GB RAM, 4 GB swap): 80 × 400 MB = 32 GB → swap fills → host goes silently offline at TCP layer. No OOM-killer event in dmesg — workers die from Python IPC failures during swap-thrash. Recovers 10-15 min later with ~40 fewer workers; engine continues at degraded reliability.
4. Same pattern hit `r630` (62 GB RAM) once it reached subtype phase. Killed pre-emptively.
5. `gen8` (78 GB RAM) survived but cycled through one near-OOM event then recovered.

**Per-worker RSS of ~300-500 MB on a ~100 MB dataset** strongly suggests CoW is being broken — possibly by pandas operations that touch every memory page during precompute, or by feature-frame mutation that defeats fork-share. **This has not been profiled with `pmap -X` yet.**

### 2b. MR sweep dominates wall-clock (per-family timing data)

Found in `/tmp/psc_logs/psc_10market_c240_redo2.log`:

**Small dataset (~4,127 bars) — 383s total:**
| Family | Sweep | Refinement | % of dataset |
|--------|-------|------------|--------------|
| mean_reversion | 209.9s | 5.2s | **57%** |
| breakout | 89.7s | 1.9s | 24% |
| trend | 4.5s | 3.0s | 3% |
| 9 subtypes (concurrent) | small | varies | 14% |

**Large dataset (~30k bars, e.g. 60m):**
| Family | Wall time |
|--------|-----------|
| mean_reversion | **2h 22m** (8,540s) |
| breakout | 47m (2,816s) |
| trend | 1m 46s |

Per-combo cost on small MR: 209.9s / 31,008 combos = **6.77 ms/combo**.
Per-combo cost on small trend: 4.45s / 9,373 combos = **0.48 ms/combo**.

Same filter mask logic per combo, but MR is 14× slower per combo because **MR generates more trades per signal mask**. Per-combo time is dominated by trade simulation, NOT filter mask evaluation.

**MR is the leverage target.** Speed it up or reduce its combo count and total dataset wall-clock drops massively.

### 2c. Latent items on the open issue list

These are documented in `MASTER_HANDOVER.md` Open Issues section but not blocking the current incident:

- Layer C (tail co-loss) gate **disabled** — calc broken.
- ECD gate **disabled** — was rejecting everything.
- Walk-forward module (`modules/walk_forward.py`, 273 lines) exists but **not consumed** anywhere.
- BH-FDR multiple-testing correction implemented in `modules/statistics.py` but **dormant** (`bh_fdr_alpha: null`).
- Challenge-vs-funded selector mode **unimplemented** (spec at `docs/CHALLENGE_VS_FUNDED_SPEC.md`).
- No engine-level **resume logic** — kill loses every completed family on the dataset.

## 3. Cluster topology (relevant for any RAM/speed proposal)

| Host | Threads | RAM | Swap | Role |
|------|---------|-----|------|------|
| c240 | 80 | 62 GB | 8 GB | Data hub + orchestrator + sweeper |
| r630 | 88 | 62 GB | 8 GB | Sweeper |
| g9 | **48** | **31 GB** | 4 GB | Sweeper (smallest box; the canary) |
| gen8 | 48 | 78 GB | 8 GB | Sweeper |

g9's 31 GB makes it the worst-case box for any 5m proposal. All Ubuntu 24.04, Python 3.12.3, Tailscale mesh. Data hub at `c240:/data/market_data/cfds/ohlc_engine/`.

## 4. Engine code map (where changes go)

- `master_strategy_engine.py::_run_dataset` — top-level dataset orchestrator.
- `modules/feature_builder.py::add_precomputed_features` — runs once per dataset, computes union of SMA/ATR/momentum lookbacks needed across all 12 families. Result frame shipped to each worker.
- `modules/filters.py` — every filter has `passes(data, i)` and `mask(data) → np.ndarray[bool]`. Filters consume precomputed feature columns; masks are pre-vectorised numpy comparisons.
- `modules/vectorized_trades.py` — replaces per-bar Python loop with 2D numpy arrays (Session 61, 14-23× speedup, zero-tolerance parity).
- `modules/strategy_types/{family}_strategy_type.py` — declares `get_filter_classes()` and `get_required_lookbacks()` per family.
- `modules/portfolio_selector.py` (2,705 lines) — gated by trade artifact presence (Sprint 84), cost-aware MC (Sprint 89), per-firm overlay (Sprints 87/92).
- `modules/post_ultimate_gate.py` — fail-closed on missing/parity-failed trade artifacts (Sprint 84).
- `modules/trade_emission.py` — Sprint 84 module that emits per-trade artifacts inline.

Worker fork model: standard `ProcessPoolExecutor.submit()` (fork on Linux, copy-on-write should keep dataset memory shared). In practice we measure ~300-500 MB RSS per worker on a ~100 MB dataset → CoW likely broken somewhere.

## 5. What we've already tried — and what didn't work

- `renice +19` + `ionice -c 3` on every worker PID. Reduced kernel CPU contention (g9 1m load 119 → 92), did **nothing** for RAM pressure. Workers kept allocating; swap kept filling.
- Lowered `max_workers_sweep` and `max_workers_refinement` to 40 each. But sweep + refinement overlap per-family → effective peak still ~80 workers.
- Pre-emptive kill of r630 sweep — clean recovery, but lost completed family work because there's no resume.

## 6. Candidate ideas — please critique, rank, or replace

### Tier S — speed wins, validated/refined by today's profiling

1. **Signal-mask memoisation.** Many filter combos produce identical signal masks (filter A subsumes filter B in some combos). Hash the final boolean mask before running trade simulation; skip if seen. **Estimated 20-40% speedup on the MR sweep specifically** (where it matters most). Effort: hours. Risk: zero (pure caching). *Profiling-confirmed leverage point.*

2. **Numba `@njit` on `vectorized_trades.py` inner kernel.** Trade simulation is the actual per-combo bottleneck (per profiling). Wrapping the simulator with `@njit` typically gives 2-5× on top of numpy. *Targets the proven hot path.*

3. **Filter-mask cache (deferred from earlier).** Precompute each filter's `mask(data)` once per family, AND combos via `np.logical_and.reduce`. Was claimed as 10-50× win in earlier draft of this brief — **profiling shows it's actually 5-15%** because filter eval is not the per-combo bottleneck. Still worth doing as engineering hygiene; cheap, low risk. **Don't oversell it.**

4. **Combo pre-screen via signal sparsity.** Skip combos that produce <50 signals before running trade sim. Promotion gate already requires ≥50 trades; saving the trade sim work on combos that can't pass is ~free. Effort: hours.

### Tier A — RAM stability for 5m sweeps

5. **`pmap -X $worker_pid | grep -i shared` profile FIRST.** Before any RAM fix, validate the CoW-broken hypothesis. 30 seconds. Tells us whether shared-memory work has the leverage we think it does, or whether the fix is "stop pandas mutating the frame".

6. **Float32 on OHLC + feature columns.** Cast at top of `feature_builder.py`. **Halves numeric memory immediately.** Trading-sweep precision irrelevant at 7 sig figs. Risk: pandas may silently up-cast in some operations — need audit. Effort: half day.

7. **`maxtasksperchild=200` on the worker pool.** Switch from `ProcessPoolExecutor` to `multiprocessing.Pool(maxtasksperchild=200)` to recycle workers periodically. Forces Python heap reset. Should eliminate within-family memory creep. Effort: 1-2 hours.

8. **Sequential families (no overlap).** Tear down family N's pool fully before family N+1 starts. Eliminates the sweep+refinement-pool overlap that doubles peak worker count. Throughput cost ~20-30%; eliminates the offline-cycle pattern entirely.

9. **Shared-memory OHLC + feature frames** via `multiprocessing.shared_memory`. Convert feature frame to numpy arrays backed by `SharedMemory` once at engine start, pass workers handles instead of pickled copies. Estimated savings: 80 workers × ~80 MB per copy = 6 GB on g9. **Conditional on idea 5 confirming CoW is broken.** If CoW is partially working, shared-memory's value drops sharply.

10. **Move 5m off g9 entirely.** g9's 31 GB just isn't enough for the 5m feature footprint. Restrict 5m sweeps to c240/r630/gen8 (62+ GB hosts); give g9 the 15m+ work. Config split, no engine change. Loses one host's parallelism but stops the offline cycles cold.

### Tier B — defensive / structural

11. **Resume logic.** Check for existing `{family}_filter_combination_sweep_results.csv` on startup; skip families with valid output. Doesn't reduce RAM. **Turns "kill + restart with smaller workers" from "lose everything" to "lose the in-flight family"**. Makes every other RAM fix viable as a hotfix.

12. **Bayesian / Optuna refinement** instead of brute-force 4×4×4×4 grid. Refinement is small in our profiling (1-5s per family) so this is low priority — but on 5m datasets where refinement scales with bars, could matter. Already on wishlist (CLAUDE.md known-issues).

## 7. Reframed consultation questions

Sprint 84-92's work changes which questions are worth asking.

### Q1 — RAM crisis: profile-first vs implement-first

The CoW-breakage hypothesis is unconfirmed. Two paths:
(a) Run `pmap -X` on a live worker, identify exactly what's not being shared, then fix the root cause (which might just be "stop mutating the precomputed frame").
(b) Skip diagnosis, ship `maxtasksperchild` + float32 + shared-memory in parallel, accept that we don't know which fix is actually doing the work.

Which is the right call **for an operator who is compute-rich, time-poor, and has 4 days of cluster time burned on the current 5m batch**?

### Q2 — Profiling-corrected speedup priorities

Given the timing data (MR sweep dominates, trade simulation is the per-combo bottleneck, filter mask eval is <15% of combo time), what's the right ship order across ideas 1-4 (signal-mask memoisation, Numba trade-sim JIT, filter-mask cache, combo pre-screen)? Specifically:
- Is signal-mask memoisation actually likely to hit 20-40% on MR? Or is the mask-collision rate lower than that empirically?
- Does Numba JIT compound multiplicatively with signal-mask memoisation, or do they hit the same compute and only the larger one matters?

### Q3 — Resume logic priority

Without resume, every RAM-fix experiment risks 2-6 hours of completed family work. With resume, we can iterate freely. Should resume ship FIRST as the unblocker, even though it doesn't reduce RAM by itself? Or does it slow the actual fix path more than it helps?

### Q4 — Layer C / ECD / walk-forward

These three were disabled or never wired in. Now that the cost overlay is real (Sprints 87/92), is there an argument for revisiting them? Specifically:
- Does asymmetric swap data make co-LPM2 / lower-tail-dependence calculations more meaningful at the selector stage?
- Walk-forward — at family leaderboard or at post-ultimate gate? (Earlier brief said ChatGPT picked post-ultimate, Gemini picked family-stage. Now that post-ultimate has teeth via Sprint 84, does that change the answer?)

### Q5 — 5m sweep value question

Session 42 dropped 5m timeframe entirely from futures sweeps after observing zero accepted strategies (5m noise too high to clear quality flags). CFD 5m sweeps may behave differently — but **we don't have evidence yet** because every 5m sweep we've started has been killed by RAM crisis before completing. Two options:
(a) Fix the RAM crisis, complete one 5m sweep, see if any strategies pass quality gates.
(b) Skip 5m entirely on CFDs as well, given the futures precedent and the operational pain.

What would you need to see to recommend (b) over (a)? Specifically: how many 5m sweep CSVs would have to come back with zero accepted strategies before "skip 5m" is the right call?

### Q6 — Anti-convergence flag

The earlier consultation round (Q1-Q16 in `EXTERNAL_LLM_BRIEFING.md`) had ChatGPT-5 and Gemini converging on "fix trade artifact emission" as the binding bottleneck. That bet paid off — Sprint 84 shipped, gates have teeth, cost-aware MC works. But by your 8x calibrated prior, the convergence point was anti-alpha for genuinely novel insight.

Where do you think this round's convergence will hide? What's the question we should be asking but aren't?

---

## 8. Reference: what the engine looks like end-to-end (post-sprint-92)

```
DATA LOAD -> FEATURE PRECOMPUTE (once per dataset, all lookbacks union)
  -> per family:
       SANITY CHECK -> FILTER COMBO SWEEP -> PROMOTION GATE
          -> REFINEMENT GRID -> FAMILY LEADERBOARD ACCEPT
          -> *** TRADE EMISSION (Sprint 84, mandatory) ***
  -> MASTER LEADERBOARD AGGREGATION
  -> ULTIMATE LEADERBOARD (cross-run)
  -> POST-ULTIMATE GATE (Sprint 84 fail-closed; concentration + fragility)
  -> PORTFOLIO SELECTOR (multi-firm overlay; cost-aware MC; sizing opt)
       -> per program: portfolio_selector_report.csv with verdict
```

12 families per dataset (3 base × 2 directions + 9 subtypes). Cluster orchestration via `run_cluster_sweep.py --distributed-plan`. Auto-ingest watcher mirrors completed datasets to canonical storage at `c240:/data/sweep_results/runs/<run_id>/`. Drive backup runs nightly + on-ingest mirror.

Cost realism:
- The5ers: `configs/the5ers_mt5_specs.yaml` (Sprint 87)
- FTMO: `configs/ftmo_mt5_specs.yaml` (Sprint 92)
- Selector auto-selects from `prop_config.firm_name`.

End-to-end winner across all 7 prop firm programs: same 3-strategy daily portfolio (N225 + CAC + YM, 0.01 lot each), 99.8-100% pass rate, 6.14-6.54% p95 DD across all programs. Captured in `configs/live_portfolios/portfolio4_cfd_top.yaml`.

---

Last updated: 2026-05-04 — Session 95 (post-Sprint-92 reframe)
