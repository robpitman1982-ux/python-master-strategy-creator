"""Smoke tests for strategy subtypes."""
from __future__ import annotations

import pytest
from modules.strategy_types import get_strategy_type, list_strategy_types


SUBTYPE_NAMES = [
    "mean_reversion_vol_dip",
    "mean_reversion_mom_exhaustion",
    "mean_reversion_trend_pullback",
    "trend_pullback_continuation",
    "trend_momentum_breakout",
    "trend_slope_recovery",
    "breakout_compression_squeeze",
    "breakout_range_expansion",
    "breakout_higher_low_structure",
]


def test_all_subtypes_registered():
    registered = list_strategy_types()
    for name in SUBTYPE_NAMES:
        assert name in registered, f"Subtype '{name}' not found in registry"


def test_subtypes_have_distinct_filter_pools():
    """Each subtype must have a different filter pool from its parent family."""
    from modules.strategy_types.mean_reversion_strategy_type import MeanReversionStrategyType
    parent_filters = set(MeanReversionStrategyType().get_filter_classes())

    for name in ["mean_reversion_vol_dip", "mean_reversion_mom_exhaustion", "mean_reversion_trend_pullback"]:
        st = get_strategy_type(name)
        subtype_filters = set(st.get_filter_classes())
        assert subtype_filters != parent_filters, f"{name} has same filter pool as parent"
        assert len(subtype_filters) >= 4, f"{name} has fewer than 4 filters"
        assert len(subtype_filters) <= 8, f"{name} has more than 8 filters — too many"


def test_subtypes_have_valid_combo_sizes():
    for name in SUBTYPE_NAMES:
        st = get_strategy_type(name)
        n_filters = len(st.get_filter_classes())
        assert st.min_filters_per_combo >= 3, f"{name} min_filters too low"
        assert st.max_filters_per_combo <= n_filters, \
            f"{name} max_filters ({st.max_filters_per_combo}) > pool size ({n_filters})"


def test_subtype_filter_classes_are_importable():
    """All filter classes in each subtype must be importable from modules.filters."""
    for name in SUBTYPE_NAMES:
        st = get_strategy_type(name)
        for fc in st.get_filter_classes():
            # Just instantiating the class list is enough — if import failed we'd already be dead
            assert callable(fc), f"{name}: {fc} is not callable"
