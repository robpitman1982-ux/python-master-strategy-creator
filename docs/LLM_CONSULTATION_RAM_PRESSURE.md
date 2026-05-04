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

Last updated: 2026-05-04 — Session 95 (Sprints 93/94/95 shipped; consultation round 4 below)

---

## ROUND 4 — Sprint 93-95 results + new consultation question

**For ChatGPT-5 / Gemini 2.5 Pro:** This section is the live update. The
Round 1-3 sections above are historical context. The actionable question
is **Q7-R4** at the end of this section — please answer that one.

### What shipped since Round 3 (commits on main)

| Sprint | Goal | Verdict | Wall-clock impact (ES daily smoke, 75-78s) |
|--------|------|---------|---------------------------------------------|
| **93** Engine resume logic | Per-family on-disk CSV detection + config fingerprint guard so kill+restart only loses the in-flight family | **CANDIDATES** | 75.5s → 34.0s when 6 of 15 families resume from disk = **55% saved** |
| **94** Filter mask cache | Cache per-filter `mask(data)` once per family; combos ANDed via `np.logical_and.reduce` | **SUSPICIOUS** | 76.1s → 76.8s = **+0.9% (within noise)** |
| **95** Signal-mask memoisation | Cache `engine.results()` keyed on `hash(combined_signal_mask)` so combos with identical signal masks share the trade-sim result | **SUSPICIOUS** | 78.1s → 77.1s = **-1.3% (within noise)** |

All three sprints: 430/430 tests pass, zero behavioural drift on the
parity check (`net_pnl`/`leader_pf`/`oos_pf` identical row-by-row vs
control). Default-off in config. Env var override (`PSC_*`) for ad-hoc
testing.

### What we know empirically

- **Sprint 93 was the structural unblocker.** No more "kill loses 6 hours
  of completed family work". Verdict-gate smoke test passed all 5 stages.
  This was the highest-impact deliverable of the three.
- **Sprints 94 and 95 are functionally correct but show no measurable
  speedup on the small dataset (ES daily, 4163 bars).** Both produced
  parity-clean but indistinguishable-from-noise wall-clock results.
- **Engine has pre-existing tie-break non-determinism** in refinement
  sort: when two refined candidates tie on `net_pnl`/`profit_factor`/
  `average_trade`, the parallel-worker scheduling determines which
  becomes the leader. Documented in Sprint 93. Affects ~1 of 15 families
  per run on small datasets. NOT introduced by 94 or 95 — was there
  already.
- **Per-worker collision rate is opaque** for Sprint 95. Workers fork
  from parent, each gets ~775 of 31,008 MR combos, and their cache
  state doesn't aggregate back to parent. Adding aggregation would
  require a Manager dict or stats file side channel — scoped out of 95.

### Three theories for why 94 and 95 went SUSPICIOUS

1. **Small-dataset smoke gate is inadequate.** ES daily is 4163 bars,
   ~6.8 ms per combo, ~75s total dataset wall-clock. Filter-mask eval
   and trade-sim are fast in absolute terms; even a 30% hit rate saves
   sub-millisecond per combo. On a 5m dataset (470k bars, ~275 ms per
   combo per Round 3 profiling), the same hit rate would save tens of
   seconds. Pre-reg threshold (10% wall-clock) was set against the
   small-dataset baseline and may be undermeasuring leverage.
2. **Trade simulation isn't actually the per-combo bottleneck on small
   datasets.** Profiling (Round 3 section 2b) showed MR per-combo cost
   is dominated by trade-sim on the BIG dataset (60m: 2h 22m for one
   family at 6.77 ms/combo × 31,008 combos). On the SMALL dataset,
   metric computation + result-dict building may be a larger share of
   per-combo time, which neither cache addresses.
3. **The ProcessPoolExecutor fork model defeats both caches.** Each
   worker has its own CoW copy of the cache. Within a worker (~775
   combos for MR), distinct filter combos that produce identical masks
   are sparse — most "mask collisions" happen across different
   workers, where caches don't share. Sprint 94's per-filter cache
   has the same issue but is less affected because all 10 unique
   filters get cached after ~10 combos in any worker.

### What's still open

- **Layer C (tail co-loss)** still disabled — Gemini Round 2 recommended
  replacement with co-LPM2 or lower-tail dependence coefficient. Not
  attempted yet.
- **ECD gate** still disabled.
- **Walk-forward** still not consumed by the selector. Gemini Round 2
  argued for moving it from post-ultimate to family-leaderboard stage.
- **HRP clustering in selector** (Gemini Q9 Round 2) — argued as the
  architectural replacement for the loosened correlation gates. Sprint
  96 is queued.
- **Numba JIT on `vectorized_trades.py`** — Sprint 97 in queue. Targets
  the actual per-combo bottleneck per profiling.
- **5m sweep RAM crisis** is still unresolved. Sprint 93 makes it safer
  to experiment (kill+restart cheap) but no fix has shipped.

### The pattern we want validated

After Sprint 95, **two consecutive engine-side optimisations have come
back SUSPICIOUS** (parity-clean, no measurable speedup on the smoke
gate). The engineering instinct is to ship them default-off and move
on. But there's a deeper question: are we hitting a **measurement
limit** (smoke too small), a **architecture limit** (fork model
defeats caching), or a **target-selection limit** (we're optimising
the wrong layer of the engine)?

### Q7-R4 — Where do we point next?

You're advising an operator who:

- Has 264 cluster threads available, mostly idle.
- Has a parity-tested vectorised engine that's already 14-23x faster
  than the original loop (Session 61, zero-tolerance parity tests).
- Has a working selector that produces RECOMMENDED portfolios for all
  7 prop-firm programs (cost-aware MC vectorised in Sprint 89).
- Is operating under the assumption that "5m sweeps take too long /
  RAM-crash" is the next big problem to solve, but hasn't yet
  re-tested on 5m post-Sprint-93.
- Just shipped 2 SUSPICIOUS sprints back-to-back at the engine layer.

**Concrete question:** what's the right next move?

Pick exactly one of:

(a) **Re-test Sprints 94 + 95 on a 5m or 60m smoke** before declaring
    them dead. The hypothesis is that the small-dataset smoke gate
    undermeasures leverage. Sprint 93 makes this cheap (kill any
    failed run, resume from where it stopped). Cost: ~1-3 hours of
    cluster time per dataset.

(b) **Revert Sprints 94 and 95 entirely**, keep Sprint 93, declare
    engine-side optimisation a dead end for now, and pivot to the
    selector layer (Sprint 96 HRP, then post-ultimate gate
    improvements like walk-forward and Layer C replacement). The
    engine optimisation work returns later, post-Numba-JIT (Sprint
    97), with profiling data to drive the design.

(c) **Skip both 94 and 95 verification**, leave them shipped as
    default-off, and go straight to **Sprint 97 (Numba JIT on
    vectorised_trades inner kernel)** because profiling already
    identified trade-sim as the per-combo bottleneck. The engine win
    expected from Numba (2-5×) is much larger than what the caches
    could provide and is not Amdahl-bounded the same way.

(d) **Pause all engine work and focus entirely on the selector** —
    Sprint 96 (HRP clustering replacing loosened gates) plus the
    Layer C / ECD / walk-forward items. The selector currently passes
    96.4% of strategies through (per Round 1 audit) — fixing that is
    a bigger pass-rate-quality lever than any engine speedup.

(e) **Something we haven't considered.** If our framing is wrong,
    please reframe.

**For your answer:**
1. Pick one of (a)/(b)/(c)/(d)/(e) and defend it in 3-5 sentences.
2. Tell us which of the three theories above (small-dataset / target
   selection / fork model) you think best explains the SUSPICIOUS
   pattern, OR propose a fourth theory.
3. **Anti-convergence flag:** if your answer aligns closely with the
   "obvious safe" answer (which we'd guess is some form of (b)), tell
   us where you held back and what your bolder take would be.

### Constraints (please respect)

- Do NOT recommend re-doing Sprint 84 work (canonical trade emission).
  That shipped 36 hours ago. The post-ultimate gate is fail-closed on
  missing trade artifacts.
- Do NOT recommend rewriting the vectorised engine. Zero-tolerance
  parity tests are guarding it for a reason.
- Do NOT recommend "buy more RAM" or "rewrite in Rust". g9 hardware
  upgrade is already in flight.
- Specific code-level recommendations beat abstract critique.

---

Last updated: 2026-05-04 — Session 96 close (Round 5 below: deferred verdict gates resolved + unexpected yaml-reload finding)

---

## ROUND 5 — Session 96 close: deferred verdict gates resolved, plus an unplanned 3.4× find

This section is the canonical session-96 summary. **For ChatGPT-5 / Gemini 2.5 Pro**: read this whole section before answering any new question. It supersedes the speculative numbers in Round 1-4 with measured data.

### Final verdict matrix (after both deferred A/B runs + a profile detour)

| Sprint | Original verdict | Re-test outcome | **Production effect** |
|--------|------------------|-----------------|----------------------|
| **93** Engine resume logic | CANDIDATES (55% wall-clock saved on 6/15-resumed smoke) | — | **Real win, default ON.** Kill+restart now costs the in-flight family only. |
| **94** Filter mask cache | SUSPICIOUS (+0.9% on smoke) | gen8 4-mode re-test post-99-bis fix: A=125.0s, B=123.2s = -1.4% (still noise) | Default OFF; foundation infrastructure for future when filter eval becomes the bottleneck. |
| **95** Signal-mask memoisation | SUSPICIOUS (-1.3% on smoke) | gen8: A=125.0s, C=123.6s = -1.1% | Default OFF; same status. |
| **96** HRP clustering in selector | (deferred) | A/B on `high_stakes_5k`: A=668.3s, B=674.4s, **strategy_names IDENTICAL** | Default OFF; HRP fired correctly (15 clusters / 25 strategies) but the top 3-strategy combo already maxes diversity. Pre-reg's "Honest expected outcome" predicted exactly this — pays off when pool grows. |
| **97** Numba JIT on `vectorized_trades.py` | Skipped after profile reading | n/a | Inner kernel already pure numpy; expected gain ≤15%, not worth parity risk. |
| **98** RAM prevention (recycling_pool + sequential_families) | CANDIDATES on parity gate | **5m heavy A/B**: r630 (ON) peak RSS 35.8 GB / swap 108 MB; c240 (OFF) peak RSS 51.6 GB / swap **3.2 GB swap-thrash starting** | **Real win, 30.6% peak RSS reduction met pre-reg ≥30% gate; default flip-on for any 5m config.** |
| **99** Trade-array refactor | (planned) | **Trial RED** — see Sprint 99-bis | Not pursued. Trade-object loop wasn't the bottleneck. |
| **99-bis** is_enabled() yaml-reload fix | (unplanned discovery) | cProfile sequential: 78.76s → 23.40s = **3.4× faster** | Shipped (`be0ee0e`); real gain on dev workflow / cProfile / unit tests; **noise on parallel sweeps (1-2%)**. |

### The 99-bis story (worth knowing)

Sprint 99 was scoped as a Trade-array refactor to capture the 2-5×
speedup that Numba couldn't deliver. Per pre-reg, we ran a cProfile
trial first to confirm the targeted code paths were >20% of per-combo
time before committing to the refactor.

The profile dropped a bombshell. The bottleneck wasn't the Trade
loop. It was Sprints 94 + 95 themselves:

```
load_config (yaml.safe_load):  57.87s of 78.76s total = 73%
filter_mask_cache.is_enabled:  28.95s
signal_mask_memo.is_enabled:   28.97s
```

Both `is_enabled()` functions called `load_config()` →
`yaml.safe_load()` on **every** combo. With 1500 combos × 2 cache
flag checks = 3000 yaml loads. **Both flags were default-OFF, so this
was pure overhead introduced by the SUSPICIOUS sprints themselves.**

The fix: cache the `is_enabled()` result at module level, resolved
once per process. 30 lines across 3 modules. Shipped as `be0ee0e`.

**Re-profiled after fix:**
- Sequential (1 worker, 1500 combos): 78.76s → 23.40s (3.4× faster)
- Parallel (40 workers, smoke): 76.1s → 76.8s (no change)

The 3.4× was a sequential-profiling artifact. In parallel runs each
worker forks once and amortises the yaml load across many combos
within the worker's lifetime — yaml was never the parallel-run
bottleneck. The fix is real and valuable for **dev workflow** but
does NOT speed up production sweeps.

**Critically**: this means my prediction that "Sprints 94 + 95
will flip from SUSPICIOUS to CANDIDATES on re-test post-fix" was
WRONG. They stayed SUSPICIOUS. The cache benefits exist but are
genuinely small in absolute terms; not the masked-by-yaml-overhead
issue I'd hypothesised.

### What's actually solved and what isn't

**SOLVED:**
- ✅ 5m sweep RAM crisis. Sprint 98 flags + worker count 82→40 = stably-completing 5m sweeps.
- ✅ Kill + restart cost. Sprint 93 = O(in-flight family) instead of O(everything).
- ✅ Dev workflow speed. Sprint 99-bis = cProfile / unit tests / small interactive runs 3.4× faster.
- ✅ Selector cost realism. Sprints 87/89/92 (already shipped pre-session 95) = real cost-aware MC.
- ✅ Trade artifact reliability. Sprint 84 (already shipped pre-session 95) = canonical emission.

**NOT SOLVED (and likely not worth solving with the same playbook):**
- ❌ 2-5× engine speedup on production parallel sweeps. Multiple angles tried (94, 95, 97, 99) all bounded by the engine already being heavily vectorised. Per-combo time on 5m is dominated by trade simulation in numpy, which is already C-level fast.
- ❌ HRP-driven selector diversity wins on the current pool (the top 3-strategy combo already maxes cluster diversity).

**STILL OPEN (architectural, bigger lifts):**
- Layer C (tail co-loss) — Gemini Round 2 recommended replacement; not attempted
- ECD gate — disabled
- Walk-forward at family leaderboard stage — module exists, never wired
- Distributed intra-dataset sweep — planner exists, autonomous dispatch doesn't
- Polars / shared-memory OHLC — bigger refactor, untested

### Q8-R5 — One question for the round

Sessions 95 + 96 produced 5 sprints shipped, 1 skipped, and 1
discovered-and-fixed bug. The pattern that emerged: **engine-side
performance optimisation has hit its diminishing-returns ceiling**.
The vectorised engine is already where Python+numpy can take it; the
remaining levers are RAM-prevention (Sprint 98 = solved), kill+restart
recovery (Sprint 93 = solved), and dev-workflow speed (Sprint 99-bis
= bonus).

If you were advising the operator on **Round-6 priorities**, given:
- 264 cluster threads, mostly idle
- Stable 5m sweeps on the cluster
- Selector that produces RECOMMENDED portfolios for all 7 prop firm
  programs, but the candidate pool is daily-dominated and 96.4% of
  strategies pass the post-ultimate gate (per Round 1 audit)
- A real, funded FTMO + The5ers Swing portfolio running the top combo
  on Contabo (committed in `configs/live_portfolios/portfolio4_cfd_top.yaml`)
- Test coverage 287 → 488 across the two sessions

What's the **one architectural item** to pursue that would most
materially improve **portfolio quality** (not engine speed)? Pick
exactly one of:

(a) **Walk-forward at the family-leaderboard stage** — kill overfit
    junk before it pollutes the master leaderboard. Gemini Round 2
    flagged this; never wired. ~1 week of work; ~30% of accepted
    strategies expected to fail WF on heavy datasets.

(b) **Layer C tail co-loss replacement** with co-LPM2 or lower-tail
    dependence — fixes a disabled selector gate. Sharpens the
    correlation structure. ~3-4 days. Effect size unknown.

(c) **Per-cluster bucketed candidate cap** in the selector — replaces
    the global `candidate_cap: 60` with per-HRP-cluster quotas, so
    intraday strategies aren't locked out by daily dominance. Builds
    on Sprint 96. ~2-3 days.

(d) **Walk-forward + HRP combined** as a Round 6 sprint — biggest
    structural change to selector quality. ~2 weeks.

(e) **Reframe** — the candidate-pool problem is upstream (we're
    sweeping the wrong markets / filters / timeframes), and selector
    gates can't fix that. Spend the time generating a wider pool
    instead.

Pick one and defend in 3-5 sentences. **Anti-convergence flag**: if
ChatGPT and Gemini agree, that's anti-alpha; flag it.

---

Last updated: 2026-05-04 — Session 96 close (Round 5)
