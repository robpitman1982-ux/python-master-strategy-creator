"""Process-level memoisation of trade simulations keyed on signal mask hash.

Sprint 95. Many filter combos within a sweep produce IDENTICAL signal masks
(filter A subsumes filter B in some combos, degenerate filters that always
fire or never fire, etc.). Each unique signal mask + strategy params + cfg
fingerprint deserves to be simulated only once.

This module memoises the result of `engine.run(...) -> engine.results()` keyed
on `(sha256(signal_mask), hold_bars, stop_distance, cfg_fingerprint, id(data))`.
Cache hits skip the trade simulation entirely and return a shallow copy of the
cached result dict.

Default OFF. Toggle via `engine.signal_mask_memo.enabled` in config.yaml or
`PSC_SIGNAL_MASK_MEMO=1/0` env override (env wins).
"""
from __future__ import annotations

import hashlib
import os
import sys
from typing import Any, Callable

import numpy as np

# Process-level state
_MEMO: dict[tuple, dict] = {}
_HITS = 0
_MISSES = 0


def _mask_hash(signal_mask: np.ndarray) -> bytes:
    """sha256 truncated to 128 bits — collision-resistant for our scale."""
    arr = np.asarray(signal_mask, dtype=bool)
    return hashlib.sha256(arr.tobytes()).digest()[:16]


def _cfg_fingerprint(cfg: Any) -> tuple:
    """Stable fingerprint of the engine config fields that affect trade-sim
    output. Anything not in this tuple must NOT influence the simulation, OR
    must be added here."""
    return (
        getattr(cfg, "commission_per_contract", 0.0),
        getattr(cfg, "slippage_ticks", 0),
        getattr(cfg, "tick_value", 0.0),
        getattr(cfg, "dollars_per_point", 0.0),
        str(getattr(cfg, "oos_split_date", "")),
        getattr(cfg, "direction", "long"),
        getattr(cfg, "timeframe", ""),
        bool(getattr(cfg, "use_vectorized_trades", False)),
        float(getattr(cfg, "initial_capital", 0.0)),
        float(getattr(cfg, "risk_per_trade", 0.0)),
    )


def is_enabled() -> bool:
    """Env var wins; otherwise read config (default false)."""
    env = os.environ.get("PSC_SIGNAL_MASK_MEMO", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False
    try:
        from modules.config_loader import get_nested, load_config

        cfg = load_config()
        return bool(
            get_nested(cfg, "engine", "signal_mask_memo", "enabled", default=False)
        )
    except Exception:
        return False


def get_or_compute_summary(
    signal_mask: np.ndarray,
    hold_bars: int,
    stop_distance: float | None,
    data: Any,
    cfg: Any,
    run_fn: Callable[[], dict],
) -> dict:
    """Cache-aware engine wrapper.

    `run_fn()` should construct the engine, run it with the signal_mask, and
    return `engine.results()` as a dict.

    Returns the same dict shape as run_fn() in both hit and miss paths. Hits
    return a shallow copy so the caller may freely mutate fields.
    """
    global _HITS, _MISSES
    if not is_enabled():
        return run_fn()

    # Use a string sentinel for None to avoid NaN-not-equal-to-NaN in dict keys.
    sd_key: Any = "NONE" if stop_distance is None else float(stop_distance)
    key = (
        _mask_hash(signal_mask),
        int(hold_bars),
        sd_key,
        _cfg_fingerprint(cfg),
        id(data),
    )
    cached = _MEMO.get(key)
    if cached is not None:
        _HITS += 1
        return dict(cached)
    _MISSES += 1
    result = run_fn()
    # Shallow-copy the result dict on store so caller mutation doesn't poison
    # the cache.
    _MEMO[key] = dict(result)
    return result


def stats() -> dict:
    total = _HITS + _MISSES
    mem_bytes = sys.getsizeof(_MEMO)
    for v in _MEMO.values():
        mem_bytes += sys.getsizeof(v)
    return {
        "memo_hits": _HITS,
        "memo_misses": _MISSES,
        "hit_rate": (_HITS / total) if total > 0 else 0.0,
        "unique_masks": len(_MEMO),
        "memo_memory_mb": mem_bytes / 1_048_576,
    }


def clear_cache() -> dict:
    """Drop all memoised results; return final stats before clearing."""
    global _HITS, _MISSES
    final_stats = stats()
    _MEMO.clear()
    _HITS = 0
    _MISSES = 0
    return final_stats


def reset_counters() -> None:
    """Reset hit/miss counters but keep the cache."""
    global _HITS, _MISSES
    _HITS = 0
    _MISSES = 0
