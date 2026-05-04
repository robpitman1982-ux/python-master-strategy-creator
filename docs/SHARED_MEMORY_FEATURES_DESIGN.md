# Shared-Memory Feature DataFrame — Design

**Status**: Design only. Not yet implemented.
**Purpose**: Eliminate per-worker copy of the precomputed features DataFrame. Workers read from a single OS-level shared memory segment instead of holding 800 MB-1.2 GB private copies each.
**Expected savings**: r630 worker RSS 793 MB → ~250 MB. Safe to run 70-80 workers vs current 40. Per-market 5m wall-time projected 30-40% faster on r630.

## Why this matters

Sprint 98 calibrated worker counts conservatively (r630=40, gen8=36, g9=24) because the precomputed features DataFrame (1.4M rows × 21 numeric columns ≈ 235 MB raw + pandas overhead) gets copied into each worker on fork. On the 5m datasets, even with `copy_data=False` and the `recycling_pool` flag, average per-worker RSS climbs to ~800 MB on r630 and ~1.24 GB on gen8 — both hosts hit swap at our existing worker caps.

CPU is not the bottleneck. RAM is. The 5m sweeps would saturate 80 cores on r630 if RAM allowed.

## Approach: `multiprocessing.shared_memory` (stdlib, no new deps)

Python 3.8+'s `shared_memory.SharedMemory` gives us named POSIX shared memory segments backed by `/dev/shm`. Each numpy column gets one segment. Workers attach by name, reconstruct numpy views, and assemble a zero-copy DataFrame.

## Architecture

```
PARENT (master_strategy_engine.py)
├── Load CSV → raw_data (1.4M rows)
├── add_precomputed_features() → precomputed_data (1.4M × 21 numeric cols)
├── materialise_to_shm(precomputed_data, run_id):
│   ├── For each numeric column → SharedMemory segment "psc_<run_id>_<col>"
│   ├── DatetimeIndex.asi8 → SharedMemory "psc_<run_id>_idx"
│   └── Returns shm_meta = {col_name: (shm_name, dtype_str, shape)}
├── Pass shm_meta (small dict, ~2 KB pickled) to ProcessPoolExecutor
└── atexit.register(cleanup_shm)  # leak protection

WORKER (one per process)
├── _worker_init_shm(shm_meta):
│   ├── For each entry → SharedMemory.attach(shm_name)
│   ├── np.ndarray(shape, dtype=dtype, buffer=shm.buf)  # zero-copy view
│   └── Reassemble pd.DataFrame(cols, index=DatetimeIndex(idx_view), copy=False)
└── Set module-global _worker_data = df (replaces existing _mr_shared_data pattern)

CLEANUP
├── Normal: parent close()s + unlink()s each segment after dataset done
├── atexit: hooks unlink for crashes
└── Signal handlers (SIGTERM, SIGINT): cleanup before exit
```

## New module: `modules/shared_memory_features.py`

```python
from __future__ import annotations
import atexit, signal, uuid
from dataclasses import dataclass, field
from multiprocessing import shared_memory
from typing import Any
import numpy as np
import pandas as pd

@dataclass
class ShmMeta:
    """Metadata to reconstruct a DataFrame from named shared-memory segments."""
    columns: dict[str, tuple[str, str, tuple[int, ...]]]  # col -> (shm_name, dtype, shape)
    index_name: str
    index_dtype: str
    index_shape: tuple[int, ...]
    run_id: str


@dataclass
class ShmOwner:
    """Parent-side handle. Owns shm segments, cleans up on close()."""
    handles: list[shared_memory.SharedMemory] = field(default_factory=list)
    meta: ShmMeta | None = None
    _cleaned: bool = False

    def close(self) -> None:
        if self._cleaned:
            return
        for h in self.handles:
            try:
                h.close()
                h.unlink()
            except FileNotFoundError:
                pass
        self._cleaned = True


def materialise_to_shm(df: pd.DataFrame, run_id: str | None = None) -> ShmOwner:
    """Copy each numeric column + index into shared memory. Returns owning handle."""
    if run_id is None:
        run_id = uuid.uuid4().hex[:8]

    owner = ShmOwner()
    columns: dict[str, tuple[str, str, tuple[int, ...]]] = {}

    for col in df.columns:
        arr = np.ascontiguousarray(df[col].values)
        if not np.issubdtype(arr.dtype, np.number) and not np.issubdtype(arr.dtype, np.bool_):
            raise TypeError(
                f"Column {col!r} has dtype {arr.dtype} — only numeric/bool columns "
                "supported for shared-memory backing."
            )
        shm_name = f"psc_{run_id}_{col}"
        shm = shared_memory.SharedMemory(create=True, size=arr.nbytes, name=shm_name)
        np.ndarray(arr.shape, dtype=arr.dtype, buffer=shm.buf)[:] = arr[:]
        owner.handles.append(shm)
        columns[col] = (shm_name, str(arr.dtype), arr.shape)

    # Index as int64 (datetime64[ns] view)
    idx_arr = df.index.values
    if not np.issubdtype(idx_arr.dtype, np.datetime64):
        raise TypeError(f"Index dtype {idx_arr.dtype} not supported (expected datetime64).")
    idx_int = idx_arr.view(np.int64)
    idx_name = f"psc_{run_id}_idx"
    idx_shm = shared_memory.SharedMemory(create=True, size=idx_int.nbytes, name=idx_name)
    np.ndarray(idx_int.shape, dtype=np.int64, buffer=idx_shm.buf)[:] = idx_int[:]
    owner.handles.append(idx_shm)

    owner.meta = ShmMeta(
        columns=columns,
        index_name=idx_name,
        index_dtype="int64",
        index_shape=idx_int.shape,
        run_id=run_id,
    )

    # Crash safety: unlink on parent exit even if close() not called
    atexit.register(owner.close)
    return owner


def attach_from_shm(meta: ShmMeta) -> tuple[pd.DataFrame, list[shared_memory.SharedMemory]]:
    """Worker-side: reconstruct a zero-copy DataFrame view. Returns df + handles
    that the worker MUST keep alive for the DataFrame to remain valid."""
    handles: list[shared_memory.SharedMemory] = []
    cols: dict[str, np.ndarray] = {}

    for col, (shm_name, dtype, shape) in meta.columns.items():
        shm = shared_memory.SharedMemory(name=shm_name)
        handles.append(shm)
        cols[col] = np.ndarray(shape, dtype=np.dtype(dtype), buffer=shm.buf)

    idx_shm = shared_memory.SharedMemory(name=meta.index_name)
    handles.append(idx_shm)
    idx_int = np.ndarray(meta.index_shape, dtype=np.int64, buffer=idx_shm.buf)
    idx = pd.DatetimeIndex(idx_int.view("datetime64[ns]"))

    df = pd.DataFrame(cols, index=idx, copy=False)
    return df, handles
```

## Hooks into existing code

### `master_strategy_engine.py` (after line 1080)

```python
# Before:
precomputed_data = add_precomputed_features(...)

# After:
precomputed_data = add_precomputed_features(...)
shm_owner = None
if config.get("pipeline", {}).get("shared_memory_features", False):
    shm_owner = materialise_to_shm(precomputed_data, run_id=run_id)
    feature_shm_meta = shm_owner.meta
else:
    feature_shm_meta = None  # workers fall back to copy-on-fork

try:
    # ... existing family dispatch, but pass feature_shm_meta to workers
finally:
    if shm_owner is not None:
        shm_owner.close()
```

### Worker initializers (`mean_reversion_strategy_type.py:_mr_worker_init`, etc.)

```python
_mr_shared_data: pd.DataFrame | None = None
_mr_shm_handles: list = []  # keep alive

def _mr_worker_init(data_or_meta, cfg: EngineConfig) -> None:
    global _mr_shared_data, _mr_shm_handles, _mr_shared_cfg
    if isinstance(data_or_meta, ShmMeta):
        _mr_shared_data, _mr_shm_handles = attach_from_shm(data_or_meta)
    else:
        _mr_shared_data = data_or_meta  # legacy copy-on-fork path
    _mr_shared_cfg = cfg
```

Same pattern for trend, breakout, subtype workers.

### Config flag

`config.yaml` (and per-market configs):
```yaml
pipeline:
  shared_memory_features: true   # default false; opt-in
```

## Testing strategy

### `tests/test_shared_memory_features.py`

1. **Roundtrip equality** — write df → attach in subprocess → assert frame_equal
2. **Multiple attaches don't corrupt** — 3 workers attach simultaneously, all see identical bytes
3. **Cleanup unlinks segments** — owner.close() removes /dev/shm entries
4. **atexit fires on parent exit** — fork a parent that creates SHM then exits; verify /dev/shm is clean
5. **Worker reads numeric correctly** — write known values, read back via attach, verify
6. **Read-only enforcement** — attempt to write to attached buffer → either fail or never propagate to other workers (test the contract)
7. **String column rejection** — verify materialise raises TypeError on object dtype
8. **NaN preservation** — features have NaN in warm-up rows; verify they survive roundtrip

### Production smoke

1. ES 60m on r630 (small, fast) — verify behaviour identical to copy-on-fork path
2. Run engine parity tests with `shared_memory_features: true` — must still produce bit-identical results
3. NQ 5m on r630 with workers=70 (vs current 40) — measure RSS curve via `scripts/rss_sampler.sh`, verify no swap
4. A/B: NQ 5m at workers=40 with shm vs without shm — same wall-time? (lower per-worker RSS shouldn't affect throughput, just headroom)

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| **/dev/shm leaks** if parent crashes mid-run | atexit + SIGTERM/SIGINT handlers; manual sweep script `cleanup_orphan_shm.py` for emergencies |
| **Pandas consolidates columns into 2D blocks** | `pd.DataFrame(cols, index=idx, copy=False)` followed by `df._consolidate_inplace = lambda *a, **kw: None` (or just verify the data path doesn't hit consolidation) |
| **/dev/shm size limit** (default tmpfs ~50% RAM) | NQ 5m features = ~250 MB total, well under limit. Add a startup check: `df['close'].nbytes * len(df.columns) < shm_available()` |
| **Filter code mutates DataFrame** | Audit all filter `passes()` and `mask()` methods — they only read. Add a unit test that asserts feature columns are unchanged after sweep. |
| **Worker dies holding handles** | Multiprocessing.Pool catches and respawns. New worker re-attaches. Other workers unaffected (each has its own handle). |
| **macOS dev / cluster Linux drift** | SharedMemory has different naming conventions across OSes. Use the stdlib API which abstracts this. We only run on Linux in production. |
| **Existing `_mr_worker_init` signature change** | Keep legacy path working: detect `isinstance(arg, ShmMeta)` and dispatch. No-op for copy-on-fork callers. |

## Estimated effort

- Module + tests: ~3-4 hours
- Engine + worker init wiring: ~2 hours
- Smoke tests on cluster: ~1-2 hours (run a market, verify RSS curve)
- A/B + final validation: ~2 hours

**Total: ~1 working day** for a complete, tested rollout.

## Rollout plan

1. Implement module + tests, push behind `shared_memory_features: false` default
2. Smoke test on ES 60m (cheap dataset, fast turnaround)
3. Run engine parity tests with flag ON — must pass
4. A/B on a single 5m market: NQ 5m at workers=40, flag ON vs OFF — verify identical results, lower RSS
5. Push workers up: workers=70 with flag ON — measure throughput gain
6. Roll forward: enable flag in all 5m configs, leave 60m+ untouched (no real benefit at smaller datasets)

## Expected outcome

- r630 worker RSS: 793 MB → ~250 MB
- Headroom for ~70-80 workers (vs current 40)
- Per-market wall-time: probably 30-40% faster on r630 for big markets (CPU-bound base families finally saturate the box)
- gen8: similar gains, plus eliminates current swap pressure entirely
- g9: less benefit (already RAM-headroom OK), but consistent

## Trigger

Implement after the current overnight 5ers run finishes and parity sign-off is complete on all 10 markets. Sprint name in continuity with prior naming: `Sprint 100 — Shared-memory feature DataFrame`.
