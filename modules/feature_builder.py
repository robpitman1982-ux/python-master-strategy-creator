from __future__ import annotations

import pandas as pd


def add_precomputed_features(
    data: pd.DataFrame,
    sma_lengths: list[int] | None = None,
    avg_range_lookbacks: list[int] | None = None,
    momentum_lookbacks: list[int] | None = None,
) -> pd.DataFrame:
    """
    Add reusable precomputed feature columns to the OHLCV dataframe.

    This reduces repeated rolling calculations during:
    - filter combination sweeps
    - parameter refinement
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
    # SMA columns
    # -----------------------------
    for length in sma_lengths:
        col = f"sma_{length}"
        if col not in df.columns:
            df[col] = df["close"].rolling(length).mean()

    # -----------------------------
    # Average range columns
    # -----------------------------
    for lookback in avg_range_lookbacks:
        col = f"avg_range_{lookback}"
        if col not in df.columns:
            df[col] = df["bar_range"].rolling(lookback).mean()

    # -----------------------------
    # Momentum columns
    # -----------------------------
    for lookback in momentum_lookbacks:
        diff_col = f"mom_diff_{lookback}"
        if diff_col not in df.columns:
            df[diff_col] = df["close"] - df["close"].shift(lookback)

    return df