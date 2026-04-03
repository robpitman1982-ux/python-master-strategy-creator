# Strategy Engine Improvement Roadmap
## Synthesised from Claude, ChatGPT, and Gemini Analysis
## March 2026

---

## Guiding Principle

**Stop optimizing for "best backtest" — optimize for "highest probability of surviving 6% target before 5% drawdown, repeatedly."**

All three analyses converge on this. The engine's infrastructure is done. The next phase is about what it searches and how it judges results.

---

## Phase 1: Immediate (Next 2-3 Sessions)
### Theme: "See the multi-timeframe results, then fix exits"

### 1A. Analyse the all-timeframe ES run results
- Review master leaderboard across daily/60m/30m/15m
- Key questions: Did any timeframe produce trend? Did 15m/30m give more trades? Are accepted strategies uncorrelated?
- This determines whether the filter library is the bottleneck or just the data scope

### 1B. Add exit architecture (THE #1 engine improvement)
All three analyses agree this is the single highest-impact change.

**Add three exit types as first-class pipeline parameters:**

| Exit Type | How it works | Best for |
|-----------|-------------|----------|
| `trailing_stop` | Stop follows price by N × ATR from highest high since entry | Trend, Breakout |
| `profit_target` | Exit at N × ATR from entry price | Mean Reversion |
| `signal_exit` | Exit when price returns to/crosses a reference (e.g., fast SMA) | Mean Reversion |

**Keep `time_stop` as a backstop** — max hold bars still applies, but it's no longer the primary exit.

**Implementation:** Add an `exit_type` parameter to the refinement grid. Each strategy type declares which exit types are valid. The grid sweeps exit_type alongside hold_bars, stop_distance, etc. This means the refinement grid grows from 256 to ~768 combos (3 exit types × 256), but the quality improvement should be dramatic.

**Why this is #1:** A strong entry with bad exits looks mediocre. ChatGPT is right that trend and breakout are probably being handicapped by the blunt time-based exit. Trailing stops alone might rescue the trend family.

### 1C. Add Bootcamp-native scoring
Replace PF/PnL as the primary ranking metric with a composite score:

```
bootcamp_score = (
    0.35 × mc_pass_rate_all_steps
  + 0.25 × (1 - p95_dd_pct / 0.05)   # how far from the 5% DD limit
  + 0.20 × trade_frequency_score      # penalise < 10 trades/year
  + 0.10 × consistency_score          # % profitable rolling windows
  + 0.10 × (1 - outlier_dependency)   # how much PnL depends on top 5 trades
)
```

**Add two leaderboard modes:**
- `research_leaderboard` — current PF/PnL ranking (keep for general research)
- `bootcamp_leaderboard` — bootcamp_score ranking (primary for prop firm track)

The prop firm simulator already calculates MC pass rate. The missing pieces are trade frequency scoring, outlier dependency, and wiring it into the main pipeline rather than post-analysis.

---

## Phase 2: Core Engine Expansion (Sessions after Phase 1)
### Theme: "Expand what the engine can see"

### 2A. Add short-side strategies
Make `direction` a first-class parameter: `LONG_ONLY`, `SHORT_ONLY`, `BOTH`.

Mirror the existing filter library:
- MR Short: DistanceAboveSMA + TwoBarUp + ReversalDownBar
- Trend Short: FastSMA < SlowSMA + rally to SMA + failure below
- Breakout Short: Compression + downside expansion bar

This is not just about doubling opportunities — it's about portfolio resilience. Long-only portfolios suffer correlated drawdowns during selloffs, which is exactly when The5ers DD limit kills you.

### 2B. Split trend into two subfamilies (ChatGPT's best insight)
Current "trend" is really pullback-continuation (MR inside a trend). True trend-following is a different strategy:

**Trend-A: Pullback Continuation** (existing)
- Uptrend confirmed → price pulls back → recovery trigger → enter

**Trend-B: Momentum/Breakout Trend** (new)
- Regime is trending (ADX > 25 or similar) → breakout above prior swing high → momentum confirmation → trailing stop exit

These should be separate strategy families with separate filter pools and separate refinement grids. Mixing them in one family is probably why "trend" keeps failing — the sweep is averaging across two fundamentally different ideas.

### 2C. Add new filters (prioritised by data availability)

**Tier 1 — Can implement immediately with existing OHLCV data:**
- `InsideBarFilter` — current bar range inside previous bar (compression)
- `OutsideBarFilter` — current bar engulfs previous bar (expansion)
- `GapFilter` — open != previous close (gap up/down)
- `ATRPercentileFilter` — current ATR vs rolling 1-year ATR percentile
- `ADXFilter` — trend strength / regime detection
- `HigherHighFilter` — current high > previous high
- `LowerLowFilter` — current low < previous low

**Tier 2 — Requires volume data (already in TradeStation exports):**
- `VolumeSpikeFilter` — volume > N × average volume
- `VolumeDryUpFilter` — volume < N × average volume
- `VolumeConfirmationFilter` — breakout with above-average volume

**Tier 3 — Requires session/time awareness (need to check data format):**
- `SessionFilter` — RTH only / first hour / last hour
- `DayOfWeekFilter` — filter by day
- These depend on whether the TradeStation exports include enough time-of-day granularity

### 2D. Vectorize signal generation
Rewrite filter evaluation from per-bar loops to vectorized boolean columns:

```python
# Current (slow): loop bar-by-bar, call filter.passes(data, i)
# Target (fast): precompute all filters as boolean Series
data['f_trend_dir'] = data['sma_50'] > data['sma_200']
data['f_pullback'] = data['close'].shift(1) <= data['sma_50'].shift(1)
data['f_recovery'] = data['close'] > data['sma_50']
signals = data['f_trend_dir'] & data['f_pullback'] & data['f_recovery']
```

**Estimated speedup: 50-100×.** This unlocks everything in later phases — wider grids, walk-forward, more filters — without proportional compute cost increases.

**Also add filter result caching:** Many combinations share filters. Compute each filter once as a boolean Series, store it, then combine. This eliminates redundant computation across the combinatorial sweep.

---

## Phase 3: Robustness and Validation (After Phase 2 working)
### Theme: "Prove it's real, not lucky"

### 3A. Walk-forward validation
Replace the single 2019-01-01 split with rolling windows:
- Train on years 1-6, test on year 7
- Roll forward: train 2-7 test 8, train 3-8 test 9, etc.
- Strategy is "walk-forward robust" only if profitable in ≥75% of OOS windows

This is the gold standard for proving a strategy isn't overfit. Both ChatGPT and Gemini flag this as critical.

### 3B. Multi-split OOS validation (simpler alternative)
If full walk-forward is too compute-heavy initially, test against multiple split dates:
- 2016, 2018, 2020, 2022
- Strategy must pass OOS on ≥3 of 4 splits
- Much cheaper than walk-forward but catches single-split luck

### 3C. Perturbation tests (ChatGPT's idea)
For each accepted strategy, run:
- Entry delayed by 1 bar
- Exit delayed by 1 bar
- Stop widened by 20%
- Stop tightened by 20%
- Commission doubled
- One filter removed from the winning combo

If the strategy collapses under any of these, it's fragile and shouldn't be trusted in live trading. Flag it as `FRAGILE` in the quality system.

### 3D. Regime tagging
Tag each bar/period with market regime:
- Trending vs ranging (ADX or MA slope)
- High vol vs low vol (ATR percentile)
- Bull vs bear (above/below 200 SMA)

Then measure each strategy's performance BY regime. This lets you:
- Stop overrating strategies that only work in one environment
- Intentionally build complementary portfolios where different strategies cover different regimes

---

## Phase 4: Portfolio-Level Optimisation
### Theme: "Build the best team, not the best individual"

### 4A. Portfolio contribution scoring
For each candidate, calculate:
- Standalone bootcamp_score
- Correlation penalty vs currently selected strategies
- Regime overlap penalty
- Incremental MC pass rate improvement when added to portfolio

This lets the engine say: "This PF 1.3 strategy improves the portfolio more than that PF 1.7 strategy because it's uncorrelated and covers a regime gap."

### 4B. Portfolio-level Bootcamp simulation
Run the full 3-step challenge simulation with the combined portfolio trade stream, not individual strategies. The portfolio must pass as a unit.

### 4C. Expand to CL, NQ, GC
Different instruments have different market dynamics. The same engine, same filters, same pipeline — just different data. This is the cheapest way to find uncorrelated strategies because instrument diversification is inherently decorrelated.

---

## Phase 5: Efficiency and Scale
### Theme: "Search wider without burning money"

### 5A. Adaptive refinement (Optuna/Bayesian)
Replace brute-force grid with intelligent search. But only AFTER exits and filters are expanded — smarter optimisation of a weak idea set just finds better versions of mediocre ideas.

### 5B. Pre-screening
Before running full backtests, quickly count how many signal bars a filter combination produces. If < 30 signals across 18 years, skip the backtest entirely. This could eliminate 50%+ of combinations for free.

### 5C. Multi-VM parallel orchestration
Already planned (Session 26 roadmap item). Split datasets across VMs, consolidate results.

---

## What NOT to do (avoid these traps)

1. **Don't add VWAP/opening range/institutional flow filters yet** — they require tick-level or intraday reference data that your current exports may not support. Stick to OHLCV + volume filters first.

2. **Don't over-optimise the refinement grid before fixing exits** — a finer grid over bad exits finds better versions of bad strategies.

3. **Don't spend more time on dashboard/infrastructure** — it's good enough. Every hour spent on dashboard polish is an hour not spent on strategy quality.

4. **Don't try to implement everything at once** — each phase builds on the previous one. Exit architecture must come before short-side expansion. Vectorization should come before adding 20 new filters.

5. **Don't skip the multi-timeframe results analysis** — the current run might reveal that the filter library is already adequate and the real problem is exits and timeframe coverage. Let the data tell you.

---

## Session Planning

| Session | Focus | Estimated effort |
|---------|-------|-----------------|
| 27 | Analyse multi-timeframe results + filter summary doc | 1 session |
| 28-29 | Exit architecture (trailing stop, profit target, signal exit) | 2 sessions |
| 30 | Bootcamp scoring + dual leaderboard | 1 session |
| 31-32 | Short-side strategies | 2 sessions |
| 33 | Trend subfamily split (pullback vs momentum) | 1 session |
| 34-35 | New filters (Tier 1 + Tier 2) | 2 sessions |
| 36-37 | Vectorization | 2 sessions |
| 38-39 | Walk-forward validation | 2 sessions |
| 40 | Perturbation tests | 1 session |
| 41-42 | CL + NQ data sweep | 2 sessions |
| 43-44 | Portfolio-level optimisation | 2 sessions |

That's roughly 16-18 sessions to go from current state to a fully Bootcamp-optimised portfolio selection system. The first 5 sessions (exits + scoring) will likely produce the biggest quality jump.
