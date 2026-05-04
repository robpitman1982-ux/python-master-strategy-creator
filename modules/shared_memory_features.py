"""Shared-memory backing for the precomputed features DataFrame.

Sprint 100 — eliminate per-worker copies of the precomputed features DataFrame.
Each numeric column gets a named POSIX shared-memory segment via the stdlib
``multiprocessing.shared_memory`` API. Workers attach by name and reconstruct
zero-copy DataFrame views; the parent owns the segments and unlinks them on
teardown (or atexit on crash).

Design: docs/SHARED_MEMORY_FEATURES_DESIGN.md.

Expected savings on NQ 5m (1.4M rows × 21 cols):
    per-worker RSS 793 MB → ~250 MB on r630 (workers can grow 40 → 70-80)

Usage:
    # parent (master_strategy_engine.py)
    owner = materialise_to_shm(precomputed_data, run_id="...")
    try:
        # pass owner.meta to ProcessPoolExecutor initializer
        ...
    finally:
        owner.close()  # unlink all segments

    # worker initializer (e.g. _mr_worker_init)
    df, handles = attach_from_shm(meta)  # zero-copy
    # `handles` MUST be kept alive for the lifetime of `df`
"""
from __future__ import annotations

import atexit
import os
import uuid
from dataclasses import dataclass, field
from multiprocessing import shared_memory
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class ShmMeta:
    """Metadata to reconstruct a DataFrame from named shared-memory segments.

    Picklable, small (~few KB for the typical 21-column features set), safe to
    pass to ProcessPoolExecutor as part of an initializer arg tuple.
    """

    columns: dict[str, tuple[str, str, tuple[int, ...]]]
    """Mapping ``column_name -> (shm_name, dtype_str, shape)``."""

    index_name: str
    """Name of the SharedMemory segment holding the int64 view of the
    DatetimeIndex. The worker reconstructs the index via
    ``np.ndarray(...).view('datetime64[ns]')``.
    """

    index_dtype: str
    index_shape: tuple[int, ...]
    run_id: str


@dataclass
class ShmOwner:
    """Parent-side handle for a materialised set of shm segments.

    The parent MUST call :meth:`close` once the workers are done — otherwise
    the segments leak in ``/dev/shm`` until the OS reboots. ``close()`` is
    idempotent and is also wired to ``atexit`` for crash safety.
    """

    handles: list[shared_memory.SharedMemory] = field(default_factory=list)
    meta: ShmMeta | None = None
    _cleaned: bool = False

    def close(self) -> None:
        """Unlink all segments. Safe to call multiple times."""
        if self._cleaned:
            return
        for h in self.handles:
            # ``close`` releases this handle; ``unlink`` removes the segment
            # so other processes can't open it. Order: close → unlink.
            try:
                h.close()
            except Exception:
                pass
            try:
                h.unlink()
            except FileNotFoundError:
                pass
            except Exception:
                pass
        self._cleaned = True

    def __enter__(self) -> "ShmOwner":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def _segment_name(run_id: str, col: str) -> str:
    """Build a stable, predictable shm segment name.

    POSIX shm names are limited (NAME_MAX = 255 on Linux) and may not contain
    slashes. We compose ``psc_<run_id>_<col>`` and replace any disallowed
    characters with underscore. Column names in our project are simple
    identifiers so this is mostly defensive.
    """
    safe_col = "".join(c if c.isalnum() or c == "_" else "_" for c in col)
    name = f"psc_{run_id}_{safe_col}"
    # POSIX shm name limit on Linux is 255; macOS is stricter (~30) but we
    # don't run there in production.
    return name[:240]


def materialise_to_shm(df: pd.DataFrame, run_id: str | None = None) -> ShmOwner:
    """Copy each numeric column + the DatetimeIndex into shared memory.

    Args:
        df: Source DataFrame. All columns must be numeric or boolean. Index
            must be a DatetimeIndex.
        run_id: Optional namespace for the segment names. Defaults to a random
            8-character hex string. Use a stable run_id when you want to
            attach from a sibling process that wasn't forked by the materiser.

    Returns:
        :class:`ShmOwner`. The caller MUST eventually call ``close()`` on it
        (or use it as a context manager) to free the segments.

    Raises:
        TypeError: if any column has a non-numeric/bool dtype, or the index
            is not a DatetimeIndex.
    """
    if run_id is None:
        run_id = uuid.uuid4().hex[:8]

    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError(
            f"DataFrame index must be DatetimeIndex (got {type(df.index).__name__})"
        )

    owner = ShmOwner()
    columns: dict[str, tuple[str, str, tuple[int, ...]]] = {}

    try:
        for col in df.columns:
            arr = np.ascontiguousarray(df[col].values)
            if not (
                np.issubdtype(arr.dtype, np.number)
                or np.issubdtype(arr.dtype, np.bool_)
            ):
                raise TypeError(
                    f"Column {col!r} has dtype {arr.dtype} — only numeric "
                    "and bool columns are supported by the shared-memory "
                    "feature backing."
                )
            shm_name = _segment_name(run_id, str(col))
            shm = shared_memory.SharedMemory(
                create=True, size=max(arr.nbytes, 1), name=shm_name
            )
            np.ndarray(arr.shape, dtype=arr.dtype, buffer=shm.buf)[:] = arr[:]
            owner.handles.append(shm)
            columns[str(col)] = (shm_name, str(arr.dtype), tuple(arr.shape))

        # Index: store as int64 ns-since-epoch (the canonical datetime64[ns]
        # backing). Reconstruct via ``.view('datetime64[ns]')`` in the worker.
        idx_arr = df.index.values
        if not np.issubdtype(idx_arr.dtype, np.datetime64):
            raise TypeError(
                f"Index dtype {idx_arr.dtype} not supported (expected datetime64)."
            )
        idx_int = idx_arr.view(np.int64)
        idx_name = _segment_name(run_id, "_index_")
        idx_shm = shared_memory.SharedMemory(
            create=True, size=max(idx_int.nbytes, 1), name=idx_name
        )
        np.ndarray(idx_int.shape, dtype=np.int64, buffer=idx_shm.buf)[:] = idx_int[:]
        owner.handles.append(idx_shm)

        owner.meta = ShmMeta(
            columns=columns,
            index_name=idx_name,
            index_dtype="int64",
            index_shape=tuple(idx_int.shape),
            run_id=run_id,
        )
    except Exception:
        # If any column failed, unlink whatever we already created so we don't
        # leak segments on partial failure.
        owner.close()
        raise

    # Crash safety: even if the parent exits without calling close(), atexit
    # will try to clean up. Best-effort — won't help on SIGKILL.
    atexit.register(owner.close)
    return owner


def attach_from_shm(
    meta: ShmMeta,
) -> tuple[pd.DataFrame, list[shared_memory.SharedMemory]]:
    """Worker-side: reconstruct a zero-copy DataFrame view of the features.

    Args:
        meta: The :class:`ShmMeta` returned by :func:`materialise_to_shm` in
            the parent.

    Returns:
        A tuple of ``(dataframe, handles)``. The worker MUST keep a reference
        to ``handles`` for as long as it uses the DataFrame — when the
        ``SharedMemory`` objects are garbage-collected the underlying buffers
        become invalid and reads from the DataFrame will segfault.

    The DataFrame is read-only in spirit; mutating it would corrupt the data
    seen by other workers. We do not enforce read-only at the buffer level
    because numpy + multiprocessing.shared_memory don't expose that knob
    portably.
    """
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

    # copy=False is critical — we want zero-copy views into shared memory.
    # If pandas later consolidates these into a 2D block it'd defeat the
    # purpose; the test suite asserts the views remain backed by shm.
    df = pd.DataFrame(cols, index=idx, copy=False)
    return df, handles
