# STRATEGY ENGINE ANALYSIS

> Comprehensive write-up of what the engine does, how every major file fits together,
> what each filter is designed to capture, and where the current weaknesses are.
>
> Last updated: 2026-03-24 (Session 27 Pre-Work)

---

## Part 1: What We're Building

This repository is a **strategy discovery engine** for futures trading. It is not a live
trading system and it is not placing orders. Its job is to search historical data for
strategy candidates that are statistically robust enough to earn a place in a future
portfolio.

The intended markets are:
- **ES** (E-mini S&P 500)
- **CL** (Crude Oil)
- **NQ** (Nasdaq)
- **GC** (Gold)

The operational target is **The5ers $250K Bootcamp**, which is a three-step prop challenge:
- 6% profit target per step
- 5% max drawdown constraint
- 1:7.5 leverage on indices

That target matters because it changes what "good" looks like. The end goal is not one
beautiful backtest. The end goal is a **portfolio of about six uncorrelated strategies**
that can repeatedly survive the Bootcamp path with acceptable drawdown.

Data is currently sourced from **TradeStation CSV exports** going back to 2008. The active
timeframes are:
- daily
- 60m
- 30m
- 15m

Planned later:
- 5m in Phase 2
- 1m excluded for now because it is noisier, heavier, and less aligned with the current
  engine design

In short, this codebase is building a research pipeline that finds candidate strategies
from long-run futures data, ranks them, stress-tests them, and prepares them for future
portfolio construction.

---

## Part 2: Pipeline Architecture

The engine runs a staged funnel for each dataset and each strategy family. The families are
currently:
- trend
- mean_reversion
- breakout

### 1. Sanity Check

Before spending serious compute, the engine runs a base strategy with default settings to
confirm the dataset loads correctly and the backtest loop produces trades. This is a cheap
guardrail against broken CSVs, feature-precompute issues, or family definitions that never
trigger.

### 2. Filter Combination Sweep

The main search starts by generating all valid `C(n, k)` filter combinations for a family,
where `k` ranges from `min_filters` to `max_filters`.

Each combination is run with default entry/exit parameters, and the engine records:
- profit factor
- average trade
- net PnL
- total trades
- IS/OOS trade counts
- IS/OOS PF
- quality flag
- quality score
- yearly consistency metrics

This stage answers the first important question: **which combinations of filters even look
promising before parameter tuning?**

### 3. Promotion Gate

Sweep results then go through a deliberately loose promotion gate. Candidates are filtered by:
- minimum profit factor
- minimum total trades
- minimum trades per year

They are then ranked and capped at 20 promoted candidates. This cap is important because
refinement is much more expensive than sweep evaluation. The gate is intentionally permissive:
it is designed to keep "interesting enough" candidates alive for deeper testing rather than
killing them too early.

### 4. Refinement Grid

Promoted candidates are re-run across a parameter grid:
- `hold_bars`
- `stop_distance`
- `min_avg_range`
- `momentum_lookback`

In the current architecture, the default refinement grid is effectively **4 x 4 x 4 x 4 = 256**
parameter combinations per candidate. That makes refinement thorough, but also brute-force.

Every refined variant gets the same full metric treatment:
- IS/OOS split
- quality flag
- quality score
- consistency stats

### 5. Leaderboard

For each family, the pipeline compares:
- the best sweep combo
- the best refined combo

The refined version only becomes the family leader if it actually improves the outcome used
for selection. Then a final acceptance gate is applied, typically checking:
- minimum PF
- minimum OOS PF
- minimum total trades

Only accepted family leaders move on.

### 6. Portfolio Evaluation

Accepted strategies are reconstructed and evaluated together at the portfolio layer. This stage
produces the risk view that simple PF/PnL rankings cannot:
- Monte Carlo drawdowns at the 95th and 99th percentile
- stress tests like trade drops and extra slippage
- correlation matrix between strategies
- yearly PnL breakdown

This is where the engine shifts from "what backtested well?" to "what might actually survive?"

### 7. Master Leaderboard

After all datasets in a run finish, the engine aggregates accepted strategies across datasets
into `Outputs/master_leaderboard.csv`. This cross-dataset view is the first real portfolio
candidate pool because it brings together different timeframes under one ranking table.

---

## Part 3: File Inventory

### `master_strategy_engine.py`

Main orchestrator for the research pipeline. It loads config, iterates datasets, runs each
strategy family, triggers refinement, writes family outputs, calls portfolio evaluation, and
creates the master leaderboard.

### `modules/engine.py`

Contains the core backtest and evaluation machinery:
- `MasterStrategyEngine`
- `EngineConfig`
- trade execution loop
- quality flag assignment
- quality score calculation
- IS/OOS metric splitting

This is the heart of the system.

### `modules/strategies.py`

Defines the strategy objects used by the engine. These classes hold filter lists, parameter
state, and signal-generation logic. The current system is built around combinations of filters
that all need to pass before a long entry is taken.

### `modules/data_loader.py`

Loads TradeStation CSV data into a usable DataFrame. It normalizes column names and date/time
handling so the rest of the engine can work on consistent OHLCV inputs.

### `modules/feature_builder.py`

Precomputes reusable columns such as:
- SMAs
- ATR values
- momentum values
- bar range
- true range
- average range

This reduces repeated calculation inside filter logic.

### `modules/filters.py`

Defines all filter classes used by the strategy families. Every filter implements a `passes()`
method that checks whether the current bar satisfies a market condition. The whole search engine
is built around combining these filters into candidate entry rules.

### `modules/strategy_types/`

Family-specific strategy definitions:
- `trend_strategy_type.py`
- `mean_reversion_strategy_type.py`
- `breakout_strategy_type.py`
- `strategy_factory.py`
- `base_strategy_type.py`

These modules define:
- which filters belong to each family
- default family parameters
- which lookbacks are required
- how refinement grids are constructed
- how timeframe scaling is applied

### `modules/refiner.py`

Runs the parallel parameter refinement stage. It expands promoted candidates into refinement
grids, executes those variants, and collects/ranks the results.

### `modules/portfolio_evaluator.py`

Evaluates accepted strategies after the family stage. It reconstructs strategies from leaderboard
rows, rebuilds trade histories, and calculates:
- Monte Carlo drawdowns
- stress tests
- correlations
- yearly statistics

### `modules/prop_firm_simulator.py`

Adds a prop-firm-specific lens. It models The5ers challenge mechanics, estimates Monte Carlo
pass rates, and provides scoring/ranking logic that is more aligned with Bootcamp survival than
plain PF/PnL.

### `modules/consistency.py`

Performs year-by-year PnL analysis. It helps detect whether a strategy is broadly stable or
only works in isolated periods.

### `modules/master_leaderboard.py`

Aggregates accepted strategies across datasets from a single run into one cross-dataset
leaderboard.

### `modules/ultimate_leaderboard.py`

Aggregates accepted strategies across **multiple runs**, deduplicates them, and maintains the
bigger cross-run opportunity set for review in the dashboard.

### `modules/config_loader.py`

Loads config values and provides timeframe-aware helpers like:
- `get_timeframe_multiplier()`
- `scale_lookbacks()`

This is important because the same family logic needs different practical lookbacks on daily
versus intraday data.

### `modules/progress.py`

Provides progress tracking and writes `status.json` so long-running sweeps can be monitored by
the dashboard or remote tooling.

### `dashboard.py` / `dashboard_utils.py`

The Streamlit monitoring and analysis layer. It exposes:
- active run monitoring
- results exploration
- ultimate leaderboard browsing
- run history
- system status

### `run_cloud_sweep.py`

Thin one-command wrapper for launching a GCP sweep from the repo root. It is the operational
entry point for normal cloud runs.

### `cloud/launch_gcp_run.py`

More detailed launcher/orchestration logic:
- manifest creation
- input bundling
- upload
- remote monitoring
- artifact download
- cleanup

This is the main cloud automation engine behind `run_cloud_sweep.py`.

---

## Part 4: Complete Filter Inventory

The filter library is the engine's vocabulary. Each filter expresses one piece of market logic.
The search process tries different combinations of these pieces.

### Trend Filters (10)

| Filter | What it does | Why it exists |
|--------|---------------|---------------|
| `TrendDirectionFilter` | Fast SMA above slow SMA | Confirms uptrend regime before taking continuation trades |
| `PullbackFilter` | Previous close at or below the fast SMA | Looks for a dip inside the trend |
| `RecoveryTriggerFilter` | Current close back above the fast SMA | Uses recovery as the entry trigger after the pullback |
| `VolatilityFilter` | ATR is above a minimum threshold vs longer-term ATR | Avoids dead markets with too little movement |
| `MomentumFilter` | Current close above close N bars ago | Confirms positive directional push |
| `TwoBarUpFilter` | Two consecutive higher closes | Adds short-term bullish confirmation |
| `TrendSlopeFilter` | Fast SMA rising over recent bars | Requires the trend to be improving, not just positive |
| `HigherLowFilter` | Current low above previous low | Adds structure consistent with continuation |
| `UpCloseFilter` | Current close above previous close | Simple bullish confirmation bar |
| `CloseAboveFastSMAFilter` | Current close above fast SMA | Keeps entries on the stronger side of the short-term mean |

### Mean Reversion Filters (10 core filters plus the baseline condition set)

The code currently exposes **10 explicit mean reversion filter classes** in `modules/filters.py`.
The session brief describes this family as 11 because the operating MR setup is usually thought
of as "10 filters plus the baseline below-fast-SMA condition that frames the whole family."

| Filter | What it does | Why it exists |
|--------|---------------|---------------|
| `BelowFastSMAFilter` | Close below fast SMA | Defines the short-term stretch below the mean |
| `DistanceBelowSMAFilter` | Close is at least N ATR below the fast SMA | Requires a meaningful stretch, not a tiny dip |
| `DownCloseFilter` | Current close below previous close | Captures short-term selling pressure |
| `TwoBarDownFilter` | Two consecutive down closes | Looks for mild exhaustion |
| `ThreeBarDownFilter` | Three consecutive down closes | Looks for stronger exhaustion |
| `ReversalUpBarFilter` | Current close above current open | Adds a simple snapback trigger |
| `LowVolatilityRegimeFilter` | ATR below a regime threshold | Favors calmer conditions where MR often works better |
| `AboveLongTermSMAFilter` | Close above 200 SMA | Keeps long MR aligned with the larger trend |
| `CloseNearLowFilter` | Close in the bottom portion of the bar range | Captures weak closes that may precede reversal |
| `StretchFromLongTermSMAFilter` | Price meaningfully below 200 SMA in ATR terms | Finds deeper long-term stretch setups |

### Breakout Filters (9)

| Filter | What it does | Why it exists |
|--------|---------------|---------------|
| `CompressionFilter` | ATR below its longer-term average | Looks for squeeze conditions before expansion |
| `ExpansionBarFilter` | Current true range above ATR by a multiplier | Confirms the breakout bar is unusually large |
| `BreakoutRetestFilter` | Close above prior N-bar high, optionally with ATR buffer | Confirms resistance has been cleared |
| `BreakoutTrendFilter` | Fast SMA above slow SMA | Keeps breakouts aligned with broader trend |
| `BreakoutCloseStrengthFilter` | Close near the top of the current bar | Prefers strong closes over weak breakout attempts |
| `PriorRangePositionFilter` | Prior close high within its recent range | Looks for pre-breakout strength already in place |
| `BreakoutDistanceFilter` | Breakout exceeds prior high by at least N ATR | Avoids paper-thin breakouts |
| `RisingBaseFilter` | Lows are rising across a recent window | Captures the idea of a constructive base |
| `TightRangeFilter` | Current bar range below average by a multiplier | Looks for tight setups that can expand |

Notes:
- There is also a `RangeBreakoutFilter` class in `modules/filters.py`.
- The current session brief's nine-item breakout list reflects the actively emphasized breakout
  inventory, which centers on compression/expansion plus quality-of-breakout filters.

---

## Part 5: Current Weaknesses

### 1. Trade count is too thin

The best strategy found so far produces only about 3.4 trades per year. That is too sparse for
strong statistical confidence and too slow for a Bootcamp-style target that needs regular chances
to recover from drawdowns.

### 2. Only mean reversion works

The engine has found a credible MR edge, but trend and breakout have not yet passed cleanly.
That is a serious portfolio weakness because a prop portfolio cannot rely on one behavior type.

### 3. Filter library is solid but small

The current filters are sensible, but the total library is still limited. The engine explores
combinations thoroughly, but only within a relatively small vocabulary.

### 4. Refinement grid is brute-force

The 256-point refinement grid is simple and reliable, but not efficient. It spends compute
equally across promising and obviously poor regions.

### 5. All strategies are long-only

The whole architecture currently searches for long entries. That leaves bear-market opportunity
untapped and makes the portfolio more directionally fragile.

### 6. Exit logic is simplistic

Current exits are basically:
- time-stop
- fixed stop

That is probably good enough for early prototyping, but weak for serious strategy quality.
Trend and breakout especially want trailing or signal-aware exits, while MR wants more natural
profit-taking logic.

### 7. Single IS/OOS split

One fixed IS/OOS split is easy to reason about, but it is not enough to prove robustness across
different market regimes.

### 8. No Bootcamp-native scoring

The engine mostly ranks by PF, PnL, and quality flags. That is research-friendly, but it is not
the same as ranking by the probability of surviving Bootcamp constraints.

### 9. Bar-by-bar Python loop is slow

The engine evaluates signals and trades using Python loops. That is clear and flexible, but it
will become a bigger bottleneck as more filters, more datasets, and more validation schemes are
added.

### 10. No regime tagging

The system does not yet explicitly tag market regimes such as:
- trending
- ranging
- high volatility
- low volatility

Without regime tagging, it is harder to understand where an edge actually lives and which
strategies complement each other.

---

## Part 6: Priority Improvements

Ranked in practical order:

1. **Analyse the multi-timeframe ES run results**
   See what is actually working before changing the engine again.

2. **Improve exit architecture**
   Add trailing stops, profit targets, and signal exits because the current time-stop plus fixed
   stop logic likely suppresses trend and breakout quality.

3. **Add Bootcamp-native scoring**
   Rank strategies by drawdown-aware pass probability, not just PF/PnL.

4. **Vectorize signal generation**
   Speed matters because every planned improvement increases search load.

5. **Add short-side strategies**
   This expands opportunity and improves resilience across bearish regimes.

6. **Expand the filter library**
   New filters are valuable, but only after the engine is fast enough and exits are better.

7. **Add walk-forward validation**
   Multiple train/test windows are needed before trusting a strategy as truly robust.

8. **Introduce portfolio-level optimisation**
   The real target is the best team of strategies, not just the best standalone strategy.

9. **Add regime tagging**
   This will improve understanding, selection, and future live deployment logic.

10. **Move refinement toward adaptive search**
    Bayesian or Optuna-style refinement becomes more worthwhile after the strategy space is richer.
