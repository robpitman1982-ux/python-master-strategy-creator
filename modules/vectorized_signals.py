"""
Vectorized signal generation helpers.

compute_combined_signal_mask() ANDs the boolean masks from all filters in a combo,
returning a numpy bool array that can be passed directly to engine.run() via
the precomputed_signals parameter — skipping the bar-by-bar generate_signal() loop.

Sprint 94: when `engine.filter_mask_cache.enabled: true` (or env var
`PSC_FILTER_MASK_CACHE=1`), per-filter masks are looked up in a process-level
cache keyed on (filter_class, params, data_id). Cache miss falls through to the
filter's `mask()` call. Disabled mode is bit-identical to pre-Sprint-94 behaviour.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from modules import filter_mask_cache
from modules.filters import BaseFilter


def compute_combined_signal_mask(
    filters: list[BaseFilter],
    data: pd.DataFrame,
) -> np.ndarray:
    """
    Compute the AND of all filter masks, returning a numpy bool array.

    Where ALL filters pass on a bar, the signal is True (entry signal).
    Returns a zero array (no signals) if the filter list is empty.

    Args:
        filters: List of filter objects, each with a mask(data) method.
        data: DataFrame with OHLCV + precomputed features.

    Returns:
        numpy bool array of shape (len(data),).
    """
    if not filters:
        return np.zeros(len(data), dtype=bool)

    if filter_mask_cache.is_enabled():
        # Cached path: each per-filter mask is fetched from a process-level
        # cache (lazy populated on first miss). Combine via numpy AND-reduce.
        if len(filters) == 1:
            return filter_mask_cache.get_or_compute_mask(filters[0], data)
        masks = [filter_mask_cache.get_or_compute_mask(f, data) for f in filters]
        return np.logical_and.reduce(masks)

    # Cache-disabled path - identical to pre-Sprint-94 behaviour.
    combined = filters[0].mask(data)
    for f in filters[1:]:
        combined = combined & f.mask(data)

    if hasattr(combined, "values"):
        return combined.values.astype(bool)
    return np.asarray(combined, dtype=bool)
