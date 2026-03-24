from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

def load_tradestation_csv(filepath: str | Path, debug: bool = True) -> pd.DataFrame:
    """
    Loads TradeStation CSV exports, handling custom date/time formats,
    cleaning string artifacts, and enforcing the 2008 backtest start date.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        data_fallback = Path("Data") / filepath.name
        if not filepath.is_absolute() and data_fallback.exists():
            filepath = data_fallback
        else:
            raise FileNotFoundError(f"CSV not found: {filepath}")

    # Read as strings to control parsing
    df = pd.read_csv(filepath, dtype=str)

    # Clean column names (strip spaces and quotes)
    df.columns = [c.strip().strip('"').strip("'") for c in df.columns]

    required = {"Date", "Time", "Open", "High", "Low", "Close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}. Found: {list(df.columns)}")

    if debug:
        print("\n[LOADER DEBUG] Columns:", df.columns.tolist())

    # ---- Datetime parsing ----
    dt_text = df["Date"].astype(str).str.strip() + " " + df["Time"].astype(str).str.strip()

    dt_dayfirst = pd.to_datetime(dt_text, errors="coerce", dayfirst=True)
    dt_monthfirst = pd.to_datetime(dt_text, errors="coerce", dayfirst=False)

    nat_dayfirst = int(dt_dayfirst.isna().sum())
    nat_monthfirst = int(dt_monthfirst.isna().sum())

    # Choose the parse with fewer NaT (Not a Time)
    dt = dt_dayfirst if nat_dayfirst <= nat_monthfirst else dt_monthfirst

    # ---- Numeric helper ----
    def num(series: pd.Series) -> pd.Series:
        # strip quotes/spaces; remove commas
        x = (
            series.astype(str)
            .str.replace('"', "", regex=False)
            .str.replace(",", "", regex=False)
            .str.strip()
        )
        return pd.to_numeric(x, errors="coerce")

    open_ = num(df["Open"])
    high_ = num(df["High"])
    low_ = num(df["Low"])
    close_ = num(df["Close"])

    if "Volume" in df.columns:
        vol = num(df["Volume"]).fillna(0)
    elif "Up" in df.columns and "Down" in df.columns:
        vol = (num(df["Up"]).fillna(0) + num(df["Down"]).fillna(0))
    else:
        vol = pd.Series(np.zeros(len(df)), index=df.index)

    # ---- Construct DataFrame (Using .values to fix the index alignment bug) ----
    out = pd.DataFrame(
        {
            "open": open_.values, 
            "high": high_.values, 
            "low": low_.values, 
            "close": close_.values, 
            "volume": vol.values
        },
        index=dt,
    )
    out.index.name = "datetime"

    # ---- Clean and Filter ----
    out = out[~out.index.isna()]  # drop NaT datetimes
    out = out.dropna(subset=["open", "high", "low", "close"])  # drop bad OHLC rows
    out = out.sort_index()
    out = out[~out.index.duplicated(keep="last")]

    # Master Prompt Enforcement: Start Date 01 January 2008
    out = out.loc["2008-01-01":]

    if debug:
        print(f"[LOADER DEBUG] Final rows after cleaning and filtering: {len(out):,}")

    return out
