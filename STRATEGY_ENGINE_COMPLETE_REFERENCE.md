# Strategy Discovery Engine — Complete Technical Reference

## What this document is

This is a complete specification of the strategy discovery engine used to find algorithmic futures trading strategies. It covers every filter, every gate, every scoring formula, every parameter grid, and the exact pipeline that produces the ultimate leaderboard. It is written so that another analyst (human or LLM) can review the methodology, spot weaknesses, and suggest improvements.

The companion files to this document are:
- `ultimate_leaderboard.csv` — all accepted strategies ranked by classic research metrics
- `ultimate_leaderboard_bootcamp.csv` — all accepted strategies ranked by Bootcamp survival score

---

## 1. The goal

**Target**: The5ers $250K Bootcamp prop firm challenge.

The Bootcamp is a 3-step evaluation:

| | Step 1 | Step 2 | Step 3 | Funded |
|---|--------|--------|--------|--------|
| Balance | $100,000 | $150,000 | $200,000 | $250,000 |
| Profit target | 6% | 6% | 6% | 5% |
| Max drawdown | 5% (static) | 5% | 5% | 4% |
| Daily DD limit | None | None | None | 3% pause |
| Leverage (indices) | 1:7.5 | 1:7.5 | 1:7.5 | 1:7.5 |
| Time limit | Unlimited | Unlimited | Unlimited | — |
| Stop loss | Mandatory | Mandatory | Mandatory | Mandatory |

The challenge is sequential: trades carry through from step to step. To pass, you need to hit 6% profit before losing 5% from peak. You do this 3 times, then you're funded at $250K.

**The portfolio strategy**: run ~6 uncorrelated strategies simultaneously to smooth the equity curve. A single strategy is too volatile — one drawdown wipes you. Multiple uncorrelated strategies reduce the chance of all losing simultaneously.

**Current instrument**: ES (E-mini S&P 500 futures). Planned expansion: CL (crude oil), NQ (Nasdaq), GC (gold).

**Current data**: TradeStation CSV exports, 2008–2026. Timeframes: daily, 60m, 30m, 15m, 5m.

---

## 2. Pipeline architecture

The engine runs a staged funnel for each dataset (market × timeframe) and each strategy family. Here is the exact flow:

```
For each dataset (e.g., ES_30m):
  Load CSV once → precompute features once (SMA, ATR, momentum)
  
  For each family (15 total: 3 base + 9 subtypes + 3 shorts):
    
    1. SANITY CHECK
       Run base strategy with default params
       Confirm: data loads, trades trigger, no crashes
    
    2. FILTER COMBINATION SWEEP
       Generate all C(n,k) filter combos for this family
       Run each combo with default entry/exit params
       Record: PF, avg trade, net PnL, IS/OOS splits, quality flags
    
    3. PROMOTION GATE
       Filter combos by: min PF ≥ 1.0, min trades ≥ 50, min trades/yr ≥ 3.0
       Rank by composite score (quality 40%, OOS PF 30%, trades/yr 30%)
       Cap at 20 promoted candidates
    
    4. REFINEMENT (top 3 promoted candidates)
       Grid search over: hold_bars × stop_distance × min_avg_range × momentum_lookback × exit_type × exit_params
       Each setting re-run with full IS/OOS evaluation
       Pool all accepted refinements, sort by net_pnl
    
    5. FAMILY LEADERBOARD
       Compare best combo vs best refined
       Refined wins only if it improves net_pnl
       Final acceptance gate: PF ≥ 1.0, OOS PF ≥ 1.0, trades ≥ 60
    
    6. BOOTCAMP SCORING
       Score each accepted strategy on a 0–100 Bootcamp scale
       Components: profitability (30), OOS stability (25), drawdown control (20), trade count (15), consistency (10), quality penalty (up to -15)

  Cross-dataset portfolio evaluation:
    Reconstruct trades for all accepted strategies
    Calculate: correlation matrix, Monte Carlo drawdowns, stress tests
    Produce: ultimate_leaderboard.csv, ultimate_leaderboard_bootcamp.csv
```

---

## 3. Strategy families

There are 15 strategy families, grouped into 3 base types plus subtypes and short-side mirrors.

### 3.1 Base families

| Family | Direction | Filters available | Combo sizes | Combinations |
|--------|-----------|-------------------|-------------|--------------|
| mean_reversion | Long | 10 | 3–6 | 792 |
| trend | Long | 10 | 4–6 | 672 |
| breakout | Long | 10 | 3–5 | 582 |

### 3.2 Subtypes (tighter filter pools, same engine)

| Subtype | Parent | Purpose |
|---------|--------|---------|
| mean_reversion_vol_dip | MR | Volatility contraction + dip |
| mean_reversion_mom_exhaustion | MR | Momentum dying + reversal |
| mean_reversion_trend_pullback | MR | Above long-term SMA + below fast SMA |
| trend_pullback_continuation | Trend | Classic pullback in uptrend |
| trend_momentum_breakout | Trend | Momentum + new highs |
| trend_slope_recovery | Trend | SMA slope recovery |
| breakout_compression_squeeze | Breakout | Tight range → expansion |
| breakout_range_expansion | Breakout | Range breakout + bar expansion |
| breakout_higher_low_structure | Breakout | Higher lows → breakout |

Each subtype has a smaller, semantically coherent filter pool (typically 4–6 filters), producing ~41–120 combinations instead of 582–792.

### 3.3 Short-side families

| Family | Mirror of | Direction |
|--------|-----------|-----------|
| short_mean_reversion | mean_reversion | Short |
| short_trend | trend | Short |
| short_breakout | breakout | Short |

---

## 4. Filters — complete inventory

### 4.1 Long trend filters (10 total)

| Filter | Logic | Key params |
|--------|-------|------------|
| TrendDirectionFilter | Fast SMA > slow SMA (uptrend confirmed) | fast=50, slow=200 |
| PullbackFilter | Previous close ≤ fast SMA (price pulled back) | fast=50 |
| RecoveryTriggerFilter | Current close > fast SMA (recovered above) | fast=50 |
| VolatilityFilter | Current ATR ≥ long-term ATR × multiplier | lookback=20, min_atr_mult=1.0 |
| MomentumFilter | Close > close N bars ago | lookback=10 |
| UpCloseFilter | Close > previous close | — |
| TwoBarUpFilter | Two consecutive higher closes | — |
| TrendSlopeFilter | Fast SMA now > fast SMA N bars ago | fast=50, slope_bars=5 |
| CloseAboveFastSMAFilter | Close > fast SMA | fast=50 |
| HigherLowFilter | Current low > previous low | — |

### 4.2 Long mean reversion filters (10 total)

| Filter | Logic | Key params |
|--------|-------|------------|
| BelowFastSMAFilter | Close < fast SMA | fast=20 |
| DistanceBelowSMAFilter | Distance below SMA ≥ N × ATR | fast=20, min_distance_atr=0.3 |
| DownCloseFilter | Close < previous close | — |
| TwoBarDownFilter | Two consecutive lower closes | — |
| ReversalUpBarFilter | Close > open (up bar after down setup) | — |
| LowVolatilityRegimeFilter | ATR ≤ long-term ATR × max_mult | lookback=20, max_atr_mult=1.0 |
| AboveLongTermSMAFilter | Close > slow SMA (still in uptrend) | slow=200 |
| ThreeBarDownFilter | Three consecutive lower closes | — |
| CloseNearLowFilter | Close in bottom 35% of bar range | max_close_position=0.35 |
| StretchFromLongTermSMAFilter | Distance below long SMA ≥ N × ATR | slow=200, min_distance_atr=0.5 |

### 4.3 Long breakout filters (10 total)

| Filter | Logic | Key params |
|--------|-------|------------|
| CompressionFilter | ATR ≤ threshold (tight range) | lookback=20, max_atr_mult=0.75 |
| RangeBreakoutFilter | Close > prior N-bar high | lookback=20 |
| ExpansionBarFilter | Current range ≥ avg range × multiplier | lookback=20, expansion_mult=1.5 |
| BreakoutRetestFilter | Close > prior high + buffer | lookback=20, atr_buffer=0.0 |
| BreakoutTrendFilter | Fast SMA > slow SMA (trend context) | fast=50, slow=200 |
| BreakoutCloseStrengthFilter | Close in top 40% of bar range | threshold=0.60 |
| PriorRangePositionFilter | Prior close in top 50% of N-bar range | lookback=20, min_position=0.50 |
| BreakoutDistanceFilter | Breakout distance ≥ N × ATR | lookback=20, min_atr=0.10 |
| RisingBaseFilter | Recent lows rising (constructive base) | lookback=5 |
| TightRangeFilter | Current range ≤ avg range × mult | lookback=20, max_mult=0.85 |

### 4.4 Short MR filters (7)

AboveFastSMA, DistanceAboveSMA, UpCloseShort, TwoBarUpShort, ReversalDownBar, HighVolatilityRegime, StretchAboveLongTermSMA

### 4.5 Short trend filters (6)

DowntrendDirection, RallyInDowntrend, FailureToHold, LowerHigh, DownCloseShort, DowntrendSlope

### 4.6 Short breakout filters (2 + shared)

DownsideBreakout, WeakClose (plus shared breakout filters like Compression)

### 4.7 Timeframe scaling

All SMA lengths, ATR lookbacks, and momentum lookbacks scale with the timeframe multiplier relative to 60m:

| Timeframe | Multiplier | SMA 50 becomes | SMA 200 becomes |
|-----------|------------|----------------|-----------------|
| daily | 0.154 | 10 | 31 |
| 60m | 1.0 | 50 | 200 |
| 30m | 2.0 | 100 | 400 |
| 15m | 4.0 | 200 | 800 |
| 5m | 12.0 | 600 | 2400 |

Pattern filters (TwoBarDown, ReversalUpBar, HigherLow, etc.) do NOT scale — they are bar-pattern based.

---

## 5. Entry and exit mechanics

### 5.1 Entry signal

A signal fires when ALL filters in a combination pass on the same bar. The engine enters at the next bar's open + slippage.

Entry filters are combined with AND logic — every filter must pass simultaneously. This is an exhaustive search over all C(n,k) combinations, not a learned or optimised selection.

### 5.2 Exit types (4 supported)

| Exit type | Logic | Best for |
|-----------|-------|----------|
| time_stop | Exit after N bars (hold_bars) | Default / baseline |
| trailing_stop | Exit when price drops N×ATR from highest high since entry | Trend, breakout |
| profit_target | Exit when price rises N×ATR from entry | Mean reversion |
| signal_exit | Exit when price crosses reference level (e.g., back above fast SMA) | Mean reversion |

All exits also have a protective stop: entry price − stop_distance × ATR. The protective stop always takes priority over other exit types.

### 5.3 Exit type support by family

| Family | Supported exits |
|--------|----------------|
| Trend | time_stop, trailing_stop |
| Mean reversion | time_stop, profit_target, signal_exit |
| Breakout | time_stop, trailing_stop |

### 5.4 Trade execution defaults

| Parameter | Value |
|-----------|-------|
| Initial capital | $250,000 |
| Risk per trade | 1% |
| Commission | $2.00 per contract |
| Slippage | 4 ticks |
| Tick value | $12.50 |
| Dollars per point | $50 (ES) |
| IS/OOS split | 2019-01-01 |

---

## 6. Refinement grid

When a combo passes the promotion gate, the top 3 candidates are refined across a parameter grid.

### 6.1 Trend refinement grid (base 60m)

| Parameter | Values |
|-----------|--------|
| hold_bars | [3, 4, 5, 6, 8, 10, 12, 15] |
| stop_distance_points | [0.5, 0.75, 1.0, 1.25, 1.5, 2.5] |
| min_avg_range | [0.0] (no volatility filter wired) or [0.0, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0] when VolatilityFilter present |
| momentum_lookback | [0, 5, 8, 10, 14] when MomentumFilter present, else [0] |
| exit_type | [time_stop, trailing_stop] |
| trailing_stop_atr | [1.0, 1.5, 2.0, 2.5] (only when exit_type=trailing_stop) |

Grid size: 8 × 6 × 7 × 5 × (1 + 4) = ~8,400 per candidate. Max 3 candidates = ~25,200 refinement runs per trend family.

### 6.2 Mean reversion refinement grid (base 60m)

| Parameter | Values |
|-----------|--------|
| hold_bars | [3, 4, 5, 6, 8, 10, 12, 15] |
| stop_distance_points | [0.3, 0.4, 0.5, 0.75, 1.0, 1.5] |
| min_avg_range | [0.0] or [0.0, 0.4, 0.8, 1.2, 1.6, 2.0] when DistanceBelowSMA present |
| momentum_lookback | [0] (MR doesn't use momentum) |
| exit_type | [time_stop, profit_target, signal_exit] |
| profit_target_atr | [0.5, 0.75, 1.0, 1.25, 1.5] (only when exit_type=profit_target) |
| signal_exit_reference | ["fast_sma"] (only when exit_type=signal_exit) |

### 6.3 Breakout refinement grid (base 60m)

| Parameter | Values |
|-----------|--------|
| hold_bars | [2, 3, 4, 5, 6, 8, 10] |
| stop_distance_points | [0.5, 0.75, 1.0, 1.25, 1.5, 2.0] |
| min_avg_range | [0.0] or [0.0, 0.6, 0.75, 0.85, 0.95] when CompressionFilter present |
| momentum_lookback | [0] |
| exit_type | [time_stop, trailing_stop] |
| trailing_stop_atr | [1.0, 1.5, 2.0, 2.5] |

All grids scale with timeframe (hold_bars × multiplier, etc.).

---

## 7. Quality flags

The engine assigns a quality flag to every strategy based on IS/OOS profit factor:

| Flag | Condition | Meaning |
|------|-----------|---------|
| ROBUST | IS PF ≥ 1.15 AND OOS PF ≥ 1.15 | Strong in both periods |
| STABLE | IS PF ≥ 1.0 AND OOS PF ≥ 1.0 | Acceptable both periods |
| REGIME_DEPENDENT | IS PF < 1.0 AND OOS PF ≥ 1.2 | Only works in certain regimes |
| BROKEN_IN_OOS | IS PF > 1.2 AND OOS PF < 1.0 | Overfit — fails out of sample |
| MARGINAL | Everything else | Weak or inconsistent |

Any flag within 0.05 of a threshold gets `_BORDERLINE` appended (e.g., `ROBUST_BORDERLINE`).

**IS period**: all data before 2019-01-01.
**OOS period**: all data from 2019-01-01 onward.

---

## 8. Bootcamp scoring (0–100 scale)

Each accepted strategy gets a Bootcamp score designed to predict prop-firm survivability:

| Component | Weight | What it measures |
|-----------|--------|-----------------|
| Profitability | 30 pts | PF above 1.0. Score = 30 × clip((PF − 1.0) / 1.0) |
| OOS stability | 25 pts | Weighted: OOS PF (50%), recent 12m PF (30%), IS PF (20%) |
| Drawdown control | 20 pts | DD-to-profit ratio. Score = 20 × clip(1 − ratio/1.5) |
| Trade count | 15 pts | Total trades (50%) + trades/year (50%). Benchmarks: 120 trades, 12/yr |
| Consistency | 10 pts | Profitable year %, losing streak length, quality score, consistency flag |

**Quality penalties** (subtracted from total):

| Flag | Penalty |
|------|---------|
| ROBUST | 0 |
| STABLE | 0 |
| STABLE_BORDERLINE | −2 |
| REGIME_DEPENDENT | −5 |
| MARGINAL | −8 |
| EDGE_DECAYED_OOS | −10 |
| BROKEN_IN_OOS | −15 |

---

## 9. Final acceptance gates

### Promotion gate (combo → refinement)
- Profit factor ≥ 1.0
- Total trades ≥ 50
- Trades per year ≥ 3.0
- Max 20 candidates (ranked by composite: quality 40% + OOS PF 30% + trades/yr 30%)

### Leaderboard acceptance (refined → accepted)
- Profit factor ≥ 1.0
- OOS profit factor ≥ 1.0
- Total trades ≥ 60

### Yearly consistency analysis
Each accepted strategy gets a consistency flag:
- **CONSISTENT**: ≥ 60% profitable years, max 2 consecutive losing years
- **MIXED**: ≥ 40% profitable years, max 4 consecutive losing years
- **INCONSISTENT**: everything else

---

## 10. Portfolio evaluation

After all families and timeframes complete, all accepted strategies are evaluated together:

1. **Trade reconstruction**: replay each accepted strategy's best parameters on the full dataset
2. **Daily returns**: convert trade-level PnL to daily time series for correlation analysis
3. **Correlation matrix**: Pearson correlation between all strategy daily return series
4. **Monte Carlo stress tests** (10,000 iterations per strategy):
   - Shuffle trade order
   - Measure: 95th percentile max drawdown, 99th percentile max drawdown, median net PnL
5. **Shock tests**:
   - Drop 10% of trades randomly → measure PnL impact
   - Add extra slippage → measure PnL impact
6. **Yearly breakdown**: PnL, PF, trade count per year per strategy

---

## 11. Current results summary

From the latest full 5-timeframe ES run (27 accepted strategies, ~23 unique):

**By timeframe**: daily (13), 30m (7), 60m (6), 15m (1), 5m (0)

**By quality**: ROBUST (6), ROBUST_BORDERLINE (3), STABLE_BORDERLINE (7), REGIME_DEPENDENT (9), STABLE (1), MARGINAL_BORDERLINE (1)

**Top 6 portfolio-grade candidates** (BCS > 65):
1. 30m MR mom exhaustion — PF 2.34, 100 trades, OOS 2.76, ROBUST
2. 30m MR vol dip — PF 2.10, 67 trades, OOS 1.94, ROBUST
3. Daily MR vol dip — PF 2.21, 302 trades, OOS 2.65, ROBUST_BORDERLINE
4. 30m MR base — PF 1.65, 111 trades, OOS 1.91, ROBUST
5. Daily short MR — PF 2.21, 64 trades, OOS 1.68, ROBUST
6. 30m MR trend pullback — PF 1.71, 120 trades, OOS 1.96, ROBUST_BORDERLINE

**Critical observation**: All 6 portfolio-grade candidates are mean reversion. Zero trend or breakout strategies at portfolio grade. Every accepted trend strategy is REGIME_DEPENDENT with IS PF below 1.0.

---

## 12. Known issues and open questions

1. **Trend family underperformance**: all trend strategies use time_stop exits and are REGIME_DEPENDENT. Exit types (trailing stops) are declared as supported and wired into the refinement grid, but the latest leaderboard shows no accepted trend strategy with exit_type=trailing_stop. Either trailing stops genuinely don't help ES trend, or there's a pipeline issue.

2. **Subtype duplication**: 4 leaderboard entries are exact duplicates where a subtype found the same best strategy as its parent family (identical refined params, PF, and trade count). These inflate the count from 27 to ~23 unique strategies.

3. **5m timeframe barren**: zero accepted strategies across all families on ES 5m. The 1.28M row dataset may need different filter logic or the IS/OOS split may not suit intraday patterns.

4. **Portfolio is 100% mean reversion**: no diversification across strategy families. This is the single biggest risk for the Bootcamp — if MR goes through a bad regime, all 6 strategies lose simultaneously.

5. **Single instrument**: ES only. Cross-instrument expansion (CL, NQ) would provide natural decorrelation.

6. **No walk-forward validation**: current IS/OOS is a single fixed split at 2019-01-01. Walk-forward across multiple windows would provide stronger confidence.

---

## 13. Key Python files for code review

If you want to read the actual implementation, these are the files that matter:

| File | What it does | Lines |
|------|-------------|-------|
| `master_strategy_engine.py` | Main orchestrator — runs the full pipeline, builds leaderboards | ~800 |
| `modules/engine.py` | Trade execution engine, quality flags, IS/OOS splits | ~600 |
| `modules/filters.py` | All filter classes (entry signal logic) | ~900 |
| `modules/strategies.py` | ExitType enum, ExitConfig, BaseStrategy, build_exit_config() | ~200 |
| `modules/refiner.py` | Parallel parameter grid search (refinement stage) | ~300 |
| `modules/feature_builder.py` | Precomputed SMA, ATR, momentum columns | ~80 |
| `modules/filter_combinator.py` | C(n,k) combination generator | ~40 |
| `modules/bootcamp_scoring.py` | 0–100 Bootcamp survival score | ~150 |
| `modules/portfolio_evaluator.py` | Monte Carlo, correlations, stress tests | ~400 |
| `modules/prop_firm_simulator.py` | The5ers Bootcamp challenge simulation | ~500 |
| `modules/consistency.py` | Yearly PnL consistency analysis | ~100 |
| `modules/vectorized_signals.py` | Vectorised filter mask computation (performance) | ~40 |
| `modules/strategy_types/mean_reversion_strategy_type.py` | MR family: filter pool, refinement grid, promotion thresholds | ~400 |
| `modules/strategy_types/trend_strategy_type.py` | Trend family: same structure | ~400 |
| `modules/strategy_types/breakout_strategy_type.py` | Breakout family: same structure | ~400 |
| `modules/strategy_types/strategy_factory.py` | Registry of all 15 families | ~60 |
| `config.yaml` | All configurable thresholds and settings | ~40 |
