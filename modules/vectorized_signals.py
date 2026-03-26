"""
Vectorized signal generation helpers.

compute_combined_signal_mask() ANDs the boolean masks from all filters in a combo,
returning a numpy bool array that can be passed directly to engine.run() via
the precomputed_signals parameter — skipping the bar-by-bar generate_signal() loop.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

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

    combined = filters[0].mask(data)
    for f in filters[1:]:
        combined = combined & f.mask(data)

    if hasattr(combined, "values"):
        return combined.values.astype(bool)
    return np.asarray(combined, dtype=bool)
