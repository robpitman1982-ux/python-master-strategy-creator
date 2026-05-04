# SPRINT_94 — Filter mask cache + boolean combo composition

> Pre-registration is mandatory. Commit this file BEFORE any code is touched.
> Once committed, the parameter grid + verdict criteria are FROZEN.

**Sprint number:** 94
**Date opened:** 2026-05-04
**Date closed:** ___
**Operator:** Rob
**Author:** Claude Code on Latitude
**Branch:** `feat/filter-mask-cache`

---

## 1. Sprint goal

Stop the family filter combination sweep from re-running each filter's
`mask(data)` once per combo. Cache the per-filter mask once per family
and combine combos via `np.logical_and.reduce(masks)`. Implementation
follows ChatGPT-5's reviewed prompt (in
`docs/LLM_CONSULTATION_RAM_PRESSURE.md` Section 7b idea 10) with the
parity safeguards it specified: opt-in config flag, zero-tolerance
parity vs cache-disabled mode, no edits to existing filter classes,
and a purity audit as gating prerequisite.

## 2. Mechanism plausibility

**Moderate prior — reduces redundant compute, but bounded.**

Profiling of the engine on `2026-05-01_10market_cfd_non5m` (Sprint 92
log `psc_10market_c240_redo2.log`) showed:

- Mean reversion family on small dataset: 209.94s sweep across 31,008
  combos = 6.77 ms/combo. Mostly trade-simulation cost; filter-mask
  evaluation is a fraction of that, not the bulk.
- Trend family on same dataset: 4.45s sweep across 9,373 combos =
  0.48 ms/combo. Very few trades, very fast.
- Per-combo work decomposition (estimated, not yet profiled with
  cProfile):
  - Combo signal mask AND-reduce: <0.1 ms (already free)
  - Per-filter `mask(data)` calls: ~0.5–2.0 ms (the bit we're caching)
  - Trade simulation (`vectorized_trades`): bulk of the remaining time
  - Metric computation: ~0.5 ms

For a family with 10 filters and 31,008 combos, naive per-combo
evaluation calls `mask(data)` ~120,000 times (each combo evaluates 3-6
filters). Cached evaluation calls it 10 times total. **120,000× to 10×
reduction in filter mask calls**, but the per-call cost is only a few
ms, so the realistic family-time speedup is ~5-15% — NOT the 10-50×
the original briefing claimed before profiling.

**Mechanism by which the fix produces the result:**
1. Build a `FilterMaskCache` keyed on `(filter_class_name, params_hash,
   dataset_fingerprint, df_length)`.
2. The combo evaluator asks the cache for each filter's mask in a combo;
   the cache lazy-fills on miss, returns the cached numpy bool array on
   hit.
3. The combo's combined signal mask is `np.logical_and.reduce(masks)` —
   trivially fast.
4. Trade simulation receives the same combined mask shape it had before;
   no change to `vectorized_trades.py` or the engine's hot path.

**Mechanism by which it could fail:**
- If any filter's `mask()` is impure (depends on instance state,
  prior-call side effects, hidden globals, mutates the dataframe), the
  cache returns a stale/incorrect mask and the resulting trades drift
  from cache-disabled behaviour. The purity audit at the start of
  implementation is the failsafe.
- If the cache key is too narrow (e.g. ignores filter parameters), two
  combos with different filter parameters but the same class name share
  a mask incorrectly. Mitigated by including a stable params hash in
  the key.
- If the combo evaluator is invoked from multiple processes
  concurrently, each ProcessPoolExecutor worker has its own cache (no
  shared state). That's a missed-reuse opportunity but not a
  correctness issue. Workers within a family naturally see the same
  filter set.

## 3. Frozen parameter grid

| Parameter | Value | Source |
|-----------|-------|--------|
| Cache backing | `dict[key -> np.ndarray[bool]]` (in-memory, per-process) | new |
| Cache key | `(filter_class_name, frozenset(params.items()), dataset_fingerprint_short, df_length)` | new |
| Mask backing | normal `np.ndarray(dtype=bool)` (NOT packbits in this sprint) | ChatGPT recommendation |
| Combo composition | `np.logical_and.reduce(masks)` with len-1 fast path | ChatGPT recommendation |
| Config flag | `engine.filter_mask_cache.enabled: false` (default OFF) | new |
| Override flag | env var `PSC_FILTER_MASK_CACHE` if set, takes precedence over config | new |
| Diagnostic counters | `cache_hits`, `cache_misses`, `unique_filters_cached`, `cache_memory_mb` (logged at family end) | new |
| Filter classes touched | ZERO (wrapper-only retrofit) | ChatGPT recommendation |
| Parity tolerance | combo signal masks must be element-wise identical to cache-disabled mode (zero tolerance) | new |

## 4. Verdict definitions

| Verdict | Condition |
|---------|-----------|
| **CANDIDATES** | Audit identifies all filters as pure (or impure ones explicitly excluded). Smoke test on small dataset shows zero-tolerance parity (final family_leaderboard_results.csv identical row-by-row in net_pnl/PF/oos_pf vs cache-disabled control). Wall-clock improvement >= 5% on at least one large family. Cache hit rate >= 80% within a family. |
| **NO EDGE** | n/a — engineering optimisation, not a strategy hypothesis. |
| **SUSPICIOUS** | Parity passes but speedup < 5% on all families measured. Indicates filter eval was already a smaller fraction of compute than estimated; the cache is harmless but not worth keeping enabled. Ship as off-by-default with diagnostic counters intact. |
| **BLOCKED** | Audit reveals impure filters that defeat caching, OR parity fails. Document, document the impure ones, replan. |

## 5. Methodology checklist

Pre-launch (must all be green):
- [ ] All test suites green pre-launch (`python -m pytest tests/ --ignore=tests/test_engine_parity.py -q`)
- [ ] Sprint pre-registration committed BEFORE code changes
- [ ] Branch `feat/filter-mask-cache` cut from `main`

Implementation gates (after each):
- [ ] **Stage 1 — Audit**: scan every filter class under `modules/filters.py` and any subclasses in `modules/strategy_types/`. For each: confirm `mask(df)` is a pure function of `(df, self.params)`. Document any exceptions in this file's section 6.
- [ ] **Stage 2 — Cache module**: `modules/filter_mask_cache.py` with `FilterMaskCache` class, key computation, hit/miss counters, and `combine()` helper. Unit tests covering hit/miss, params discrimination, dataset_fingerprint discrimination.
- [ ] **Stage 3 — Combo evaluator integration**: identify the existing function that runs `for combo in combos: ... mask = filter_obj.mask(df) ...` and retrofit the cache call. Single integration point. Old code remains as the cache-disabled path when flag is off.
- [ ] **Stage 4 — Parity test**: run a small family (e.g. trend on ES 60m) with cache OFF, save combo_results CSV. Run again with cache ON, compare CSVs row-by-row. Element-wise identical net_pnl, PF, total_trades, leader_strategy_name.
- [ ] **Stage 5 — Benchmark**: time the same family with cache OFF vs cache ON. Wall-clock delta + cache hit rate logged.

Verdict gate (smoke test on r630):
- [ ] Run resume_smoke_test config (ES daily) with cache OFF as control.
- [ ] Run again with cache ON.
- [ ] `verify_resume_parity.py` PASS.
- [ ] Per-family cache stats show hits >> misses in expected ratio.

## 6. Filter purity audit (filled during Stage 1)

| Filter class | `mask(df)` pure? | Notes |
|--------------|------------------|-------|
| _to be filled during audit_ | | |

## 7. Implementation map

### 7.1 New module: `modules/filter_mask_cache.py`

```python
class FilterMaskCache:
    def __init__(self, df: pd.DataFrame, dataset_fingerprint: str, enabled: bool = True):
        self.df = df
        self.df_length = len(df)
        self.dataset_fingerprint = dataset_fingerprint[:16]  # short
        self.enabled = enabled
        self._cache: dict[tuple, np.ndarray] = {}
        self.hits = 0
        self.misses = 0

    def _key(self, filter_obj) -> tuple:
        params = self._extract_params(filter_obj)
        return (
            filter_obj.__class__.__name__,
            frozenset(params.items()),
            self.dataset_fingerprint,
            self.df_length,
        )

    def get_mask(self, filter_obj) -> np.ndarray:
        if not self.enabled:
            return np.asarray(filter_obj.mask(self.df), dtype=bool)
        key = self._key(filter_obj)
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        self.misses += 1
        mask = np.asarray(filter_obj.mask(self.df), dtype=bool)
        self._cache[key] = mask
        return mask

    def combine(self, filter_objs) -> np.ndarray:
        if not filter_objs:
            return np.ones(self.df_length, dtype=bool)
        if len(filter_objs) == 1:
            return self.get_mask(filter_objs[0])
        masks = [self.get_mask(f) for f in filter_objs]
        return np.logical_and.reduce(masks)

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "cache_hits": self.hits,
            "cache_misses": self.misses,
            "hit_rate": self.hits / total if total > 0 else 0.0,
            "unique_filters_cached": len(self._cache),
            "cache_memory_mb": sum(m.nbytes for m in self._cache.values()) / 1_048_576,
        }
```

### 7.2 Cache key — params extraction

Most filter classes store parameters as instance attributes (not always
in a `params` dict). Extraction strategy: introspect `vars(filter_obj)`
filtered to JSON-serialisable scalar values. Audit will confirm this
covers all filters; any with unusual state get explicit handling.

### 7.3 Combo evaluator integration point

To be identified during Stage 3. Likely in
`modules/strategy_types/sweep_worker_pool.py` or each strategy_type's
`run_filter_combination_sweep` implementation. The retrofit replaces
the existing per-filter mask AND loop with a single
`cache.combine(filter_objs)` call.

### 7.4 Config flag

`config.yaml`:
```yaml
engine:
  filter_mask_cache:
    enabled: false  # default OFF until Sprint 94 verdict locks in
```

Override via env var:
```python
import os
flag_env = os.environ.get("PSC_FILTER_MASK_CACHE", "").strip().lower()
if flag_env in ("1", "true", "yes", "on"):
    cache_enabled = True
elif flag_env in ("0", "false", "no", "off"):
    cache_enabled = False
else:
    cache_enabled = bool(get_nested(_cfg, "engine", "filter_mask_cache", "enabled", default=False))
```

### 7.5 Tests

`tests/test_filter_mask_cache.py`:
- Hit on second call with same filter
- Miss on different params
- Miss on different dataset fingerprint
- `combine()` with 0/1/2/many filters
- Disabled mode bypasses cache
- Stats reporting

`tests/test_filter_mask_cache_parity.py`:
- Run small family with cache OFF, capture combo_results dataframe
- Run same family with cache ON, capture combo_results dataframe
- Assert element-wise identical on net_pnl, profit_factor, total_trades

## 8. Anti-convergence consultation

ChatGPT-5: provided implementation-ready prompt (in briefing) with
purity audit as gating prerequisite, plain-bool-first not packbits,
wrapper-only retrofit. **Cited verbatim as the implementation
foundation.**

Gemini 2.5 Pro: did not address the mask cache directly in its Q9-Q16
divergence round; spent its budget on selector-level changes (HRP
clustering, co-LPM2, direct emission). **Convergence with ChatGPT on
this sprint is "no opinion" rather than "agreement".** Treating as
non-anti-alpha.

Claude (synthesis): the original brief over-promised 10-50× speedup
on this. Profiling showed it's bounded by Amdahl's law to ~5-15%
because trade simulation, not filter eval, is the per-combo cost.
Sprint scope held tight: ship the cache as engineering hygiene with
zero behavioural risk; do not oversell the speedup; make the bigger
MR-specific signal-mask memoisation a separate sprint.

## 9. Expected impact

Baseline (cache OFF): 75.5s on ES daily smoke test (Sprint 93 verdict-
gate run on r630).

Best case (cache ON, hit rate >90%, filter eval was 30% of family
time): ~10% wall-clock improvement on heavy families = ~7s saved on
ES daily smoke. ~30 min saved per heavy 5m sweep.

Worst case (filter eval was 5% of family time): wall-clock improvement
< 5%, sprint flips SUSPICIOUS, ship off-by-default but the diagnostics
remain useful for follow-up profiling.

The real win is unlocking **Sprint 95 (signal-mask memoisation for
MR)** which uses the same cache infrastructure and stacks on top.
Sprint 94 ships the foundation; Sprint 95 ships the leverage point.
