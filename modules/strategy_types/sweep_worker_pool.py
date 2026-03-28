"""Unified sweep worker initialization for shared ProcessPoolExecutor.

All three base sweep families (trend, MR, breakout) use the same (data, cfg) pair
within a dataset.  This module provides a single initializer that populates all
families' globals at once, so ONE pool can serve every family sweep.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from typing import Any

import pandas as pd

from modules.engine import EngineConfig


def sweep_worker_init(data: pd.DataFrame, cfg: EngineConfig) -> None:
    """Initialise worker globals for ALL sweep families at once."""
    # Import lazily inside the worker to avoid circular imports at module level
    import modules.strategy_types.trend_strategy_type as trend_mod
    import modules.strategy_types.mean_reversion_strategy_type as mr_mod
    import modules.strategy_types.breakout_strategy_type as bo_mod

    trend_mod._trend_shared_data = data
    trend_mod._trend_shared_cfg = cfg

    mr_mod._mr_shared_data = data
    mr_mod._mr_shared_cfg = cfg

    bo_mod._breakout_shared_data = data
    bo_mod._breakout_shared_cfg = cfg


def create_shared_sweep_pool(
    data: pd.DataFrame,
    cfg: EngineConfig,
    max_workers: int,
) -> ProcessPoolExecutor:
    """Create a ProcessPoolExecutor initialised for all sweep families."""
    return ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=sweep_worker_init,
        initargs=(data, cfg),
    )
