"""Generate per-market 5m sweep configs for the5ers overnight run.

Outputs to configs/local_sweeps/<MARKET>_5m_5ers.yaml.
Reads contract economics from configs/cfd_markets.yaml.
Writes Sprint 98 RAM-safe flags + sequential_families.
"""
from __future__ import annotations

from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parent.parent
CFD_CFG = REPO / "configs" / "cfd_markets.yaml"
OUT_DIR = REPO / "configs" / "local_sweeps"

# 10 markets to run tonight (NQ already done)
MARKET_PLAN = {
    # market: (host, max_workers)
    "ES":  ("r630", 40),
    "CL":  ("r630", 40),
    "GC":  ("r630", 40),
    "YM":  ("r630", 40),
    "SI":  ("gen8", 36),
    "EC":  ("gen8", 36),
    "JY":  ("gen8", 36),
    "BP":  ("g9",   24),
    "AD":  ("g9",   24),
    "BTC": ("g9",   24),
}


def main() -> None:
    with CFD_CFG.open("r", encoding="utf-8") as fh:
        cfd_markets = yaml.safe_load(fh) or {}

    for market, (host, workers) in MARKET_PLAN.items():
        market_cfg = cfd_markets.get(market, {})
        if not market_cfg:
            print(f"[WARN] {market} not in cfd_markets.yaml — skipping")
            continue

        engine_cfg = market_cfg.get("engine", {})
        oos = market_cfg.get("oos_split_date", "2020-01-01")

        config = {
            "instrument_universe": "cfd_dukascopy",
            "price_source": "dukascopy",
            "sweep": {
                "name": f"{market.lower()}_5m_5ers_overnight",
                "output_dir": f"Outputs/{market.lower()}_5m_5ers",
            },
            "datasets": [{
                "path": f"/data/market_data/cfds/ohlc_engine/{market}_5m_dukascopy.csv",
                "market": market,
                "timeframe": "5m",
            }],
            "strategy_types": "all",
            "output_dir": f"Outputs/{market.lower()}_5m_5ers",
            "engine": {
                "initial_capital": 250000.0,
                "risk_per_trade": 0.01,
                "commission_per_contract": int(engine_cfg.get("commission_per_contract", 0)),
                "slippage_ticks": int(engine_cfg.get("slippage_ticks", 1)),
                "tick_value": float(engine_cfg.get("tick_value", 0.01)),
                "dollars_per_point": float(engine_cfg.get("dollars_per_point", 1.0)),
                "use_vectorized_trades": True,
            },
            "pipeline": {
                "max_workers_sweep": workers,
                "max_workers_refinement": workers,
                "max_candidates_to_refine": 5,
                "oos_split_date": oos,
                "skip_portfolio_evaluation": True,
                "skip_portfolio_selector": True,
                "recycling_pool": True,
                "maxtasksperchild": 200,
                "sequential_families": True,
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

        out_path = OUT_DIR / f"{market}_5m_5ers.yaml"
        with out_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(config, fh, sort_keys=False, default_flow_style=False)
        print(f"  [{host}, workers={workers}, oos={oos}] {out_path.name}")


if __name__ == "__main__":
    main()
