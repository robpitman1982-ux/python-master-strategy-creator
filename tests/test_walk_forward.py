"""Tests for modules.walk_forward — rolling-window validation."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from modules.walk_forward import (
    WalkForwardResult,
    annotate_dataframe_with_walk_forward,
    compute_walk_forward,
)


def _synthetic_trades(
    start: str,
    n_per_year: int,
    years: int,
    mean_pnl: float,
    std_pnl: float,
    seed: int = 0,
) -> pd.DataFrame:
    """Generate a synthetic trades DataFrame across `years` years."""
    rng = np.random.default_rng(seed)
    start_ts = pd.Timestamp(start)
    n_total = n_per_year * years
    days_offsets = np.linspace(0, years * 365, n_total).astype(int)
    times = pd.to_datetime([start_ts + pd.Timedelta(days=int(d)) for d in days_offsets])
    pnls = rng.normal(mean_pnl, std_pnl, size=n_total)
    return pd.DataFrame({"exit_time": times, "net_pnl": pnls})


def _trades_with_regime_shift(
    start: str,
    n_per_year: int,
    early_years: int,
    early_mean: float,
    late_years: int,
    late_mean: float,
    std_pnl: float = 50.0,
    seed: int = 0,
) -> pd.DataFrame:
    early = _synthetic_trades(start, n_per_year, early_years, early_mean, std_pnl, seed)
    late_start = pd.Timestamp(start) + pd.DateOffset(years=early_years)
    late = _synthetic_trades(
        late_start.strftime("%Y-%m-%d"), n_per_year, late_years, late_mean, std_pnl, seed + 1
    )
    return pd.concat([early, late], ignore_index=True).sort_values("exit_time").reset_index(drop=True)


# -----------------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------------

def test_empty_df_returns_zero_result():
    result = compute_walk_forward(pd.DataFrame())
    assert isinstance(result, WalkForwardResult)
    assert result.n_windows == 0
    assert result.passes_gate() is False


def test_missing_columns_returns_zero_result():
    df = pd.DataFrame({"foo": [1, 2, 3]})
    result = compute_walk_forward(df)
    assert result.n_windows == 0


def test_short_history_no_windows():
    """Span < train_years + test_years → 0 windows."""
    df = _synthetic_trades("2020-01-01", 100, years=2, mean_pnl=10.0, std_pnl=50.0)
    # Default 3+1 needs 4 years span
    result = compute_walk_forward(df)
    assert result.n_windows == 0


def test_sparse_trades_skip_windows():
    """Windows with < min_trades_per_window get skipped."""
    df = _synthetic_trades("2015-01-01", 5, years=10, mean_pnl=10.0, std_pnl=50.0)
    # 50 total trades / 10 years = 5/year. min_trades_per_window=20 means
    # most windows will be skipped because train (3yr * 5/yr = 15) is below 20.
    result = compute_walk_forward(df, min_trades_per_window=20)
    # Should be 0 valid windows
    assert result.n_windows == 0


def test_strategy_with_no_pnl_column():
    df = pd.DataFrame({
        "exit_time": pd.to_datetime(["2020-01-01", "2021-01-01"]),
    })
    result = compute_walk_forward(df)
    assert result.n_windows == 0


# -----------------------------------------------------------------------------
# Constant positive alpha (the "real edge" case)
# -----------------------------------------------------------------------------

def test_constant_positive_alpha_passes():
    """Strategy with steady positive edge over 10 years should pass walk-forward."""
    df = _synthetic_trades("2014-01-01", 200, years=10, mean_pnl=10.0, std_pnl=50.0, seed=42)
    result = compute_walk_forward(df, train_years=3, test_years=1, step_years=1)
    assert result.n_windows >= 6  # 10 years span - 4 = 6 windows minimum
    assert result.mean_test_t > 1.0
    assert result.min_test_t > 0.0  # all positive
    assert result.passes_gate(min_mean_t=1.0, min_min_t=-0.5, min_windows=3) is True


def test_constant_positive_alpha_train_test_correlated():
    """Stationary edge → train and test t's should correlate moderately."""
    df = _synthetic_trades("2014-01-01", 200, years=10, mean_pnl=10.0, std_pnl=50.0, seed=42)
    result = compute_walk_forward(df)
    # With pure stationary noise, train and test should be similarly positive
    # but may not be highly correlated window-to-window. Just check it's not
    # severely negative (which would indicate inverted relationship).
    assert result.train_test_t_correlation > -0.3


# -----------------------------------------------------------------------------
# Regime change (the "looks great then dies" case)
# -----------------------------------------------------------------------------

def test_regime_shift_caught_by_min_t():
    """Strong edge for 5 years then dies: mean_t may be positive but min_t fails."""
    df = _trades_with_regime_shift(
        "2014-01-01",
        n_per_year=200,
        early_years=5, early_mean=15.0,
        late_years=5, late_mean=-5.0,
        std_pnl=50.0,
        seed=42,
    )
    result = compute_walk_forward(df)
    assert result.n_windows >= 4
    # Late windows should have negative test_t
    assert result.min_test_t < 0.0
    # Strict gate (default min_min_t=-0.5) catches this
    assert result.passes_gate(min_mean_t=1.0, min_min_t=-0.5, min_windows=3) is False


def test_pure_noise_fails():
    """No edge anywhere: mean_t around 0, fails gate."""
    df = _synthetic_trades("2014-01-01", 200, years=10, mean_pnl=0.0, std_pnl=100.0, seed=42)
    result = compute_walk_forward(df)
    assert result.n_windows >= 6
    assert abs(result.mean_test_t) < 1.0  # no real signal
    assert result.passes_gate(min_mean_t=1.0) is False


def test_decaying_signal():
    """Strong-then-weak: detects the decay."""
    df = _trades_with_regime_shift(
        "2014-01-01",
        n_per_year=200,
        early_years=4, early_mean=20.0,
        late_years=6, late_mean=2.0,  # weak but still positive
        std_pnl=50.0,
        seed=42,
    )
    result = compute_walk_forward(df)
    # First windows (which test the early period) should be much stronger
    # than later windows (which test the weak period).
    early_test_ts = [w.test_t for w in result.windows[:2]]
    late_test_ts = [w.test_t for w in result.windows[-2:]]
    if early_test_ts and late_test_ts:
        assert max(early_test_ts) > max(late_test_ts)


# -----------------------------------------------------------------------------
# Window math sanity
# -----------------------------------------------------------------------------

def test_window_count_matches_span():
    """For 10-year span with 3+1 windows stepping 1 year, expect ~6 windows."""
    df = _synthetic_trades("2014-01-01", 200, years=10, mean_pnl=5.0, std_pnl=50.0)
    result = compute_walk_forward(df, train_years=3, test_years=1, step_years=1)
    # 10 years span, train+test=4, step=1: 10-4+1 = 7 possible starts but
    # last one may not fit if rounding cuts it off. Allow 6-7.
    assert 6 <= result.n_windows <= 7


def test_step_years_2_halves_windows():
    df = _synthetic_trades("2014-01-01", 200, years=10, mean_pnl=5.0, std_pnl=50.0)
    r1 = compute_walk_forward(df, train_years=3, test_years=1, step_years=1)
    r2 = compute_walk_forward(df, train_years=3, test_years=1, step_years=2)
    assert r2.n_windows < r1.n_windows


def test_train_years_5_test_years_2():
    df = _synthetic_trades("2010-01-01", 200, years=15, mean_pnl=10.0, std_pnl=50.0)
    result = compute_walk_forward(df, train_years=5, test_years=2, step_years=1)
    assert result.n_windows >= 5
    # First train window: 2010-01-01 to 2015-01-01
    # First test window:  2015-01-01 to 2017-01-01
    first = result.windows[0]
    assert first.train_start.year == 2010
    assert first.train_end.year == 2015
    assert first.test_end.year == 2017


# -----------------------------------------------------------------------------
# Aggregation correctness
# -----------------------------------------------------------------------------

def test_mean_min_median_consistency():
    df = _synthetic_trades("2014-01-01", 200, years=12, mean_pnl=8.0, std_pnl=50.0)
    result = compute_walk_forward(df)
    test_ts = [w.test_t for w in result.windows]
    if len(test_ts) >= 2:
        assert math.isclose(result.mean_test_t, float(np.mean(test_ts)), rel_tol=1e-9)
        assert result.min_test_t == min(test_ts)
        assert math.isclose(result.median_test_t, float(np.median(test_ts)), rel_tol=1e-9)


def test_to_dict_format():
    df = _synthetic_trades("2014-01-01", 200, years=10, mean_pnl=10.0, std_pnl=50.0)
    result = compute_walk_forward(df)
    d = result.to_dict()
    assert set(d.keys()) == {
        "wf_n_windows", "wf_mean_test_t", "wf_min_test_t",
        "wf_median_test_t", "wf_train_test_corr",
    }


def test_passes_gate_thresholds():
    """Same result, different threshold settings → different verdicts."""
    df = _synthetic_trades("2014-01-01", 200, years=10, mean_pnl=5.0, std_pnl=50.0)
    result = compute_walk_forward(df)
    # Loose gate
    assert result.passes_gate(min_mean_t=0.0, min_min_t=-2.0, min_windows=2) is True
    # Strict gate (likely fails on this modest signal)
    assert result.passes_gate(min_mean_t=3.0, min_min_t=2.0, min_windows=10) is False


# -----------------------------------------------------------------------------
# DataFrame annotation
# -----------------------------------------------------------------------------

def test_annotate_leaderboard_with_walk_forward():
    leaderboard = pd.DataFrame({
        "leader_strategy_name": ["StratA", "StratB"],
        "leader_pf": [1.5, 1.2],
    })
    trades_a = _synthetic_trades("2014-01-01", 200, years=10, mean_pnl=10.0, std_pnl=50.0, seed=1)
    trades_b = _synthetic_trades("2014-01-01", 200, years=10, mean_pnl=0.0, std_pnl=50.0, seed=2)

    annotate_dataframe_with_walk_forward(
        leaderboard,
        trades_by_strategy={"StratA": trades_a, "StratB": trades_b},
    )

    assert "wf_n_windows" in leaderboard.columns
    assert "wf_mean_test_t" in leaderboard.columns
    assert "wf_passes" in leaderboard.columns
    # Real signal A should pass; noise B should not
    assert bool(leaderboard.loc[0, "wf_passes"]) is True
    assert bool(leaderboard.loc[1, "wf_passes"]) is False


def test_annotate_missing_strategy_gets_zero():
    leaderboard = pd.DataFrame({
        "leader_strategy_name": ["StratA", "MissingStrat"],
    })
    trades_a = _synthetic_trades("2014-01-01", 200, years=10, mean_pnl=10.0, std_pnl=50.0)

    annotate_dataframe_with_walk_forward(
        leaderboard,
        trades_by_strategy={"StratA": trades_a},
    )
    assert leaderboard.loc[1, "wf_n_windows"] == 0
    assert bool(leaderboard.loc[1, "wf_passes"]) is False


def test_annotate_empty_df_is_noop():
    df = pd.DataFrame()
    result = annotate_dataframe_with_walk_forward(df, {})
    assert result is df


def test_annotate_missing_strategy_col_is_noop():
    df = pd.DataFrame({"foo": [1, 2]})
    result = annotate_dataframe_with_walk_forward(df, {})
    assert "wf_n_windows" not in result.columns
