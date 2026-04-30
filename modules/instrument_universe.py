from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class InstrumentUniverseError(ValueError):
    """Raised when a sweep config mixes data source and instrument economics."""


@dataclass(frozen=True)
class InstrumentSpec:
    market: str
    tick_value: float
    dollars_per_point: float
    description: str


FUTURES_TRADESTATION = "futures_tradestation"
CFD_DUKASCOPY = "cfd_dukascopy"


FUTURES_SPECS: dict[str, InstrumentSpec] = {
    "ES": InstrumentSpec("ES", 12.50, 50.0, "E-mini S&P 500 futures"),
    "NQ": InstrumentSpec("NQ", 5.00, 20.0, "E-mini Nasdaq futures"),
    "YM": InstrumentSpec("YM", 5.00, 5.0, "Dow futures"),
    "RTY": InstrumentSpec("RTY", 5.00, 50.0, "Russell 2000 futures"),
    "GC": InstrumentSpec("GC", 10.00, 100.0, "Gold futures"),
    "SI": InstrumentSpec("SI", 25.00, 5000.0, "Silver futures"),
    "HG": InstrumentSpec("HG", 12.50, 25000.0, "Copper futures"),
    "CL": InstrumentSpec("CL", 10.00, 1000.0, "Crude oil futures"),
}


# Verified from modules/cfd_mapping.py / The5ers MT5 specs for symbols the
# project actively maps to MT5. Other Dukascopy CFDs can still be swept, but are
# treated as unverified until their execution contract is captured.
CFD_DUKASCOPY_SPECS: dict[str, InstrumentSpec] = {
    "ES": InstrumentSpec("ES", 0.01, 1.0, "SP500 CFD, 1 lot = $1/point"),
    "NQ": InstrumentSpec("NQ", 0.01, 1.0, "NAS100 CFD, 1 lot = $1/point"),
    "YM": InstrumentSpec("YM", 0.01, 1.0, "US30 CFD, 1 lot = $1/point"),
    "GC": InstrumentSpec("GC", 1.00, 100.0, "XAUUSD CFD, 1 lot = 100 oz"),
    "SI": InstrumentSpec("SI", 5.00, 5000.0, "XAGUSD CFD, 1 lot = 5000 oz"),
    "CL": InstrumentSpec("CL", 1.00, 100.0, "XTIUSD CFD, 1 lot = 100 barrels"),
}


def infer_universe_from_paths(datasets: list[dict[str, Any]]) -> str | None:
    """Infer a price-source universe from dataset path names."""
    path_text = " ".join(str(ds.get("path", "")).lower() for ds in datasets)
    if "dukascopy" in path_text or "/cfds/" in path_text or "\\cfds\\" in path_text:
        return CFD_DUKASCOPY
    if "tradestation" in path_text or "/futures/" in path_text or "\\futures\\" in path_text:
        return FUTURES_TRADESTATION
    return None


def get_declared_universe(config: dict[str, Any]) -> str | None:
    """Read the explicit universe marker from a sweep/engine config."""
    for key in ("instrument_universe", "universe", "price_source"):
        value = config.get(key)
        if value:
            return str(value)

    sweep_meta = config.get("sweep", {})
    if isinstance(sweep_meta, dict):
        for key in ("instrument_universe", "universe", "price_source"):
            value = sweep_meta.get(key)
            if value:
                return str(value)

    return None


def canonical_dukascopy_filename(market: str, timeframe: str) -> str:
    """Return the canonical converted CFD OHLC basename on c240."""
    return f"{market}_{timeframe}_dukascopy.csv"


def _as_float(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise InstrumentUniverseError(f"engine.{field} must be numeric, got {value!r}") from exc


def _close_enough(actual: float, expected: float) -> bool:
    return abs(actual - expected) <= max(1e-9, abs(expected) * 1e-9)


def _path_source_label(path: str) -> str | None:
    text = path.lower().replace("\\", "/")
    if "dukascopy" in text or "/cfds/" in text:
        return CFD_DUKASCOPY
    if "tradestation" in text or "/futures/" in text:
        return FUTURES_TRADESTATION
    return None


def _effective_dataset_path(dataset_path: str, data_dir: str | None = None) -> Path:
    if data_dir:
        return Path(data_dir) / Path(dataset_path).name
    return Path(dataset_path)


def validate_sweep_config(
    config: dict[str, Any],
    *,
    data_dir: str | None = None,
    require_existing_data: bool = False,
) -> str:
    """Validate that a sweep config does not mix futures and CFD universes.

    Returns the resolved universe string. Raises InstrumentUniverseError on
    ambiguity or dangerous source/economics mismatches.
    """
    datasets = config.get("datasets") or []
    if not isinstance(datasets, list) or not datasets:
        raise InstrumentUniverseError("config must contain at least one dataset")

    declared = get_declared_universe(config)
    inferred = infer_universe_from_paths(datasets)
    universe = declared or inferred
    if universe is None:
        raise InstrumentUniverseError(
            "instrument universe is ambiguous; set instrument_universe to "
            f"{FUTURES_TRADESTATION!r} or {CFD_DUKASCOPY!r}"
        )

    if universe not in {FUTURES_TRADESTATION, CFD_DUKASCOPY}:
        raise InstrumentUniverseError(
            f"unknown instrument_universe {universe!r}; expected "
            f"{FUTURES_TRADESTATION!r} or {CFD_DUKASCOPY!r}"
        )

    if declared and inferred and declared != inferred:
        raise InstrumentUniverseError(
            f"declared universe {declared!r} disagrees with dataset paths "
            f"which look like {inferred!r}"
        )

    engine = config.get("engine") or {}
    dpp = _as_float(engine.get("dollars_per_point"), "dollars_per_point")
    tick_value = _as_float(engine.get("tick_value"), "tick_value")
    if dpp <= 0 or tick_value <= 0:
        raise InstrumentUniverseError("engine dollars_per_point and tick_value must be positive")

    markets = {str(ds.get("market", "")).upper() for ds in datasets if ds.get("market")}
    if len(markets) != 1:
        raise InstrumentUniverseError(
            "each sweep config must contain exactly one market; "
            f"found {sorted(markets) or 'none'}"
        )
    market = next(iter(markets))

    specs = FUTURES_SPECS if universe == FUTURES_TRADESTATION else CFD_DUKASCOPY_SPECS
    spec = specs.get(market)
    if spec is not None:
        if not _close_enough(dpp, spec.dollars_per_point):
            raise InstrumentUniverseError(
                f"{market} {universe} requires dollars_per_point="
                f"{spec.dollars_per_point}, got {dpp}. {spec.description}"
            )
        if not _close_enough(tick_value, spec.tick_value):
            raise InstrumentUniverseError(
                f"{market} {universe} requires tick_value={spec.tick_value}, "
                f"got {tick_value}. {spec.description}"
            )

    for ds in datasets:
        raw_path = str(ds.get("path", ""))
        effective_path = _effective_dataset_path(raw_path, data_dir)
        label = _path_source_label(str(effective_path)) or _path_source_label(raw_path)
        if label and label != universe:
            raise InstrumentUniverseError(
                f"dataset path {effective_path} looks like {label!r}, "
                f"but config universe is {universe!r}"
            )

        if universe == CFD_DUKASCOPY:
            expected_name = canonical_dukascopy_filename(
                str(ds.get("market", "")).upper(),
                str(ds.get("timeframe", "")),
            )
            if Path(raw_path).name != expected_name:
                raise InstrumentUniverseError(
                    f"CFD Dukascopy dataset basename must be {expected_name!r}; "
                    f"got {Path(raw_path).name!r}. Regenerate CFD configs from "
                    "configs/cfd_markets.yaml."
                )

        if require_existing_data and not effective_path.exists():
            raise InstrumentUniverseError(f"dataset file not found: {effective_path}")

    return universe

