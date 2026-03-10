from __future__ import annotations

from itertools import combinations
from typing import List, Type


def generate_filter_combinations(
    filter_classes: list[Type],
    min_filters: int = 3,
    max_filters: int = 5,
) -> list[list[Type]]:
    """
    Generate combinations of filter classes.

    Example:
        [Trend, Pullback, Recovery, Volatility, Momentum]
    ->
        [
            [Trend, Pullback, Recovery],
            [Trend, Pullback, Recovery, Volatility],
            ...
        ]
    """
    if not filter_classes:
        return []

    combos: list[list[Type]] = []

    max_filters = min(max_filters, len(filter_classes))

    for r in range(min_filters, max_filters + 1):
        for combo in combinations(filter_classes, r):
            combos.append(list(combo))

    return combos


def build_filter_combo_name(filter_objects: list) -> str:
    """
    Create a readable short name for a filter set.
    """
    if not filter_objects:
        return "NoFilters"

    parts: List[str] = []
    for filter_obj in filter_objects:
        name = getattr(filter_obj, "name", filter_obj.__class__.__name__)
        short_name = name.replace("Filter", "")
        parts.append(short_name)

    return "_".join(parts)