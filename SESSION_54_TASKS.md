# SESSION 54 TASKS — Filter & Exit Improvements for Strategy Discovery
# Date: 2026-04-01
# Priority: HIGH — massive improvement session
# Estimated compute: Local development + test, then cloud re-sweep
#
# CONTEXT: Three-way LLM review (Claude, Gemini, ChatGPT) identified
# consensus improvements. This session implements the highest-confidence
# changes that all three independently recommended.
#
# PRINCIPLE: Each task is one commit. Test after each. No patches.
#
# ============================================================
# PHASE 1: NEW FILTERS (Tasks 1-7)
# ============================================================

## Task 1: Add EfficiencyRatioFilter (Universal)
# ALL THREE LLMs agreed this is the #1 new filter needed.
#
# Logic: abs(Close - Close[N]) / Sum(abs(Close[i] - Close[i-1]), i=1..N)
# Returns ratio between 0 (pure chop) and 1 (perfect trend).
# For trend/breakout: require ratio >= threshold (clean trend)
# For MR: require ratio <= threshold (choppy/ranging = MR territory)
#
# File: modules/filters.py
# Add class EfficiencyRatioFilter(BaseFilter):
#   __init__(self, lookback: int = 14, min_ratio: float = 0.45, mode: str = "above")
#   mode="above": passes when ratio >= min_ratio (for trend/breakout)
#   mode="below": passes when ratio <= min_ratio (for MR)
#   Implement both passes() and vectorized mask()
#
# Parameter ranges to sweep:
#   lookback: [10, 14, 20]
#   min_ratio: [0.30, 0.40, 0.50, 0.60] for trend
#   max_ratio: [0.25, 0.35, 0.45] for MR
#
# Add to feature_builder.py: NO new features needed (uses close prices only)
# Register in: trend_strategy_type.py, breakout_strategy_type.py get_filter_classes()
# Also add "below" mode version to: mean_reversion_strategy_type.py get_filter_classes()
#
# Test: Add unit test in tests/ confirming ratio=1.0 for perfectly trending data,
#        ratio~0 for oscillating data.
# Commit: "feat: add EfficiencyRatioFilter for trend quality detection"
## Task 2: Add ATRExpansionRatioFilter (Universal)
# ALL THREE LLMs agreed volatility TRANSITION detection is critical.
#
# Logic: ATR(short_period) / ATR(long_period)
# For breakout/trend: passes when ratio >= threshold (vol expanding)
# For MR: passes when ratio <= threshold (vol contracting)
#
# File: modules/filters.py
# Add class ATRExpansionRatioFilter(BaseFilter):
#   __init__(self, short_period: int = 10, long_period: int = 50,
#            threshold: float = 1.10, mode: str = "expanding")
#   mode="expanding": passes when ratio >= threshold
#   mode="contracting": passes when ratio <= threshold
#   Implement vectorized mask() using existing atr_{N} columns
#
# IMPORTANT: Need to ensure both ATR periods are precomputed.
# Update feature_builder.py: Add atr_10 and atr_50 to precomputed features
# Update each strategy_type's get_required_avg_range_lookbacks() to include
# the short and long periods.
#
# Parameter ranges:
#   short_period: [5, 8, 10]
#   long_period: [30, 50]
#   expanding threshold: [1.05, 1.10, 1.15, 1.20]
#   contracting threshold: [0.75, 0.80, 0.85, 0.90]
#
# Register in: breakout_strategy_type.py (expanding mode)
#              trend_strategy_type.py (expanding mode)
#              mean_reversion_strategy_type.py (contracting mode)
#
# Test: Verify ratio > 1 when short ATR > long ATR, < 1 when opposite.
# Commit: "feat: add ATRExpansionRatioFilter for volatility transition detection"

## Task 3: Add WickRejectionFilter (MR + Trend Pullback)
# ALL THREE LLMs agreed reversal detection is too simplistic.
#
# Logic (Long version):
#   lower_wick = min(Open, Close) - Low
#   upper_wick = High - max(Open, Close)
#   body = abs(Close - Open)
#   full_range = High - Low
#   Passes when: (lower_wick / full_range) >= wick_ratio
#                AND (Close - Low) / full_range >= close_position
#                AND full_range >= ATR * min_range_mult
#
# For Short: mirror (upper wick rejection)
#
# File: modules/filters.py
# Add class WickRejectionFilter(BaseFilter):
#   __init__(self, wick_ratio: float = 0.5, close_position: float = 0.70,
#            min_range_mult: float = 1.0, direction: str = "long")
#
# Parameter ranges:
#   wick_ratio: [0.40, 0.50, 0.60]
#   close_position: [0.65, 0.70, 0.80]
#   min_range_mult: [0.8, 1.0, 1.2]
#
# Register in: mean_reversion_strategy_type.py get_filter_classes()
#              short_mean_reversion (with direction="short")
#
# Test: Verify passes for classic hammer candle, fails for doji.
# Commit: "feat: add WickRejectionFilter for pin bar / rejection detection"
## Task 4: Add CumulativeDeclineFilter (MR)
# ALL THREE LLMs agreed consecutive-bar filters miss cumulative moves.
#
# Logic: (Close[N bars ago] - Close) / ATR(M) >= threshold
# Measures total decline over N bars regardless of individual bar direction.
# A down-up-down-down pattern that drops 2 ATR total gets caught.
#
# File: modules/filters.py
# Add class CumulativeDeclineFilter(BaseFilter):
#   __init__(self, lookback: int = 4, atr_period: int = 20,
#            min_decline_atr: float = 1.5, direction: str = "long")
#   direction="long": decline = Close[lookback ago] - Close (positive = fell)
#   direction="short": advance = Close - Close[lookback ago] (positive = rose)
#
# Parameter ranges:
#   lookback: [2, 3, 4, 5, 7]
#   min_decline_atr: [1.0, 1.5, 2.0, 2.5]
#
# Register in: mean_reversion_strategy_type.py get_filter_classes()
#              short_mean_reversion (direction="short")
#
# Test: Verify detects cumulative 2-ATR drop over 4 bars even with 1 up bar.
# Commit: "feat: add CumulativeDeclineFilter for exhaustion measurement"

## Task 5: Add ConsecutiveNarrowRangeFilter (Breakout)
# Two of three LLMs agreed multi-bar contraction > single-bar inside bar.
#
# Logic: Count bars in last N where range < avg_range(20) * ratio_threshold.
#        Passes when count >= min_count.
#
# File: modules/filters.py
# Add class ConsecutiveNarrowRangeFilter(BaseFilter):
#   __init__(self, lookback: int = 5, range_ratio: float = 0.80,
#            min_narrow_count: int = 3)
#
# Parameter ranges:
#   lookback: [3, 4, 5, 6]
#   range_ratio: [0.70, 0.80, 0.90]
#   min_narrow_count: [2, 3, 4]
#
# Register in: breakout_strategy_type.py get_filter_classes()
#
# Test: Verify passes when 3 of 5 bars have tight range, fails when only 1.
# Commit: "feat: add ConsecutiveNarrowRangeFilter for multi-bar compression"

## Task 6: Add DistanceFromExtremeFilter (MR + Trend)
# Two of three LLMs agreed distance from rolling high/low is missing.
#
# Logic: (rolling_high(N) - Close) / ATR(M) >= threshold (for long MR)
#        (Close - rolling_low(N)) / ATR(M) >= threshold (for short MR)
#        (rolling_high(N) - Close) / ATR(M) <= threshold (for trend = near highs)
#
# File: modules/filters.py
# Add class DistanceFromExtremeFilter(BaseFilter):
#   __init__(self, lookback: int = 20, atr_period: int = 20,
#            threshold: float = 1.5, mode: str = "far_from_high")
#   Modes: "far_from_high", "near_high", "far_from_low", "near_low"
#
# Parameter ranges:
#   lookback: [10, 20, 40]
#   threshold: [0.5, 1.0, 1.5, 2.0, 2.5] (far modes)
#              [0.3, 0.5, 0.8, 1.0] (near modes)
#
# Register in: mean_reversion_strategy_type.py (far_from_high mode)
#              trend_strategy_type.py (near_high mode)
#
# Test: Basic distance calculation verification.
# Commit: "feat: add DistanceFromExtremeFilter for stretch measurement"
## Task 7: Add FailedBreakoutExclusionFilter (Breakout)
# ChatGPT emphasized this most, all three agreed exclusion filters are needed.
#
# Logic: REJECT entry if any of the last N bars broke above the range high
#        but closed back inside the range (or in lower half of bar).
#        This is a NEGATIVE filter — it vetoes entries, not enables them.
#
# Implementation approach: passes() returns True when NO failed breakout
# detected in lookback. When a failed breakout IS detected, returns False.
#
# File: modules/filters.py
# Add class FailedBreakoutExclusionFilter(BaseFilter):
#   __init__(self, lookback: int = 3, range_lookback: int = 20)
#   For each of last `lookback` bars:
#     prior_high = rolling_max(high, range_lookback) at that bar
#     if high[bar] > prior_high AND close[bar] < prior_high: failed breakout
#   If any failed breakout found: return False (exclude)
#
# Register in: breakout_strategy_type.py get_filter_classes()
#
# Test: Verify rejects when bar poked above range then closed inside.
# Commit: "feat: add FailedBreakoutExclusionFilter to reduce false breakouts"

# ============================================================
# PHASE 2: EXIT LOGIC IMPROVEMENTS (Tasks 8-10)
# ============================================================

## Task 8: Add BREAK_EVEN exit type
# ALL THREE LLMs agreed this is the #1 exit improvement.
#
# Logic: Once MFE reaches break_even_atr × ATR, move protective stop
#        to entry_price + lock_amount (default lock_amount = 0).
#        This ELIMINATES the loss on trades that were once in profit.
#
# File: modules/strategies.py
#   Add ExitType.BREAK_EVEN = "break_even"
#   Add break_even_atr: float | None = None to ExitConfig
#   Add break_even_lock_atr: float = 0.0 to ExitConfig
#
# File: modules/engine.py
#   In the position management section (around line 280):
#   After updating MFE, BEFORE checking other exits:
#   if exit_config.break_even_atr and MFE >= break_even_atr * entry_atr:
#       new_stop = entry_price + break_even_lock_atr * entry_atr (long)
#       or entry_price - break_even_lock_atr * entry_atr (short)
#       self.position["stop_price"] = max(current_stop, new_stop) (long)
#       or min(current_stop, new_stop) (short)
#
# IMPORTANT: Break-even is NOT a standalone exit type — it's a MODIFIER
# that works WITH any other exit type. A strategy can use TIME_STOP +
# break-even, or TRAILING_STOP + break-even. Add it as an independent
# field that applies regardless of exit_type.
#
# Parameter ranges for refinement grids:
#   break_even_atr: [None, 0.5, 0.75, 1.0, 1.25]
#   break_even_lock_atr: [0.0, 0.05, 0.1]
#
# Update ALL strategy type refinement grids to include break_even_atr.
#
# Test: Verify stop moves to entry after MFE exceeds threshold.
#       Verify stop doesn't move back below entry once activated.
# Commit: "feat: add break-even stop modifier to exit system"
## Task 9: Add Time-Conditional Early Exit
# Two of three LLMs agreed: cut losers faster.
#
# Logic: If bars_in_trade >= early_exit_bars AND unrealized PnL < 0,
#        exit at close. Don't wait for full hold_bars timeout.
#
# File: modules/strategies.py
#   Add early_exit_bars: int | None = None to ExitConfig
#   (None = disabled, integer = check after this many bars)
#
# File: modules/engine.py
#   In position management, BEFORE the time exit check:
#   if exit_config.early_exit_bars and bars_held >= exit_config.early_exit_bars:
#       if unrealized PnL < 0:  # Still losing
#           close at market (close price ± slippage)
#           exit_reason = "EARLY_EXIT"
#
# Parameter ranges:
#   early_exit_bars: [None, 2, 3, 4] (None = disabled for backward compat)
#
# Update MR and breakout refinement grids to include this.
# Trend family probably shouldn't use it (trends need room).
#
# Test: Verify exits early when losing, doesn't exit early when winning.
# Commit: "feat: add time-conditional early exit for faster loser cutting"

## Task 10: Chandelier Exit improvement
# Two of three LLMs flagged this. We already have TRAILING_STOP but
# Chandelier is specifically: highest_high - N × ATR(current), recalculated
# each bar using CURRENT ATR (not entry ATR).
#
# Our current trailing stop already does this (uses current ATR each bar).
# VERIFY this is correct by reading the engine code. If it IS already
# doing Chandelier-style recalculation, just add it to more refinement grids.
# If it's using entry ATR, fix it to use current ATR.
#
# Also: Add trailing_stop_atr to trend and breakout refinement grids
# if not already present.
#
# trailing_stop_atr values: [1.5, 2.0, 2.5, 3.0]
#
# Commit: "feat: verify and expand trailing stop to more families"

# ============================================================
# PHASE 3: PARAMETER & PIPELINE FIXES (Tasks 11-14)
# ============================================================

## Task 11: Cap trend/breakout stop distance at 1.5 ATR
# Gemini specifically flagged: 2.5 ATR stops are prop-firm suicide.
# For 5% DD Bootcamp, a single 2.5 ATR stop on ES could use the entire DD budget.
#
# File: trend_strategy_type.py, breakout_strategy_type.py
# Change stop_distance_points grids:
#   Trend: [0.75, 1.0, 1.25, 1.5] (was [0.75, 1.0, 1.25, 1.5, 2.0, 2.5])
#   Breakout: [0.5, 0.75, 1.0, 1.25, 1.5] (tighter for breakout)
#   MR: keep as is [0.4, 0.5, 0.75, 1.0, 1.25, 1.5] (already appropriate)
#
# Commit: "fix: cap stop distance grids at 1.5 ATR for prop firm viability"

## Task 12: Lower MR profit target grid for prop-firm DD control
# ChatGPT recommended biasing toward lower targets for higher hit rate.
#
# File: mean_reversion_strategy_type.py
# Change profit_target_atr grid:
#   Was: [0.5, 1.0, 1.5, 2.0, 3.0]
#   New: [0.4, 0.6, 0.8, 1.0, 1.25, 1.5]
#
# Commit: "fix: lower MR profit target grid for prop firm DD constraints"
## Task 13: Add market concentration cap to portfolio selector
# Two of three LLMs flagged the NQ-heavy portfolio risk.
#
# File: modules/portfolio_selector.py
# In the combinatorial sweep stage, add constraint:
#   max_per_market: int = 2 (configurable via config.yaml)
#   When building C(n,k) combinations, reject any combo where
#   more than max_per_market strategies share the same market prefix.
#
# Also: Treat ES+NQ+RTY+YM as "equity_index" bucket with max 3 total.
#        Treat GC+SI+HG as "metals" bucket with max 2 total.
#        CL stands alone.
#
# Config:
#   portfolio_selector:
#     max_strategies_per_market: 2
#     max_equity_index_strategies: 3
#
# Commit: "feat: add market concentration caps to portfolio selector"

## Task 14: Add drawdown overlap correlation to portfolio selector
# ALL THREE LLMs agreed Pearson correlation is insufficient.
#
# File: modules/portfolio_selector.py
# After computing Pearson correlation matrix, also compute:
#   For each strategy pair:
#     1. Compute equity curve from cumulative returns
#     2. Compute drawdown series: equity / running_max - 1
#     3. Create binary vector: 1 if drawdown > 2%, else 0
#     4. Compute overlap = dot(binary_A, binary_B) / len(binary_A)
#   Reject portfolio if max pairwise DD overlap > threshold (e.g., 0.30)
#
# This ensures strategies don't draw down at the same time.
#
# Config:
#   portfolio_selector:
#     max_dd_overlap: 0.30
#
# Commit: "feat: add drawdown overlap gating to portfolio selector"

# ============================================================
# PHASE 4: PORTFOLIO SELECTOR BUGS (Tasks 15-17)
# These were identified in Session 52 and need fixing before re-running.
# ============================================================

## Task 15: Fix sizing optimizer DD constraint
# From Session 52 handover: optimizer oversizes for High Stakes.
#
# File: modules/portfolio_selector.py, line ~869
# In optimise_sizing() weight combo loop, AFTER computing mc results:
#   dd = mc["p95_worst_dd_pct"]
#   if dd > config.max_drawdown_pct:
#       continue  # Skip this weight combo
#
# Commit: "fix: add DD constraint to sizing optimizer"

## Task 16: Fix verdict/rating for non-Bootcamp programs
# From Session 52: verdict uses hardcoded step3 and 0.045 DD threshold.
#
# File: modules/portfolio_selector.py, lines 1060-1065
# Change to use config-aware thresholds:
#   final_rate = p.get("opt_final_pass_rate", ...)
#   if final_rate > 0.6 and p95_dd < prop_config.max_drawdown_pct * 0.9 and n_markets >= 3:
#       verdict = "RECOMMENDED"
#   elif final_rate > 0.3 and n_markets >= 2:
#       verdict = "VIABLE"
#   else:
#       verdict = "MARGINAL"
#
# Pass prop_config into _write_report().
#
# Commit: "fix: use program-aware thresholds for portfolio verdict"

## Task 17: Fix step3_pass_rate references for non-3-step programs
# Search entire codebase for "step3" and replace with dynamic step references.
#
# Commit: "fix: replace hardcoded step3 references with dynamic step count"
# ============================================================
# PHASE 5: DEFERRED (Session 55+)
# These are important but shouldn't block the re-sweep.
# ============================================================
#
# - Setup/Trigger architecture refactor (Tasks 1-7 filters work within
#   current AND-gate; refactoring to setup/trigger is a major structural
#   change that should be its own session)
# - Walk-forward validation (replace fixed IS/OOS split)
# - Parameter plateau scoring for robustness
# - ATR-based slippage instead of fixed ticks (Gemini's bug finding)
# - Day-of-week / session filters for intraday
# - Gap fade / failed breakout dedicated families
# - Risk-efficiency promotion lane
# - Prop rule versioning
#
# ============================================================
# EXECUTION PLAN
# ============================================================
#
# 1. Claude Code executes Tasks 1-17 locally
# 2. Run tests after each task
# 3. Run one local backtest (ES 60m, mean_reversion) to verify filters work
# 4. Commit all to GitHub
# 5. Launch cloud sweep across all 8 markets × 4 timeframes
# 6. Download results, run portfolio selector for all 3 programs
# 7. Compare pass rates vs Session 52 baseline (46.5% Bootcamp)
#
# Expected outcome: More strategies accepted (especially on 30m/15m),
# lower individual strategy DD (break-even + tighter stops),
# better portfolio diversification (DD overlap gating + market caps),
# higher prop firm pass rates across all 3 programs.