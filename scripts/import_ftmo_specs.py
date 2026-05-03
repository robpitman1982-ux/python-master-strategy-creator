#!/usr/bin/env python3
"""Import FTMO MT5 symbol specs CSV into configs/ftmo_mt5_specs.yaml.

Run after:
  1. Operator runs `scripts/ftmo_symbol_spec_export.mq5` on FTMO Free Trial demo.
  2. Send back the produced `<MT5>/MQL5/Files/ftmo_symbol_specs.csv`.
  3. Save it to `data/ftmo_symbol_specs.csv` (or pass --csv).

This script:
  - Reads the per-symbol MT5 export
  - Converts MT5 swap-points to USD-per-micro using The5ers convention:
      USD_per_micro = swap_long * contract_size * 10^(-digits) / 100
    where "1 micro" = 0.01 lot = MT5 min_lot.
  - For non-USD profit currencies (EUR/GBP/JPY/AUD), converts to USD using
    static rates (override via --rates).
  - Maps FTMO MT5 symbol names to our futures market codes (ES, NQ, etc.)
  - Writes configs/ftmo_mt5_specs.yaml

Usage:
    python scripts/import_ftmo_specs.py --csv data/ftmo_symbol_specs.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Map operator's market code -> FTMO MT5 symbol name
SYMBOL_MAP = {
    "ES":    "US500.cash",
    "NQ":    "US100.cash",
    "YM":    "US30.cash",
    "RTY":   "US2000.cash",
    "DAX":   "GER40.cash",
    "FTSE":  "UK100.cash",
    "N225":  "JP225.cash",
    "STOXX": "EU50.cash",
    "CAC":   "FRA40.cash",
    "AUS":   "AUS200.cash",
    "GC":    "XAUUSD",
    "SI":    "XAGUSD",
    "CL":    "USOIL.cash",
    "BRENT": "UKOIL.cash",
    "BTC":   "BTCUSD",
    "ETH":   "ETHUSD",
    "EC":    "EURUSD",
    "BP":    "GBPUSD",
    "JY":    "USDJPY",
    "AD":    "AUDUSD",
    "NZD":   "NZDUSD",
    "CD":    "USDCAD",
    "SF":    "USDCHF",
    "NG":    "NATGAS.cash",
    "W":     "WHEAT.c",
    "HG":    "XCUUSD",       # FTMO copper CFD
    "DXY":   "DXY.cash",
}

# Operator-supplied futures dollars-per-point (used by Sprint 88
# deployability calc; not used in cost-aware MC directly)
FUTURES_DPP = {
    "ES": 50.0, "NQ": 20.0, "YM": 5.0, "RTY": 50.0,
    "DAX": 25.0, "FTSE": 10.0, "N225": 5.0, "STOXX": 10.0,
    "CAC": 10.0, "AUS": 25.0,
    "GC": 100.0, "SI": 5000.0, "CL": 1000.0, "BRENT": 1000.0,
    "BTC": 5.0, "ETH": 50.0,
    "EC": 125000.0, "BP": 62500.0, "JY": 125000.0, "AD": 100000.0,
    "NZD": 100000.0, "CD": 100000.0, "SF": 125000.0,
    "NG": 10000.0, "W": 50.0, "HG": 25000.0, "DXY": 1000.0,
}

# CFD dollars-per-point (operator convention from cfd_markets.yaml /
# the5ers_mt5_specs.yaml). For FX, null means selector uses swap_*_per_micro
# directly without dpp scaling.
CFD_DPP = {
    "ES": 1.0, "NQ": 1.0, "YM": 1.0, "RTY": 1.0,
    "DAX": 1.0, "FTSE": 1.0, "N225": 10.0, "STOXX": 1.0,
    "CAC": 1.0, "AUS": 1.0,
    "GC": 100.0, "SI": 5000.0, "CL": 100.0, "BRENT": 100.0,
    "BTC": 1.0, "ETH": 1.0,
    "EC": None, "BP": None, "JY": None, "AD": None,
    "NZD": None, "CD": None, "SF": None,
    "NG": 1000.0, "W": 1.0, "HG": 1.0, "DXY": 100.0,
}

# Approximate FX rates to USD (for non-USD-profit symbols swap conversion).
# Operator can override with --rates EUR=1.07,GBP=1.30,...
DEFAULT_FX_RATES_TO_USD = {
    "USD": 1.0,
    "EUR": 1.07,
    "GBP": 1.30,
    "JPY": 0.0064,
    "AUD": 0.65,
    "CAD": 0.74,
    "CHF": 1.13,
    "NZD": 0.60,
    "HKD": 0.128,
    "CZK": 0.044,
    "HUF": 0.0028,
    "PLN": 0.25,
    "SEK": 0.094,
    "NOK": 0.094,
    "MXN": 0.057,
    "ZAR": 0.054,
    "ILS": 0.27,
    "SGD": 0.74,
    "CNH": 0.14,
}

# MT5 swap_3days numeric → weekday name
WEEKDAY_MAP = {0: "sunday", 1: "monday", 2: "tuesday", 3: "wednesday",
               4: "thursday", 5: "friday", 6: "saturday"}


def _convert_swap_to_usd_per_micro(
    swap_raw: float, contract_size: float, digits: int, profit_currency: str,
    fx_rates: dict[str, float],
) -> float:
    """USD per micro per night = swap × contract_size × 10^(-digits) / 100 × fx_rate.

    The /100 normalizes to per-min-lot (0.01 lot) which is our "1 micro"
    convention (matches The5ers config).
    """
    base = swap_raw * contract_size * (10.0 ** (-digits)) / 100.0
    rate = fx_rates.get(profit_currency.upper(), 1.0)
    return base * rate


def _read_csv_rows(csv_path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    with csv_path.open("r", encoding="utf-8") as fh:
        # Note: FTMO descriptions contain commas (e.g. "Crude Oil Brent, Spot CFD").
        # csv.DictReader handles that correctly with default quoting.
        reader = csv.DictReader(fh)
        for row in reader:
            rows[row["symbol"]] = row
    return rows


def build_yaml(csv_path: Path, fx_rates: dict[str, float]) -> str:
    csv_rows = _read_csv_rows(csv_path)

    lines: list[str] = []
    lines.append("# FTMO MT5 Per-Symbol Cost Overlay")
    lines.append("# =====================================================================")
    lines.append("# AUTO-GENERATED from FTMO Free Trial demo (FTMO-Demo server).")
    lines.append("# Source: scripts/ftmo_symbol_spec_export.mq5 -> ftmo_symbol_specs.csv")
    lines.append("# Conversion: scripts/import_ftmo_specs.py")
    lines.append(f"# CSV path: {csv_path}")
    lines.append("#")
    lines.append("# Convention (matches the5ers_mt5_specs.yaml):")
    lines.append("#   - 1 'micro' = 0.01 lot (MT5 min_lot for most symbols)")
    lines.append("#   - swap_long_per_micro = USD per 0.01 lot per night")
    lines.append("#   - For non-USD profit currencies, swap converted to USD via")
    lines.append("#     static FX rates (see _DEFAULT_FX_RATES_TO_USD).")
    lines.append("# =====================================================================")
    lines.append("")
    lines.append("firm:")
    lines.append('  name: "FTMO"')
    lines.append('  account_server: "FTMO-Demo"')
    lines.append('  mt5_hedge_mode: true')
    lines.append('  base_currency: "USD"')
    lines.append('  server_timezone: "Europe/Prague"')
    lines.append('  daily_dd_reset: "00:00 CE(S)T"')
    lines.append("")
    lines.append("# FTMO has no excluded markets — all common CFDs available.")
    lines.append("excluded_markets: []")
    lines.append("")

    for code, ftmo_sym in SYMBOL_MAP.items():
        if ftmo_sym not in csv_rows:
            lines.append(f"# {code}: FTMO symbol '{ftmo_sym}' not present in MT5 demo export — skipped")
            continue
        r = csv_rows[ftmo_sym]
        contract_size = float(r["contract_size"])
        digits = int(r["digits"])
        swap_long_raw = float(r["swap_long"])
        swap_short_raw = float(r["swap_short"])
        profit_curr = r["currency_profit"]

        swap_long_usd = _convert_swap_to_usd_per_micro(swap_long_raw, contract_size, digits, profit_curr, fx_rates)
        swap_short_usd = _convert_swap_to_usd_per_micro(swap_short_raw, contract_size, digits, profit_curr, fx_rates)

        spread_pts_raw = int(r["spread_typical_pts"])
        point = float(r["point"])
        spread_in_price = spread_pts_raw * point

        triple_day_idx = int(r["swap_3days_weekday"])
        triple_day = WEEKDAY_MAP.get(triple_day_idx, "friday")
        triple_multiplier = 3.0  # FTMO standard (no special 10x for CL like The5ers)

        # FX symbols: cfd_dollars_per_point=null in our convention
        cfd_dpp = CFD_DPP.get(code)

        lines.append(f"{code}:")
        lines.append(f'  cfd_symbol: "{ftmo_sym}"')
        lines.append(f'  description: "{r["description"].strip()}"')
        lines.append(f'  currency_profit: "{profit_curr}"')
        lines.append(f"  contract_size: {int(contract_size) if contract_size.is_integer() else contract_size}")
        lines.append(f"  digits: {digits}")
        lines.append(f"  futures_dollars_per_point: {FUTURES_DPP.get(code, 'null')}")
        lines.append(f"  cfd_dollars_per_point: {cfd_dpp if cfd_dpp is not None else 'null'}")
        lines.append(f"  min_lot: {float(r['min_lot'])}")
        lines.append(f"  lot_step: {float(r['lot_step'])}")
        lines.append(f"  max_lot: {float(r['max_lot'])}")
        lines.append(f"  stops_level_pts: {int(r['stops_level_pts'])}")
        lines.append(f'  spread_type: {"floating" if r["spread_floating"] == "true" else "fixed"}')
        lines.append(f"  typical_spread_pts: {round(spread_in_price, 6)}")
        lines.append(f"  commission_pct: 0.0  # FTMO commissions: zero on indices/FX/metals; not in MT5 export")
        lines.append(f"  execution: \"Market\"")
        lines.append(f"  swap_type: \"points\"  # MT5 SWAP_MODE = {r['swap_mode']}")
        lines.append(f"  swap_points_long: {swap_long_raw}")
        lines.append(f"  swap_points_short: {swap_short_raw}")
        lines.append(f"  swap_long_per_micro: {round(swap_long_usd, 6)}  # USD-converted from {profit_curr}")
        lines.append(f"  swap_short_per_micro: {round(swap_short_usd, 6)}")
        lines.append(f'  triple_day: "{triple_day}"')
        lines.append(f"  triple_multiplier: {triple_multiplier}")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="data/ftmo_symbol_specs.csv",
                        help="Path to FTMO MT5 export CSV")
    parser.add_argument("--out", default="configs/ftmo_mt5_specs.yaml",
                        help="Output YAML path")
    parser.add_argument("--rates", default="",
                        help="FX rate overrides as CCY=rate,CCY=rate (rate = USD per CCY)")
    args = parser.parse_args()

    csv_path = REPO_ROOT / args.csv if not Path(args.csv).is_absolute() else Path(args.csv)
    out_path = REPO_ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    if not csv_path.exists():
        print(f"ERROR: CSV not found: {csv_path}", file=sys.stderr)
        return 1

    fx_rates = dict(DEFAULT_FX_RATES_TO_USD)
    if args.rates:
        for tok in args.rates.split(","):
            ccy, rate = tok.split("=")
            fx_rates[ccy.strip().upper()] = float(rate)

    yaml_text = build_yaml(csv_path, fx_rates)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml_text, encoding="utf-8")
    print(f"Wrote {out_path} ({len(yaml_text)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
