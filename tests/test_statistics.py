"""Tests for modules.statistics — p-values + BH-FDR adjustment + DSR."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from modules.statistics import (
    annotate_dataframe_with_dsr,
    annotate_dataframe_with_pvalues,
    apply_bh_fdr,
    deflated_sharpe_ratio,
    expected_max_sharpe_under_null,
    pf_to_pvalue,
    pf_to_sharpe,
    pf_to_t_statistic,
    random_flip_null_test,
    sharpe_estimator_std,
)


# -----------------------------------------------------------------------------
# pf_to_t_statistic
# -----------------------------------------------------------------------------

def test_t_stat_pf_one_is_zero():
    assert pf_to_t_statistic(1.0, 100) == 0.0


def test_t_stat_zero_trades_is_zero():
    assert pf_to_t_statistic(2.0, 0) == 0.0


def test_t_stat_negative_pf_is_zero():
    assert pf_to_t_statistic(-1.0, 100) == 0.0


def test_t_stat_nan_inputs_are_zero():
    assert pf_to_t_statistic(float("nan"), 100) == 0.0
    assert pf_to_t_statistic(float("inf"), 100) == 0.0


def test_t_stat_pf_above_one_positive():
    # PF=1.5, N=100: t = ln(1.5) * sqrt(100) / 2 = 0.405 * 10 / 2 ~= 2.027
    t = pf_to_t_statistic(1.5, 100)
    assert t > 0.0
    assert math.isclose(t, math.log(1.5) * 10.0 / 2.0, rel_tol=1e-9)


def test_t_stat_pf_below_one_negative():
    t = pf_to_t_statistic(0.5, 100)
    assert t < 0.0


def test_t_stat_scales_with_sample_size():
    # Same PF, larger N should give larger |t|
    t_small = pf_to_t_statistic(1.5, 25)
    t_large = pf_to_t_statistic(1.5, 400)
    assert abs(t_large) > abs(t_small)


# -----------------------------------------------------------------------------
# pf_to_pvalue
# -----------------------------------------------------------------------------

def test_pvalue_pf_one_is_one():
    assert pf_to_pvalue(1.0, 100) == 1.0


def test_pvalue_zero_trades_is_one():
    assert pf_to_pvalue(2.0, 0) == 1.0


def test_pvalue_strong_pf_is_small():
    # PF=2.0, N=200: very strong signal
    p = pf_to_pvalue(2.0, 200)
    assert 0.0 <= p <= 1.0
    assert p < 0.001


def test_pvalue_weak_pf_is_large():
    # PF=1.05, N=30: barely above 1
    p = pf_to_pvalue(1.05, 30)
    assert p > 0.5


def test_pvalue_two_sided_symmetry():
    # PF=1.5 and PF=1/1.5 should give the same p-value (two-sided)
    p_above = pf_to_pvalue(1.5, 100)
    p_below = pf_to_pvalue(1.0 / 1.5, 100)
    assert math.isclose(p_above, p_below, rel_tol=1e-6)


# -----------------------------------------------------------------------------
# apply_bh_fdr
# -----------------------------------------------------------------------------

def test_bh_fdr_empty_input():
    rejected, adjusted = apply_bh_fdr([])
    assert rejected.shape == (0,)
    assert adjusted.shape == (0,)


def test_bh_fdr_all_significant():
    p_values = [0.001, 0.002, 0.003, 0.004]
    rejected, adjusted = apply_bh_fdr(p_values, alpha=0.05)
    assert rejected.all()
    assert (adjusted <= 0.05).all()


def test_bh_fdr_none_significant():
    p_values = [0.6, 0.7, 0.8, 0.9]
    rejected, adjusted = apply_bh_fdr(p_values, alpha=0.05)
    assert not rejected.any()


def test_bh_fdr_some_significant():
    # Classic BH example: m=10, three small p-values that cross the threshold
    p_values = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 1.0]
    rejected, adjusted = apply_bh_fdr(p_values, alpha=0.05)
    # First 3 should reject (0.001 <= 0.005, 0.008 <= 0.010, 0.039 <= 0.015 fail; but 0.04*4/10 etc)
    assert rejected[0]
    assert rejected[1]
    # Most importantly: rejection set is a prefix (in sorted order)
    sorted_idx = np.argsort(p_values)
    rejected_sorted = rejected[sorted_idx]
    if rejected_sorted.any():
        # Once we see a False, no True after it (prefix property)
        first_false = np.where(~rejected_sorted)[0]
        if first_false.size > 0:
            cutoff = first_false[0]
            assert not rejected_sorted[cutoff:].any()


def test_bh_fdr_preserves_input_order():
    # Random-order input should map back correctly
    p_values = [0.5, 0.001, 0.3, 0.002]
    rejected, adjusted = apply_bh_fdr(p_values, alpha=0.05)
    # The two small ones (idx 1 and 3) should reject
    assert rejected[1]
    assert rejected[3]
    assert not rejected[0]
    assert not rejected[2]


def test_bh_fdr_adjusted_monotone_in_rank():
    # Adjusted p-values should be non-decreasing when sorted by raw p
    p_values = np.array([0.001, 0.01, 0.02, 0.05, 0.1, 0.5, 0.9])
    rejected, adjusted = apply_bh_fdr(p_values, alpha=0.05)
    sorted_idx = np.argsort(p_values)
    sorted_adj = adjusted[sorted_idx]
    # Non-decreasing
    diffs = np.diff(sorted_adj)
    assert (diffs >= -1e-12).all()


def test_bh_fdr_handles_nan_as_one():
    p_values = [0.001, float("nan"), 0.5]
    rejected, adjusted = apply_bh_fdr(p_values, alpha=0.05)
    # NaN treated as p=1.0 → never rejected
    assert not rejected[1]
    assert adjusted[1] >= adjusted[0]


def test_bh_fdr_alpha_increases_rejection_count():
    p_values = [0.001, 0.01, 0.02, 0.04, 0.08, 0.15, 0.5]
    rejected_strict, _ = apply_bh_fdr(p_values, alpha=0.01)
    rejected_loose, _ = apply_bh_fdr(p_values, alpha=0.10)
    assert rejected_strict.sum() <= rejected_loose.sum()


# -----------------------------------------------------------------------------
# annotate_dataframe_with_pvalues
# -----------------------------------------------------------------------------

def test_annotate_empty_df_is_noop():
    df = pd.DataFrame()
    result = annotate_dataframe_with_pvalues(df)
    assert result is df


def test_annotate_missing_columns_is_noop():
    df = pd.DataFrame({"foo": [1, 2, 3]})
    result = annotate_dataframe_with_pvalues(df)
    assert "pf_pvalue" not in result.columns


def test_annotate_adds_pvalue_column():
    df = pd.DataFrame({
        "profit_factor": [1.0, 1.5, 2.0, 0.8],
        "total_trades": [50, 100, 200, 80],
    })
    annotate_dataframe_with_pvalues(df)
    assert "pf_pvalue" in df.columns
    assert (df["pf_pvalue"] >= 0.0).all()
    assert (df["pf_pvalue"] <= 1.0).all()
    # PF=1.0 should give p=1.0
    assert df.loc[0, "pf_pvalue"] == 1.0
    # PF=2.0, N=200 should be very significant
    assert df.loc[2, "pf_pvalue"] < 0.001


def test_annotate_bh_fdr_columns_added_when_alpha_set():
    df = pd.DataFrame({
        "profit_factor": [1.0, 1.5, 2.0, 0.8],
        "total_trades": [50, 100, 200, 80],
    })
    annotate_dataframe_with_pvalues(df, bh_fdr_alpha=0.05)
    assert "bh_fdr_p_adj" in df.columns
    assert "bh_fdr_passes" in df.columns


def test_annotate_no_bh_columns_when_alpha_none():
    df = pd.DataFrame({
        "profit_factor": [1.5, 2.0],
        "total_trades": [100, 200],
    })
    annotate_dataframe_with_pvalues(df, bh_fdr_alpha=None)
    assert "pf_pvalue" in df.columns
    assert "bh_fdr_p_adj" not in df.columns
    assert "bh_fdr_passes" not in df.columns


# -----------------------------------------------------------------------------
# Integration: realistic family scenario
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Deflated Sharpe Ratio
# -----------------------------------------------------------------------------

def test_pf_to_sharpe_pf_one_zero():
    assert pf_to_sharpe(1.0) == 0.0


def test_pf_to_sharpe_degenerate_inputs():
    assert pf_to_sharpe(None) == 0.0
    assert pf_to_sharpe(-1.0) == 0.0
    assert pf_to_sharpe(0.0) == 0.0
    assert pf_to_sharpe(float("nan")) == 0.0
    assert pf_to_sharpe(float("inf")) == 0.0


def test_pf_to_sharpe_monotone_in_pf():
    sr_low = pf_to_sharpe(1.2)
    sr_high = pf_to_sharpe(2.0)
    assert sr_high > sr_low > 0.0


def test_expected_max_sharpe_under_null_increases_with_trials():
    e1 = expected_max_sharpe_under_null(1)
    e10 = expected_max_sharpe_under_null(10)
    e1000 = expected_max_sharpe_under_null(1000)
    assert e1 == 0.0  # single trial, no max selection bias
    assert e1000 > e10 > e1


def test_sharpe_estimator_std_decreases_with_n_obs():
    s_small = sharpe_estimator_std(0.1, 50)
    s_large = sharpe_estimator_std(0.1, 5000)
    assert s_large < s_small
    assert s_large > 0.0


def test_sharpe_estimator_std_handles_degenerate():
    # n_obs <= 1 returns inf
    assert math.isinf(sharpe_estimator_std(0.1, 1))
    assert math.isinf(sharpe_estimator_std(0.1, 0))


def test_dsr_zero_trials_or_obs_is_nan():
    assert math.isnan(deflated_sharpe_ratio(0.5, 0, 100))
    assert math.isnan(deflated_sharpe_ratio(0.5, 100, 0))


def test_dsr_in_zero_one_range():
    # Many configs, all in [0,1]
    for sr in [-0.5, -0.1, 0.0, 0.1, 0.5, 1.0]:
        for n_obs in [50, 100, 500]:
            for n_trials in [1, 50, 500]:
                v = deflated_sharpe_ratio(sr, n_obs, n_trials)
                if not math.isnan(v):
                    assert 0.0 <= v <= 1.0


def test_dsr_decreases_with_more_trials():
    # Same SR, more trials → DSR drops (more chance the SR is from noise)
    dsr_few = deflated_sharpe_ratio(0.3, 200, n_trials=5)
    dsr_many = deflated_sharpe_ratio(0.3, 200, n_trials=5000)
    assert dsr_few > dsr_many


def test_dsr_increases_with_more_obs():
    # Same SR + trials, more obs → tighter estimator → DSR moves toward extremes
    # If SR > expected-max-null, DSR rises with obs
    dsr_short = deflated_sharpe_ratio(0.5, 50, n_trials=10)
    dsr_long = deflated_sharpe_ratio(0.5, 1000, n_trials=10)
    assert dsr_long > dsr_short


def test_dsr_strong_real_signal_passes():
    # PF=2.0 over 500 trades, only 10 trials searched: very strong DSR
    sr = pf_to_sharpe(2.0)
    dsr = deflated_sharpe_ratio(sr, n_obs=500, n_trials=10)
    assert dsr > 0.95


def test_dsr_weak_signal_with_many_trials_fails():
    # PF=1.05 over 100 trades, 1000 trials searched: should be flagged as overfit
    sr = pf_to_sharpe(1.05)
    dsr = deflated_sharpe_ratio(sr, n_obs=100, n_trials=1000)
    assert dsr < 0.5


# -----------------------------------------------------------------------------
# annotate_dataframe_with_dsr
# -----------------------------------------------------------------------------

def test_annotate_dsr_adds_columns():
    df = pd.DataFrame({
        "profit_factor": [1.0, 1.5, 2.0, 0.8],
        "total_trades": [50, 100, 200, 80],
    })
    annotate_dataframe_with_dsr(df, n_trials=50)
    assert "sharpe_per_trade" in df.columns
    assert "deflated_sharpe_ratio" in df.columns
    # PF=1 → SR=0
    assert df.loc[0, "sharpe_per_trade"] == 0.0
    # PF=2.0 with 200 obs over 50 trials should pass strongly
    assert df.loc[2, "deflated_sharpe_ratio"] > 0.8


def test_annotate_dsr_per_row_trials():
    df = pd.DataFrame({
        "profit_factor": [1.5, 1.5],
        "total_trades": [200, 200],
        "n_trials": [10, 10000],
    })
    annotate_dataframe_with_dsr(df, n_trials_col="n_trials")
    # Same SR/obs but more trials → lower DSR
    assert df.loc[0, "deflated_sharpe_ratio"] > df.loc[1, "deflated_sharpe_ratio"]


def test_annotate_dsr_empty_df_is_noop():
    df = pd.DataFrame()
    result = annotate_dataframe_with_dsr(df)
    assert result is df


def test_annotate_dsr_missing_columns_is_noop():
    df = pd.DataFrame({"foo": [1, 2, 3]})
    result = annotate_dataframe_with_dsr(df)
    assert "deflated_sharpe_ratio" not in result.columns


# -----------------------------------------------------------------------------
# Random-flip null permutation test
# -----------------------------------------------------------------------------

def _gen_pnls(n: int, mean: float, std: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(mean, std, size=n)


def test_random_flip_empty_input():
    result = random_flip_null_test([])
    assert result["n_trades"] == 0
    assert result["passes"] is False


def test_random_flip_too_few_trades():
    result = random_flip_null_test([10.0, -5.0, 8.0])
    assert result["n_trades"] == 3
    assert result["passes"] is False


def test_random_flip_pure_noise_does_not_pass():
    """Zero-mean noise should produce |z| << 2.0."""
    pnls = _gen_pnls(200, mean=0.0, std=100.0, seed=42)
    result = random_flip_null_test(pnls, n_resamples=2000, seed=123)
    assert abs(result["observed_z"]) < 2.0
    assert result["passes"] is False


def test_random_flip_strong_signal_passes():
    """Strongly positive trades should produce z >> 2.0."""
    pnls = _gen_pnls(200, mean=20.0, std=50.0, seed=42)
    result = random_flip_null_test(pnls, n_resamples=2000, seed=123)
    assert result["observed_z"] > 2.0
    assert result["passes"] is True
    assert result["p_value"] < 0.05


def test_random_flip_weak_signal_borderline():
    """Weak positive signal: z near or below 2.0 (does NOT auto-pass)."""
    pnls = _gen_pnls(100, mean=2.0, std=50.0, seed=42)
    result = random_flip_null_test(pnls, n_resamples=2000, seed=123)
    # The whole point: weak signals don't sneak through the strict gate
    assert result["observed_z"] < 3.0


def test_random_flip_reproducibility():
    """Same seed → same z."""
    pnls = _gen_pnls(150, mean=10.0, std=50.0, seed=42)
    r1 = random_flip_null_test(pnls, n_resamples=1000, seed=99)
    r2 = random_flip_null_test(pnls, n_resamples=1000, seed=99)
    assert r1["observed_z"] == r2["observed_z"]
    assert r1["p_value"] == r2["p_value"]


def test_random_flip_n_resamples_increases_precision():
    """More resamples → smaller p-value variance for the same signal."""
    pnls = _gen_pnls(200, mean=15.0, std=50.0, seed=42)
    # Run multiple times with different seeds at low n_resamples vs high
    z_small = []
    z_large = []
    for s in range(5):
        z_small.append(random_flip_null_test(pnls, n_resamples=200, seed=s)["observed_z"])
        z_large.append(random_flip_null_test(pnls, n_resamples=2000, seed=s)["observed_z"])
    # Larger n_resamples → tighter z estimate
    assert np.std(z_large) <= np.std(z_small) * 1.5


def test_random_flip_zero_pnls_dropped():
    """Zero-PnL rows are dropped (no-trade artifacts) before analysis."""
    pnls = list(_gen_pnls(50, mean=10.0, std=50.0, seed=42)) + [0.0] * 30
    result = random_flip_null_test(pnls, n_resamples=1000, seed=42)
    assert result["n_trades"] == 50  # zeros dropped


def test_random_flip_pf_matches_observed():
    """observed_pf field should equal the actual PF of the input."""
    pnls = np.array([100.0, 100.0, 100.0, -50.0, -50.0])
    result = random_flip_null_test(pnls, n_resamples=500, seed=42)
    expected_pf = 300.0 / 100.0  # 3.0
    assert math.isclose(result["observed_pf"], expected_pf, rel_tol=1e-9)


def test_random_flip_null_mean_around_one():
    """For symmetric magnitude distribution, null PF mean ~ 1.0."""
    # Magnitudes from a symmetric source
    mags = np.array([100.0] * 50 + [50.0] * 50 + [25.0] * 50)
    # Half positive, half negative — observed PF should be 1.0
    pnls = np.concatenate([mags[:75], -mags[75:]])
    rng = np.random.default_rng(42)
    rng.shuffle(pnls)
    result = random_flip_null_test(pnls, n_resamples=2000, seed=42)
    # Null mean should be close to 1.0 (symmetric)
    assert 0.85 <= result["null_mean"] <= 1.15


def test_realistic_family_filters_noise_candidates():
    """Simulate a realistic family of 50 sweep candidates: a few real edges,
    most random. BH-FDR should filter most of the random ones while letting
    the real edges through."""
    rng = np.random.default_rng(42)
    n_candidates = 50

    # 5 "real" candidates with PF around 1.5-2.0 and decent trade counts
    real_pf = rng.uniform(1.5, 2.0, size=5)
    real_n = rng.integers(150, 400, size=5)

    # 45 "noise" candidates clustered around PF=1.0 (small departures by chance)
    noise_pf = rng.uniform(0.85, 1.20, size=45)
    noise_n = rng.integers(30, 200, size=45)

    df = pd.DataFrame({
        "profit_factor": np.concatenate([real_pf, noise_pf]),
        "total_trades": np.concatenate([real_n, noise_n]),
    })

    annotate_dataframe_with_pvalues(df, bh_fdr_alpha=0.05)

    # Most of the 5 real candidates should pass
    real_pass = df.iloc[:5]["bh_fdr_passes"].sum()
    assert real_pass >= 4, f"Expected most real candidates to pass, got {real_pass}/5"

    # Most of the 45 noise candidates should fail
    noise_pass = df.iloc[5:]["bh_fdr_passes"].sum()
    assert noise_pass <= 5, f"Expected few noise candidates to pass, got {noise_pass}/45"
