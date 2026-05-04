"""Unified sweep worker initialization for shared sweep pool.

All three base sweep families (trend, MR, breakout) use the same (data, cfg)
pair within a dataset. This module provides a single initializer that
populates all families' globals at once, so ONE pool can serve every family
sweep.

Sprint 98: switched from `concurrent.futures.ProcessPoolExecutor` to
`multiprocessing.Pool` with `maxtasksperchild` so worker processes recycle
periodically, preventing the per-worker private-dirty heap accumulation
that drove the 5m sweep RAM crisis (~190 MB private-dirty per worker
observed via pmap -X). The `RecyclingSweepPool` wrapper preserves the
existing executor API surface (`.map()`, `.shutdown()`) so callers don't
change.

Sprint 100: ``sweep_worker_init`` accepts either a pandas DataFrame
(legacy copy-on-fork path) or a :class:`ShmMeta` (shared-memory backing).
When a ShmMeta is passed, the worker attaches to the named segments and
hands the resulting zero-copy DataFrame to the per-family globals. The
attach handles are stashed at module level on each strategy_types module
to keep them alive for the worker's lifetime.
"""
from __future__ import annotations

import multiprocessing as mp
import os
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import pandas as pd

from modules.config_loader import get_nested, load_config
from modules.engine import EngineConfig
from modules.shared_memory_features import ShmMeta, attach_from_shm


def sweep_worker_init(data_or_meta: pd.DataFrame | ShmMeta, cfg: EngineConfig) -> None:
    """Initialise worker globals for ALL sweep families at once.

    Sprint 100: accepts either a DataFrame (copy-on-fork legacy path) or a
    :class:`ShmMeta` (shared-memory zero-copy path). For ShmMeta, attaches
    once and shares the same DataFrame view across all 3 family modules.
    """
    # Import lazily inside the worker to avoid circular imports at module level
    import modules.strategy_types.trend_strategy_type as trend_mod
    import modules.strategy_types.mean_reversion_strategy_type as mr_mod
    import modules.strategy_types.breakout_strategy_type as bo_mod

    if isinstance(data_or_meta, ShmMeta):
        df, handles = attach_from_shm(data_or_meta)
        # Stash handles on each module so they outlive this initializer call.
        # SharedMemory objects must remain referenced or the buffer gets
        # released and subsequent reads segfault.
        trend_mod._trend_shm_handles = handles
        mr_mod._mr_shm_handles = handles
        bo_mod._breakout_shm_handles = handles
        data = df
    else:
        data = data_or_meta

    trend_mod._trend_shared_data = data
    trend_mod._trend_shared_cfg = cfg

    mr_mod._mr_shared_data = data
    mr_mod._mr_shared_cfg = cfg

    bo_mod._breakout_shared_data = data
    bo_mod._breakout_shared_cfg = cfg


class RecyclingSweepPool:
    """Wrapper around `multiprocessing.Pool(maxtasksperchild=N)` that exposes
    the subset of the `ProcessPoolExecutor` API the engine uses (`map`,
    `shutdown`).

    Worker processes are recycled after `maxtasksperchild` tasks, dropping
    accumulated heap state. Empirically (pmap -X on a live r630 worker)
    this reduces per-worker RSS from ~360 MB back toward ~220 MB on the
    5m sweep workload.
    """

    def __init__(
        self,
        max_workers: int,
        maxtasksperchild: int = 200,
        initializer: Any = None,
        initargs: tuple = (),
    ) -> None:
        # Use fork on Linux to keep CoW behaviour for read-only data; spawn
        # would re-import the world per worker.
        try:
            ctx = mp.get_context("fork")
        except ValueError:
            ctx = mp.get_context()
        self._pool = ctx.Pool(
            processes=max_workers,
            maxtasksperchild=maxtasksperchild,
            initializer=initializer,
            initargs=initargs,
        )
        self._closed = False

    def map(self, fn, iterable):
        """ProcessPoolExecutor-compatible map(): order-preserving, blocking
        iterator. Backed by `multiprocessing.Pool.imap` (chunksize=1)."""
        if self._closed:
            raise RuntimeError("Pool is closed")
        # imap is order-preserving; chunksize=1 mirrors PPE.map's per-task
        # dispatch granularity.
        yield from self._pool.imap(fn, iterable, chunksize=1)

    def submit(self, fn, *args, **kwargs):
        """ProcessPoolExecutor-compatible submit(): returns an object with
        .result()/.done() that wraps an AsyncResult."""
        if self._closed:
            raise RuntimeError("Pool is closed")
        ar = self._pool.apply_async(fn, args=args, kwds=kwargs)
        return _AsyncResultFuture(ar)

    def shutdown(self, wait: bool = True) -> None:
        if self._closed:
            return
        self._closed = True
        if wait:
            self._pool.close()
            self._pool.join()
        else:
            self._pool.terminate()
            self._pool.join()


class _AsyncResultFuture:
    """Future-shim around `multiprocessing.AsyncResult`."""

    def __init__(self, ar) -> None:
        self._ar = ar

    def result(self, timeout=None):
        return self._ar.get(timeout=timeout)

    def done(self) -> bool:
        return self._ar.ready()

    def cancel(self) -> bool:  # pragma: no cover - mp.Pool can't cancel
        return False


_RECYCLING_ENABLED_CACHE: bool | None = None
_MAXTASKSPERCHILD_CACHE: int | None = None


def _is_recycling_enabled() -> bool:
    """Read the recycling-pool flag (cached). Env var `PSC_RECYCLING_POOL`
    overrides config (1/true/yes/on -> enabled; 0/false/no/off -> disabled).

    Sprint 99-bis: resolved once per process to avoid yaml-reload overhead.
    """
    global _RECYCLING_ENABLED_CACHE
    if _RECYCLING_ENABLED_CACHE is not None:
        return _RECYCLING_ENABLED_CACHE
    env = os.environ.get("PSC_RECYCLING_POOL", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        _RECYCLING_ENABLED_CACHE = True
        return True
    if env in ("0", "false", "no", "off"):
        _RECYCLING_ENABLED_CACHE = False
        return False
    try:
        cfg = load_config()
        _RECYCLING_ENABLED_CACHE = bool(
            get_nested(cfg, "pipeline", "recycling_pool", default=False)
        )
    except Exception:
        _RECYCLING_ENABLED_CACHE = False
    return _RECYCLING_ENABLED_CACHE


def _maxtasksperchild() -> int:
    """Cached read of the maxtasksperchild config value."""
    global _MAXTASKSPERCHILD_CACHE
    if _MAXTASKSPERCHILD_CACHE is not None:
        return _MAXTASKSPERCHILD_CACHE
    try:
        cfg = load_config()
        _MAXTASKSPERCHILD_CACHE = int(
            get_nested(cfg, "pipeline", "maxtasksperchild", default=200)
        )
    except Exception:
        _MAXTASKSPERCHILD_CACHE = 200
    return _MAXTASKSPERCHILD_CACHE


def reset_pool_flag_cache() -> None:
    """Force re-evaluation on next call (test helper)."""
    global _RECYCLING_ENABLED_CACHE, _MAXTASKSPERCHILD_CACHE
    _RECYCLING_ENABLED_CACHE = None
    _MAXTASKSPERCHILD_CACHE = None


def create_shared_sweep_pool(
    data: pd.DataFrame | ShmMeta,
    cfg: EngineConfig,
    max_workers: int,
):
    """Create a sweep pool initialised for all sweep families.

    Returns a `RecyclingSweepPool` (when `pipeline.recycling_pool: true`) or
    a `ProcessPoolExecutor` (default, backward-compatible). Both expose the
    same `.map()` and `.shutdown()` surface used by the family workers.

    Sprint 100: ``data`` may be a DataFrame (legacy copy-on-fork) or a
    :class:`ShmMeta` (zero-copy shared-memory backing).
    """
    if _is_recycling_enabled():
        return RecyclingSweepPool(
            max_workers=max_workers,
            maxtasksperchild=_maxtasksperchild(),
            initializer=sweep_worker_init,
            initargs=(data, cfg),
        )
    return ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=sweep_worker_init,
        initargs=(data, cfg),
    )
