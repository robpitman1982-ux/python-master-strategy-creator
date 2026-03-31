# PROMPT: Deep Strategy Discovery Review — Futures Trading Engine Optimization

> **Instructions to the LLM:** You are being asked to perform a thorough, expert-level review of an automated futures strategy discovery engine. The full system documentation is provided above (or separately). Read it carefully before answering. Your goal is to suggest concrete, implementable changes that will help this engine discover MORE profitable, LOW-DRAWDOWN strategies that can survive prop firm evaluations. Think like a quantitative researcher with deep knowledge of futures markets, technical analysis, statistical edge detection, and systematic trading system design.

---

## CONTEXT

I have built an automated strategy discovery engine that sweeps filter combinations across 8 futures markets (ES, NQ, CL, GC, SI, HG, RTY, YM) on 4 timeframes (daily, 60m, 30m, 15m). It currently has 315 accepted strategies organized into 15 families (long/short × trend/MR/breakout × 3 subtypes each). The engine assembles portfolios for The5ers prop firm challenges:

- **Pro Growth $20K**: 1 step, 6% DD limit, 3% daily DD, 10% target
- **High Stakes $100K**: 2 steps, 10% DD limit, 5% daily DD, 8%+5% targets
- **Bootcamp $250K**: 3 steps, 5% DD limit, no daily DD, 6% × 3 targets

The DOMINANT constraint is drawdown management. A low-DD, moderate-profit strategy is far more valuable than a high-profit, high-DD strategy. The portfolio selector combines 4-6 uncorrelated strategies and runs Monte Carlo simulations through the sequential prop firm steps.

**Current best result:** 46.5% pass rate through all 3 Bootcamp steps. Need to improve this significantly.

---

## THE FULL SYSTEM REVIEW

*[Paste the complete SYSTEM_REVIEW_FOR_LLM_ANALYSIS.md document here]*

---

## WHAT I NEED FROM YOU

Please provide a comprehensive, prioritized analysis covering ALL of the following areas. For each suggestion, rate it:
- **Impact**: HIGH / MEDIUM / LOW (expected improvement to pass rate or DD reduction)
- **Complexity**: EASY / MEDIUM / HARD (implementation effort)
- **Data Required**: What data is needed (existing OHLCV only, or needs new data sources)
### AREA 1: NEW FILTERS TO ADD

Looking at the current filter catalogue (Section 4), what SPECIFIC new filters should be added? For each:
- Give the exact filter logic (what does it compute, what threshold does it check)
- Which strategy family should it belong to (or universal)
- Why you think it will find edge the current filters miss
- What parameter ranges to sweep

Think about:
- Rate-of-change / acceleration filters (beyond simple momentum)
- Volatility state change detection (vol expanding vs contracting, not just high/low)
- Price structure filters (swing highs/lows, market structure)
- Bar pattern filters beyond what we have (engulfing patterns, pin bars, dojis)
- Range contraction/expansion sequences
- Distance-from-extremes filters (how far from N-day high/low)
- Mean reversion exhaustion signals (consecutive down days, cumulative decline)
- Trend quality filters (ADX-like measurements using only OHLC)
- Support/resistance zone awareness
- Gap behavior (gap-and-go vs gap-and-fade patterns)
- Candle body vs wick ratio analysis
- Multi-bar patterns (N-bar narrowing range, N-bar ascending/descending closes)

### AREA 2: PARAMETER RANGE OPTIMIZATION

Looking at the current refinement grids (Section 5, Stage 3):
- Are the hold_bars ranges appropriate for each timeframe?
- Are the stop_distance (ATR multiple) ranges too narrow or too wide?
- Should the min_avg_range (distance-below-SMA for MR) have different ranges?
- What about the profit_target_atr values — are they optimized for prop firm DD constraints?
- Should we add trailing_stop_atr to the grid for more families?

### AREA 3: EXIT LOGIC IMPROVEMENTS

The current exits are TIME_STOP, PROFIT_TARGET, TRAILING_STOP, and SIGNAL_EXIT. What new exit mechanisms would help reduce drawdown while preserving profits?

Consider:
- Break-even stop (move stop to entry after X ATR profit)
- Time-decay exits (reduce position or tighten stop over holding period)
- Volatility-adjusted trailing stops (Chandelier exit)
- Partial profit taking (exit half at target, trail the rest)
- Hybrid exits (combine time + trailing + profit target)
- Conditional exits (exit at close if unprofitable after N bars)
- ATR-based time stops (exit after N × ATR of cumulative range elapsed)
### AREA 4: STRATEGY STRUCTURE CHANGES

The current architecture is: pick 3-6 filters → all must pass → enter. This is a pure AND-gate. Consider:
- Should some filters be OR-gated (either A or B must pass)?
- Should there be "setup" filters (must be true yesterday) vs "trigger" filters (must be true today)?
- Should filter combinations have weights instead of binary pass/fail?
- Should we have "must NOT pass" (exclusion) filters?
- Would conditional filter chains help (if A is true, also require B, but if C is true instead, require D)?

### AREA 5: MISSING STRATEGY FAMILIES / CONCEPTS

What entire strategy concepts are we missing? The engine currently has trend, MR, and breakout in long and short. What about:
- Range-bound / channel strategies
- Fade strategies (systematic fade of overnight gaps, opening range breakout fades)
- Momentum exhaustion beyond simple MR
- Carry / calendar spread concepts applied to single instruments
- Regime-switching meta-strategies
- Pairs or relative-value between correlated markets (ES vs NQ, GC vs SI)

### AREA 6: QUALITY AND ROBUSTNESS IMPROVEMENTS

How can we better detect curve-fitting and ensure strategies are robust?
- Is the IS/OOS split date (2019) appropriate?
- Should we use walk-forward validation instead?
- Are the quality flag thresholds (ROBUST at IS PF ≥ 1.15, OOS PF ≥ 1.15) right?
- How should we handle strategies that work well in specific market regimes?
- Should we add regime-dependent acceptance (strategy tagged as "bull market only" etc.)?

### AREA 7: PORTFOLIO CONSTRUCTION IMPROVEMENTS

The portfolio selector uses Pearson correlation on daily returns to measure diversification. Is this optimal?
- Should we use rank correlation, tail correlation, or drawdown overlap instead?
- Should portfolio selection weight strategies differently based on their drawdown characteristics?
- How should we handle the sequential-steps structure (passing Step 1 before Step 2)?
- Should there be a maximum allocation to any single market?

### AREA 8: MARKET-SPECIFIC INSIGHTS

For each of the 8 markets (ES, NQ, CL, GC, SI, HG, RTY, YM):
- What is the market's known character and typical edge?
- What specific filter modifications or strategy types would work better for this market?
- Are there known structural edges (e.g., end-of-month rebalancing, roll dates, seasonal patterns)?
---

## FORMAT YOUR RESPONSE

Please structure your response with clear sections matching Areas 1-8 above. For EACH specific suggestion:

1. **Name**: Short descriptive name
2. **Logic**: Exact computation and threshold
3. **Family**: Which strategy family/families it applies to
4. **Impact/Complexity/Data**: Ratings
5. **Rationale**: Why this will help, citing specific market microstructure or statistical reasoning
6. **Parameter ranges**: What values to sweep
7. **Priority rank**: Within its area, how important is this vs other suggestions

Please be SPECIFIC and CONCRETE. Don't say "consider adding momentum indicators" — say exactly which indicator, how to compute it from OHLCV data, what thresholds to use, and why it addresses a gap in the current filter set.

Focus especially on changes that will reduce strategy drawdown while maintaining profitability, as this is the dominant constraint for prop firm success.

---

## BONUS: If you can identify any BUGS, LOGICAL ERRORS, or STRUCTURAL WEAKNESSES in the system design as described, please flag them separately at the end of your response. This includes:
- Filters that are redundant or logically equivalent
- Parameter ranges that are clearly wrong for specific timeframes
- Gate thresholds that are too loose or too tight
- Anything in the pipeline that could be causing good strategies to be filtered out prematurely