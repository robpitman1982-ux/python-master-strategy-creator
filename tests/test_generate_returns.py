"""Tests for generate_returns.py — data cache and parallel rebuild machinery."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch

import pandas as pd

from generate_returns import _data_cache, _dataset_to_folder, _load_cached


def test_dataset_to_folder_standard():
    assert _dataset_to_folder("ES_60m_2008_2026_tradestation.csv") == "ES_60m"


def test_dataset_to_folder_daily():
    assert _dataset_to_folder("NQ_daily_2008_2026_tradestation.csv") == "NQ_daily"


def test_dataset_to_folder_short_name():
    assert _dataset_to_folder("ES.csv") == "ES"


def test_load_cached_returns_same_object():
    """_load_cached should return the same DataFrame for repeated calls."""
    _data_cache.clear()
    fake_df = pd.DataFrame({"a": [1, 2, 3]})
    with patch("generate_returns.load_tradestation_csv", return_value=fake_df) as mock_load:
        from pathlib import Path
        p = Path("/fake/data.csv")
        result1 = _load_cached(p)
        result2 = _load_cached(p)
        assert result1 is result2
        mock_load.assert_called_once()
    _data_cache.clear()


def test_parallel_rebuild_collects_results():
    """ThreadPoolExecutor + as_completed collects all results from worker functions."""
    items = [{"key": f"strat_{i}", "value": float(i)} for i in range(5)]

    def _worker(item: dict) -> tuple[str, float]:
        return (item["key"], item["value"])

    results: dict[str, float] = {}
    max_workers = min(os.cpu_count() or 4, len(items))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_worker, item): item for item in items}
        for future in as_completed(futures):
            key, val = future.result()
            results[key] = val

    assert len(results) == 5
    for i in range(5):
        assert results[f"strat_{i}"] == float(i)


def test_parallel_rebuild_handles_none_results():
    """None results from workers should be skipped without error."""
    items = [1, 2, None, 4, None]

    def _worker(item):
        if item is None:
            return None
        return (f"s{item}", item * 10)

    collected = {}
    max_workers = min(os.cpu_count() or 4, len(items))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_worker, item): item for item in items}
        for future in as_completed(futures):
            result = future.result()
            if result:
                key, val = result
                collected[key] = val

    assert len(collected) == 3
    assert collected == {"s1": 10, "s2": 20, "s4": 40}


def test_parallel_rebuild_handles_exceptions():
    """Exceptions in individual workers should not crash the pool."""
    items = [1, 2, "bad", 4]

    def _worker(item):
        if item == "bad":
            raise ValueError("bad item")
        return (f"s{item}", item)

    collected = {}
    errors = 0
    max_workers = min(os.cpu_count() or 4, len(items))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_worker, item): item for item in items}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    key, val = result
                    collected[key] = val
            except ValueError:
                errors += 1

    assert len(collected) == 3
    assert errors == 1
