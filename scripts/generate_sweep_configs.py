#!/usr/bin/env python3
"""Generate sweep config YAMLs for all markets from cfd_markets.yaml.

Reads the master CFD market config and generates one sweep config per market,
with all available timeframes included. Output configs are ready for
run_local_sweep.py or run_cluster_sweep.py.

Usage:
    python scripts/generate_sweep_configs.py
    python scripts/generate_sweep_configs.py --markets ES NQ GC
    python scripts/generate_sweep_configs.py --timeframes daily 60m
    python scripts/generate_sweep_configs.py --workers 80 --data-dir /data/market_data/dukascopy/
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from modules.instrument_universe import CFD_DUKASCOPY, canonical_dukascopy_filename

DEFAULT_MARKETS_CONFIG = REPO_ROOT / "configs" / "cfd_markets.yaml"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "configs" / "local_sweeps"
ALL_TIMEFRAMES = ["5m", "15m", "30m", "60m", "daily"]


def generate_configs(
    markets_config: Path = DEFAULT_MARKETS_CONFIG,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    markets: list[str] | None = None,
    timeframes: list[str] | None = None,
    data_dir: str = "Data",
    max_workers: int = 36,
) -> list[Path]:
    """Generate sweep configs and return list of output paths."""
    with open(markets_config) as f:
        all_markets = yaml.safe_load(f)

    if markets:
        selected = {m: all_markets[m] for m in markets if m in all_markets}
        unknown = set(markets) - set(all_markets.keys())
        if unknown:
            print(f"WARNING: Unknown markets: {', '.join(sorted(unknown))}")
    else:
        selected = all_markets

    tfs = timeframes or ALL_TIMEFRAMES
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []

    for market, spec in selected.items():
        # Build datasets list for selected timeframes
        data_files = spec.get("data_files", {})
        datasets = []
        for tf in tfs:
            if tf in data_files:
                datasets.append({
                    "path": f"{data_dir}/{canonical_dukascopy_filename(market, tf)}",
                    "market": market,
                    "timeframe": tf,
                })

        if not datasets:
            print(f"  SKIP {market}: no data files for timeframes {tfs}")
            continue

        engine = spec.get("engine", {})
        oos_date = spec.get("oos_split_date", "2020-01-01")

        config = {
            "instrument_universe": CFD_DUKASCOPY,
            "price_source": "dukascopy",
            "sweep": {
                "name": f"{market.lower()}_all_tf_cfd",
                "output_dir": "Outputs",
            },
            "datasets": datasets,
            "strategy_types": "all",
            "engine": {
                "initial_capital": 250000.0,
                "risk_per_trade": 0.01,
                "commission_per_contract": engine.get("commission_per_contract", 0),
                "slippage_ticks": engine.get("slippage_ticks", 0),
                "tick_value": engine.get("tick_value", 12.50),
                "dollars_per_point": engine.get("dollars_per_point", 50.0),
                "use_vectorized_trades": True,
            },
            "pipeline": {
                "max_workers_sweep": max_workers,
                "max_workers_refinement": max_workers,
                "max_candidates_to_refine": 5,
                "oos_split_date": oos_date,
                "skip_portfolio_evaluation": True,
                "skip_portfolio_selector": True,
            },
            "promotion_gate": {
                "min_profit_factor": 1.0,
                "min_average_trade": 0.0,
                "require_positive_net_pnl": False,
                "min_trades": 50,
                "min_trades_per_year": 3.0,
                "max_promoted_candidates": 20,
            },
            "leaderboard": {
                "min_net_pnl": 0.0,
                "min_pf": 1.0,
                "min_oos_pf": 1.0,
                "min_total_trades": 60,
            },
        }

        # Write config
        tf_label = "all_timeframes" if len(datasets) > 1 else datasets[0]["timeframe"]
        filename = f"{market}_{tf_label}.yaml"
        out_path = output_dir / filename
        with open(out_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        generated.append(out_path)
        tf_list = ", ".join(d["timeframe"] for d in datasets)
        print(f"  {filename:40s}  [{tf_list}]")

    return generated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate sweep config YAMLs from cfd_markets.yaml"
    )
    parser.add_argument("--markets", nargs="*", default=None,
                        help="Specific markets to generate (default: all 24)")
    parser.add_argument("--timeframes", nargs="*", default=None,
                        help="Timeframes to include (default: all 5)")
    parser.add_argument("--data-dir", type=str, default="Data",
                        help="Data directory prefix for dataset paths")
    parser.add_argument("--workers", type=int, default=36,
                        help="max_workers for sweep and refinement")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR),
                        help="Output directory for generated configs")
    parser.add_argument("--markets-config", type=str, default=str(DEFAULT_MARKETS_CONFIG),
                        help="Path to cfd_markets.yaml")
    args = parser.parse_args()

    print(f"Generating sweep configs -> {args.output_dir}/\n")

    generated = generate_configs(
        markets_config=Path(args.markets_config),
        output_dir=Path(args.output_dir),
        markets=args.markets,
        timeframes=args.timeframes,
        data_dir=args.data_dir,
        max_workers=args.workers,
    )

    print(f"\nGenerated {len(generated)} config(s)")


if __name__ == "__main__":
    main()
