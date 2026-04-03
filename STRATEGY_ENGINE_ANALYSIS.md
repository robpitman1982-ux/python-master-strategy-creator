# Strategy Discovery Engine — Complete System Analysis
## Rob Pitman | March 2026

---

## Part 1: What We're Building

The strategy discovery engine is a research tool that systematically searches for statistically robust algorithmic trading strategies across futures instruments. It is not a trading system — it produces *candidates* that, once validated, will be converted to EasyLanguage for live execution on TradeStation.

The end goal is qualifying for The5ers $250K Bootcamp prop firm program: a 3-step challenge requiring 6% profit at each step without exceeding 5% drawdown, using 1:7.5 leverage on indices. To pass reliably, the plan is to deploy a portfolio of ~6 uncorrelated strategies that smooth the equity curve enough to clear all three steps.

The engine currently searches across one instrument (ES / E-mini S&P 500) using data exported from TradeStation going back to 2008. Four timeframes are active: daily, 60-minute, 30-minute, and 15-minute. Three strategy families are tested: Mean Reversion, Trend Following, and Breakout.

---

## Part 2: How the Pipeline Works

The engine runs a sequential funnel for each strategy family on each dataset:

**Stage 1 — Sanity Check.** Run the base strategy with all default filters enabled to confirm the data loads correctly and the engine produces trades. This catches data format issues before burning compute on the full sweep.

**Stage 2 — Filter Combination Sweep.** Generate all mathematical combinations of the available filters (C(n, k) for k = min_filters to max_filters). Each combination is run with default hold_bars and stop_distance values. The engine records profit factor, average trade, net PnL, total trades, IS/OOS performance splits, and a quality flag for every combination. This is the most compute-intensive stage — on ES 60m with mean reversion, this produces 792 combinations to evaluate.

**Stage 3 — Promotion Gate.** Filter the sweep results by minimum profit factor, minimum trades, and minimum trades per year. Sort by net PnL descending and cap at 20 promoted candidates. The promotion gate is deliberately loose — the idea is to let marginal candidates through so they can be refined, rather than killing them early.

**Stage 4 — Refinement Grid Search.** For each promoted candidate, run a grid search over four parameters: hold_bars (how many bars to hold the position), stop_distance (how far away the stop loss sits, in ATR multiples), min_avg_range (a volatility threshold), and momentum_lookback (how many bars of momentum to check). The grid is typically 4×4×4×4 = 256 parameter combinations per candidate. Each is evaluated with full IS/OOS split and quality scoring. On 60m this produces ~192 refined variants per candidate.

**Stage 5 — Leaderboard.** Compare the best combo (from the sweep) versus the best refined variant for each family. The refined version wins only if it improves net PnL. A final acceptance gate applies: minimum overall PF, minimum OOS PF, and minimum total trades. Strategies that pass are marked `accepted_final = True`.

**Stage 6 — Portfolio Evaluation.** For all accepted leaders across families, the engine reconstructs trade histories and calculates: IS/OOS profit factors, maximum drawdown, Monte Carlo drawdown distributions (95th and 99th percentile), stress tests (10% random trade removal, extra slippage), and a correlation matrix between strategy returns. Yearly PnL breakdowns show consistency across market regimes.

**Stage 7 — Master Leaderboard.** After all datasets complete, an aggregator scans every dataset's output directory, collects accepted strategies, adds market/timeframe labels, ranks them by quality flag and net PnL, and writes a single `master_leaderboard.csv`.

---

## Part 3: The Files and What They Do

### Core Engine

**`master_strategy_engine.py`** — The main orchestrator. Loops through each dataset defined in the config, runs all three strategy families sequentially, manages the promotion gate logic, calls the refinement grid, builds the family leaderboard, triggers portfolio evaluation, and finally runs the master leaderboard aggregator. This is the file you invoke when you start a sweep.

**`modules/engine.py`** — The trade execution engine (`MasterStrategyEngine`). This is the backtest core: it iterates bar-by-bar through the data, checks for entry signals via `strategy.generate_signal()`, manages open positions with stop losses and time-based exits, tracks MAE/MFE (maximum adverse/favorable excursion), calculates all performance metrics (profit factor, win rate, average trade, drawdown), assigns quality flags and quality scores, and splits results into IS/OOS periods based on a configurable date.

**`modules/strategies.py`** — Strategy class definitions. Contains `BaseStrategy` (abstract), `TestStrategy` (trivial up-close trigger for testing), `FilterBasedTrendStrategy` (fixed 5-filter trend baseline), `CombinableFilterTrendStrategy` (dynamic filter assembly), and `RefinedFiveFilterTrendStrategy` (parameter-tuneable trend). Each strategy implements `generate_signal(data, i) → int` which returns 1 for a buy signal and 0 for no signal. All strategies are long-only.

**`modules/data_loader.py`** — Loads TradeStation CSV exports. Handles date parsing, column naming, and index setting. Expects OHLCV data with Date, Time, Open, High, Low, Close, Volume columns.

**`modules/feature_builder.py`** — Precomputes reusable columns that filters rely on: SMAs at various lengths, bar range, previous close, true range, ATR at various lookbacks, and momentum differences. These are calculated once per dataset load and stored as DataFrame columns so filters can access them by column name instead of recalculating per-bar.

### Filters

**`modules/filters.py`** — All filter classes, organized by strategy family. Every filter inherits from `BaseFilter` and implements `passes(data, i) → bool`. The sweep engine tests combinations of these filters to find which ones work together.

#### Trend Filters (8 total)

| Filter | What it checks | Purpose |
|--------|---------------|---------|
| **TrendDirectionFilter** | Fast SMA (50) > Slow SMA (200) | Confirms we're in an uptrend — the primary regime filter |
| **PullbackFilter** | Previous close ≤ fast SMA | Price has pulled back to or below the moving average — buy the dip |
| **RecoveryTriggerFilter** | Current close > fast SMA | Price has recovered above the MA — confirms the pullback is over |
| **VolatilityFilter** | Current ATR > minimum threshold | Ensures enough price movement to make the trade worthwhile |
| **MomentumFilter** | Close > close N bars ago | Confirms upward momentum over a lookback period |
| **TwoBarUpFilter** | Two consecutive higher closes | Short-term bullish pressure confirmation |
| **TrendSlopeFilter** | Fast SMA is rising (SMA today > SMA N bars ago) | The trend itself is accelerating, not just positive |
| **HigherLowFilter** | Current low > previous low | Classic higher-low pattern confirming trend continuation |

Additional trend-related: **UpCloseFilter** (close > open, bullish bar), **CloseAboveFastSMAFilter** (close > fast SMA).

#### Mean Reversion Filters (11 total)

| Filter | What it checks | Purpose |
|--------|---------------|---------|
| **BelowFastSMAFilter** | Close < fast SMA (20) | Price is below its short-term average — stretched to the downside |
| **DistanceBelowSMAFilter** | Close is ≥ N points/ATR below fast SMA | Requires a *meaningful* stretch, not just a tiny dip |
| **DownCloseFilter** | Close < previous close | Short-term selling pressure |
| **TwoBarDownFilter** | Two consecutive down closes | Stronger short-term exhaustion signal |
| **ThreeBarDownFilter** | Three consecutive down closes | Even stronger exhaustion — rarer but more conviction |
| **ReversalUpBarFilter** | Close > open on current bar | The reversal trigger — price is snapping back up |
| **LowVolatilityRegimeFilter** | ATR < maximum threshold | Targets calm markets where MR works better (less trending) |
| **AboveLongTermSMAFilter** | Close > slow SMA (200) | Only take MR longs when the macro trend is up |
| **CloseNearLowFilter** | Close in bottom 35% of bar range | Price closed weak — sets up the reversal |
| **StretchFromLongTermSMAFilter** | Close stretched below 200 SMA by ≥ N ATR | Deep pullback within long-term uptrend |

#### Breakout Filters (8 total)

| Filter | What it checks | Purpose |
|--------|---------------|---------|
| **CompressionFilter** | ATR below historical average × multiplier | Volatility has contracted — a squeeze is building |
| **ExpansionBarFilter** | Current bar range > average range × multiplier | The breakout bar itself is larger than normal |
| **BreakoutRetestFilter** | Close > prior N-bar high (with optional ATR buffer) | Price has broken above resistance |
| **BreakoutTrendFilter** | Fast SMA > slow SMA | Breakout is happening in the direction of the larger trend |
| **BreakoutCloseStrengthFilter** | Close in top 60%+ of bar range | Breakout bar closed strong, not just spiked and reversed |
| **PriorRangePositionFilter** | Previous close in top 50%+ of N-bar range | Price was already positioned high before breaking out |
| **BreakoutDistanceFilter** | Close > prior high by ≥ N × ATR | Breakout has enough distance to be meaningful |
| **RisingBaseFilter** | Second-half lows > first-half lows over lookback | Lows are rising — base pattern forming |
| **TightRangeFilter** | Current bar range < average × 0.85 | Today's bar is tight — potential squeeze setup |

### Strategy Type Implementations

**`modules/strategy_types/trend_strategy_type.py`** — Defines how trend strategies work: which filters are available, default parameters (hold_bars=6, stop_distance_atr=1.25), how the refinement grid scales across timeframes, and how to build a refined strategy from a set of filter classes and tuned parameters. Trend uses ATR-based stops.

**`modules/strategy_types/mean_reversion_strategy_type.py`** — Same structure for MR. Default hold_bars=5, stop_distance_atr=0.75. MR strategies hold for shorter periods and use tighter stops because they're betting on a quick snapback. The refinement grid includes hold_bars [2–12], stop_distance [0.3–1.5 ATR], and a distance/range parameter.

**`modules/strategy_types/breakout_strategy_type.py`** — Breakout family. Default hold_bars=8, stop_distance_atr=1.5. Breakouts use wider stops to give the move room to develop. The compression and expansion filters are the key edge identifiers.

### Refinement and Evaluation

**`modules/refiner.py`** — Parallel parameter grid search. Takes a strategy factory function and a grid of parameter values, distributes the work across multiple CPU cores using `ProcessPoolExecutor`, evaluates each parameter combination, and returns a sorted DataFrame of results.

**`modules/portfolio_evaluator.py`** — Reconstructs trade histories from leaderboard rows, runs Monte Carlo simulations (10,000 iterations by default), calculates stress test metrics, builds correlation matrices between strategy return streams, and produces yearly PnL breakdowns.

**`modules/prop_firm_simulator.py`** — Simulates a complete prop firm challenge. Models The5ers Bootcamp 3-step structure ($100K → $150K → $200K → funded at $250K), applies 6% profit targets and 5% drawdown limits at each step, runs Monte Carlo pass rate estimation, and scores/ranks multiple strategies for prop firm suitability.

**`modules/consistency.py`** — Year-by-year PnL analysis. Calculates percentage of profitable years, maximum consecutive losing years, and rolling 3-year PnL. Used to flag strategies that only work in specific market regimes.

**`modules/master_leaderboard.py`** — Cross-dataset aggregator. Scans all output subdirectories, filters to accepted strategies, adds market/timeframe labels, ranks by quality flag and net PnL.

### Configuration and Scaling

**`config.yaml`** — Central configuration: dataset paths, engine settings (capital, risk, commission, slippage), pipeline settings (max workers, OOS split date, max candidates), promotion gate thresholds, and leaderboard acceptance gates.

**`modules/config_loader.py`** — Loads config.yaml with hardcoded fallback defaults. Contains `get_timeframe_multiplier()` which returns scaling factors (daily=0.154, 60m=1.0, 30m=2.0, 15m=4.0, 5m=12.0) and `scale_lookbacks()` which adjusts SMA lengths, ATR lookbacks, and momentum lookbacks by these multipliers. Pattern-based filters (TwoBarDown, ReversalUpBar, etc.) are NOT scaled — they apply the same logic regardless of timeframe.

### Cloud Infrastructure

**`run_cloud_sweep.py`** — One-click wrapper that creates a GCP compute VM, uploads the code and data bundle, starts the engine, monitors progress, downloads results when done, and destroys the VM.

**`cloud/launch_gcp_run.py`** — The detailed Python launcher handling manifests, bundles, remote validation, monitoring, tarball download, and cleanup.

**`dashboard.py`** + **`dashboard_utils.py`** — Streamlit web dashboard served from the always-on console VM. Five tabs: Live Monitor (progress during active runs), Results (leaderboard, equity curves, correlation heatmaps), Ultimate Leaderboard (cross-run aggregation), Run History, and System health.

---

## Part 4: What We're Currently Aiming At

### Immediate objective: Build a candidate pool

The all-timeframe ES sweep currently running (daily + 60m + 30m + 15m × all 3 families on a 96-core GCP SPOT instance) is the first real attempt to build a broad pool of strategy candidates. Previously only ES 60m had been run, which produced exactly one accepted strategy (mean reversion, PF 1.71, 61 trades over 18 years).

The hypothesis is that shorter timeframes (15m, 30m) should produce more trade signals (addressing the thin trade count problem), while daily timeframe might be better suited for trend-following strategies (which failed on 60m).

### Success criteria for this run

1. **Multiple accepted strategies across timeframes** — ideally 4-8 ROBUST or STABLE strategies
2. **At least one working trend strategy** — daily timeframe is the best hope
3. **Uncorrelated returns** — correlation matrix should show near-zero correlation between MR and trend strategies
4. **Higher trade counts on shorter timeframes** — 15m should produce more than the ~3.4 trades/year that 60m MR gives

### After the candidate pool: prop firm optimization

Once we have a pool of accepted strategies, the next phase is assembling a portfolio specifically optimized for The5ers Bootcamp constraints:

- Select ~6 strategies with low cross-correlation
- Run Monte Carlo simulations of the full 3-step challenge
- Verify the portfolio can achieve 6% profit before hitting 5% drawdown with high probability
- The prop firm simulator already exists — it just needs real strategy trade lists to evaluate

### Expansion roadmap

After ES is thoroughly mined:
1. **CL (Crude Oil)** — different market dynamics, likely different filter combinations work
2. **NQ (Nasdaq 100)** — correlated with ES but higher volatility, may favour different strategies
3. **GC (Gold)** — historically a good trend-following market

Each instrument gets the same multi-timeframe sweep treatment. The ultimate leaderboard accumulates candidates across all instruments and all runs.

---

## Part 5: Known Weaknesses and Where We Can Improve

### 1. Trade count is too thin

The best strategy found so far (ES 60m MR) takes only ~3.4 trades per year — 61 trades across 18 years. At the prop firm level, this means it could take years to complete the challenge with a single strategy. The acceptance threshold is currently 60 total trades, but the Master Prompt originally targeted 400 trades for MR and 200 for trend.

**Improvement ideas:**
- **Lower timeframes should help naturally** — 15m and 30m data has 4× and 2× more bars, so filter combinations that trigger on 60m should trigger more often
- **Relax pattern filter requirements** — TwoBarDown + ReversalUpBar is a very specific pattern. Adding filters like single DownClose (instead of requiring two consecutive) or removing ReversalUpBar (entering on weakness instead of waiting for reversal) could increase signal frequency
- **Add new filters that identify more setups** — Volume-based filters (volume spike, volume dry-up), time-of-day filters (morning vs afternoon sessions), day-of-week filters, options expiration filters
- **Shorter hold periods** — The current winner holds for 12 bars (12 hours on 60m). Shorter holds mean faster turnover and more trades per year

### 2. Only mean reversion works so far

Trend and breakout both failed on ES 60m. Trend was REGIME_DEPENDENT (only works in certain market conditions), breakout was BROKEN_IN_OOS (overfit to in-sample). This is a significant gap — a portfolio of only MR strategies will struggle in strong trending markets.

**Improvement ideas:**
- **Daily timeframe for trend** — Trend-following historically works better on daily and weekly charts where noise is lower. The current run includes daily, so we'll see
- **Different trend filter architecture** — The current trend filters (pullback-to-SMA, recovery trigger) are essentially mean-reversion-of-a-trend. True trend strategies might work better with breakout-style entries (buy new highs) or momentum-based entries (buy when momentum exceeds threshold)
- **Longer trend hold periods** — Current default is 6 bars. Trend strategies on daily charts might need 20-60 bar holds to capture the move
- **Trailing stops for trend** — Current exits are time-based (hold N bars) or fixed stop. Trend strategies should use trailing stops (e.g., exit when price crosses below a trailing MA) to let winners run
- **Regime filtering** — Instead of trying to make trend work all the time, explicitly detect trending vs ranging regimes (e.g., ADX > 25) and only trade trend strategies during trending markets

### 3. Filter combinations are exhaustive but the filter library is small

The combinatorial sweep is mathematically thorough — it tests *every* combination. But it's only combining filters from a library of 8-11 per family. The search space is limited by the diversity of what's available.

**New filter ideas to implement:**

**Volume-based:**
- `VolumeSpike` — volume > N × average volume (institutional activity)
- `VolumeDryUp` — volume < N × average volume (potential squeeze building)
- `VolumeConfirmation` — breakout accompanied by above-average volume

**Time-based:**
- `SessionFilter` — only trade during specific sessions (US open, London overlap)
- `DayOfWeekFilter` — some days historically have directional bias
- `AvoidFOMC` — skip trading around Fed meeting days

**Market structure:**
- `SwingHighLow` — identify swing points for support/resistance
- `InsideBar` — current bar's range is inside previous bar's range (compression)
- `OutsideBar` — current bar engulfs previous bar (expansion)
- `GapFilter` — open gaps up/down from previous close

**Volatility regime:**
- `VIXRegimeFilter` — if VIX data is available, filter by volatility regime
- `ATRPercentile` — ATR relative to its own history (is current vol high or low?)
- `BollingerSqueeze` — Bollinger Band width at extreme lows

**Multi-timeframe:**
- `HigherTimeframeTrend` — check if the daily trend aligns with the 60m signal
- `MultiTimeframeConfluence` — signal must align across 2+ timeframes

### 4. The refinement grid is brute-force

The 4×4×4×4 = 256 parameter grid per candidate is fixed and exhaustive. This is reliable but not efficient — it tests many parameter combinations that are clearly suboptimal.

**Improvement ideas:**
- **Bayesian optimization** — Use tools like Optuna or Scikit-Optimize to intelligently explore the parameter space, concentrating search around promising regions
- **Adaptive grid** — Start with a coarse grid, identify hot zones, then refine with a finer grid in those zones only
- **Larger parameter ranges** — The current grid is narrow (e.g., hold_bars [2,3,4,5,6] for MR). Wider ranges might find strategies with different characteristics
- **More parameters** — Currently only 4 parameters are refined. Adding filter-specific parameters (SMA length, ATR lookback, distance thresholds) would explore a richer space
- **Genetic algorithms** — Evolve parameter sets over generations, crossing high-performing parents to find novel combinations

### 5. All strategies are long-only

The entire engine only generates buy signals. This means it can only make money when markets go up (trend) or bounce (MR). Short strategies would double the opportunity set.

**Improvement ideas:**
- **Short-side MR** — Buy when price is stretched above the SMA and sell when it snaps back. Mirror the existing MR filters
- **Short-side trend** — Sell when fast SMA < slow SMA with recovery below the MA
- **Direction parameter** — Add a direction flag to the strategy factory. The same filter logic can be inverted for shorts (DistanceAboveSMA, TwoBarUp before reversal down, etc.)

### 6. Exit logic is simplistic

Currently there are only two exit mechanisms: time-based (hold for N bars) and stop loss. There's no profit target, no trailing stop, and no signal-based exit.

**Improvement ideas:**
- **Profit targets** — Exit at N × ATR profit. MR strategies naturally target a mean return, so a 1-2 ATR target makes sense
- **Trailing stops** — Move the stop up as the trade goes in your favour. Essential for trend strategies to capture large moves
- **Signal-based exits** — Exit when an opposing signal fires (e.g., MR exits when price returns above the SMA)
- **Partial exits** — Scale out at profit targets while leaving a runner with a trailing stop
- **Volatility-adjusted exits** — Wider stops and targets in high-vol, tighter in low-vol

### 7. Compute efficiency

The engine processes data bar-by-bar in a Python loop. This is correct but slow — each filter's `passes()` method is called with DataFrame iloc access, which has overhead.

**Improvement ideas:**
- **Vectorized signal generation** — Precompute all filter conditions as boolean columns, then combine them with logical AND. This would replace the per-bar loop with vectorized pandas operations and could be 10-100× faster
- **Caching filter results** — Many filter combinations share common filters. Cache individual filter results and combine them, rather than re-evaluating shared filters across different combinations
- **Numba/Cython** — JIT-compile the hot loop for near-C performance
- **Pre-filtering** — Before running the full backtest, quickly check if a filter combination produces enough signals. If a combination only triggers 10 times across 18 years, skip the full backtest
- **Parallel datasets** — Currently datasets run sequentially. With multi-VM orchestration (already planned), different datasets could run simultaneously

### 8. No walk-forward validation

The current IS/OOS split is a single fixed date (2019-01-01). This gives one IS period and one OOS period. A strategy could pass OOS by luck.

**Improvement ideas:**
- **Walk-forward analysis** — Roll the IS/OOS window forward through time (e.g., train on 2008-2014, test on 2015; train on 2009-2015, test on 2016; etc.). A strategy must pass consistently across multiple OOS windows
- **K-fold cross-validation** — Split the data into K segments and rotate which segment is OOS
- **Multiple OOS split dates** — Test with splits at 2016, 2018, 2020, and 2022. A ROBUST strategy should pass all of them

### 9. No cost modeling for prop firm specifics

The engine models commission and slippage but doesn't account for prop firm-specific constraints like leverage limits, position size restrictions, or daily drawdown rules.

**Improvement ideas:**
- **Leverage-adjusted position sizing** — The5ers limits indices to 1:7.5 leverage. At $250K funded, that's ~$1.87M notional = ~37 ES contracts max. Current sizing doesn't account for this
- **Daily drawdown tracking** — The5ers funded stage has a 3% daily pause. The prop firm simulator handles this but it's not used during strategy discovery
- **Per-step simulation during refinement** — Instead of just checking total PF, simulate whether the strategy can actually pass each Bootcamp step

### 10. Data is single-instrument single-exchange

All data comes from TradeStation ES (CME). There's no cross-validation against other data sources, no synthetic data generation, and no regime labelling.

**Improvement ideas:**
- **Multiple data sources** — Validate strategies against data from a different vendor (e.g., Databento, TickData) to ensure results aren't artifact of TradeStation's data cleaning
- **Synthetic data testing** — Generate Monte Carlo price series with known statistical properties and test whether the engine produces false positives
- **Regime labelling** — Tag each period as trending/ranging/volatile/calm and analyze which strategies work in which regimes

---

## Part 6: Priority Improvements for The5ers Qualification

Ranked by impact on actually passing the Bootcamp:

1. **Get results from the multi-timeframe run** — see what we have before optimizing
2. **Add short-side strategies** — doubles opportunity set, critical for drawdown recovery during bear moves
3. **Implement trailing stops for trend** — the single biggest edge improvement for trend strategies
4. **Add volume and time-of-day filters** — cheapest way to expand the filter library
5. **Vectorize signal generation** — enables much larger sweeps at the same compute cost
6. **Walk-forward validation** — ensures strategies are genuinely robust, not lucky
7. **Portfolio-level optimization** — optimize the portfolio as a unit for Bootcamp constraints, not individual strategies
8. **Expand to CL and NQ** — more instruments = more uncorrelated candidates
