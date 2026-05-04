#!/usr/bin/env python3
"""Sprint 99 trial — cProfile a single MR family run to confirm where the
per-combo time actually goes.

Decision threshold: if Trade-object construction in `engine.run_vectorized`
PLUS the Python loops in `engine.results()` together account for >=20% of
total cumulative time, refactor proceeds. Otherwise sprint exits RED.

Usage:
    python scripts/profile_engine_combo.py \
        --data /data/market_data/cfds/ohlc_engine/ES_daily_dukascopy.csv \
        --market ES --timeframe daily --max-combos 1500
"""
from __future__ import annotations

import argparse
import cProfile
import pstats
import sys
import time
from io import StringIO
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Cap thread libs before any numpy import
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from modules.config_loader import load_config  # noqa: E402
from modules.data_loader import load_tradestation_csv  # noqa: E402
from modules.engine import EngineConfig  # noqa: E402
from modules.feature_builder import add_precomputed_features  # noqa: E402
from modules.strategy_types import get_strategy_type  # noqa: E402
from modules.strategy_types.mean_reversion_strategy_type import _run_mr_combo_case, _mr_worker_init  # noqa: E402
from itertools import combinations as _combs


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True, help="Path to OHLC CSV")
    p.add_argument("--market", default="ES")
    p.add_argument("--timeframe", default="daily")
    p.add_argument("--max-combos", type=int, default=500,
                   help="Cap the number of combos profiled (sequential, in-process)")
    p.add_argument("--output", default="/tmp/sprint99_profile.txt")
    args = p.parse_args()

    cfg_yaml = load_config()
    print(f"Loading {args.data} ...")
    data = load_tradestation_csv(Path(args.data))
    print(f"  {len(data):,} bars")

    # Precompute features
    strat = get_strategy_type("mean_reversion")
    sma_lengths = [5, 8, 20, 31, 50]
    avg_range = [5, 8, 20]
    momentum = [2, 5, 8]
    print("Precomputing features ...")
    data = add_precomputed_features(
        data, sma_lengths=sma_lengths,
        avg_range_lookbacks=avg_range, momentum_lookbacks=momentum,
    )
    print(f"  {len(data.columns)} columns")

    # Engine config
    cfg = EngineConfig(
        initial_capital=250_000.0,
        risk_per_trade=0.01,
        symbol=args.market,
        commission_per_contract=0,
        slippage_ticks=1,
        tick_value=0.01,
        dollars_per_point=1.0,
        oos_split_date="2020-01-01",
        timeframe=args.timeframe,
        direction="long",
        use_vectorized_trades=True,
    )

    # Initialise worker globals (we run the worker function in-process)
    _mr_worker_init(data, cfg)

    # Build N combos
    filter_classes = strat.get_filter_classes()
    n_filters = len(filter_classes)
    min_f = strat.min_filters_per_combo
    max_f = strat.max_filters_per_combo
    all_combos = []
    for k in range(min_f, max_f + 1):
        for c in _combs(filter_classes, k):
            all_combos.append(c)
            if len(all_combos) >= args.max_combos:
                break
        if len(all_combos) >= args.max_combos:
            break
    combos = all_combos[:args.max_combos]
    print(f"Profiling {len(combos)} MR combos in-process ...")

    # cProfile the loop
    profiler = cProfile.Profile()
    t0 = time.perf_counter()
    profiler.enable()
    for combo in combos:
        _run_mr_combo_case((combo, cfg))
    profiler.disable()
    elapsed = time.perf_counter() - t0
    per_combo_ms = elapsed / len(combos) * 1000
    print(f"\nTotal: {elapsed:.2f}s, per-combo: {per_combo_ms:.2f} ms")

    # Dump top 40 by cumulative
    s = StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats(pstats.SortKey.CUMULATIVE)
    ps.print_stats(40)
    cum_text = s.getvalue()

    # Dump top 40 by tottime (own time, not children)
    s2 = StringIO()
    ps2 = pstats.Stats(profiler, stream=s2).sort_stats(pstats.SortKey.TIME)
    ps2.print_stats(40)
    tot_text = s2.getvalue()

    summary = f"""
=========================================================================
Sprint 99 trial profile — MR family on {args.market} {args.timeframe}
=========================================================================
Combos profiled: {len(combos)}
Total wall:      {elapsed:.2f}s
Per-combo:       {per_combo_ms:.2f} ms

=========================================================================
TOP 40 BY CUMULATIVE TIME
=========================================================================
{cum_text}

=========================================================================
TOP 40 BY OWN TIME (tottime)
=========================================================================
{tot_text}
"""
    Path(args.output).write_text(summary, encoding="utf-8")
    print(f"\nSaved to {args.output}")
    print("\n=== TOP 20 BY CUMULATIVE ===")
    s3 = StringIO()
    ps3 = pstats.Stats(profiler, stream=s3).sort_stats(pstats.SortKey.CUMULATIVE)
    ps3.print_stats(20)
    print(s3.getvalue())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
