from __future__ import annotations

import pytest

from modules.instrument_universe import (
    CFD_DUKASCOPY,
    FUTURES_TRADESTATION,
    InstrumentUniverseError,
    canonical_dukascopy_filename,
    validate_sweep_config,
)


def _base_config(
    *,
    universe: str,
    path: str,
    market: str = "ES",
    timeframe: str = "daily",
    tick_value: float = 0.01,
    dollars_per_point: float = 1.0,
) -> dict:
    return {
        "instrument_universe": universe,
        "datasets": [
            {
                "path": path,
                "market": market,
                "timeframe": timeframe,
            }
        ],
        "engine": {
            "tick_value": tick_value,
            "dollars_per_point": dollars_per_point,
        },
    }


def test_canonical_dukascopy_filename():
    assert canonical_dukascopy_filename("ES", "daily") == "ES_daily_dukascopy.csv"
    assert canonical_dukascopy_filename("NQ", "60m") == "NQ_60m_dukascopy.csv"


def test_valid_cfd_config_passes():
    cfg = _base_config(
        universe=CFD_DUKASCOPY,
        path="Data/ES_daily_dukascopy.csv",
    )
    assert validate_sweep_config(cfg) == CFD_DUKASCOPY


def test_cfd_config_rejects_futures_es_contract_values():
    cfg = _base_config(
        universe=CFD_DUKASCOPY,
        path="Data/ES_daily_dukascopy.csv",
        tick_value=12.50,
        dollars_per_point=50.0,
    )
    with pytest.raises(InstrumentUniverseError, match="requires dollars_per_point=1.0"):
        validate_sweep_config(cfg)


def test_cfd_config_rejects_stale_dated_dukascopy_basename():
    cfg = _base_config(
        universe=CFD_DUKASCOPY,
        path="Data/ES_daily_2012_2026_dukascopy.csv",
    )
    with pytest.raises(InstrumentUniverseError, match="basename must be"):
        validate_sweep_config(cfg)


def test_futures_config_rejects_dukascopy_path():
    cfg = _base_config(
        universe=FUTURES_TRADESTATION,
        path="Data/ES_daily_dukascopy.csv",
        tick_value=12.50,
        dollars_per_point=50.0,
    )
    with pytest.raises(InstrumentUniverseError, match="disagrees with dataset paths"):
        validate_sweep_config(cfg)


def test_valid_futures_config_passes():
    cfg = _base_config(
        universe=FUTURES_TRADESTATION,
        path="Data/ES_daily_2008_2026_tradestation.csv",
        tick_value=12.50,
        dollars_per_point=50.0,
    )
    assert validate_sweep_config(cfg) == FUTURES_TRADESTATION


def test_rejects_multi_market_sweep_config():
    cfg = _base_config(
        universe=CFD_DUKASCOPY,
        path="Data/ES_daily_dukascopy.csv",
    )
    cfg["datasets"].append(
        {
            "path": "Data/NQ_daily_dukascopy.csv",
            "market": "NQ",
            "timeframe": "daily",
        }
    )
    with pytest.raises(InstrumentUniverseError, match="exactly one market"):
        validate_sweep_config(cfg)


def test_cluster_runner_builds_canonical_cfd_config():
    from run_cluster_sweep import build_single_config

    config = build_single_config(
        market="NQ",
        timeframe="60m",
        market_spec={"data_files": {"60m": "legacy_name.csv"}, "engine": {"tick_value": 0.01, "dollars_per_point": 1.0}},
        data_dir="/data/market_data/cfds/ohlc_engine",
        workers=36,
    )

    assert config["instrument_universe"] == CFD_DUKASCOPY
    assert config["datasets"][0]["path"].endswith("NQ_60m_dukascopy.csv")
    assert validate_sweep_config(config) == CFD_DUKASCOPY
