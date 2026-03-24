# ES ALL-TIMEFRAMES RESULTS ANALYSIS

> Session 27 Part B review based on the recovered all-timeframes run outputs now present under `Outputs/`.
> Source files used:
> - `Outputs/master_leaderboard.csv`
> - `Outputs/ES_daily/family_leaderboard_results.csv`
> - `Outputs/ES_60m/family_leaderboard_results.csv`
> - `Outputs/ES_30m/family_leaderboard_results.csv`
> - `Outputs/ES_15m/family_leaderboard_results.csv`
> - available `correlation_matrix.csv`, `portfolio_review_table.csv`, and `yearly_stats_breakdown.csv` files

---

## Overall Summary

The recovered run produced **9 accepted strategies across 4 ES timeframes**:

- **Daily**: 3 accepted
- **60m**: 2 accepted
- **30m**: 3 accepted
- **15m**: 1 accepted

Accepted families by timeframe:

| Timeframe | Mean Reversion | Trend | Breakout |
|----------|----------------|-------|----------|
| Daily | True | True | True |
| 60m | True | True | False |
| 30m | True | True | True |
| 15m | True | False | False |

Key answers:

- **Which timeframes produced ROBUST strategies?**
  - **30m**: mean reversion
  - **60m**: mean reversion
- **Which families succeeded overall?**
  - Mean reversion accepted on **all 4** timeframes
  - Trend accepted on **daily, 60m, 30m**
  - Breakout accepted on **daily, 30m**
- **Did trend work on daily?**
  - **Yes**, but not cleanly robust. Daily trend was accepted with `quality_flag = REGIME_DEPENDENT`, `leader_pf = 1.86`, `is_pf = 0.85`, `oos_pf = 2.57`.

High-level read:

- Mean reversion is still the most reliable family.
- **30m** is the strongest Bootcamp-style timeframe so far because it combines multiple accepted families with the highest trade frequency.
- **15m did not become the broad solution**. It produced one accepted MR strategy, but trend failed and breakout produced no trades.

---

## Per-Timeframe Breakdown

### ES daily

| Family | accepted_final | quality_flag | leader_pf | is_pf | oos_pf | leader_trades | is_trades | oos_trades | leader_net_pnl | Best filter combination |
|--------|----------------|--------------|-----------|-------|--------|---------------|-----------|------------|----------------|-------------------------|
| mean_reversion | True | STABLE_BORDERLINE | 2.16 | 1.03 | 2.39 | 351 | 203 | 148 | 3,010,479.50 | `DownCloseFilter, LowVolatilityRegimeFilter, StretchFromLongTermSMAFilter` |
| trend | True | REGIME_DEPENDENT | 1.86 | 0.85 | 2.57 | 212 | 129 | 83 | 480,666.00 | `PullbackFilter, VolatilityFilter, UpCloseFilter, HigherLowFilter` |
| breakout | True | STABLE_BORDERLINE | 1.30 | 1.03 | 1.52 | 366 | 195 | 171 | 244,518.00 | `CompressionFilter, PriorRangePositionFilter, TightRangeFilter` |

Takeaways:

- Daily was much stronger than expected.
- Trend did work on daily, but the IS/OOS split says the edge is regime-sensitive rather than uniformly stable.
- Daily mean reversion is the standout PnL winner of the entire run.

### ES 60m

| Family | accepted_final | quality_flag | leader_pf | is_pf | oos_pf | leader_trades | is_trades | oos_trades | leader_net_pnl | Best filter combination |
|--------|----------------|--------------|-----------|-------|--------|---------------|-----------|------------|----------------|-------------------------|
| mean_reversion | True | ROBUST | 1.71 | 1.67 | 1.80 | 61 | 42 | 19 | 83,878.44 | `DistanceBelowSMAFilter, TwoBarDownFilter, ReversalUpBarFilter` |
| trend | True | REGIME_DEPENDENT | 1.13 | 0.83 | 1.71 | 285 | 172 | 113 | 58,975.75 | `PullbackFilter, RecoveryTriggerFilter, MomentumFilter, TwoBarUpFilter, TrendSlopeFilter, HigherLowFilter` |
| breakout | False | BROKEN_IN_OOS | 3.42 | 273.54 | 0.00 | 7 | 4 | 3 | 2,321.50 | `CompressionFilter, ExpansionBarFilter, BreakoutCloseStrengthFilter, TightRangeFilter` |

Takeaways:

- 60m mean reversion remains a solid benchmark and is still ROBUST.
- 60m trend was accepted, but again only as regime-dependent.
- 60m breakout is not viable in its current form.

### ES 30m

| Family | accepted_final | quality_flag | leader_pf | is_pf | oos_pf | leader_trades | is_trades | oos_trades | leader_net_pnl | Best filter combination |
|--------|----------------|--------------|-----------|-------|--------|---------------|-----------|------------|----------------|-------------------------|
| mean_reversion | True | ROBUST | 2.11 | 2.40 | 1.94 | 126 | 71 | 55 | 386,129.00 | `DistanceBelowSMAFilter, TwoBarDownFilter, ReversalUpBarFilter` |
| trend | True | REGIME_DEPENDENT | 1.19 | 0.68 | 1.52 | 698 | 386 | 312 | 112,627.00 | `PullbackFilter, RecoveryTriggerFilter, VolatilityFilter, MomentumFilter, TwoBarUpFilter, TrendSlopeFilter` |
| breakout | True | REGIME_DEPENDENT | 1.15 | 0.98 | 1.23 | 209 | 96 | 113 | 45,650.00 | `CompressionFilter, RangeBreakoutFilter, ExpansionBarFilter, BreakoutTrendFilter, TightRangeFilter` |

Takeaways:

- 30m is the strongest all-around timeframe in the run.
- It has one ROBUST strategy plus two more accepted strategies.
- 30m trend has by far the highest trade count in the run.

### ES 15m

| Family | accepted_final | quality_flag | leader_pf | is_pf | oos_pf | leader_trades | is_trades | oos_trades | leader_net_pnl | Best filter combination |
|--------|----------------|--------------|-----------|-------|--------|---------------|-----------|------------|----------------|-------------------------|
| mean_reversion | True | LOW_IS_SAMPLE | 1.22 | 0.74 | 1.25 | 206 | 25 | 181 | 35,931.50 | `BelowFastSMAFilter, TwoBarDownFilter, ReversalUpBarFilter, CloseNearLowFilter, StretchFromLongTermSMAFilter` |
| breakout | False | NO_TRADES | 0.00 | 0.00 | 0.00 | 0 | 0 | 0 | 0.00 | `CompressionFilter, RangeBreakoutFilter, ExpansionBarFilter, BreakoutTrendFilter, TightRangeFilter` |
| trend | False | MARGINAL | 0.60 | 0.48 | 0.70 | 442 | 266 | 176 | -74,257.00 | `PullbackFilter, RecoveryTriggerFilter, VolatilityFilter, MomentumFilter, TwoBarUpFilter, TrendSlopeFilter` |

Takeaways:

- 15m did not generalize well.
- The only accepted 15m strategy is sample-light MR, not a confident portfolio anchor.
- High trade count alone did not rescue 15m trend quality.

### Trade Count Comparison

Total leader trades by accepted strategies:

- Daily MR: 351
- Daily trend: 212
- Daily breakout: 366
- 60m MR: 61
- 60m trend: 285
- 30m MR: 126
- 30m trend: 698
- 30m breakout: 209
- 15m MR: 206

What this says:

- **30m**, not 15m, gave the biggest trade-frequency breakthrough.
- **30m trend** is the clear volume leader.
- **60m MR** remains useful but trade-thin.

---

## Master Leaderboard Review

Top 5 accepted strategies by the run's master leaderboard ranking:

| Rank | Timeframe | Family | Strategy | Quality | PF | Net PnL |
|------|-----------|--------|----------|---------|----|---------|
| 1 | Daily | Mean Reversion | `RefinedMR_HB5_ATR0.4_DIST1.2_MOM0` | STABLE_BORDERLINE | 2.16 | 3,010,479.50 |
| 2 | Daily | Trend | `RefinedTrend_HB5_ATR0.75_VOL0.9_MOM10` | REGIME_DEPENDENT | 1.86 | 480,666.00 |
| 3 | 30m | Mean Reversion | `RefinedMR_HB20_ATR0.4_DIST1.4_MOM0` | ROBUST | 2.11 | 386,129.00 |
| 4 | Daily | Breakout | `RefinedBreakout_HB5_ATR0.5_COMP0.9_MOM0` | STABLE_BORDERLINE | 1.30 | 244,518.00 |
| 5 | 30m | Trend | `RefinedTrend_HB24_ATR1.25_VOL0.8_MOM20` | REGIME_DEPENDENT | 1.19 | 112,627.00 |

Patterns that repeat across timeframes:

- Mean reversion based on `DistanceBelowSMAFilter + TwoBarDownFilter + ReversalUpBarFilter` worked on **30m and 60m**.
- Trend was accepted on **daily, 30m, and 60m**, but never as ROBUST.
- Breakout only survived on **daily and 30m**.

Important nuance:

- The master leaderboard is stronger than the portfolio-evaluation layer right now.
- Several accepted strategies did **not** make it into the portfolio/correlation outputs, which means reconstruction coverage is still incomplete despite the earlier timeframe bug fix.

---

## Correlation Analysis

Correlation coverage is partial because the portfolio evaluator only reconstructed a subset of accepted leaders:

- **Daily**: 2 reconstructed strategies
- **60m**: 2 reconstructed strategies
- **30m**: 1 reconstructed strategy
- **15m**: no correlation matrix produced

Observed accepted-strategy pairs:

| Timeframe | Pair | Correlation | Interpretation |
|-----------|------|-------------|----------------|
| Daily | MR vs breakout | 0.273 | comfortably below the 0.3 warning line |
| 60m | MR vs trend | -0.009 | essentially uncorrelated |

Flags:

- **No reconstructed pair exceeded 0.3 correlation.**
- The most uncorrelated reconstructed pair is **60m MR vs 60m trend** at roughly **-0.009**.

Caveat:

- This is not a full accepted-strategy correlation study yet because daily trend, 30m MR, 30m breakout, and 15m MR were not all reconstructed into the portfolio layer.
- So the low-correlation signal is encouraging, but still incomplete.

---

## Trade Count Assessment

Using the 2008-01-02 to 2026-03-17 dataset span, approximate trades/year for accepted leaders:

| Timeframe | Family | Strategy | Trades/Year | Classification |
|-----------|--------|----------|-------------|----------------|
| Daily | Mean Reversion | `RefinedMR_HB5_ATR0.4_DIST1.2_MOM0` | 19.3 | Bootcamp Core |
| Daily | Trend | `RefinedTrend_HB5_ATR0.75_VOL0.9_MOM10` | 11.6 | Viable but not Core |
| Daily | Breakout | `RefinedBreakout_HB5_ATR0.5_COMP0.9_MOM0` | 20.1 | Bootcamp Core |
| 30m | Mean Reversion | `RefinedMR_HB20_ATR0.4_DIST1.4_MOM0` | 6.9 | Viable but not Core |
| 30m | Trend | `RefinedTrend_HB24_ATR1.25_VOL0.8_MOM20` | 38.3 | Bootcamp Core |
| 30m | Breakout | `RefinedBreakout_HB6_ATR0.5_COMP0.8_MOM0` | 11.5 | Viable but not Core |
| 60m | Mean Reversion | `RefinedMR_HB12_ATR0.5_DIST1.2_MOM0` | 3.4 | Bootcamp Supplemental |
| 60m | Trend | `RefinedTrend_HB15_ATR1.0_VOL0.0_MOM14` | 15.7 | Bootcamp Core |
| 15m | Mean Reversion | `RefinedMR_HB12_ATR1.25_DIST1.2_MOM0` | 11.3 | Viable but not Core |

Most important trade-count conclusions:

- **60m MR** is still useful, but it remains too thin as a primary Bootcamp building block.
- **30m trend** is the strongest trade-frequency candidate by a large margin.
- Daily strategies are viable enough on frequency, which changes the old assumption that only lower timeframes could solve the trade-count problem.

---

## Implications for Roadmap

### 1. Trend does not need to be deprioritized

Trend did **not** fail everywhere.
It was accepted on daily, 60m, and 30m.

What the run actually says is:

- trend can work,
- but it tends to come through as **REGIME_DEPENDENT** rather than truly robust,
- so **trend subfamily splitting and better exits** are still high-value improvements.

### 2. Breakout should not be deprioritized either

Breakout failed on 60m and 15m, but succeeded on daily and 30m.

So the conclusion is not "breakout is broken."
It is closer to:

- breakout is **timeframe-sensitive**,
- daily and 30m may be the right home for it,
- 60m breakout is currently weak.

### 3. 30m looks like the clearest Bootcamp path

This is the strongest directional conclusion from the run:

- 30m produced **3 accepted strategies**
- one is **ROBUST**
- one has **very strong trade frequency**
- breakout also survives there

If the goal is a practical Bootcamp portfolio, **30m deserves top billing in the next refinement cycle**.

### 4. Filter expansion is still worthwhile, but not because the whole system is too thin

The all-timeframes run did produce multiple viable strategies.
So the problem is no longer "nothing works."

The better framing now is:

- the system has some real edges,
- but family/timeframe coverage is uneven,
- and filter expansion could improve weak zones like 60m breakout and 15m trend.

### 5. Instrument expansion is still important

The reconstructed intra-timeframe correlations are encouragingly low, but the coverage is incomplete and all strategies are still ES-only.

That means CL/NQ expansion remains valuable for two reasons:

- diversification beyond ES regime dependence
- more chances to find robust, trade-active families where ES is weak

### 6. Portfolio evaluator reconstruction still needs follow-up

This run exposed a remaining operational gap:

- leaderboard acceptance found 9 strategies
- portfolio evaluation only reconstructed a subset of them

So the roadmap item to re-run all timeframes with fully correct portfolio evaluation is still valid.

---

## Bottom Line

The recovered all-timeframes run is much stronger than the earlier partial snapshot suggested.

What it really says:

- **Mean reversion is the most reliable family**
- **30m is the strongest all-around timeframe**
- **Daily also worked much better than expected**
- **Trend did work on daily**, but as regime-dependent rather than robust
- **Breakout is viable on daily and 30m**
- **15m is not the obvious answer**
- **60m MR remains good but thin**

If choosing the next practical development priorities from these results:

1. Emphasize **30m and daily** in the next result-driven iteration
2. Improve **trend exits / subfamily structure** rather than abandoning trend
3. Keep **breakout** in play, but focus on the timeframes where it already shows life
4. Fix the remaining **portfolio reconstruction coverage** gap
5. Continue toward **CL/NQ expansion** for diversification
