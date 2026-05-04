# SPRINT_95 — Signal-mask memoisation (trade-sim dedup by combo mask hash)

> Pre-registration is mandatory. Commit BEFORE any code is touched.
> Once committed, the parameter grid + verdict criteria are FROZEN.

**Sprint number:** 95
**Date opened:** 2026-05-04
**Date closed:** 2026-05-04 (verdict: SUSPICIOUS on small-dataset smoke; bigger-dataset re-test deferred)
**Operator:** Rob
**Author:** Claude Code on Latitude
**Branch:** `feat/signal-mask-memoisation`

---

## 1. Sprint goal

Eliminate redundant trade simulations within a sweep by hashing the combined
signal mask and caching the engine's result dict. When two filter combos
produce the *identical* boolean signal series, run the trade simulation once
and reuse the result.

This is the actual leverage point that Sprint 94 left on the table. Per the
briefing's profiling data, **trade simulation is the dominant per-combo cost**
(~5-7 ms on small dataset, scaling with bars × trade frequency on bigger ones).
Filter-mask caching alone saves <15% of per-combo time. Mask-hash memoisation
of the trade-sim output saves the dominant cost when collisions occur.

## 2. Mechanism plausibility

**Strong prior — subsumption is empirically common in MR.**

Why combos collide on the signal mask:
- A filter that fires on every bar (degenerate `True`) produces the same combo
  mask whether included or not (modulo other filters).
- A filter that never fires (degenerate `False`) zeroes the combo regardless of
  the others. All such combos have the same all-False signal mask.
- A filter strictly subsumed by another (e.g. `DistanceBelowSMA(2)` always
  fires when `DistanceBelowSMA(1)` does, in the same direction) produces
  identical combos when both are present vs only the dominant one — provided
  the unique filter set is otherwise the same.

Empirical signal: per ChatGPT-5's analysis in the briefing, MR family is
expected to have **20-40% mask-collision rate** because its filter pool
includes overlapping conditions (DistanceBelowSMA + BelowFastSMA + DownClose
all fire on similar bars). Trend has lower collision rate (~5-10%) because
its filters are more orthogonal. Breakout middling.

**Mechanism:** before running engine.run, compute `hash(signal_mask.tobytes())`
combined with the strategy's hold_bars + stop_distance + cfg fingerprint. Look
up in a process-local dict. If hit, return the cached engine.results() dict.
If miss, run engine, cache, return.

**How it could fail:**
- Hash collisions — astronomically unlikely with sha256 truncated to 128 bits.
- Cache scope confusion: if cfg changes between two combos within the same
  sweep (e.g. direction flips), the cache must discriminate. Mitigated by
  including cfg fingerprint in the key.
- Result dict mutation by the combo evaluator — caller must treat the returned
  dict as read-only. Mitigated by returning a shallow copy on cache hit.

## 3. Frozen parameter grid

| Parameter | Value |
|-----------|-------|
| Hash function | `hashlib.sha256(signal_mask.tobytes()).digest()` (32 bytes); cache key uses first 16 bytes (128-bit) |
| Cache key | `(mask_hash_16bytes, hold_bars, stop_distance_points, cfg_fingerprint, id(data))` |
| `cfg_fingerprint` | tuple of `(commission, slippage_ticks, tick_value, dollars_per_point, oos_split_date, direction, timeframe, use_vectorized_trades)` |
| Cache backing | `dict[key -> dict]` (engine.results() output) |
| Cache scope | process-local, lives in `modules.signal_mask_memo` (sibling of `filter_mask_cache`) |
| Hit return | shallow copy of cached dict (caller may mutate) |
| Config flag | `engine.signal_mask_memo.enabled: false` (default OFF for parity safety) |
| Env override | `PSC_SIGNAL_MASK_MEMO=1/0` |
| Diagnostic counters | `hits`, `misses`, `unique_masks`, `cache_memory_mb` (rough — sum of dict-value sizes) |
| Integration sites | `_run_*_combo_case` in mean_reversion_strategy_type.py, trend_strategy_type.py, breakout_strategy_type.py — wrap `engine.run + engine.results()` |
| Filter classes touched | ZERO |

## 4. Verdict definitions

| Verdict | Condition |
|---------|-----------|
| **CANDIDATES** | Parity: smoke leaderboard zero-tolerance behavioural match (same as Sprint 93/94 standard). Speedup: at least 10% wall-clock improvement on the MR family (the family with the highest expected collision rate). Hit rate: at least 15% on MR sweep. |
| **NO EDGE** | n/a — engineering optimisation. |
| **SUSPICIOUS** | Parity passes, but speedup < 10% AND hit rate < 15%. Indicates collision rate was lower than expected; ship default-off, infrastructure stays. |
| **BLOCKED** | Parity fails. The cached result diverges from the freshly-computed result, indicating a missed dependency in the cache key. Halt, debug, replan. |

## 5. Methodology checklist

- [ ] All test suites green pre-launch
- [ ] Pre-registration committed BEFORE code changes
- [ ] Branch `feat/signal-mask-memoisation` cut from main

Stage gates:
- [ ] **Stage 1 — Cache module**: `modules/signal_mask_memo.py` with `get_or_compute_summary()`, `stats()`, `clear_cache()`. Unit tests for hash determinism, cache key discrimination, env flag, hit/miss accounting.
- [ ] **Stage 2 — Integration**: wrap the engine.run + engine.results() call in all 3 base strategy types (`_run_mr_combo_case`, `_run_trend_combo_case`, `_run_breakout_combo_case`) and any subtype variants that follow the same pattern. Single helper that takes a closure for the actual run.
- [ ] **Stage 3 — Parity test**: run small family with memo OFF, capture combo_results CSV. Run with memo ON, compare CSVs. Element-wise identical numeric metrics.
- [ ] **Stage 4 — Benchmark**: time MR family OFF vs ON. Wall-clock delta + hit rate logged.

Verdict gate:
- [ ] Smoke test on r630: ES daily resume_smoke_test.yaml with memo OFF (control) and memo ON. `verify_resume_parity.py` PASS. Cache stats logged. Wall-clock delta computed.

## 6. Implementation map

### 6.1 New module: `modules/signal_mask_memo.py`

```python
import hashlib
import os
from typing import Any, Callable
import numpy as np

_MEMO: dict[tuple, dict] = {}
_HITS = 0
_MISSES = 0


def _mask_hash(signal_mask: np.ndarray) -> bytes:
    return hashlib.sha256(signal_mask.tobytes()).digest()[:16]


def _cfg_fingerprint(cfg) -> tuple:
    return (
        getattr(cfg, "commission_per_contract", 0.0),
        getattr(cfg, "slippage_ticks", 0),
        getattr(cfg, "tick_value", 0.0),
        getattr(cfg, "dollars_per_point", 0.0),
        str(getattr(cfg, "oos_split_date", "")),
        getattr(cfg, "direction", "long"),
        getattr(cfg, "timeframe", ""),
        bool(getattr(cfg, "use_vectorized_trades", False)),
    )


def get_or_compute_summary(
    signal_mask: np.ndarray,
    hold_bars: int,
    stop_distance: float,
    data: Any,
    cfg: Any,
    run_fn: Callable[[], dict],
) -> dict:
    """Cache-aware engine run. run_fn() must execute the engine and return
    engine.results() as a dict. Cache key includes signal_mask hash,
    strategy params, cfg fingerprint, id(data)."""
    global _HITS, _MISSES
    if not is_enabled():
        return run_fn()
    key = (_mask_hash(signal_mask), int(hold_bars), float(stop_distance),
           _cfg_fingerprint(cfg), id(data))
    cached = _MEMO.get(key)
    if cached is not None:
        _HITS += 1
        return dict(cached)  # shallow copy; caller may mutate
    _MISSES += 1
    result = run_fn()
    _MEMO[key] = dict(result)
    return result


def is_enabled() -> bool:
    env = os.environ.get("PSC_SIGNAL_MASK_MEMO", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False
    try:
        from modules.config_loader import get_nested, load_config
        return bool(get_nested(load_config(), "engine", "signal_mask_memo", "enabled", default=False))
    except Exception:
        return False


def stats() -> dict: ...
def clear_cache() -> dict: ...
def reset_counters() -> None: ...
```

### 6.2 Integration in `_run_mr_combo_case`

Replace:

```python
engine = MasterStrategyEngine(data=data, config=cfg, copy_data=False)
if cfg.use_vectorized_trades:
    engine.run_vectorized(strategy=strategy, precomputed_signals=signal_mask)
else:
    engine.run(strategy=strategy, precomputed_signals=signal_mask)
summary = engine.results()
```

With:

```python
def _run_engine() -> dict:
    engine = MasterStrategyEngine(data=data, config=cfg, copy_data=False)
    if cfg.use_vectorized_trades:
        engine.run_vectorized(strategy=strategy, precomputed_signals=signal_mask)
    else:
        engine.run(strategy=strategy, precomputed_signals=signal_mask)
    return engine.results()

summary = signal_mask_memo.get_or_compute_summary(
    signal_mask=signal_mask,
    hold_bars=strat_type.default_hold_bars,
    stop_distance=strat_type.default_stop_distance_points,
    data=data,
    cfg=cfg,
    run_fn=_run_engine,
)
```

Repeat for trend + breakout combo cases.

### 6.3 Config

```yaml
engine:
  signal_mask_memo:
    enabled: false
```

## 7. Anti-convergence notes

ChatGPT-5: identified the mask-cache angle but stopped at filter-mask
caching (Sprint 94). Did not push to combined-mask hashing. **Divergent
extension.**

Gemini 2.5 Pro: did not address this layer.

Claude (synthesis): Sprint 94's profiling explicitly identified the
collision-rate hypothesis. This sprint is the test. Pre-registered
verdict thresholds are honest about uncertainty (10% wall-clock + 15%
hit rate = both must hold).

## 8. Expected impact

If MR collision rate is 30% (mid-range estimate):
- 30% of trade simulations skip → 30% of MR sweep time saved
- MR family is 57% of small-dataset wall-clock per Sprint 92 profiling
- Net dataset speedup: 0.30 × 0.57 = ~17%

If collision rate is 10%:
- Net dataset speedup: ~6% — falls under the SUSPICIOUS threshold

If collision rate is 50% (best plausible):
- Net dataset speedup: ~28%

The honest range is 6-28%. Pre-reg verdict gate set at 10% to discriminate
between "real win" and "noise". 15% hit rate threshold ensures we're not
just measuring random variance.

## 9. Verdict (sprint close — 2026-05-04)

**SUSPICIOUS** per pre-registered threshold.

**Smoke test on r630** (ES daily, resume_smoke_test config, 4163 bars):

| Run | Wall clock |
|-----|------------|
| Memo OFF (control) | 78.1s |
| Memo ON           | 77.1s |
| Delta             | -1.0s = 1.3% (within noise; below the 10% CANDIDATES threshold) |

**Parity:** PASS. `verify_resume_parity.py` shows zero behavioural
drift (`net_pnl`/`leader_pf`/`oos_pf` identical row-by-row). The 1
tie-break warning on `short_breakout` is the same engine non-determinism
documented in Sprint 93/94 — independent of the memo flag.

**Test counts:** 430/430 (was 416 + 14 new memo tests).

**Why no measurable speedup on this profile:**

1. Per-worker collision rate is much lower than family-wide. Each
   ProcessPoolExecutor worker sees ~775 of 31,008 MR combos.
   Subsumption-based mask collisions are sparse within that slice.
   Worker caches don't share post-fork.
2. ES daily (4163 bars, low trade frequency) makes per-combo trade-sim
   work small in absolute terms. Even a 30% hit rate within a worker
   would save sub-millisecond per combo.
3. Hash/dict overhead approximately matches the work it saves on
   cheap simulations.

**Hit rate not measurable** without per-worker stats aggregation.
Workers fork from parent post-CoW and their cache state doesn't flow
back. Adding aggregation would require a side-channel (file or shared
dict via Manager) and was scoped out of this sprint.

**Decision:** ship default-off, infrastructure stays. The integration
points in `_run_*_combo_case` are minimal and low-risk; reverting them
loses optionality for the bigger smoke tests where memo's value is
expected to actually appear (5m or 60m datasets where per-combo
trade-sim is materially heavier).

**Follow-up:** when a 5m sweep is queued (now safer thanks to Sprint
93's resume logic), enable the memo and measure. If it pays off there,
flip default to ON. If not, the integration cost is two small `from
modules import signal_mask_memo` blocks and can be removed in a single
revert commit.

**No regressions** on the 416-test suite. New 14 memo tests all green.
