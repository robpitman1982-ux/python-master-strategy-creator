# LLM Consultation — Engine RAM Pressure on 5m Sweeps

**Goal**: reduce per-worker RAM footprint so the strategy-discovery engine can run at
near-maximum CPU parallelism across the cluster without triggering OOM cascades.

**Owner**: Rob Pitman. Two-tier workflow — claude.ai for strategic dialogue, Claude Code
for execution. This doc is for cross-LLM consultation (ChatGPT-5 / Gemini 2.5 Pro).
Reply with concrete code-level changes, not generic advice.

---

## 1. The cluster

| Host  | CPU threads | RAM       | Swap    | Role                              |
|-------|-------------|-----------|---------|-----------------------------------|
| c240  | 80          | 62 GB     | 8 GB    | Data hub + orchestrator + sweeper |
| r630  | 88          | 62 GB     | 8 GB    | Sweeper                           |
| g9    | 48          | **31 GB** | **4 GB**| Sweeper (smallest box)            |
| gen8  | 48          | 78 GB     | 8 GB    | Sweeper                           |

All Ubuntu 24.04, Python 3.12.3, on Tailscale VPN. Connected via SSH mesh. Shared
data hub at `c240:/data/market_data/cfds/ohlc_engine/` (SMB to other nodes).

## 2. The engine, in one paragraph

`master_strategy_engine.py` runs a funnel per **strategy family** on a **dataset
(market × timeframe)**:

```
SANITY CHECK -> FILTER COMBO SWEEP -> PROMOTION GATE -> REFINEMENT GRID
   -> LEADERBOARD ACCEPT -> (per-family CSVs written) -> next family
```

12 families per dataset (3 base × 2 directions + 6 named subtypes). Currently runs
with `ProcessPoolExecutor`; `max_workers_sweep=40` and `max_workers_refinement=40`.
Sweep and refinement of consecutive families overlap — when family N's sweep
finishes, family N+1's sweep can start before family N's refinement is done. So
peak concurrency = sweep-pool + refinement-pool = up to ~80 worker processes.

`filter_combination_sweep_results.csv` and `top_combo_refinement_results_narrow.csv`
are written per family. **There is no resume logic** — restart re-runs everything.

## 3. The bug we're consulting on

On the **5m timeframe specifically**, RAM grows monotonically as the engine moves
through families. By the time we reach the **subtype phase** (~6 families deep), the
process-tree's total RSS exceeds physical RAM on g9 (31 GB) and even bites r630
(62 GB). Observed pattern:

1. Engine launches with ~80 workers.
2. Each worker holds a copy of the **full 5m OHLC DataFrame** (~50–100 MB) plus
   precomputed feature arrays (SMA/ATR/momentum at multiple lookbacks).
3. As later families need additional precomputed features (different lookbacks,
   different signal masks), per-worker RSS climbs from ~300 MB → ~500 MB+.
4. On g9 (31 GB total): 80 × 400 MB = 32 GB → swap fills up → host **goes
   silently offline at TCP layer** (kernel buried in swap thrash). 10–15 min later
   it recovers because ~40 worker processes have died from Python IPC failures
   (not from OOM-killer — kernel OOM didn't fire). Engine continues at degraded
   capacity with the surviving ~125 worker PIDs.
5. Same pattern just hit r630 once it reached the subtype phase (61/62 GB used,
   swap 7.1/8 GB, load 119 → killed pre-emptively).

**Failure mode is not a clean OOM kill** — it's swap-thrash death-spiral that takes
the host's network stack down for 10–15 minutes. dmesg shows no OOM-killer
activity. Workers die from Python IPC timeouts, leaving partial results in the
per-family CSVs.

## 4. What we've tried — and why it didn't help

- **`renice +19` + `ionice -c 3` on every worker PID.**
  Reduced kernel CPU contention waste (g9 load 1m dropped 119 → 92), but did
  nothing for RAM pressure. Workers kept allocating; swap kept filling.
- **Lowered `max_workers_sweep` and `max_workers_refinement` to 40 each.**
  But sweep + refinement overlap → effective peak still ~80 workers.
- **Soft throttle as the only intervention** = the offline-cycle pattern above.
- **Pre-emptive kill** = clean recovery but loses N hours of family-sweep work
  because there's no resume.

## 5. Constraints — please respect

- **No resume logic exists.** Adding it is in scope for a fix, but the engine
  blindly runs every family on each launch. Any fix that requires a restart
  loses prior family work.
- **5m datasets are the binding case.** 60m / daily are fine — only 5m has the
  data volume + feature-array bulk that triggers the issue.
- **Cluster is heterogeneous** — `g9` has 31 GB total, half the next-smallest
  host. Solutions must consider g9 as the worst-case.
- **Cross-LLM independence**: don't suggest "try renice / lower workers" — already
  done. Don't suggest "buy more RAM" — already on it (g9 hardware upgrade pending).
- **Goal is near-max parallelism**, not stability at the cost of throughput. We
  want the work done, not just safely incomplete.

## 6. Engine code map (where to change things)

- `master_strategy_engine.py` — main orchestrator. `run_family_filter_combination_sweep`
  call at line ~828; sweep CSV write at ~838.
- `modules/feature_builder.py` — precomputes SMA/ATR/momentum/etc per dataset.
  Currently called once per dataset and the resulting frame is sent to each
  worker (i.e. each worker has a full copy).
- `modules/strategy_types/{family}_strategy_type.py` — each family declares
  `get_filter_classes()` and `get_required_lookbacks()`. The combination of those
  drives precompute scope.
- `modules/filters.py` — every filter has `passes(data, i)` and `mask(data)` (numpy
  bool array). Filters are stateless w.r.t. data — they read from the precomputed
  feature columns.
- `modules/vectorized_trades.py` — recently-added vectorised trade simulator,
  numpy-only, holds 2D arrays for all trades simultaneously.
- `config.yaml` `pipeline.max_memory_gb` exists but only triggers a worker-cap
  *at startup*, not adaptively per family.
- `pipeline.use_vectorized_trades: true` is on globally.

Worker fork model: standard `ProcessPoolExecutor.submit()` — Linux fork() so
copy-on-write *should* keep dataset memory shared until a worker writes to it.
In practice we see ~300-500 MB RSS per worker, suggesting CoW is being broken
(perhaps by pandas operations that touch every row, or by feature-frame mutation
during precompute).

## 7. Our own brainstorm — please critique and improve

These are the team's current candidate fixes, ranked by guess at impact-vs-effort.
Tell us which are wrong, which are right, what we missed, and where to start.

### Quick wins (hours)

1. **Float32 numeric columns.** OHLC + features stored as float64 by default.
   Casting to float32 on load halves the numeric-array memory immediately.
   Loss of precision is irrelevant for trading sweeps. *Worry: does pandas
   silently up-cast back to float64 in any operation we use? Need audit.*

2. **`maxtasksperchild` on the ProcessPoolExecutor.** `concurrent.futures` doesn't
   expose this directly but `multiprocessing.Pool` does. Switching to a
   `multiprocessing.Pool(maxtasksperchild=200)` recycles workers periodically,
   forcing Python heap reset. Should eliminate within-family creep at minimal cost.

3. **Sequential families (no overlap).** Tear down the family's PoolExecutor at
   end of sweep + refinement, before starting next family's pool. Ensures peak
   concurrency = workers-of-one-pool, not two pools. Throughput loss ~20-30%
   but eliminates the headline peak.

### Real fixes (days)

4. **Shared-memory OHLC + feature frames** via `multiprocessing.shared_memory`
   (Python 3.8+). Convert the dataset DataFrame's columns to numpy arrays
   backed by `SharedMemory` once at engine start, pass workers handles instead
   of pickled copies. Estimated savings on 5m: 80 workers × ~80 MB per copy =
   6 GB on g9, more on the bigger boxes.

5. **Resume logic.** Check for existing `{family}_filter_combination_sweep_results.csv`
   on startup; if present and well-formed (row count matches expected n_combos),
   skip that family's sweep. Same for refinement. Reduces blast radius of any
   restart from "lose everything" to "lose the in-flight family". Doesn't reduce
   peak RAM but turns "kill + restart with smaller workers" into a viable strategy.

6. **Adaptive worker count per family.** Probe RSS of recent workers at family
   boundaries; if RSS × max_workers > RAM × 0.7, lower max_workers for the next
   family. Conservative when needed, aggressive when not.

### Architectural (weeks)

7. **Refactor feature_builder to lazy / on-demand per family.** Currently
   precomputes everything once and ships full frame to workers. If each family
   only needed its own slice, total memory drops + simpler.

8. **Replace pandas with polars** for the OHLC + feature frame. Polars is
   columnar Arrow with zero-copy semantics and aggressive memory reuse.
   ~2-5x memory reduction reported in similar workloads. Big refactor.

### Last resort

9. **Move 5m work off g9 entirely.** g9's 31 GB just isn't enough for the 5m
   feature footprint. Restrict 5m sweeps to c240/r630/gen8 (62+ GB hosts);
   give g9 the 15m+ work. This is a config split — no engine change. Loses
   one host's worth of 5m parallelism but stops the offline cycles cold.

## 7b. Bonus — ideas that buy *both* speed and RAM

The list above is RAM-focused. These are ideas that should win on both axes
simultaneously — and several of them dwarf the RAM-only fixes by giving
order-of-magnitude speedups while also shrinking the working set.

### Tier S — likely the biggest leverage of any idea in this doc

10. **Per-filter mask cache + boolean combo composition.** Right now the sweep
    appears to evaluate each filter combo by re-running every filter's `mask()`
    on the data. With ~10 filters per family and C(10,3..6) ≈ 800 combos, that's
    ~800× redundant filter work. Instead: precompute each filter's `mask(data)`
    **once** into a `dict[FilterClass, np.ndarray[bool]]` (10 arrays × ~10 MB
    each at 1-byte bool, or ~1.25 MB each bit-packed). Every combo becomes a
    single `np.logical_and.reduce([masks[f] for f in combo])`. Estimated
    speedup on the sweep stage: **10-50x**, plus it eliminates the per-worker
    filter-state memory footprint because workers just AND pre-built arrays.
    Effort: 1-2 days. Risk: modest — needs each filter to be confirmed pure
    (no parameter that varies per combo within sweep).

11. **Bit-packed masks (`np.packbits` / `bitarray`).** A 5m dataset over 18 years
    is ~1.9M bars. Bool array = 1.9 MB; bit-packed = 240 KB. With 10 filters
    cached per family that's 12 MB → 2.4 MB. Bitwise AND on packed arrays is
    nearly free (single SIMD instruction per 64 bars). Combine with idea 10
    for the cleanest implementation.

12. **Trade-list memoisation by signal-mask hash.** Many filter combos produce
    *identical* signal masks (subsumption: filter A makes filter B redundant in
    that combo). Hash the final boolean mask before running the trade
    simulation; if seen before, look up the cached PnL instead of re-simulating.
    On ES+5m we'd expect 20-40% mask-collision rate, hence 20-40% sweep speedup
    free. Effort: hours. Risk: zero — pure caching.

### Tier A — substantial, well-bounded wins

13. **Numba `@njit` on the sweep inner loop.** Once masks are pre-cached, the
    per-combo loop becomes: AND masks → simulate trades → compute metrics. The
    last two are still Python+numpy. Wrapping the inner kernel with `@njit`
    typically gives 5-10x more on top of the numpy speedup. `vectorized_trades.py`
    is already numpy-only, so the JIT path should be straightforward.

14. **Persistent feature cache as Parquet.** `feature_builder` currently runs at
    every engine startup. Cache its output to
    `Outputs/<dataset>/.feature_cache.parquet` keyed on `(dataset_path,
    feature_set_version)`. Skips minutes of work on every restart, supports
    fast iteration during dev, and reduces parent-process peak memory because
    we never hold both raw OHLC and computed features simultaneously. Effort:
    half a day.

15. **Bayesian / Optuna refinement instead of brute-force grid.** Current
    refinement is a 4×4×4×4 = 256-point grid per candidate. Optuna can find
    the same optimum in 30-50 trials with proper TPE search. **5x speedup
    on the refinement phase**, which is the heaviest stage memory-wise (it
    touches the full feature matrix repeatedly). Effort: 1 day. Already on
    the wishlist (`CLAUDE.md` known-issues list).

16. **Aggressive early-stopping in refinement.** Track the running PnL
    distribution within a refinement grid. If the first 25% of points are all
    below the leaderboard `min_oos_pf` threshold, abort the rest. Combined
    with idea 15 if both ship.

### Tier B — useful, but smaller or more contextual

17. **NUMA pinning on multi-socket hosts** (`taskset` / `numactl`). r630 + c240
    are dual-socket. Without pinning, half the worker memory accesses traverse
    the QPI link (~2x latency vs same-socket). A simple `numactl --cpunodebind=N
    --membind=N` per worker pool half eliminates this. Doesn't reduce total RAM
    but materially improves access bandwidth → ~10-15% wall-clock improvement.

18. **`gc.disable()` during sweep, explicit `gc.collect()` at family boundaries.**
    Python's GC pauses accumulate during long-running compute. Disabling it
    during the inner loop and forcing collection at clean boundaries reduces
    pause time and gives a more deterministic memory profile. Effort: 30 min.

19. **Streaming OHLC for sweep phase.** Sweep evaluates filter combos
    bar-by-bar; refinement needs random-access to bar history. If we stream
    OHLC in 100k-bar chunks for sweep only, peak memory drops without
    affecting refinement. Effort: medium — needs filter masks to be
    chunk-composable (most are; lookback-window filters need overlap).

20. **Reduce IS/OOS history depth.** 18 years of futures data is great for
    statistical confidence but a 5m dataset over 10 years is still ~1M bars
    and might give the same conclusions at half the memory. Worth A/B testing
    on one dataset to see if the leaderboard rankings change.

21. **Polars (or DuckDB) for OHLC + features.** Mentioned in tier "Real fixes"
    above. Polars is columnar Arrow-backed with zero-copy semantics, often
    2-5x less memory than pandas for the same data. Big refactor (every
    feature_builder + filter touches the frame).

22. **Distributed *intra-dataset* sweep.** Currently `run_cluster_sweep.py`
    distributes whole datasets to hosts. For 5m specifically — where one
    dataset is the bottleneck — split a single dataset's **families** across
    hosts. ES 5m on c240, NQ 5m on r630, etc., one family per host at a time.
    Per-host RAM peak drops because each runs only one family.

23. **Disable hyperthreading on g9.** g9 reports 48 threads but that's likely
    24 cores × 2 HT. With swap-thrash already a problem, HT context switching
    makes it worse. Boot with `nosmt` and run 24 workers — fewer but each
    fully dedicated. Often *faster* under memory pressure than full HT.



A ranked list of which 2-3 of the above (or your own ideas not in our list)
would give the biggest RAM reduction *while keeping ~80 worker parallelism*.
For each pick:

- One-paragraph design sketch
- Key API / library calls or code patterns
- Risks / gotchas
- A rough effort estimate (hours / days / weeks)

If we got the diagnosis wrong (e.g. it's not actually CoW breakage), tell us
how to verify the actual cause first.

---

Last updated: 2026-05-04 — Session 95

---

## Round 3 — Synthesis after Gemini + ChatGPT consultations

This section captures the operator's decisions after reading Gemini's divergent
take and ChatGPT's implementation-ready prompt for the filter-mask cache. It is
the canonical "what we're shipping next" section — supersedes any earlier
single-LLM recommendation.

### Headline calls

1. **Direct trade emission from the engine is the strategic bet.** Not because
   it's the biggest speedup (it isn't — it's not a speedup at all), but because
   it unblocks every cost-aware downstream piece. Cost-aware MC stops silently
   falling back to block-bootstrap. Post-ultimate gates start having teeth.
   Real The5ers swap data flows through. This is the paradigm-shift change.
2. **Filter-mask cache is the engineering tax cut.** Real speedup, but
   Amdahl-bounded by whatever fraction of sweep time is actually filter
   evaluation. **Profile before implementing** — 30 minutes of `cProfile` on
   one family's sweep tells us if filter eval is 80% (5× speedup max) or 30%
   (1.4× speedup max). We don't know yet. Don't oversell internally as
   "10-50×" until profiling confirms.
3. **Both ship in parallel.** Different files, different concerns, different
   risks. Track 1 = engine emission (master_strategy_engine.py post-promotion
   hook). Track 2 = `FilterMaskCache` per ChatGPT's API, plus mandatory purity
   audit of `modules/filters.py` first.

### Where Gemini won the divergence (anti-convergence rule paid off)

- **Q11 direct emission > rebuild path**: Gemini's bolder call is right.
  Vectorised engine has trade arrays in numpy at promotion-gate time; emit only
  for the ~20 promoted candidates per family. Rebuild path becomes deletable.
- **Q16 walk-forward at family leaderboard, not post-ultimate**: ChatGPT's
  post-ultimate placement is convergent and wrong. WF is an OOS test — late OOS
  is no test. Move it to Phase 1e (`_passes_final_leaderboard_gate`).
  Pragmatic compromise: light WF (single split with t-stat) at family stage,
  full rolling WF at post-ultimate.
- **Q14 fix costs > daily quotas**: Gemini's logic is sound — fix swaps, daily
  dominance dies organically. But **conditional on Q11**: cost-aware MC needs
  `strategy_trades.csv` to function. Order: emission → real costs → re-run →
  *then* decide on quotas. No quotas pre-emptively.

### Where Gemini's bolder calls need refinement before implementing

- **Q9 pure greedy frontier** has local-optima pathology with 289 candidates.
  Right answer is **beam-search greedy** (top-K=5 partial portfolios at each
  step) or greedy with backtracking. Pure greedy can miss globally better
  5-strategy portfolios that share a diversifier.
- **Q10 co-LPM2** is better than stress-window but has its own pathology —
  it treats `-0.1%/-0.1%` pairings the same as `-5%/-5%`. Formal fix:
  **lower-tail dependence coefficient** (λ from copula theory). Pragmatic
  fallback: co-LPM2 with a left-tail floor so trivial losses don't dilute.
- **Q12 drop the cap entirely** ignores combinatorics: C(289,8) = 10^15.
  Right move is **drop the cap on the input pool but cluster-prefilter
  before C(n,k)**. Layer A+B clustering → ~30 clusters → C(30,8) = 5M
  tractable → MC the best representative per accepted cluster-tuple.
- **Q13 analytical via covariance** needs **semi-covariance (LPM2-based)**,
  not standard covariance, because pass rate is a left-tail function not a
  variance function. Then MC the top-100 analytical winners.

### What ChatGPT got right that Gemini missed

- **Cache plain bool arrays first, not packed.** ChatGPT's reasoning is
  correct: packed bits complicate the hot path because trade simulation
  needs unpacked bools for indexing. Pack only if RAM is *still* the
  bottleneck after caching ships. The brief above incorrectly stacked
  these as "tier S together" — they should ship sequentially.
- **Purity audit is the gating prerequisite.** Whole optimisation depends
  on `filter.mask(df)` being pure. Audit must run first, list any impure
  filters, fix or exclude them from caching before code lands.
- **API retrofit shape is right**: `FilterMaskCache.combine(filter_objs)`
  keeps every existing filter class untouched. Critical for low-risk
  refactor of a parity-tested engine.

### Cache key recommendation (synthesised)

```python
cache_key = (
    dataset_id_hash,        # market+timeframe identifier
    len(data),              # cheaper than hashing the array
    filter_class_name,      # str
    frozenset(filter_params.items()),  # hashable param signature
)
```

Don't include a content-hash of the data array — too expensive on every
lookup, and dataset_id + length is already unique per loaded dataset.

### What neither model raised

The measured per-worker RSS is **300-500 MB on a ~100 MB dataset**. That
means **copy-on-write is being broken somewhere** — probably by pandas
operations that touch every memory page. Before committing to shared-memory
implementation work, run:

```
pmap -X $worker_pid | grep -i shared
```

on a live r630 worker. 30 seconds. Tells us whether CoW is partially
working (in which case shared-memory is a real win) or completely broken
(in which case we need to find what's mutating the dataset frame, fix
that, and shared-memory becomes secondary).

### Ship order

**Day 1**: profile one family's sweep with `cProfile` → confirms whether
filter eval is the bottleneck. CoW check via `pmap -X` → tells us shared
memory's actual potential.

**Days 2-3 (parallel tracks)**:
- Track 1: direct trade emission from `master_strategy_engine.py` post-promotion
  hook. Emit `strategy_trades.csv` alongside per-family CSVs. Remove
  `generate_returns.py` from the critical path. Add fail-closed check in
  `post_ultimate_gate.py` if trades are missing.
- Track 2: `FilterMaskCache` retrofit per ChatGPT's API. Purity audit first.
  Config flag for instant rollback. Parity tests against current behaviour.

**Day 4**: re-run `2026-05-01_10market_cfd_non5m` with full trade artifacts
and (if the5ers_mt5_specs.yaml is ready) real costs. This is when we
discover whether daily dominance survives real swaps — answers Q14, Q1, and
half of Q12 in one cluster batch.

**After**: deferred decisions (greedy vs beam-search vs budgets, co-LPM2
vs lower-tail dependence, candidate pool architecture, walk-forward
placement) become tractable because they have real cost data to calibrate
against. Don't make those calls in the dark.

