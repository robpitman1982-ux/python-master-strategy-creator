"""Tests for modules.shared_memory_features (Sprint 100)."""
from __future__ import annotations

import multiprocessing as mp
import sys

import numpy as np
import pandas as pd
import pytest

from modules.shared_memory_features import (
    ShmMeta,
    ShmOwner,
    attach_from_shm,
    materialise_to_shm,
)


def _make_synthetic_features(n_rows: int = 1000, seed: int = 7) -> pd.DataFrame:
    """Build a small features DataFrame matching the shape produced by
    add_precomputed_features (numeric columns, DatetimeIndex, NaN warm-up)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n_rows, freq="5min")
    close = 100.0 + np.cumsum(rng.normal(0, 0.5, size=n_rows))
    df = pd.DataFrame(
        {
            "open": close + rng.normal(0, 0.1, size=n_rows),
            "high": close + np.abs(rng.normal(0, 0.3, size=n_rows)),
            "low": close - np.abs(rng.normal(0, 0.3, size=n_rows)),
            "close": close,
            "sma_20": pd.Series(close).rolling(20).mean().values,  # has NaN warm-up
            "atr_14": pd.Series(close).rolling(14).std().values,   # has NaN warm-up
            "is_signal": (close > 100).astype(np.bool_),           # bool column
            "vol_pct": rng.uniform(0, 1, size=n_rows).astype(np.float32),  # float32 width
        },
        index=idx,
    )
    return df


def test_roundtrip_in_process_preserves_values_and_index():
    df = _make_synthetic_features()
    with materialise_to_shm(df, run_id="t_roundtrip") as owner:
        attached, handles = attach_from_shm(owner.meta)
        try:
            pd.testing.assert_frame_equal(attached, df, check_freq=False)
        finally:
            for h in handles:
                h.close()


def test_nan_values_preserved():
    df = _make_synthetic_features(n_rows=200)  # SMA_20 will have ~19 NaN warm-up
    assert df["sma_20"].isna().any(), "expected NaN warm-up rows in fixture"
    with materialise_to_shm(df, run_id="t_nan") as owner:
        attached, handles = attach_from_shm(owner.meta)
        try:
            assert attached["sma_20"].isna().sum() == df["sma_20"].isna().sum()
            # NaN positions match exactly
            assert (attached["sma_20"].isna() == df["sma_20"].isna()).all()
            # Non-NaN values match exactly
            mask = ~df["sma_20"].isna()
            np.testing.assert_array_equal(
                attached["sma_20"].values[mask], df["sma_20"].values[mask]
            )
        finally:
            for h in handles:
                h.close()


def test_dtype_widths_preserved():
    """float32 stays float32, bool stays bool — no silent upcasting."""
    df = _make_synthetic_features()
    with materialise_to_shm(df, run_id="t_dtype") as owner:
        attached, handles = attach_from_shm(owner.meta)
        try:
            assert attached["vol_pct"].dtype == np.float32
            assert attached["is_signal"].dtype == np.bool_
            assert attached["close"].dtype == np.float64
        finally:
            for h in handles:
                h.close()


def test_string_column_rejected():
    df = pd.DataFrame(
        {"close": [100.0, 101.0], "name": ["a", "b"]},
        index=pd.date_range("2020-01-01", periods=2, freq="5min"),
    )
    with pytest.raises(TypeError, match="dtype.*supported"):
        materialise_to_shm(df, run_id="t_string")


def test_non_datetime_index_rejected():
    df = pd.DataFrame({"close": [100.0, 101.0]}, index=[0, 1])
    with pytest.raises(TypeError, match="DatetimeIndex"):
        materialise_to_shm(df, run_id="t_idx")


def test_close_unlinks_segments():
    """After owner.close(), workers cannot attach by the segment names."""
    from multiprocessing import shared_memory as shm_mod

    df = _make_synthetic_features(n_rows=100)
    owner = materialise_to_shm(df, run_id="t_unlink")
    meta = owner.meta
    owner.close()

    # Picking any segment should fail to attach
    sample_name = next(iter(meta.columns.values()))[0]
    with pytest.raises(FileNotFoundError):
        shm_mod.SharedMemory(name=sample_name)


def test_close_is_idempotent():
    df = _make_synthetic_features(n_rows=50)
    owner = materialise_to_shm(df, run_id="t_idem")
    owner.close()
    # Second close must not raise
    owner.close()


def _attach_in_subprocess(
    meta: ShmMeta, queue: "mp.Queue[Any]"
) -> None:  # pragma: no cover - runs in child
    """Worker function for cross-process roundtrip test."""
    try:
        df, handles = attach_from_shm(meta)
        # Return summary so we can compare from the parent
        result = {
            "shape": df.shape,
            "columns": list(df.columns),
            "first_close": float(df["close"].iloc[0]),
            "sum_close": float(df["close"].sum()),
            "nan_in_sma20": int(df["sma_20"].isna().sum()),
            "dtypes": {c: str(df[c].dtype) for c in df.columns},
        }
        for h in handles:
            h.close()
        queue.put(("ok", result))
    except Exception as exc:
        queue.put(("err", repr(exc)))


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="multiprocessing.shared_memory cross-process semantics on Windows "
    "diverge from Linux/macOS — production target is Linux only.",
)
def test_roundtrip_cross_process():
    """A child process must be able to attach to segments the parent created
    and read identical bytes."""
    df = _make_synthetic_features()
    ctx = mp.get_context("spawn")
    with materialise_to_shm(df, run_id="t_xproc") as owner:
        queue: "mp.Queue[Any]" = ctx.Queue()
        proc = ctx.Process(target=_attach_in_subprocess, args=(owner.meta, queue))
        proc.start()
        proc.join(timeout=30)
        assert proc.exitcode == 0, "subprocess crashed"
        status, payload = queue.get(timeout=5)
        assert status == "ok", f"subprocess raised: {payload}"
        assert payload["shape"] == df.shape
        assert payload["columns"] == list(df.columns)
        assert payload["first_close"] == pytest.approx(float(df["close"].iloc[0]))
        assert payload["sum_close"] == pytest.approx(float(df["close"].sum()))
        assert payload["nan_in_sma20"] == int(df["sma_20"].isna().sum())
        # Dtype preservation across the process boundary
        assert payload["dtypes"]["close"] == "float64"
        assert payload["dtypes"]["vol_pct"] == "float32"
        assert payload["dtypes"]["is_signal"] == "bool"


def test_meta_is_picklable():
    """ShmMeta must be picklable so it can ride in a ProcessPoolExecutor
    initializer arg tuple."""
    import pickle

    df = _make_synthetic_features(n_rows=50)
    with materialise_to_shm(df, run_id="t_pickle") as owner:
        blob = pickle.dumps(owner.meta)
        restored = pickle.loads(blob)
        assert restored.run_id == owner.meta.run_id
        assert restored.columns == owner.meta.columns
        assert restored.index_name == owner.meta.index_name


def test_two_workers_see_identical_data():
    """Two attach calls on the same meta produce DataFrames with identical
    contents (the underlying bytes are shared via the OS shared-memory layer,
    even though each attach gets its own virtual address mapping)."""
    df = _make_synthetic_features(n_rows=300)
    with materialise_to_shm(df, run_id="t_two") as owner:
        df1, h1 = attach_from_shm(owner.meta)
        df2, h2 = attach_from_shm(owner.meta)
        try:
            pd.testing.assert_frame_equal(df1, df2, check_freq=False)
        finally:
            for h in h1 + h2:
                h.close()


def test_writes_in_one_attach_visible_in_another():
    """The whole point of shared memory: a write in one attach must be
    visible to all other attaches backed by the same segment. This is the
    actual zero-copy guarantee — DataFrame addresses can differ but the bytes
    are the same physical memory."""
    df = _make_synthetic_features(n_rows=200)
    with materialise_to_shm(df, run_id="t_share") as owner:
        df1, h1 = attach_from_shm(owner.meta)
        df2, h2 = attach_from_shm(owner.meta)
        try:
            # Mutate via numpy view from attach #1
            df1["close"].values[0] = 999.999
            # Read from attach #2 — must see the write
            assert df2["close"].values[0] == 999.999
        finally:
            for h in h1 + h2:
                h.close()


def test_empty_dataframe_handled():
    """Edge case: a DataFrame with columns but zero rows."""
    df = pd.DataFrame(
        {"close": np.array([], dtype=np.float64)},
        index=pd.DatetimeIndex([]),
    )
    # SharedMemory can't allocate size=0; materialise_to_shm rounds up to 1 byte
    with materialise_to_shm(df, run_id="t_empty") as owner:
        attached, handles = attach_from_shm(owner.meta)
        try:
            assert attached.shape == (0, 1)
            assert list(attached.columns) == ["close"]
        finally:
            for h in handles:
                h.close()
