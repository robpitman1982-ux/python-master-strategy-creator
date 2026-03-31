# SESSION 54 PRE-EXECUTION REVIEW
# Date: 2026-04-01
# Reviewer: Claude (claude.ai project chat)
#
# This review catches issues BEFORE Claude Code runs, preventing costly mistakes.
# Read this FIRST, then execute SESSION_54_TASKS.md.

## CRITICAL ISSUES TO FIX IN TASKS

### Issue 1: ExitConfig is frozen=True — adding fields requires care
# File: modules/strategies.py line 28
# ExitConfig is a frozen dataclass. Adding break_even_atr and early_exit_bars
# (Tasks 8 and 9) requires updating:
#   a) The @dataclass definition (add new fields with defaults)
#   b) build_exit_config() function (lines 45-75) — must pass new fields through
#   c) EVERY call site that constructs ExitConfig directly — search for "ExitConfig("
#   d) _InlineMeanReversionStrategy.__init__() which calls build_exit_config()
#   e) _run_refinement_case() in refiner.py which reads task dict and passes to factory
#
# ACTION: When adding break_even_atr to ExitConfig, also add it to:
#   - build_exit_config() kwargs and return value
#   - _InlineMeanReversionStrategy.__init__()
#   - _InlineTrendStrategy.__init__() (in trend_strategy_type.py)
#   - _InlineBreakoutStrategy.__init__() (in breakout_strategy_type.py)
#   - All short variants that inherit from these

### Issue 2: New filters need THREE registrations, not two
# For each new filter class added to get_filter_classes():
#   1. Add to get_filter_classes() return list
#   2. Add elif branch in build_filter_objects_from_classes() with params
#   3. Add elif branch in build_candidate_specific_strategy() with params
# Missing #3 will cause refinement to silently use default params.
# This must be done in EACH strategy type file that uses the filter.
#
# FILES TO UPDATE per filter:
#   - mean_reversion_strategy_type.py (3 methods)
#   - trend_strategy_type.py (3 methods)
#   - breakout_strategy_type.py (3 methods)
#   - short_strategy_types.py (inherits, but check if overrides exist)

### Issue 3: mask() return type inconsistency
# Existing long-side filters return pd.Series from mask()
# Existing short-side filters return np.ndarray from mask()
# vectorized_signals.py handles both (checks hasattr .values)
# BUT: New filters should be CONSISTENT. Recommend returning pd.Series
# for long-side use and np.ndarray for short-side, matching existing pattern.
# OR: Always return np.ndarray since that's what the engine consumes.
### Issue 4: ATRExpansionRatioFilter needs new ATR columns precomputed
# Task 2 requires ATR(10) and ATR(50) columns. Currently only atr_20 is
# guaranteed. Each strategy type's get_required_avg_range_lookbacks() must
# return [10, 20, 50] (or similar) for the feature_builder to create them.
# If this is missed, the filter will find missing columns and either error
# or fall back to default values, producing wrong results silently.
#
# ACTION: Update get_required_avg_range_lookbacks() in:
#   - mean_reversion_strategy_type.py
#   - trend_strategy_type.py
#   - breakout_strategy_type.py
# To include the short and long ATR periods needed by ATRExpansionRatioFilter.

### Issue 5: Break-even stop in engine.py — injection point matters
# The break-even check must happen AFTER updating MFE but BEFORE checking
# the protective stop. If you check break-even after the stop check, the
# trade might stop out at the original stop level on the same bar where
# it would have qualified for break-even.
#
# Correct order in engine.py position management:
#   1. Update MFE/MAE excursions
#   2. Check break-even activation → update stop_price if triggered
#   3. Check protective stop (now potentially at break-even level)
#   4. Check profit target
#   5. Check trailing stop
#   6. Check signal exit
#   7. Check early exit (Task 9)
#   8. Check time exit

### Issue 6: Refinement grid explosion risk
# Adding break_even_atr with 4 values to the refinement grid MULTIPLIES
# the grid size by 4x. Current MR grid is roughly:
#   8 hold × 6 stop × 6 range × 1 mom × 3 exit × 5 target = 4,320 combos
# Adding break_even_atr [None, 0.5, 0.75, 1.0] = 17,280 combos
# That's 4x slower per candidate × 20 candidates = serious compute increase.
#
# RECOMMENDATION: Only add break_even_atr to the grid for TIME_STOP exits.
# For PROFIT_TARGET and SIGNAL_EXIT, the target/signal already limits losses.
# Or: Start with just [None, 0.75] (2 values) to keep grid manageable.

### Issue 7: Task 14 (DD overlap) needs equity curve data
# The drawdown overlap computation requires building equity curves from
# the daily return matrix. This data IS available (strategy_returns.csv
# has daily resampled returns). But the computation must handle strategies
# with different active date ranges — two strategies may not overlap in
# calendar time if they trade different markets/timeframes.
#
# ACTION: Only compute DD overlap for calendar days where BOTH strategies
# have non-zero returns. If overlap period is too short (< 252 trading
# days), skip the DD overlap check for that pair.
### Issue 8: FailedBreakoutExclusionFilter is conceptually different
# This is the first EXCLUSION filter. All existing filters use the pattern:
# "passes() returns True → entry allowed". This filter reverses it:
# "passes() returns True → NO failed breakout detected → entry allowed"
# "passes() returns False → failed breakout detected → entry BLOCKED"
#
# This means the AND-gate logic still works naturally — if this filter
# returns False, the combined mask is False. No engine changes needed.
# But the NAMING is confusing. Consider naming it NoRecentFailedBreakoutFilter
# or document clearly that True = "safe to enter" not "breakout failed".

### Issue 9: Short-side filter variants
# Task 3 (WickRejectionFilter) and Task 4 (CumulativeDeclineFilter) have
# direction="short" variants. These need to be registered in
# short_strategy_types.py's get_filter_classes() overrides AND in the
# build_filter_objects_from_classes() of the PARENT class (since short
# types inherit from long types but override get_filter_classes()).
#
# ShortMeanReversionStrategyType inherits from MeanReversionStrategyType.
# It overrides get_filter_classes() but does NOT override
# build_filter_objects_from_classes(). So the parent's elif chain must
# handle the short-side filter classes too.

### Issue 10: Test coverage for new filters
# test_vectorized_filters.py tests every filter by comparing mask() vs
# passes() bar-by-bar. New filters MUST be added to this test suite.
# The test uses make_synthetic_ohlcv() from test_smoke.py and
# add_all_features() — ensure the synthetic data has enough bars
# (500+) and that new ATR columns (atr_10, atr_50) are included
# in add_all_features().

## EXECUTION ORDER RECOMMENDATION

# Claude Code should execute in this order:
# 1. Tasks 1-7 (filters) — each is independent, can be done in sequence
# 2. Task 8 (break-even) — needs careful ExitConfig changes
# 3. Task 9 (early exit) — builds on Task 8's ExitConfig changes
# 4. Task 10 (trailing stop verification)
# 5. Tasks 11-12 (parameter grid changes) — simple value changes
# 6. Tasks 13-14 (portfolio selector improvements)
# 7. Tasks 15-17 (bug fixes)
#
# CRITICAL: Run `python -m pytest tests/ -v` after EACH task.
# If tests fail, fix before proceeding. Do NOT accumulate broken state.

## THINGS THAT ARE FINE AS-IS (no concerns)

# - The combinatorial search (filter_combinator.py) doesn't need changes —
#   adding filters to get_filter_classes() automatically increases C(n,k)
# - The promotion gate thresholds are fine for initial discovery
# - The leaderboard acceptance logic doesn't need changes
# - The cloud launcher and dashboard don't need updates
# - generate_returns.py doesn't need changes (uses leaderboard output)