"""Process-level cache for filter mask arrays — Sprint 94.

Each filter's `mask(data)` is a pure function of `(filter_class, params, data)`
(verified by the Sprint 94 audit). The combo-level filter combination sweep
re-evaluates these masks once per combo, redundantly when many combos share
the same filter+params subset.

This module caches the resulting bool array per `(filter_class, params,
data_id)` so successive calls for the same filter+params on the same
DataFrame return the cached mask instead of re-running the filter logic.

Cache lifetime is the worker process. Dataset boundaries invalidate via
`clear_cache()` or via the data identity check (different DataFrame → different
key, old entries become unreachable but linger until cleared).

Designed as a wrapper around `compute_combined_signal_mask` so no filter
class is touched. Disabled by default; toggled via:
    config.yaml: engine.filter_mask_cache.enabled: true
    env override: PSC_FILTER_MASK_CACHE=1 (overrides config)
"""
from __future__ import annotations

import os
from typing import Any

import numpy as np
import pandas as pd

# Process-level cache: dict[cache_key, np.ndarray[bool]]
_MASK_CACHE: dict[tuple, np.ndarray] = {}
_HITS = 0
_MISSES = 0


def _is_scalar(value: Any) -> bool:
    """True if value is a hashable JSON-scalar (used in params hash)."""
    return isinstance(value, (int, float, bool, str, type(None)))


def _params_signature(filter_obj: Any) -> tuple:
    """Return a hashable signature of filter parameters from `vars(filter_obj)`.

    Per the Sprint 94 audit, all 60 filter classes in `modules/filters.py`
    set their parameters as scalar instance attributes in `__init__` and never
    mutate them at `mask()` time. `vars()` over those scalars is a complete
    fingerprint.
    """
    items = []
    for k, v in sorted(vars(filter_obj).items()):
        if k.startswith("_"):
            continue
        if _is_scalar(v):
            items.append((k, v))
        else:
            # Non-scalar attribute (rare; e.g. a list of lookbacks) - serialise
            # via repr for stability. Audit found no such filters; safety net.
            items.append((k, repr(v)))
    return tuple(items)


def _cache_key(filter_obj: Any, data: pd.DataFrame) -> tuple:
    """Build the cache key for a (filter, data) pair."""
    return (
        filter_obj.__class__.__name__,
        _params_signature(filter_obj),
        id(data),  # discriminates DataFrames within process
        len(data),
    )


def is_enabled() -> bool:
    """Read the cache flag from env var (override) or config (default false)."""
    env = os.environ.get("PSC_FILTER_MASK_CACHE", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False
    # Fall back to config — lazy import to avoid circular at module load.
    try:
        from modules.config_loader import get_nested, load_config

        cfg = load_config()
        return bool(
            get_nested(cfg, "engine", "filter_mask_cache", "enabled", default=False)
        )
    except Exception:
        return False


def get_or_compute_mask(filter_obj: Any, data: pd.DataFrame) -> np.ndarray:
    """Return the bool mask for `filter_obj` on `data`, cached.

    Always returns a numpy bool array (not pandas Series). Coerces the filter's
    return value the same way `compute_combined_signal_mask` does.
    """
    global _HITS, _MISSES
    key = _cache_key(filter_obj, data)
    cached = _MASK_CACHE.get(key)
    if cached is not None:
        _HITS += 1
        return cached
    _MISSES += 1
    raw = filter_obj.mask(data)
    if hasattr(raw, "values"):
        arr = raw.values.astype(bool)
    else:
        arr = np.asarray(raw, dtype=bool)
    _MASK_CACHE[key] = arr
    return arr


def stats() -> dict:
    """Return current cache statistics."""
    total = _HITS + _MISSES
    mem_bytes = sum(m.nbytes for m in _MASK_CACHE.values())
    return {
        "cache_hits": _HITS,
        "cache_misses": _MISSES,
        "hit_rate": (_HITS / total) if total > 0 else 0.0,
        "unique_filters_cached": len(_MASK_CACHE),
        "cache_memory_mb": mem_bytes / 1_048_576,
    }


def clear_cache() -> dict:
    """Drop all cached masks; return final stats before clearing."""
    global _HITS, _MISSES
    final_stats = stats()
    _MASK_CACHE.clear()
    _HITS = 0
    _MISSES = 0
    return final_stats


def reset_counters() -> None:
    """Reset hit/miss counters without clearing the cache (useful between families)."""
    global _HITS, _MISSES
    _HITS = 0
    _MISSES = 0
