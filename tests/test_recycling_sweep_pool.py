"""Tests for the RecyclingSweepPool wrapper - Sprint 98.

Verifies the wrapper preserves the ProcessPoolExecutor API surface used by
the engine (`map`, `submit`, `shutdown`) and that it exercises
maxtasksperchild correctly.

`fork` is unavailable on Windows, so skip the wrapper tests on win32.
"""

from __future__ import annotations

import os
import sys

import pytest

WINDOWS_SKIP = pytest.mark.skipif(
    sys.platform == "win32",
    reason="multiprocessing.get_context('fork') is unavailable on Windows",
)


def _square(x: int) -> int:
    return x * x


def _identity(x):
    return x


def _record_pid(_):
    return os.getpid()


def _init_set_global():
    import sys
    sys.modules["__main__"].__dict__["INIT_RAN"] = True


def _check_init(_):
    import sys
    return getattr(sys.modules["__main__"], "INIT_RAN", False)


# ---------------------------------------------------------------------------
# Flag handling tests run on every platform (no fork required)
# ---------------------------------------------------------------------------

def test_recycling_flag_env_truthy(monkeypatch):
    monkeypatch.setenv("PSC_RECYCLING_POOL", "1")
    from modules.strategy_types.sweep_worker_pool import (
        _is_recycling_enabled,
        reset_pool_flag_cache,
    )
    reset_pool_flag_cache()  # Sprint 99-bis: flag is cached after first call
    assert _is_recycling_enabled() is True


def test_recycling_flag_env_falsy(monkeypatch):
    monkeypatch.setenv("PSC_RECYCLING_POOL", "0")
    from modules.strategy_types.sweep_worker_pool import (
        _is_recycling_enabled,
        reset_pool_flag_cache,
    )
    reset_pool_flag_cache()
    assert _is_recycling_enabled() is False


def test_recycling_flag_default_off(monkeypatch):
    monkeypatch.delenv("PSC_RECYCLING_POOL", raising=False)
    from modules.strategy_types.sweep_worker_pool import (
        _is_recycling_enabled,
        reset_pool_flag_cache,
    )
    reset_pool_flag_cache()
    # Default config has recycling_pool: false.
    assert _is_recycling_enabled() is False


def test_create_shared_sweep_pool_default_returns_ppe(monkeypatch):
    """When recycling is OFF, the factory still returns a ProcessPoolExecutor
    so existing behaviour is unchanged."""
    monkeypatch.setenv("PSC_RECYCLING_POOL", "0")
    from concurrent.futures import ProcessPoolExecutor
    from modules.strategy_types.sweep_worker_pool import create_shared_sweep_pool
    import pandas as pd
    from modules.engine import EngineConfig
    pool = create_shared_sweep_pool(
        data=pd.DataFrame({"x": [1, 2, 3]}),
        cfg=EngineConfig(initial_capital=1.0, risk_per_trade=0.01),
        max_workers=2,
    )
    try:
        assert isinstance(pool, ProcessPoolExecutor)
    finally:
        pool.shutdown(wait=True)


# ---------------------------------------------------------------------------
# Wrapper API tests (require fork - Linux only)
# ---------------------------------------------------------------------------

@WINDOWS_SKIP
def test_recycling_pool_map_preserves_order():
    from modules.strategy_types.sweep_worker_pool import RecyclingSweepPool
    pool = RecyclingSweepPool(max_workers=2, maxtasksperchild=10)
    try:
        results = list(pool.map(_square, [1, 2, 3, 4, 5]))
        assert results == [1, 4, 9, 16, 25]
    finally:
        pool.shutdown(wait=True)


@WINDOWS_SKIP
def test_recycling_pool_submit_returns_future_like():
    from modules.strategy_types.sweep_worker_pool import RecyclingSweepPool
    pool = RecyclingSweepPool(max_workers=2, maxtasksperchild=10)
    try:
        future = pool.submit(_square, 7)
        assert future.result(timeout=10) == 49
        assert future.done() is True
        assert future.cancel() is False  # multiprocessing.Pool can't cancel
    finally:
        pool.shutdown(wait=True)


@WINDOWS_SKIP
def test_recycling_pool_shutdown_idempotent():
    from modules.strategy_types.sweep_worker_pool import RecyclingSweepPool
    pool = RecyclingSweepPool(max_workers=2, maxtasksperchild=10)
    pool.shutdown(wait=True)
    pool.shutdown(wait=True)  # second call no-op


@WINDOWS_SKIP
def test_recycling_pool_submit_after_shutdown_raises():
    from modules.strategy_types.sweep_worker_pool import RecyclingSweepPool
    pool = RecyclingSweepPool(max_workers=2, maxtasksperchild=10)
    pool.shutdown(wait=True)
    with pytest.raises(RuntimeError):
        pool.submit(_square, 1)


@WINDOWS_SKIP
def test_recycling_pool_workers_actually_recycle():
    """maxtasksperchild=2 means workers must restart after every 2 tasks.
    Send 8 tasks to a 2-worker pool; expect more than 2 unique PIDs
    (workers got recycled at least once)."""
    from modules.strategy_types.sweep_worker_pool import RecyclingSweepPool
    pool = RecyclingSweepPool(max_workers=2, maxtasksperchild=2)
    try:
        pids = list(pool.map(_record_pid, list(range(8))))
        unique_pids = set(pids)
        # 2 workers × at least 2 lifetimes (each handles 2 tasks then exits) = 4+ unique PIDs
        assert len(unique_pids) >= 3, (
            f"expected workers to recycle (3+ unique PIDs), got {len(unique_pids)}: {pids}"
        )
    finally:
        pool.shutdown(wait=True)


@WINDOWS_SKIP
def test_recycling_pool_uses_initializer():
    """Initializer must run in each worker so the worker has its globals set."""
    from modules.strategy_types.sweep_worker_pool import RecyclingSweepPool
    pool = RecyclingSweepPool(
        max_workers=2,
        maxtasksperchild=10,
        initializer=_init_set_global,
    )
    try:
        results = list(pool.map(_check_init, [1, 2, 3]))
        assert all(results), f"initializer did not run in all workers: {results}"
    finally:
        pool.shutdown(wait=True)
