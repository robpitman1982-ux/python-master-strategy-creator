# Python Master Strategy Creator — Complete System Review for Cross-LLM Analysis

## Document Purpose
This document provides a complete technical review of an automated futures strategy discovery engine. It is designed to be shared with other LLMs (ChatGPT, Gemini, Grok, DeepSeek) to get independent analysis on how to improve the system's filters, parameters, and strategy logic to discover more profitable, low-drawdown strategies for prop firm challenges.

---

## 1. THE GOAL — What We're Optimizing For

We are building portfolios of futures trading strategies to pass The5ers prop firm evaluations. The three target programs are:

| Program | Account | Steps | Max DD | Daily DD | Profit Target | Key Constraint |
|---------|---------|-------|--------|----------|---------------|----------------|
| **Pro Growth** | $20K | 1 | 6% | 3% | 10% | Tiny account, tight DD |
| **High Stakes** | $100K | 2 | 10% | 5% | 8% + 5% | Must pass 2 steps sequentially |
| **Bootcamp** | $250K | 3 | 5% | None | 6% × 3 | Tightest DD, 3 sequential steps |
**Critical insight:** The dominant constraint is drawdown management, not raw profit. A strategy with PF 1.3 and $5K max drawdown is far more valuable than PF 2.0 with $15K drawdown. We need MANY strategies with LOW individual drawdown and LOW correlation to each other, so the portfolio can diversify risk.

**What success looks like:** A portfolio of 4-6 uncorrelated strategies across different markets and timeframes, each contributing small but consistent profits, with combined portfolio P95 drawdown well under the program limit. Current best Bootcamp portfolio achieves ~46% pass rate through all 3 steps.

---

## 2. MARKETS AND DATA

8 futures markets, each with 4 timeframes (daily, 60m, 30m, 15m):

| Market | Symbol | $/Point | Tick Value | Data Range | Character |
|--------|--------|---------|------------|------------|-----------|
| E-mini S&P 500 | ES | $50 | $12.50 | 2008-2026 | High liquidity, trends well |
| E-mini Nasdaq | NQ | $20 | $5.00 | 2008-2026 | Tech-heavy, volatile |
| Crude Oil | CL | $10 | $0.01 | 2008-2026 | Commodity, regime-driven |
| Gold | GC | $100 | $0.10 | 2008-2026 | Safe haven, uncorrelated |
| Silver | SI | $5,000 | $0.005 | 2008-2026 | High vol, mean-reverting |
| Copper | HG | $250 | $0.0005 | 2008-2026 | Industrial, lowest DD strategies |
| Russell 2000 | RTY | $50 | $12.50 | 2008-2026 | Small-cap, diverges from ES |
| Dow Jones | YM | $5 | $1.00 | 2008-2026 | Large-cap, lower vol than ES |

Data is OHLCV bars from TradeStation. No volume-profile data, no tick data, no order book data. Only OHLC + volume + time.
---

## 3. CURRENT STRATEGY FAMILIES (15 total)

The engine organizes strategies into 15 "strategy types", each with its own filter pool and parameter grid:

### Long-Side Families (9)

**Trend Family (3 subtypes):**
- `trend` — Base trend following (SMA crossover + pullback + recovery + momentum)
- `trend_pullback_continuation` — Focus on pullback-then-resume pattern
- `trend_momentum_breakout` — Momentum-confirmed trend entries
- `trend_slope_recovery` — Slope acceleration detection

**Mean Reversion Family (3 subtypes):**
- `mean_reversion` — Base MR (below SMA + down bars + reversal bar)
- `mean_reversion_vol_dip` — Low-volatility dip buying
- `mean_reversion_mom_exhaustion` — Momentum exhaustion reversals
- `mean_reversion_trend_pullback` — MR within trend context

**Breakout Family (3 subtypes):**
- `breakout` — Base breakout (compression + range break + expansion)
- `breakout_compression_squeeze` — Tight-range squeeze breakouts
- `breakout_range_expansion` — Pure range expansion plays
- `breakout_higher_low_structure` — Higher-low structural breakouts

### Short-Side Families (3)
- `short_mean_reversion` — Overbought shorting (above SMA + up bars + reversal down)
- `short_trend` — Downtrend following (SMA below + rally failure + lower high)
- `short_breakout` — Downside breakout (below support + weak close + compression)
---

## 4. COMPLETE FILTER CATALOGUE

### 4.1 Trend Filters (12 available for long trend)
```
TrendDirectionFilter     — Fast SMA(50) > Slow SMA(200) [confirms uptrend]
PullbackFilter           — Previous close ≤ Fast SMA [price pulled back]
RecoveryTriggerFilter    — Current close > Fast SMA [recovery from pullback]
VolatilityFilter         — Current ATR ≥ long-term ATR × multiplier [vol is elevated]
MomentumFilter           — Close > Close[N bars ago] [price has upward momentum]
UpCloseFilter            — Close > Previous Close [simple up bar]
TwoBarUpFilter           — Two consecutive up closes
TrendSlopeFilter         — Fast SMA today > Fast SMA[5 bars ago] [trend accelerating]
CloseAboveFastSMAFilter  — Close > Fast SMA [price above short MA]
HigherLowFilter          — Current low > Previous low [higher low structure]
HigherHighFilter         — Current high > Previous high [trend continuation]
OutsideBarFilter         — Current range engulfs previous bar entirely
```

### 4.2 Mean Reversion Filters (13 available for long MR)
```
BelowFastSMAFilter          — Close < Fast SMA(20) [below mean]
DistanceBelowSMAFilter      — (SMA - Close) ≥ ATR × min_distance [stretched below]
DownCloseFilter              — Close < Previous Close [down bar]
TwoBarDownFilter             — Two consecutive down closes
ThreeBarDownFilter           — Three consecutive down closes
ReversalUpBarFilter          — Close > Open [bullish reversal bar]
LowVolatilityRegimeFilter   — ATR ≤ Long-term ATR × max_mult [low vol regime]
AboveLongTermSMAFilter       — Close > SMA(200) [still in long-term uptrend]
CloseNearLowFilter           — (Close - Low) / Range ≤ 0.35 [close near bar low]
StretchFromLongTermSMAFilter — (SMA200 - Close) ≥ ATR × distance [far from LT mean]
InsideBarFilter              — Range entirely within previous bar [compression]
ATRPercentileFilter          — ATR rank in bottom 30% of lookback [low vol environment]
GapDownFilter                — Open < Previous Low [gap down]
```
### 4.3 Breakout Filters (15 available)
```
CompressionFilter            — ATR ≤ Long-term ATR × 0.75 [volatility squeeze]
RangeBreakoutFilter          — Close > Highest high of N bars [range breakout]
ExpansionBarFilter           — True Range ≥ ATR × 1.5 [expansion bar]
BreakoutRetestFilter         — Close > Prior high + ATR buffer [breakout with buffer]
BreakoutTrendFilter          — Fast SMA > Slow SMA [breakout in uptrend context]
BreakoutCloseStrengthFilter  — (Close - Low) / Range ≥ 0.60 [strong close]
PriorRangePositionFilter     — Previous close in top half of N-bar range
BreakoutDistanceFilter       — Close - Prior high ≥ ATR × 0.10 [meaningful breakout]
RisingBaseFilter             — Second-half lows ≥ First-half lows [ascending base]
TightRangeFilter             — Current range ≤ Avg range × 0.85 [tight bar]
InsideBarFilter              — (shared with MR)
OutsideBarFilter             — (shared with Trend)
ATRPercentileFilter          — (shared)
HigherHighFilter             — (shared with Trend)
GapUpFilter                  — Open > Previous High [gap up]
```

### 4.4 Short MR Filters (9 available)
```
AboveFastSMAFilter           — Close > Fast SMA(20) [above mean]
DistanceAboveSMAFilter       — (Close - SMA) ≥ ATR × distance [stretched above]
UpCloseShortFilter           — Close > Previous Close [still rising - exhaustion setup]
TwoBarUpShortFilter          — Two consecutive up closes [exhaustion]
ReversalDownBarFilter        — Close < Open [bearish reversal bar]
HighVolatilityRegimeFilter   — ATR ≥ Long-term ATR × 1.1 [high vol for short MR]
StretchAboveLongTermSMAFilter — (Close - SMA200) ≥ ATR × distance [far above LT mean]
InsideBarFilter              — (shared)
GapUpFilter                  — (shared)
```
### 4.5 Short Trend Filters (8 available)
```
DowntrendDirectionFilter     — Fast SMA(50) < Slow SMA(200) [confirms downtrend]
RallyInDowntrendFilter       — Previous close ≥ Fast SMA [rally within downtrend]
FailureToHoldFilter          — Current close < Fast SMA [rally failed]
LowerHighFilter              — Current high < Previous high [structural decline]
DownCloseShortFilter         — Close < Previous Close [bearish bar]
DowntrendSlopeFilter         — Fast SMA today < Fast SMA[5 bars ago] [trend worsening]
LowerLowFilter               — Current low < Previous low [breakdown]
OutsideBarFilter             — (shared)
```

### 4.6 Short Breakout Filters (9 available)
```
DownsideBreakoutFilter       — Close < Lowest low of N bars [downside breakout]
WeakCloseFilter              — (Close - Low) / Range ≤ 0.35 [weak close]
CompressionFilter            — (shared)
TightRangeFilter             — (shared)
BreakoutCloseStrengthFilter  — (shared, but measures weak close for shorts)
DowntrendDirectionFilter     — (shared with Short Trend)
InsideBarFilter              — (shared)
GapDownFilter                — (shared)
LowerLowFilter               — (shared)
```

### 4.7 Universal / Cross-Family Filters
```
InsideBarFilter    — Range within previous bar (compression signal)
OutsideBarFilter   — Range engulfs previous bar (expansion signal)
GapUpFilter        — Open > Previous High
GapDownFilter      — Open < Previous Low
ATRPercentileFilter — ATR percentile rank within lookback window
HigherHighFilter   — Current high > Previous high
LowerLowFilter     — Current low < Previous low
```
---

## 5. HOW THE PIPELINE WORKS

### Stage 1: Filter Combination Sweep
For each strategy family, the engine generates C(n, k) combinations of its filter pool, where k ranges from 3 to 5 (or 6 for MR). Example: 13 MR filters choosing 3-6 at a time = 792 combinations. Each combination becomes a strategy: ALL selected filters must pass simultaneously on a bar to generate an entry signal. The engine runs a full backtest for each combination.

### Stage 2: Promotion Gate
Strategies that pass minimum thresholds get promoted for refinement:
- Profit Factor ≥ 0.80 (loose — catches near-misses)
- Total trades ≥ 60
- Trades per year ≥ 3.0
- Max 20 promoted candidates per family (ranked by composite score)

### Stage 3: Parameter Refinement
Each promoted candidate gets its filter combination tested across a grid of exit parameters:

**Mean Reversion Refinement Grid:**
- `hold_bars`: [2, 3, 4, 5, 6, 8, 10, 12] (scaled by timeframe multiplier)
- `stop_distance_points` (ATR multiple): [0.4, 0.5, 0.75, 1.0, 1.25, 1.5]
- `min_avg_range` (distance-below-SMA threshold): [0.4, 0.6, 0.8, 1.0, 1.2, 1.4]
- `momentum_lookback`: [0] (not used in MR)
- `exit_type`: [TIME_STOP, PROFIT_TARGET, SIGNAL_EXIT]
- `profit_target_atr`: [0.5, 1.0, 1.5, 2.0, 3.0]
- `signal_exit_reference`: ["fast_sma"]

**Trend Refinement Grid:**
- `hold_bars`: [3, 4, 5, 6, 8, 10, 12, 15]
- `stop_distance_points`: [0.75, 1.0, 1.25, 1.5, 2.0, 2.5]
- `min_avg_range`: [0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4]
- `momentum_lookback`: [0, 5, 8, 10, 14]
- Same exit types as MR
### Stage 4: Quality Assessment
Each refined strategy gets evaluated on:
- **IS/OOS Split**: Pre-2019 = In-Sample, Post-2019 = Out-of-Sample
- **Quality Flag**: ROBUST (IS PF ≥ 1.15, OOS PF ≥ 1.15), STABLE (both ≥ 1.0), MARGINAL (below), BROKEN_IN_OOS, REGIME_DEPENDENT, etc.
- **Yearly Consistency**: % profitable years, max consecutive losing years
- **Bootcamp Score**: 0-100 composite weighing profitability (30%), OOS stability (25%), drawdown control (20%), trade frequency (15%), consistency (10%), minus quality penalties

### Stage 5: Leaderboard
Best refined strategy per family per market/timeframe enters the ultimate leaderboard. Currently 315 strategies across all 8 markets and 4 timeframes.

### Stage 6: Portfolio Selection
1. **Hard filter**: ROBUST/STABLE quality, OOS PF > 1.0, bootcamp_score > 40, ≥ 60 trades
2. **Return matrix**: Daily-resampled returns for correlation calculation
3. **Pearson correlation matrix**: Between all candidate pairs
4. **Combinatorial sweep**: C(n, 4) combinations of strategies, gated by max pairwise correlation
5. **Portfolio Monte Carlo**: 10,000 simulations of each portfolio through the prop firm steps (sequential: must pass Step 1 before starting Step 2, etc.)
6. **Sizing optimizer**: Grid search of micro contract weights per strategy to minimize time-to-fund while maintaining ≥ 40% pass rate

---

## 6. EXIT LOGIC (Trade Management)

The engine supports 4 exit types:

### TIME_STOP (Default)
- Enter at close + slippage. Protective stop = entry ± (ATR × stop_distance_atr). Exit after `hold_bars` bars at close ± slippage. Stop checked each bar.

### PROFIT_TARGET
- Same entry and stop. Additional target = entry ± (ATR × profit_target_atr). Target checked before time exit.

### TRAILING_STOP
- Trailing stop tracks highest high (long) or lowest low (short) minus ATR × trailing_stop_atr. Only moves in favorable direction. Replaces time exit.

### SIGNAL_EXIT
- For long MR, exits when close ≥ Fast SMA (mean reversion complete). Falls through to time exit if signal not triggered.
---

## 7. TRADE SIMULATION DETAILS

- **Position sizing**: `risk_amount = initial_capital × 0.01`, `contracts = risk_amount / (stop_distance × dollars_per_point)`, minimum 1 contract
- **Uses initial_capital** for sizing (not compounding)
- **Commission**: $2.00 per contract round-trip
- **Slippage**: 4 ticks per side (e.g., ES = 4 × $12.50 / $50 = 1.0 points slippage each way)
- **No pyramiding**: Only one position at a time
- **Sequential**: Must close current trade before opening new one
- **Direction**: Each family is either long-only or short-only (no switching within a strategy)

---

## 8. PRECOMPUTED FEATURES AVAILABLE TO FILTERS

The `feature_builder.py` adds these columns to every dataframe before backtesting:

```
bar_range      = High - Low
prev_close     = Close shifted by 1 bar
true_range     = max(H-L, |H-prevC|, |L-prevC|)
sma_{N}        = Simple moving average of Close (configurable lengths)
avg_range_{N}  = Rolling mean of bar_range
atr_{N}        = Rolling mean of true_range (Average True Range)
mom_diff_{N}   = Close - Close[N bars ago] (momentum difference)
```

**Standard SMA lengths by family:**
- Trend: SMA(50), SMA(200) scaled by timeframe
- MR: SMA(20), SMA(200) scaled by timeframe
- Breakout: SMA(50), SMA(200) scaled by timeframe

**Timeframe scaling:**
- 60m = base (multiplier 1.0)
- Daily = 60/390 ≈ 0.154 (so SMA50 on daily → SMA(8))
- 30m = 60/30 = 2.0 (so SMA50 on 30m → SMA(100))
- 15m = 60/15 = 4.0 (so SMA50 on 15m → SMA(200))
- 5m = 60/5 = 12.0 (so SMA50 on 5m → SMA(600))
---

## 9. CURRENT RESULTS — What's Working and What Isn't

### Best Strategies by Market (from ultimate leaderboard, 315 total)
- **NQ**: 56 strategies — dominates the leaderboard. Daily MR is the single best strategy.
- **GC**: 53 strategies — gold works well, structurally uncorrelated to equity indices.
- **RTY**: 39 strategies — Russell 2000, different character from ES/NQ.
- **CL**: 38 strategies — crude oil, regime-driven.
- **SI**: 37 strategies — silver, high vol, good MR.
- **ES**: 36 strategies — S&P 500, solid but highly correlated with NQ.
- **YM**: 30 strategies — Dow, lower vol.
- **HG**: 26 strategies — copper, produced the LOWEST drawdown strategy in the entire leaderboard (15m short breakout, ~$4.5K DD).

### Portfolio Results (Bootcamp $250K)
Top portfolio: NQ daily MR + SI daily BO + NQ 60m MR + NQ 15m MR → **46.5% pass rate**, 13.4 months median time-to-fund, 8.8% P95 DD.

### Key Observation
- **Daily timeframe strategies dominate** — MR daily is the best strategy type
- **Intraday (30m, 15m) produces few accepted strategies** — the 30m/15m strategies struggle to pass quality gates
- **Mean reversion is the strongest family overall**
- **Short-side strategies are valuable for diversification** but produce fewer winners
- **Portfolio correlation is excellent** — median absolute correlation ~0.003 between selected strategies

---

## 10. KNOWN LIMITATIONS AND GAPS

### What the Engine Currently CANNOT Do
1. **No multi-timeframe confirmation** — Can't use daily trend as filter for 60m entry
2. **No intermarket signals** — Can't use VIX level to filter ES entries, or gold strength to filter silver
3. **No volume-based filters beyond simple threshold** — No VWAP, no volume profile, no accumulation/distribution
4. **No time-of-day or day-of-week filters** — Can't avoid/target specific sessions or days
5. **No seasonality filters** — No month-of-year, no quarterly patterns
6. **No volatility regime TRANSITION detection** — Can detect high/low vol, but not vol INCREASING or DECREASING
7. **No pattern recognition** — No head-and-shoulders, no double tops, no wedges
8. **No adaptive lookback periods** — All lookbacks are fixed; can't adapt to current market conditions
9. **No partial position management** — All-in, all-out only; no scaling in/out
10. **No break-even stop** — Can't move stop to breakeven after X profit
11. **No Chandelier exit** — Can't trail stop from highest high by ATR multiple (trailing stop exists but is different)
12. **No RSI, MACD, Stochastic, Bollinger Bands, or other standard indicators** — Only price action, SMA, and ATR-based filters
13. **No order flow / market microstructure** — No bid/ask, no depth, no tick data analysis
14. **No regime classification** — Can't detect "trending market" vs "ranging market" as a meta-state

### Current Bottlenecks
- 5m timeframe requires dedicated long runs (gets preempted on SPOT VMs)
- GCP quota limits to single 96-vCPU VM
- Refinement grid is brute-force (not Bayesian/Optuna)
- Each strategy family runs independently — no cross-family filter sharing during sweep