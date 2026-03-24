# IMPROVEMENT ROADMAP

> Phased plan synthesised from Claude, ChatGPT, and Gemini analysis.
> Target: improve the engine in the order most likely to increase Bootcamp survival odds.
>
> Last updated: 2026-03-24 (Session 27 Pre-Work)

---

## Guiding Principle

**Stop optimizing for "best backtest" - optimize for "highest probability of surviving 6% target before 5% drawdown, repeatedly."**

That is the core shift in this roadmap. The current engine is good at finding interesting
historical edges, but the next phase should optimize for **prop-firm survivability**, not just
profit factor and net PnL.

---

## Phase 1 - Immediate (Next 2-3 Sessions): "See the results, then fix exits"

### 1A: Analyse multi-timeframe ES run results

Before adding new engine complexity, review what the current all-timeframe ES sweep actually
produces:
- which families work on which timeframes
- where trade count improves
- whether trend finally works on daily or shorter timeframes
- which accepted strategies are realistic Bootcamp candidates

This step prevents blind optimisation.

### 1B: Add exit architecture - `trailing_stop`, `profit_target`, `signal_exit` as first-class parameters

The engine currently relies too heavily on time-stop plus fixed stop logic. That is probably the
largest quality bottleneck.

Add these exit types:

**Trailing stop**
- Follows price by `N x ATR` from the highest high since entry
- Best fit for trend and breakout
- Lets winners run instead of being cut off by arbitrary hold bars

**Profit target**
- Exits at `N x ATR` from entry
- Best fit for mean reversion
- Matches the "snap back to the mean" logic better than waiting on a time-stop

**Signal exit**
- Exit when price crosses a reference level tied to the strategy logic
- Example for MR: close back above fast SMA
- Example for trend: loss of trend condition or adverse SMA cross

Keep `time_stop` as a backstop, not the primary exit.

This also implies adding `exit_type` to refinement, increasing the search space from about
256 combinations to about 768. That cost increase is worth it if exit quality materially
improves strategy robustness.

### 1C: Bootcamp-native scoring (`bootcamp_score`)

Add a new scoring layer aimed at the actual target:
- MC pass rate (35%)
- drawdown margin from the 5% limit (25%)
- trade frequency (20%)
- consistency (10%)
- outlier dependency (10%)

Maintain two leaderboard modes:
- `research_leaderboard`
- `bootcamp_leaderboard`

That preserves research visibility while giving strategy selection a target-aligned ranking mode.

---

## Phase 2 - Core Engine Expansion: "Expand what the engine can see"

### 2A: Short-side strategies - direction as a first-class parameter

Add:
- `LONG_ONLY`
- `SHORT_ONLY`
- `BOTH`

This means mirroring the family logic for short setups rather than assuming all edge lives on the
long side. This matters for:
- bear markets
- drawdown recovery
- lower portfolio beta

### 2B: Split trend into two subfamilies

The current trend family likely mixes two different ideas:

**Trend-A: Pullback Continuation**
- Existing logic
- Uptrend plus pullback plus recovery

**Trend-B: Momentum/Breakout Trend**
- New logic
- Trend regime plus breakout above swing high plus trailing stop

Splitting the family allows separate filters, separate defaults, and more appropriate exits.

### 2C: New filters prioritised by data availability

**Tier 1 (OHLCV only)**
- `InsideBar`
- `OutsideBar`
- `Gap`
- `ATRPercentile`
- `ADX`
- `HigherHigh`
- `LowerLow`

**Tier 2 (volume)**
- `VolumeSpike`
- `VolumeDryUp`
- `VolumeConfirmation`

**Tier 3 (time/session)**
- `SessionFilter`
- `DayOfWeek`

These should be added in that order so the engine expands first with filters that fit the current
data model most naturally.

### 2D: Vectorize signal generation

This is the performance unlock:
- precompute filters as boolean columns
- combine them with logical AND
- cache filter outputs
- reuse them across combinations

Expected speedup: **50-100x**

That speedup is strategically important because it makes wider sweeps, more filters, and more
validation financially and operationally realistic.

---

## Phase 3 - Robustness and Validation: "Prove it's real, not lucky"

### 3A: Walk-forward validation

Add rolling windows such as:
- 6 years train / 1 year test

Require broad OOS profitability rather than one good split. This is the cleanest way to reduce
the chance of accidental overfitting.

### 3B: Multi-split OOS

If full walk-forward is too heavy initially, test simpler fixed splits:
- 2016
- 2018
- 2020
- 2022

This is a lighter alternative that still checks whether a candidate survives across multiple
regime boundaries.

### 3C: Perturbation tests

Stress candidates by intentionally degrading assumptions:
- entry delay
- exit delay
- wider stop
- tighter stop
- doubled commission
- filter removal

This helps detect fragile strategies that only work under one narrow parameter set.

### 3D: Regime tagging

Classify market conditions such as:
- trending vs ranging
- high volatility vs low volatility
- bull vs bear

Then measure each strategy by regime so the future portfolio can be built and traded more
intelligently.

---

## Phase 4 - Portfolio-Level Optimisation: "Best team, not best individual"

### 4A: Portfolio contribution scoring

Evaluate each strategy not only by standalone quality, but by what it adds to the portfolio:
- standalone score
- correlation penalty
- regime overlap penalty
- incremental Monte Carlo improvement

This is the shift from "best single backtest" to "best team composition."

### 4B: Portfolio-level Bootcamp simulation

Simulate the full Bootcamp path using the combined trade stream of multiple strategies, not just
one strategy at a time. This is the right test if the actual deployment goal is a diversified
portfolio.

### 4C: Expand to CL, NQ, GC

Once ES has been mined properly, extend the same engine to:
- CL
- NQ
- GC

That should improve decorrelation and enlarge the candidate pool more naturally than endlessly
optimising one market.

---

## Phase 5 - Efficiency and Scale: "Search wider without burning money"

### 5A: Adaptive refinement (Optuna/Bayesian)

Replace fixed brute-force refinement with adaptive search, but only after:
- exits are richer
- scoring is target-aligned
- the filter library is broader

Doing this too early would optimise a still-incomplete search space.

### 5B: Pre-screening

Add fast rejection of obviously weak combinations, for example:
- skip combos with fewer than 30 signals across the full history

This saves backtest time before the expensive parts of the engine even start.

### 5C: Multi-VM parallel orchestration

The current GCP quota in `us-central1` is **200 vCPU**.
Current full run usage is about **96 vCPU**.

That means practical options look like:
- `2 x 96 = 192` vCPU: possible but tight
- `96 + 80 = 176` vCPU: safer
- `96 + 48 = 144` vCPU: conservative

This becomes much more valuable when:
- CL, NQ, and GC are added
- walk-forward multiplies the amount of work
- multiple datasets need to run in parallel

The dashboard would then need to track multiple active VMs and consolidate their outputs cleanly.

---

## What NOT to Do

- Don't add VWAP or opening range filters yet; the current data setup is not ideal for them.
- Don't over-optimise refinement before fixing exits.
- Don't spend more time on dashboard or infrastructure right now.
- Don't implement everything at once; the phases intentionally build on each other.
- Don't skip multi-timeframe results analysis before starting the next engine changes.

---

## Session Planning Table

| Session | Focus | Effort |
|---------|-------|--------|
| 27 | Analyse multi-timeframe results + filter summary | 1 session |
| 28-29 | Exit architecture (trailing, target, signal) | 2 sessions |
| 30 | Bootcamp scoring + dual leaderboard | 1 session |
| 31-32 | Vectorization (before new filters) | 2 sessions |
| 33-34 | Short-side strategies | 2 sessions |
| 35 | Trend subfamily split | 1 session |
| 36-37 | New filters (Tier 1 + Tier 2) | 2 sessions |
| 38-39 | Walk-forward validation | 2 sessions |
| 40 | Perturbation tests | 1 session |
| 41-42 | CL + NQ data sweep | 2 sessions |
| 43-44 | Portfolio-level optimisation | 2 sessions |

---

## Bottom Line

The roadmap is intentionally sequenced:
- exits before filters
- filters before vectorization
- vectorization before walk-forward
- portfolio optimisation after the engine has a broader and more realistic candidate pool

That order gives the best chance of improving real Bootcamp survivability without wasting time on
premature optimisation.
