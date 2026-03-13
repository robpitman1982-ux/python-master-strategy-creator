from __future__ import annotations

import numpy as np
import pandas as pd


def add_precomputed_features(
    data: pd.DataFrame,
    sma_lengths: list[int] | None = None,
    avg_range_lookbacks: list[int] | None = None,
    momentum_lookbacks: list[int] | None = None,
) -> pd.DataFrame:
    """
    Add reusable precomputed feature columns to the OHLCV dataframe.
    Now includes True Range (TR) and Average True Range (ATR) for dynamic scaling.
    """

    df = data.copy()

    sma_lengths = sma_lengths or []
    avg_range_lookbacks = avg_range_lookbacks or []
    momentum_lookbacks = momentum_lookbacks or []

    # -----------------------------
    # Basic reusable columns
    # -----------------------------
    df["bar_range"] = df["high"] - df["low"]
    df["prev_close"] = df["close"].shift(1)

    # -----------------------------
    # True Range & ATR Calculations
    # -----------------------------
    high_low = df["high"] - df["low"]
    high_prev_close = np.abs(df["high"] - df["prev_close"])
    low_prev_close = np.abs(df["low"] - df["prev_close"])
    
    df["true_range"] = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    # -----------------------------
    # SMA columns
    # -----------------------------
    for length in sma_lengths:
        col = f"sma_{length}"
        if col not in df.columns:
            df[col] = df["close"].rolling(length).mean()

    # -----------------------------
    # Average Range / ATR columns
    # -----------------------------
    for lookback in avg_range_lookbacks:
        # Standard average bar range
        avg_range_col = f"avg_range_{lookback}"
        if avg_range_col not in df.columns:
            df[avg_range_col] = df["bar_range"].rolling(lookback).mean()
            
        # Average True Range (ATR)
        atr_col = f"atr_{lookback}"
        if atr_col not in df.columns:
            df[atr_col] = df["true_range"].rolling(lookback).mean()

    # -----------------------------
    # Momentum columns
    # -----------------------------
    for lookback in momentum_lookbacks:
        diff_col = f"mom_diff_{lookback}"
        if diff_col not in df.columns:
            df[diff_col] = df["close"] - df["close"].shift(lookback)

    return df