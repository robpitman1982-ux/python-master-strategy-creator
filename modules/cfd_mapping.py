"""
CFD Instrument Mapping — Verified from The5ers MT5 (Five Percent Online)
Account: 26213568, Server: FivePercentOnline-Real
Verified: 2026-04-01 by Rob Pitman

Maps futures symbols (used in backtesting) to CFD symbols (used on The5ers MT5).
RTY (Russell 2000) and HG (Copper) are NOT available on The5ers — excluded.
"""
from __future__ import annotations

CFD_INSTRUMENT_MAP = {
    "ES": {
        "cfd_symbol": "SP500",
        "cfd_description": "Standard and Poor's 500 Index",
        "cfd_contract_size": 1,        # 1 lot = $1 per point
        "cfd_digits": 2,
        "cfd_min_lot": 0.01,
        "cfd_lot_step": 0.01,
        "cfd_max_lot": 500,
        "cfd_stops_level": 10,         # min 10 points for SL/TP
        "cfd_spread_type": "floating",
        "cfd_commission_pct": 0.0,     # No commission on indices
        "cfd_margin_pct": 4.0,         # 4% notional margin
        "cfd_swap_long": -144,
        "cfd_swap_short": -144,
        "cfd_execution": "Market",
        "futures_dollars_per_point": 50.0,
        "futures_symbol": "ES",
        "sessions": "Mon-Fri 01:05-23:50 server time",
    },
    "NQ": {
        "cfd_symbol": "NAS100",
        "cfd_description": "NASDAQ 100 Index",
        "cfd_contract_size": 1,
        "cfd_digits": 2,
        "cfd_min_lot": 0.01,
        "cfd_lot_step": 0.01,
        "cfd_max_lot": 500,
        "cfd_stops_level": 10,
        "cfd_spread_type": "floating",
        "cfd_commission_pct": 0.0,
        "cfd_margin_pct": 4.0,
        "cfd_swap_long": -360,
        "cfd_swap_short": -360,
        "cfd_execution": "Market",
        "futures_dollars_per_point": 20.0,
        "futures_symbol": "NQ",
        "sessions": "Mon-Fri 01:05-23:50 server time",
    },
    "YM": {
        "cfd_symbol": "US30",
        "cfd_description": "US Dow Jones 30 Index",
        "cfd_contract_size": 1,
        "cfd_digits": 2,
        "cfd_min_lot": 0.01,
        "cfd_lot_step": 0.01,
        "cfd_max_lot": 500,
        "cfd_stops_level": 10,
        "cfd_spread_type": "floating",
        "cfd_commission_pct": 0.0,
        "cfd_margin_pct": 4.0,
        "cfd_swap_long": -720,
        "cfd_swap_short": -720,
        "cfd_execution": "Market",
        "futures_dollars_per_point": 5.0,
        "futures_symbol": "YM",
        "sessions": "Mon-Fri 01:05-23:50 server time",
    },
    "GC": {
        "cfd_symbol": "XAUUSD",
        "cfd_description": "Gold vs US Dollar",
        "cfd_contract_size": 100,      # 1 lot = 100 oz = $100 per $1 move
        "cfd_digits": 2,
        "cfd_min_lot": 0.01,
        "cfd_lot_step": 0.01,
        "cfd_max_lot": 100,
        "cfd_stops_level": 10,
        "cfd_spread_type": "floating",
        "cfd_commission_pct": 0.001,   # 0.001% per lot
        "cfd_margin_pct": 4.0,
        "cfd_swap_long": -200,
        "cfd_swap_short": -200,
        "cfd_execution": "Market",
        "futures_dollars_per_point": 100.0,
        "futures_symbol": "GC",
        "sessions": "Mon-Fri 01:05-23:50 server time",
    },
    "SI": {
        "cfd_symbol": "XAGUSD",
        "cfd_description": "Silver vs US Dollar",
        "cfd_contract_size": 5000,     # 1 lot = 5000 oz (same as SI futures!)
        "cfd_digits": 3,
        "cfd_min_lot": 0.01,
        "cfd_lot_step": 0.001,         # Finer granularity than other symbols
        "cfd_max_lot": 100,
        "cfd_stops_level": 10,
        "cfd_spread_type": "floating",
        "cfd_commission_pct": 0.001,
        "cfd_margin_pct": 4.0,
        "cfd_swap_long": -35,
        "cfd_swap_short": -35,
        "cfd_execution": "Market",
        "futures_dollars_per_point": 5000.0,
        "futures_symbol": "SI",
        "sessions": "Mon-Fri 01:05-23:50 server time",
    },
    "CL": {
        "cfd_symbol": "XTIUSD",
        "cfd_description": "US Crude Spot vs US Dollar",
        "cfd_contract_size": 100,      # 1 lot = 100 barrels = $100 per $1 move
        "cfd_digits": 2,
        "cfd_min_lot": 0.01,
        "cfd_lot_step": 0.01,
        "cfd_max_lot": 100,
        "cfd_stops_level": 10,
        "cfd_spread_type": "floating",
        "cfd_commission_pct": 0.03,    # 0.03% per lot (highest of all)
        "cfd_margin_pct": 20.0,        # 20% notional (much higher than indices)
        "cfd_swap_long": -70,
        "cfd_swap_short": -40,
        "cfd_execution": "Instant",    # Different from indices!
        "futures_dollars_per_point": 1000.0,
        "futures_symbol": "CL",
        "sessions": "Mon-Fri 01:05-23:50 server time",
    },
}

# Markets NOT available on The5ers CFD:
# RTY (Russell 2000) — no US2000 symbol found
# HG (Copper) — no copper symbol found

AVAILABLE_CFD_MARKETS = list(CFD_INSTRUMENT_MAP.keys())
UNAVAILABLE_MARKETS = ["RTY", "HG"]


def get_cfd_symbol(futures_market: str) -> str | None:
    """Map futures symbol to CFD symbol. Returns None if not available."""
    info = CFD_INSTRUMENT_MAP.get(futures_market.upper())
    return info["cfd_symbol"] if info else None


def futures_pnl_to_cfd_lots(
    futures_market: str,
    micro_weight: float,
) -> float:
    """Convert portfolio selector micro weight to CFD lot size.

    The portfolio selector outputs weights like 0.3 (= 3 micros of futures).
    This converts to the equivalent CFD lot size on The5ers MT5.

    For indices (contract_size=1): 1 micro futures ≈ varies by market
    For commodities (contract_size=100/5000): direct ratio applies
    """
    info = CFD_INSTRUMENT_MAP.get(futures_market.upper())
    if info is None:
        return 0.0

    contract_size = info["cfd_contract_size"]
    futures_dpp = info["futures_dollars_per_point"]

    # micro_weight 0.1 = 1 micro = 1/10th of full contract
    # Full futures contract = futures_dollars_per_point per point
    # CFD 1.0 lot = contract_size per point
    # So: n_micros * (futures_dpp / 10) = desired_dpp
    #     desired_dpp / contract_size = cfd_lots

    n_micros = micro_weight * 10  # 0.3 weight = 3 micros
    desired_dollars_per_point = n_micros * (futures_dpp / 10.0)
    cfd_lots = desired_dollars_per_point / contract_size

    # Round to lot step
    lot_step = info["cfd_lot_step"]
    cfd_lots = round(cfd_lots / lot_step) * lot_step

    # Clamp to min/max
    cfd_lots = max(info["cfd_min_lot"], min(info["cfd_max_lot"], cfd_lots))

    return round(cfd_lots, 3)


def get_cfd_execution_row(
    futures_market: str,
    strategy_name: str,
    micro_weight: float,
    strategy_family: str = "",
    timeframe: str = "",
    direction: str = "LONG",
    hold_bars: int = 0,
    stop_distance_atr: float = 0.0,
    exit_type: str = "TIME_STOP",
) -> dict:
    """Build a single row for the CFD execution guide CSV."""
    info = CFD_INSTRUMENT_MAP.get(futures_market.upper(), {})
    cfd_lots = futures_pnl_to_cfd_lots(futures_market, micro_weight)

    return {
        "futures_market": futures_market.upper(),
        "cfd_symbol": info.get("cfd_symbol", "UNKNOWN"),
        "strategy_name": strategy_name,
        "micro_weight": micro_weight,
        "n_micros": int(micro_weight * 10),
        "cfd_lot_size": cfd_lots,
        "cfd_contract_size": info.get("cfd_contract_size", 0),
        "strategy_family": strategy_family,
        "timeframe": timeframe,
        "direction": direction,
        "hold_bars": hold_bars,
        "stop_distance_atr": stop_distance_atr,
        "exit_type": exit_type,
        "cfd_commission_pct": info.get("cfd_commission_pct", 0.0),
        "cfd_execution_type": info.get("cfd_execution", "Market"),
        "cfd_stops_level": info.get("cfd_stops_level", 10),
        "cfd_min_lot": info.get("cfd_min_lot", 0.01),
    }


def print_mapping_summary() -> None:
    """Print a human-readable summary of the CFD mapping."""
    print("=" * 70)
    print("CFD INSTRUMENT MAPPING — The5ers MT5 (Verified)")
    print("=" * 70)
    for fut, info in CFD_INSTRUMENT_MAP.items():
        cfd = info["cfd_symbol"]
        cs = info["cfd_contract_size"]
        dpp = info["futures_dollars_per_point"]
        print(f"  {fut:4s} -> {cfd:10s}  contract_size={cs:>5}  "
              f"futures_$/pt={dpp:>7.1f}  1lot=${cs}/pt")
    print(f"\n  Available: {', '.join(AVAILABLE_CFD_MARKETS)}")
    print(f"  Not available: {', '.join(UNAVAILABLE_MARKETS)}")
    print("=" * 70)


if __name__ == "__main__":
    print_mapping_summary()
