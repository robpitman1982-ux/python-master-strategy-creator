"""Smoke tests for short-side strategy types."""
from __future__ import annotations

from modules.strategy_types import get_strategy_type, list_strategy_types

SHORT_TYPES = ["short_mean_reversion", "short_trend", "short_breakout"]


def test_short_types_registered():
    registered = list_strategy_types()
    for name in SHORT_TYPES:
        assert name in registered, f"Short type '{name}' not in registry"


def test_short_types_return_short_direction():
    for name in SHORT_TYPES:
        st = get_strategy_type(name)
        direction = st.get_engine_direction()
        assert direction == "short", f"{name}.get_engine_direction() returned '{direction}'"


def test_short_filters_are_callable():
    for name in SHORT_TYPES:
        st = get_strategy_type(name)
        for fc in st.get_filter_classes():
            assert callable(fc), f"{name}: {fc} is not callable"


def test_short_filter_masks_return_bool_array():
    """Verify each short filter mask() returns a numpy bool array."""
    import numpy as np
    import pandas as pd
    from modules.filters import AboveFastSMAFilter, DowntrendDirectionFilter, DownsideBreakoutFilter

    n = 300
    data = pd.DataFrame({
        "close": np.random.randn(n).cumsum() + 100,
        "high": np.random.randn(n).cumsum() + 102,
        "low": np.random.randn(n).cumsum() + 98,
        "open": np.random.randn(n).cumsum() + 100,
        "sma_20": np.random.randn(n).cumsum() + 100,
        "sma_50": np.random.randn(n).cumsum() + 100,
        "sma_200": np.random.randn(n).cumsum() + 100,
        "atr_20": np.abs(np.random.randn(n)) + 1,
    })

    for FilterClass in [AboveFastSMAFilter, DowntrendDirectionFilter, DownsideBreakoutFilter]:
        f = FilterClass()
        result = f.mask(data)
        assert result.dtype == bool or result.dtype == np.bool_, \
            f"{FilterClass.__name__}.mask() did not return bool array"
        assert len(result) == n
