"""Statistical utilities for strategy promotion and selection.

Four related tools:

1. p-value approximation from profit factor and trade count
   (used as the building block for multiple-testing correction)

2. Benjamini-Hochberg FDR adjustment
   (controls the false discovery rate when many candidates are tested)

3. Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014)
   (penalises observed Sharpe by the number of trials in the search;
    the more candidates tested, the higher the SR needs to clear)

4. Random-flip null permutation test
   (asks: under "trades are random direction draws," how often would we
    see a profit factor at least this large? Robust to non-Gaussian PnL.)

Reference:
- Lo, A. (2002). The Statistics of Sharpe Ratios. Financial Analysts Journal.
- Benjamini, Y. and Hochberg, Y. (1995). Controlling the False Discovery Rate.
- Bailey, D. and Lopez de Prado, M. (2014). The Deflated Sharpe Ratio.
- Efron, B. and Tibshirani, R. (1993). An Introduction to the Bootstrap. Chapman & Hall.
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd


def pf_to_t_statistic(pf: float, n_trades: int) -> float:
    """Approximate t-statistic for log(profit factor) under the null PF=1.

    Following Lo (2002) for Sharpe ratios, which translates to PF as:

        t ~= ln(PF) * sqrt(N) / 2

    The factor 1/2 in the denominator is the asymptotic standard deviation of
    log(PF) for trade distributions with symmetric win/loss magnitude.
    Real distributions are skewed (winners tend smaller, losers tend larger
    pre-stop), so this is an *approximation* — the gate uses it only as a
    relative ranking signal under multiple-testing correction. It is NOT a
    substitute for trade-level bootstrap or permutation testing at final
    promotion.

    Returns 0.0 for degenerate inputs (PF <= 0, N <= 0, NaN).
    """
    if pf is None or n_trades is None:
        return 0.0
    try:
        pf_f = float(pf)
        n = int(n_trades)
    except (TypeError, ValueError):
        return 0.0
    if pf_f <= 0.0 or n <= 0 or not math.isfinite(pf_f):
        return 0.0
    if pf_f == 1.0:
        return 0.0
    return math.log(pf_f) * math.sqrt(n) / 2.0


def pf_to_pvalue(pf: float, n_trades: int) -> float:
    """Two-sided p-value for log(PF) under the null PF=1.

    Uses the t-statistic approximation from `pf_to_t_statistic` and the
    standard normal CDF for the asymptotic limit. For large N (>50) this is
    a reasonable approximation; for smaller N the p-values are slightly
    optimistic (would underestimate true p-value).

    Returns 1.0 for degenerate inputs (no signal at all).
    """
    t = pf_to_t_statistic(pf, n_trades)
    if t == 0.0:
        return 1.0
    # Two-sided: 2 * P(Z > |t|) = 2 * (1 - Phi(|t|))
    # Use erf for numerical stability vs scipy.stats.norm.sf
    z = abs(t) / math.sqrt(2.0)
    p = math.erfc(z)  # = 2 * (1 - Phi(|t|))
    return max(min(p, 1.0), 0.0)


def apply_bh_fdr(
    p_values: Iterable[float],
    alpha: float = 0.05,
) -> tuple[np.ndarray, np.ndarray]:
    """Benjamini-Hochberg FDR adjustment.

    Args:
        p_values: iterable of raw p-values (any order, NaN treated as 1.0).
        alpha: target false discovery rate.

    Returns:
        (rejected, adjusted_p_values) — both arrays the same length and order
        as the input.
        - `rejected[i]` is True iff candidate i passes the BH-FDR gate at alpha.
        - `adjusted_p_values[i]` is the BH-adjusted p-value (monotone from below
          in rank order). Useful as a continuous statistic.

    BH procedure:
      1. Sort raw p-values ascending: p_(1), p_(2), ..., p_(m)
      2. For each rank i, compare p_(i) to (i/m) * alpha.
      3. Find largest k where p_(k) <= (k/m) * alpha. Reject all p_(1..k).
      4. Adjusted p_(i) = min over j>=i of (m/j) * p_(j), capped at 1.0.
    """
    p_arr = np.asarray(list(p_values), dtype=float)
    n_input = p_arr.shape[0]
    if n_input == 0:
        return np.zeros(0, dtype=bool), np.zeros(0, dtype=float)

    # Treat NaN as 1.0 (no evidence)
    p_arr = np.where(np.isnan(p_arr), 1.0, p_arr)
    p_arr = np.clip(p_arr, 0.0, 1.0)

    m = n_input
    order = np.argsort(p_arr)
    sorted_p = p_arr[order]
    ranks = np.arange(1, m + 1)

    # Adjusted p in sorted order: p_adj[i] = min_{j>=i} (m/j) * p_(j), capped
    raw_scaled = sorted_p * m / ranks
    # Reverse cummin to enforce monotonicity from the largest rank down
    sorted_adj = np.minimum.accumulate(raw_scaled[::-1])[::-1]
    sorted_adj = np.clip(sorted_adj, 0.0, 1.0)

    # Decision: largest k where sorted_p[k] <= (k+1)/m * alpha
    threshold = ranks / m * alpha
    passes = sorted_p <= threshold
    if not passes.any():
        sorted_rejected = np.zeros(m, dtype=bool)
    else:
        last_pass_idx = np.max(np.where(passes)[0])
        sorted_rejected = np.zeros(m, dtype=bool)
        sorted_rejected[: last_pass_idx + 1] = True

    # Map back to original input order
    adjusted = np.empty(m, dtype=float)
    adjusted[order] = sorted_adj
    rejected = np.empty(m, dtype=bool)
    rejected[order] = sorted_rejected
    return rejected, adjusted


# =============================================================================
# Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014)
# =============================================================================

# Euler-Mascheroni constant
_GAMMA_EM = 0.5772156649015329


def _normal_inv_cdf(p: float) -> float:
    """Inverse CDF of the standard normal (Phi^-1).

    Uses Beasley-Springer-Moro approximation. Accurate to ~1e-9 for
    p in (1e-12, 1 - 1e-12). Outside that range, returns +/- 7.0 as a clamp.
    """
    if p <= 0.0:
        return -7.0
    if p >= 1.0:
        return 7.0
    # Use math.erfinv via the relationship Phi^-1(p) = sqrt(2) * erfinv(2p - 1)
    # math.erf is in stdlib; erfinv is not until 3.13. Provide a fallback.
    try:
        from math import erfinv  # type: ignore[attr-defined]
        return math.sqrt(2.0) * erfinv(2.0 * p - 1.0)
    except ImportError:
        # Beasley-Springer-Moro fallback (sufficient accuracy for our use)
        a = [-3.969683028665376e+01, 2.209460984245205e+02,
             -2.759285104469687e+02, 1.383577518672690e+02,
             -3.066479806614716e+01, 2.506628277459239e+00]
        b = [-5.447609879822406e+01, 1.615858368580409e+02,
             -1.556989798598866e+02, 6.680131188771972e+01,
             -1.328068155288572e+01]
        c = [-7.784894002430293e-03, -3.223964580411365e-01,
             -2.400758277161838e+00, -2.549732539343734e+00,
             4.374664141464968e+00, 2.938163982698783e+00]
        d = [7.784695709041462e-03, 3.224671290700398e-01,
             2.445134137142996e+00, 3.754408661907416e+00]
        p_low = 0.02425
        p_high = 1 - p_low
        if p < p_low:
            q = math.sqrt(-2 * math.log(p))
            return (((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
                   ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1)
        if p <= p_high:
            q = p - 0.5
            r = q * q
            return (((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5]) * q / \
                   (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1)
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
               ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1)


def _normal_cdf(x: float) -> float:
    """Standard normal CDF (Phi)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def expected_max_sharpe_under_null(n_trials: int, sr_variance: float = 1.0) -> float:
    """Expected maximum Sharpe ratio under the null (no skill) over N trials.

    Bailey & Lopez de Prado equation 7:

        E[max SR] = sqrt(V) * ((1 - gamma) * Phi^-1(1 - 1/N)
                              + gamma * Phi^-1(1 - 1/(N*e)))

    where gamma is the Euler-Mascheroni constant (~0.5772) and V is the
    variance of trial SRs (defaults to 1.0; for our use we substitute the
    variance specific to a particular T using the SR estimator's variance).

    Args:
        n_trials: number of independent trials in the search.
        sr_variance: variance of SRs across trials (defaults to 1.0).

    Returns:
        Expected maximum Sharpe under H0.
    """
    if n_trials < 2:
        # With 1 trial, "max" is just the single observation; no upward bias.
        return 0.0
    a = _normal_inv_cdf(1.0 - 1.0 / n_trials)
    b = _normal_inv_cdf(1.0 - 1.0 / (n_trials * math.e))
    return math.sqrt(max(sr_variance, 0.0)) * ((1.0 - _GAMMA_EM) * a + _GAMMA_EM * b)


def sharpe_estimator_std(
    sr: float,
    n_obs: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Asymptotic standard deviation of the Sharpe ratio estimator.

    Bailey & Lopez de Prado equation 9 / Mertens (2002):

        sigma(SR_hat) = sqrt((1 - skew * SR + ((kurt - 1)/4) * SR^2) / (T - 1))

    For Gaussian returns (skew=0, kurt=3), reduces to:
        sigma(SR_hat) = sqrt((1 + SR^2 / 2) / (T - 1))

    Args:
        sr: observed Sharpe ratio (per-observation, not annualised).
        n_obs: number of observations (trades).
        skewness: third standardised moment (0 = symmetric).
        kurtosis: Pearson kurtosis (3 = normal).

    Returns:
        Standard deviation of the SR estimator.
    """
    if n_obs < 2:
        return float("inf")
    var = (1.0 - skewness * sr + ((kurtosis - 1.0) / 4.0) * sr * sr) / (n_obs - 1)
    if var <= 0.0:
        return float("inf")
    return math.sqrt(var)


def deflated_sharpe_ratio(
    sr: float,
    n_obs: int,
    n_trials: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Deflated Sharpe Ratio: probability that the true SR > 0 given trial count.

    Returns the probability (0..1) that the observed SR is genuinely above
    the expected-max-under-null benchmark, i.e.,

        DSR = Phi( (SR - E[max SR_null]) / sigma(SR_hat) )

    Interpretation:
        DSR < 0.5  → observed SR is below the null benchmark (likely overfit)
        DSR > 0.5  → observed SR exceeds the null benchmark (some real edge)
        DSR > 0.95 → observed SR significantly exceeds the null benchmark

    Args:
        sr: observed Sharpe ratio (per-observation, not annualised).
        n_obs: number of observations (trades).
        n_trials: number of trials in the search (e.g., number of combos
                  in the sweep family).
        skewness: optional skew of returns (default 0 = Gaussian).
        kurtosis: optional Pearson kurtosis (default 3 = Gaussian).

    Returns:
        DSR in [0.0, 1.0]. NaN if inputs are degenerate.
    """
    if n_obs < 2 or n_trials < 1:
        return float("nan")
    sr_var_under_null = 1.0 / max(n_obs - 1, 1)
    sr_max_null = expected_max_sharpe_under_null(n_trials, sr_var_under_null)
    sigma_sr = sharpe_estimator_std(sr, n_obs, skewness, kurtosis)
    if not math.isfinite(sigma_sr) or sigma_sr <= 0.0:
        return float("nan")
    z = (sr - sr_max_null) / sigma_sr
    return _normal_cdf(z)


def pf_to_sharpe(pf: float) -> float:
    """Approximate per-trade Sharpe ratio from profit factor.

    Derivation: for a t-statistic of log(PF) ~ ln(PF) * sqrt(N) / 2 (Lo 2002),
    and t = SR * sqrt(N), we get SR ≈ ln(PF) / 2.

    This is a per-trade Sharpe (not annualised), suitable as input to
    deflated_sharpe_ratio() with n_obs=trade count.

    Returns 0.0 for degenerate inputs (PF<=0, NaN, etc).
    """
    if pf is None:
        return 0.0
    try:
        pf_f = float(pf)
    except (TypeError, ValueError):
        return 0.0
    if pf_f <= 0.0 or not math.isfinite(pf_f):
        return 0.0
    if pf_f == 1.0:
        return 0.0
    return math.log(pf_f) / 2.0


def annotate_dataframe_with_dsr(
    df: pd.DataFrame,
    pf_col: str = "profit_factor",
    n_trades_col: str = "total_trades",
    n_trials: int | None = None,
    n_trials_col: str | None = None,
    dsr_col: str = "deflated_sharpe_ratio",
    sr_col: str = "sharpe_per_trade",
) -> pd.DataFrame:
    """Add `sharpe_per_trade` and `deflated_sharpe_ratio` columns to a results df.

    Args:
        df: results dataframe (one row per candidate).
        pf_col: column with profit factor.
        n_trades_col: column with trade count.
        n_trials: total trials in the search family (e.g., 50 if 50 combos
                  were swept). If None, falls back to n_trials_col.
        n_trials_col: alternative — name of a column holding per-row n_trials
                      (useful when different rows belong to different families).
        dsr_col: output column for DSR.
        sr_col: output column for the per-trade Sharpe estimate.

    Returns the df modified in-place AND returned for chaining. Empty df is
    a no-op.
    """
    if df is None or df.empty:
        return df
    if pf_col not in df.columns or n_trades_col not in df.columns:
        return df

    pf_vals = df[pf_col].to_list()
    n_vals = df[n_trades_col].to_list()

    if n_trials_col is not None and n_trials_col in df.columns:
        trials_vals = df[n_trials_col].to_list()
    elif n_trials is not None:
        trials_vals = [int(n_trials)] * len(df)
    else:
        # No trial count → DSR collapses to "is observed SR > 0", trivially.
        trials_vals = [1] * len(df)

    sr_list = []
    dsr_list = []
    for pf, n, trials in zip(pf_vals, n_vals, trials_vals):
        sr = pf_to_sharpe(pf)
        try:
            n_int = int(n)
            t_int = max(int(trials), 1)
        except (TypeError, ValueError):
            sr_list.append(float("nan"))
            dsr_list.append(float("nan"))
            continue
        sr_list.append(sr)
        dsr_list.append(deflated_sharpe_ratio(sr, n_int, t_int))

    df[sr_col] = sr_list
    df[dsr_col] = dsr_list
    return df


# =============================================================================
# Random-flip null permutation test
# =============================================================================

def _safe_profit_factor(pnls: np.ndarray) -> float:
    """Profit factor with safe handling of edge cases.

    PF = sum(positive) / |sum(negative)|.
    Returns NaN if there are no losses (or no wins) to define PF.
    """
    gross_profit = float(pnls[pnls > 0].sum())
    gross_loss = float(-pnls[pnls < 0].sum())
    if gross_loss <= 0.0:
        # No losses → PF is undefined (or infinite). Treat as missing.
        return float("nan") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def random_flip_null_test(
    pnls: list[float] | np.ndarray,
    n_resamples: int = 5000,
    seed: int = 42,
) -> dict:
    """Random-direction-flip permutation test for profit factor.

    Under the null "this rule has no edge" (equivalently: trades have random
    direction), randomly flip the sign of each trade's PnL and recompute the
    profit factor. Repeat n_resamples times to build the null distribution.
    Compare the observed PF against it.

    The flip preserves trade magnitudes; only direction randomises. This
    matches the betfair-trader-project-validated convention of using n=5000
    resamples for the strict z >= 2.0 gate.

    Args:
        pnls: per-trade dollar PnL values (positive = win, negative = loss).
        n_resamples: number of null permutations (recommended >= 5000).
        seed: RNG seed for reproducibility.

    Returns:
        dict with:
          observed_pf: float — observed profit factor
          observed_z:  float — (observed - null_mean) / null_std
          p_value:     float — one-sided P(null_pf >= observed_pf)
          passes:      bool  — z >= 2.0 at n=5000
          null_mean:   float — mean of null distribution
          null_std:    float — std of null distribution
          n_resamples: int   — actual count of valid resamples
          n_trades:    int   — trade count of input

        For degenerate inputs (n<5 or all-same-sign), returns a dict with
        observed_z=0, passes=False, and notes the issue in the dict via
        nan/zero fields.
    """
    arr = np.asarray(list(pnls), dtype=float)
    n = arr.shape[0]

    base = {
        "observed_pf": float("nan"),
        "observed_z": 0.0,
        "p_value": 1.0,
        "passes": False,
        "null_mean": float("nan"),
        "null_std": 0.0,
        "n_resamples": 0,
        "n_trades": int(n),
    }

    if n < 5:
        return base

    # Drop zeros (no-trade rows) and NaN
    arr = arr[~np.isnan(arr)]
    arr = arr[arr != 0.0]
    n = arr.shape[0]
    if n < 5:
        base["n_trades"] = int(n)
        return base

    base["n_trades"] = int(n)

    obs_pf = _safe_profit_factor(arr)
    base["observed_pf"] = obs_pf
    if not math.isfinite(obs_pf):
        return base

    abs_pnls = np.abs(arr)

    # All-positive or all-negative input: under random flip the "wins" set
    # and "losses" set are equally probable as either direction, so the
    # null distribution still has structure. We just need to make sure
    # _safe_profit_factor returns finite values for the flipped arrays.

    rng = np.random.default_rng(seed)
    # Vectorised: build (n_resamples, n) sign matrix; broadcast multiply.
    signs = rng.choice([-1.0, 1.0], size=(n_resamples, n))
    flipped = abs_pnls[None, :] * signs  # (n_resamples, n)

    # Per-row profit / loss split
    pos_mask = flipped > 0
    gross_profits = np.where(pos_mask, flipped, 0.0).sum(axis=1)
    gross_losses = np.where(~pos_mask & (flipped < 0), -flipped, 0.0).sum(axis=1)

    valid = gross_losses > 0
    null_pfs = np.full(n_resamples, np.nan, dtype=float)
    null_pfs[valid] = gross_profits[valid] / gross_losses[valid]

    valid_pfs = null_pfs[~np.isnan(null_pfs)]
    n_valid = valid_pfs.shape[0]

    if n_valid < 100:
        # Not enough non-degenerate resamples to build a distribution
        base["n_resamples"] = int(n_valid)
        return base

    null_mean = float(valid_pfs.mean())
    null_std = float(valid_pfs.std(ddof=1))

    if null_std <= 0.0 or not math.isfinite(null_std):
        base["null_mean"] = null_mean
        base["null_std"] = null_std
        base["n_resamples"] = int(n_valid)
        return base

    z = (obs_pf - null_mean) / null_std
    p = float((valid_pfs >= obs_pf).sum() / n_valid)

    return {
        "observed_pf": obs_pf,
        "observed_z": z,
        "p_value": p,
        "passes": bool(z >= 2.0),
        "null_mean": null_mean,
        "null_std": null_std,
        "n_resamples": int(n_valid),
        "n_trades": int(n),
    }


def annotate_dataframe_with_pvalues(
    df: pd.DataFrame,
    pf_col: str = "profit_factor",
    n_trades_col: str = "total_trades",
    pvalue_col: str = "pf_pvalue",
    bh_fdr_alpha: float | None = None,
    bh_adj_col: str = "bh_fdr_p_adj",
    bh_reject_col: str = "bh_fdr_passes",
) -> pd.DataFrame:
    """Add `pf_pvalue` and (optionally) BH-FDR-adjusted columns to a results df.

    Always populates `pvalue_col`. If `bh_fdr_alpha` is not None, also
    populates `bh_adj_col` and `bh_reject_col` based on FDR control across
    the full df (treated as one test family).

    Returns the df modified in-place AND returned for chaining. Empty df is a
    no-op.
    """
    if df is None or df.empty:
        return df
    if pf_col not in df.columns or n_trades_col not in df.columns:
        return df

    pvals = np.array([
        pf_to_pvalue(pf, n)
        for pf, n in zip(df[pf_col].to_list(), df[n_trades_col].to_list())
    ])
    df[pvalue_col] = pvals

    if bh_fdr_alpha is not None:
        rejected, adjusted = apply_bh_fdr(pvals, alpha=float(bh_fdr_alpha))
        df[bh_adj_col] = adjusted
        df[bh_reject_col] = rejected

    return df
