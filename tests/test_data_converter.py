"""
Tests for the TDS-to-TradeStation format converter.
These tests use inline sample data — no external files required.
"""
from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import pandas as pd
import pytest

# Import converter functions
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.convert_tds_to_engine import (
    convert_date,
    convert_time,
    convert_file,
    parse_tds_filename,
    SYMBOL_MAP,
    TIMEFRAME_MAP,
)


# ---------------------------------------------------------------------------
# Sample TDS data
# ---------------------------------------------------------------------------

SAMPLE_TDS_ROWS = """\
Date,Time,Open,High,Low,Close,Tick volume
2012.01.16,00:00:00,1290.9,1291.1,1288.1,1288.1,192
2012.01.16,01:00:00,1287.9,1288.4,1286.4,1287.4,214
2012.01.16,02:00:00,1287.6,1287.6,1286.6,1287.1,76
2025.12.31,23:00:00,5500.5,5510.0,5490.0,5505.0,1500
"""


def _write_tds_csv(path: Path, content: str = SAMPLE_TDS_ROWS) -> Path:
    """Write sample TDS CSV and return path."""
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Test: date conversion
# ---------------------------------------------------------------------------

class TestDateConversion:
    def test_basic_date(self):
        assert convert_date("2012.01.16") == "01/16/2012"

    def test_end_of_year(self):
        assert convert_date("2025.12.31") == "12/31/2025"

    def test_leading_zeros(self):
        assert convert_date("2008.03.05") == "03/05/2008"

    def test_first_day(self):
        assert convert_date("2020.01.01") == "01/01/2020"


# ---------------------------------------------------------------------------
# Test: time conversion
# ---------------------------------------------------------------------------

class TestTimeConversion:
    def test_strips_seconds(self):
        assert convert_time("00:00:00") == "00:00"

    def test_preserves_hours_minutes(self):
        assert convert_time("13:45:30") == "13:45"

    def test_midnight(self):
        assert convert_time("00:00:00") == "00:00"

    def test_end_of_day(self):
        assert convert_time("23:59:59") == "23:59"


# ---------------------------------------------------------------------------
# Test: header format
# ---------------------------------------------------------------------------

class TestHeaderFormat:
    def test_output_headers_match_tradestation(self, tmp_path):
        """Converted file must have exactly the quoted TradeStation headers."""
        tds_file = tmp_path / "USA_500_Index_GMT+0_NO-DST_H1.csv"
        _write_tds_csv(tds_file)
        out_dir = tmp_path / "out"
        convert_file(tds_file, out_dir)

        out_files = list(out_dir.glob("*.csv"))
        assert len(out_files) == 1

        with open(out_files[0], "r") as f:
            header = f.readline().strip()
        assert header == '"Date","Time","Open","High","Low","Close","Vol","OI"'

    def test_oi_column_is_zero(self, tmp_path):
        """OI column should be 0 for all rows."""
        tds_file = tmp_path / "USA_500_Index_GMT+0_NO-DST_D1.csv"
        _write_tds_csv(tds_file)
        out_dir = tmp_path / "out"
        convert_file(tds_file, out_dir)

        df = pd.read_csv(list(out_dir.glob("*.csv"))[0])
        assert (df["OI"] == 0).all()


# ---------------------------------------------------------------------------
# Test: empty/missing volume
# ---------------------------------------------------------------------------

class TestVolumeHandling:
    def test_missing_volume_defaults_zero(self, tmp_path):
        """If Tick volume is empty, Vol should be 0."""
        content = """\
Date,Time,Open,High,Low,Close,Tick volume
2012.01.16,00:00:00,1290.9,1291.1,1288.1,1288.1,
2012.01.16,01:00:00,1287.9,1288.4,1286.4,1287.4,214
"""
        tds_file = tmp_path / "USA_500_Index_GMT+0_NO-DST_H1.csv"
        _write_tds_csv(tds_file, content)
        out_dir = tmp_path / "out"
        convert_file(tds_file, out_dir)

        df = pd.read_csv(list(out_dir.glob("*.csv"))[0])
        assert df.iloc[0]["Vol"] == 0
        assert df.iloc[1]["Vol"] == 214

    def test_empty_file_skipped(self, tmp_path):
        """Empty TDS file should be skipped without error."""
        content = "Date,Time,Open,High,Low,Close,Tick volume\n"
        tds_file = tmp_path / "USA_500_Index_GMT+0_NO-DST_H1.csv"
        _write_tds_csv(tds_file, content)
        out_dir = tmp_path / "out"
        result = convert_file(tds_file, out_dir)
        assert "SKIPPED" in result["status"]


# ---------------------------------------------------------------------------
# Test: round-trip with engine loader
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_converted_file_loads_in_engine(self, tmp_path):
        """Converted file should load successfully with load_tradestation_csv()."""
        from modules.data_loader import load_tradestation_csv

        tds_file = tmp_path / "USA_500_Index_GMT+0_NO-DST_H1.csv"
        _write_tds_csv(tds_file)
        out_dir = tmp_path / "out"
        convert_file(tds_file, out_dir)

        out_files = list(out_dir.glob("*.csv"))
        df = load_tradestation_csv(out_files[0], debug=False)

        assert len(df) > 0
        assert set(df.columns) >= {"open", "high", "low", "close", "volume"}
        assert df.index.name == "datetime"
        # OHLC values should be present
        assert df["open"].iloc[0] == pytest.approx(1290.9)
        assert df["close"].iloc[0] == pytest.approx(1288.1)

    def test_ohlc_values_preserved(self, tmp_path):
        """OHLC values must survive the TDS -> TS conversion exactly."""
        tds_file = tmp_path / "USA_500_Index_GMT+0_NO-DST_D1.csv"
        _write_tds_csv(tds_file)
        out_dir = tmp_path / "out"
        convert_file(tds_file, out_dir)

        tds_df = pd.read_csv(tds_file)
        ts_df = pd.read_csv(list(out_dir.glob("*.csv"))[0])

        for col in ["Open", "High", "Low", "Close"]:
            tds_vals = pd.to_numeric(tds_df[col])
            ts_vals = pd.to_numeric(ts_df[col])
            assert tds_vals.tolist() == ts_vals.tolist(), f"{col} mismatch"


# ---------------------------------------------------------------------------
# Test: symbol name extraction
# ---------------------------------------------------------------------------

class TestSymbolExtraction:
    def test_simple_symbol(self):
        _, market, tf = parse_tds_filename("AUDUSD_GMT+0_NO-DST_H1.csv")
        assert market == "AD"
        assert tf == "60m"

    def test_multi_word_symbol(self):
        _, market, tf = parse_tds_filename("USA_500_Index_GMT+0_NO-DST_D1.csv")
        assert market == "ES"
        assert tf == "daily"

    def test_all_symbols_mapped(self):
        """Every symbol in the mapping table should parse correctly."""
        for tds_sym, market in SYMBOL_MAP.items():
            for tf_code, tf_label in TIMEFRAME_MAP.items():
                filename = f"{tds_sym}_GMT+0_NO-DST_{tf_code}.csv"
                _, parsed_market, parsed_tf = parse_tds_filename(filename)
                assert parsed_market == market
                assert parsed_tf == tf_label

    def test_unknown_symbol_raises(self):
        with pytest.raises(ValueError, match="Unknown TDS symbol"):
            parse_tds_filename("FAKESYMBOL_GMT+0_NO-DST_H1.csv")


# ---------------------------------------------------------------------------
# Test: timeframe detection
# ---------------------------------------------------------------------------

class TestTimeframeDetection:
    @pytest.mark.parametrize("tf_code,expected", [
        ("D1", "daily"),
        ("H1", "60m"),
        ("M30", "30m"),
        ("M15", "15m"),
        ("M5", "5m"),
        ("M1", "1m"),
    ])
    def test_timeframe_codes(self, tf_code, expected):
        _, _, tf = parse_tds_filename(f"EURUSD_GMT+0_NO-DST_{tf_code}.csv")
        assert tf == expected

    def test_unknown_timeframe_raises(self):
        with pytest.raises(ValueError, match="Unknown timeframe"):
            parse_tds_filename("EURUSD_GMT+0_NO-DST_W1.csv")


# ---------------------------------------------------------------------------
# Test: duplicate timestamp handling
# ---------------------------------------------------------------------------

class TestDuplicateHandling:
    def test_duplicate_timestamps_removed(self, tmp_path):
        """Duplicate timestamps should keep last occurrence."""
        content = """\
Date,Time,Open,High,Low,Close,Tick volume
2012.01.16,00:00:00,100.0,101.0,99.0,100.5,10
2012.01.16,00:00:00,200.0,201.0,199.0,200.5,20
2012.01.16,01:00:00,300.0,301.0,299.0,300.5,30
"""
        tds_file = tmp_path / "EURUSD_GMT+0_NO-DST_H1.csv"
        _write_tds_csv(tds_file, content)
        out_dir = tmp_path / "out"
        result = convert_file(tds_file, out_dir)

        df = pd.read_csv(list(out_dir.glob("*.csv"))[0])
        assert len(df) == 2  # duplicate removed
        # Should keep last occurrence (200.0 open)
        assert df.iloc[0]["Open"] == pytest.approx(200.0)
