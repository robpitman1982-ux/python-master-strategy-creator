# STRATEGY ENGINE ANALYSIS

> Comprehensive write-up of what the engine does, how every file works,
> what every filter does, and current weaknesses.
>
> Last updated: 2026-03-24 (Session 27 Pre-Work)

---

## Part 1: What We're Building

### Overview

This is a **strategy discovery engine** for futures trading — not a live trading system.
Its purpose is to sweep thousands of filter combinations and parameter ranges across historical
data, identify statistically robust algorithmic strategies, and produce ranked candidates for
future portfolio construction.

### Target Instruments

| Instrument | Exchange | Tick Value | Current Phase |
|------------|----------|------------|---------------|
| ES (S&P 500 E-mini) | CME | $12.50 | Active — all timeframes |
| CL (Crude Oil) | NYMEX | $10.00 | Phase 2 |
| NQ (Nasdaq E-mini) | CME | $5.00 | Phase 2 |
| GC (Gold) | COMEX | $10.00 | Phase 3 |

### Target Deployment

**The5ers $250K Bootcamp** — a 3-step prop firm challenge:
- Step 1: $100K account, 6% profit target, 5% max drawdown
- Step 2: $150K account, 6% profit target, 5% max drawdown
- Step 3: $200K account, 6% profit target, 5% max drawdown
- Funded: $250K account, 1:7.5 leverage on indices

**Portfolio goal**: ~6 uncorrelated strategies across multiple instruments and timeframes.
Deploying a portfolio rather than a single strategy reduces DD risk via diversification.

### Data

- Source: TradeStation CSV exports (OHLCV, bar-by-bar)
- History: back to 2008 (18 years)
- Timeframes: daily, 60m, 30m, 15m (Phase 1); 5m (Phase 2); 1m excluded — too noisy and slow to process
- IS/OOS split: 2019-01-01 (configurable) — ~11 years in-sample, ~5 years out-of-sample

---

## Part 2: Pipeline Architecture

The engine runs a **funnel** for each strategy family (trend, mean_reversion, breakout)
on each dataset. Each stage narrows candidates before the next.

### Stage 1 — Sanity Check

Run the base strategy for this family using all default filters and parameters.
Purpose: confirm the data file loads correctly and the engine produces trades.
If no trades fire, abort early with a clear error message.

### Stage 2 — Filter Combination Sweep

Generate all C(n, k) filter combinations where k ranges from `min_filters` to `max_filters`.
For each combo:
- Run with default `hold_bars`, `stop_distance`, `min_avg_range`, `momentum_lookback`
- Record: PF, avg_trade, net_pnl, total_trades, IS trades, OOS trades
- Assign quality flag (ROBUST / STABLE / MARGINAL / BROKEN_IN_OOS / etc.)
- Compute quality_score (continuous metric for ranking)
- Record consistency stats: pct_profitable_years, max_consecutive_losing_years

This is the widest stage — can produce thousands of combos for large filter libraries.

### Stage 3 — Promotion Gate

Filter sweep results by minimum thresholds:
- `min_pf`: minimum profit factor (default 1.1)
- `min_trades`: minimum total trades across full history
- `min_trades_per_year`: minimum annualised trade frequency

Rank surviving combos by composite score: `quality_score × oos_pf × (trades_per_year / 10)`.
Cap at `max_promoted_candidates` (default 20) to prevent refinement explosion.

**Deliberately loose**: the gate is intentionally permissive — refinement will further narrow.

### Stage 4 — Refinement Grid

For each promoted candidate, run a 4D parameter grid search:
- `hold_bars`: how many bars to hold position before time-stop
- `stop_distance`: stop loss in ATR multiples
- `min_avg_range`: minimum bar range filter (regime filter)
- `momentum_lookback`: lookback for MomentumFilter (if used)

Grid size: 4 × 4 × 4 × 4 = 256 combinations per candidate.
Each combination gets a full IS/OOS split and quality flag.
All accepted refinements are pooled and sorted by net_pnl.

### Stage 5 — Leaderboard

For each family, compare:
- Best combo result (from sweep, with default params)
- Best refined result (from refinement grid)

The refined variant wins **only if it improves net_pnl**. The winner becomes the family leader.

Final acceptance gate: `min_pf`, `min_oos_pf`, `min_total_trades` (configurable).
Accepted leaders go to portfolio evaluation.

### Stage 6 — Portfolio Evaluation

For each accepted leader, reconstruct the full trade history.
Compute:
- IS/OOS profit factors
- Max drawdown (full history and OOS-only)
- Monte Carlo simulation: 95th and 99th percentile drawdowns (10,000 iterations)
- Stress tests: 10% trade reduction, extra slippage (+0.5 tick)
- Correlation matrix between strategy daily returns
- Yearly PnL breakdown per strategy

### Stage 7 — Master Leaderboard

After all datasets complete (multi-dataset run), aggregate:
- Collect all `accepted_final == True` rows from every dataset's leaderboard CSV
- Rank by: quality flag priority → net_pnl → PF
- Write `Outputs/master_leaderboard.csv`

### Stage 8 — Ultimate Leaderboard

After sweep completion (via `run_cloud_sweep.py`):
- Scan all `strategy_console_storage/runs/*/artifacts/Outputs/master_leaderboard.csv`
- Deduplicate by (strategy_type, dataset, name, filters) — keep highest PF
- Rank as above
- Write `strategy_console_storage/ultimate_leaderboard.csv`

---

## Part 3: File Inventory

### Orchestration

**`master_strategy_engine.py`** — Main entry point. Loops over datasets from `config.yaml`,
instantiates `MasterStrategyEngine` for each, runs the full funnel, then calls portfolio
evaluation and master leaderboard aggregation. Handles multi-dataset progress and summary output.

**`run_cloud_sweep.py`** — One-click GCP sweep wrapper. Auto-detects console storage path,
calls `cloud.launch_gcp_run.launch()`, then triggers ultimate leaderboard update on completion.

### Core Engine

**`modules/engine.py`** — The heart of the system. Contains:
- `MasterStrategyEngine`: orchestrates sweep → promotion → refinement → leaderboard
- `EngineConfig`: dataclass holding all pipeline parameters
- Trade execution loop: bar-by-bar Python loop with entry/exit logic
- `_assign_quality_flag()`: maps IS/OOS PF pair to a quality flag
- `quality_score`: continuous metric (0–1) for composite ranking
- Progress reporting to `status.json` via `ProgressTracker`

**`modules/strategies.py`** — Strategy class hierarchy:
- `BaseStrategy`: holds filter list, parameter set, trade result
- `ComboStrategy`: n filters combined with logical AND
- `RefinedStrategy`: adds parameter overrides (hold_bars, stop_distance, etc.)
- Trade entry triggered when all filters pass; exit via time-stop or stop-loss

**`modules/data_loader.py`** — Loads TradeStation CSV exports.
Handles: header detection, date/time parsing, "$1,234.56" monetary format,
column normalisation (Date, Time, Open, High, Low, Close, Volume).

**`modules/feature_builder.py`** — Precomputes derived columns on the DataFrame:
- `fast_sma`, `slow_sma`, `long_sma` (configurable periods)
- `atr` (Average True Range, configurable period)
- `momentum` (close vs close N bars ago)
- `bar_range` (High − Low)
- `true_range` (max of H-L, H-prev_C, prev_C-L)
- `sma_slope` (SMA change over N bars)

### Filters

**`modules/filters.py`** — All filter classes. Each implements `passes(row, prev_row, df, idx) -> bool`.
See Part 4 for complete inventory.

### Strategy Type Families

**`modules/strategy_types/base_strategy_type.py`** — Abstract base class all families implement:
- `get_available_filters()` → list of filter instances for this family
- `get_required_filters()` → filters always included (regardless of sweep)
- `get_default_params()` → default entry/exit parameters
- `build_candidate_specific_strategy()` → construct strategy from combo + params

**`modules/strategy_types/trend_strategy_type.py`** — Trend-following family.
Entry: long on pullback-and-recovery in uptrending market.
Required: TrendDirectionFilter (SMA cross). Optional: any combination of trend filters.

**`modules/strategy_types/mean_reversion_strategy_type.py`** — Mean reversion family.
Entry: long after price stretches below fast SMA, showing exhaustion + reversal signal.
Required: BelowFastSMAFilter. Optional: distance filters, exhaustion filters, volatility regime.

**`modules/strategy_types/breakout_strategy_type.py`** — Breakout family.
Entry: long on expansion from compression with trend confirmation.
Required: CompressionFilter + ExpansionBarFilter. Optional: close strength, prior range, etc.

**`modules/strategy_types/strategy_factory.py`** — Registry: `get_strategy_type(name)` and
`list_strategy_types()`. Maps string names to class instances.

### Optimisation

**`modules/refiner.py`** — Parallel parameter grid search using `ThreadPoolExecutor`.
Generates the 4D grid, runs each combination as an independent backtest,
collects results, deduplicates near-identical filter combos before refinement.

**`modules/optimizer.py`** — Legacy grid search (being replaced by refiner).
Kept for reference; no longer called in main pipeline.

### Validation and Scoring

**`modules/portfolio_evaluator.py`** — Post-leaderboard analysis:
- Reconstructs trade histories for each accepted strategy
- Monte Carlo: shuffles trade order 10,000 times, computes DD distribution
- Stress tests: drops 10% of trades randomly, adds extra slippage
- Correlation: daily PnL series → Pearson correlation matrix
- Yearly breakdown: per-year PnL for consistency view
- Calls `_rebuild_strategy_from_leaderboard_row()` with timeframe parameter

**`modules/prop_firm_simulator.py`** — The5ers challenge simulation:
- Supports Bootcamp ($250K, 3 steps), High Stakes, Hyper Growth configs
- Monte Carlo pass rate: simulate N challenge attempts, count passes
- Strategy ranking by MC pass rate
- Daily drawdown simulation (for funded stage)

**`modules/consistency.py`** — Year-by-year PnL analysis:
- `analyse_yearly_consistency()`: groups trades by calendar year
- Outputs: pct_profitable_years, max_consecutive_losing_years, consistency_flag
- Flags: CONSISTENT (≥70% profitable), INCONSISTENT (<50%), MODERATE otherwise

### Aggregation

**`modules/master_leaderboard.py`** — `aggregate_master_leaderboard()`:
Scans all per-dataset output directories for `leaderboard.csv`,
filters to `accepted_final == True`, merges with dataset metadata,
ranks by quality flag + net_pnl + PF, writes `Outputs/master_leaderboard.csv`.

**`modules/ultimate_leaderboard.py`** — `update_ultimate_leaderboard()`:
Scans all `strategy_console_storage/runs/*/artifacts/Outputs/master_leaderboard.csv`,
deduplicates by (strategy_type, dataset, name, filters),
writes `strategy_console_storage/ultimate_leaderboard.csv`.

### Infrastructure

**`modules/config_loader.py`** — `load_config()` reads `config.yaml`, exposes `get_nested()` helper.
`get_timeframe_multiplier(timeframe)`: returns scaling factor (daily=1.0, 60m=0.154, 15m=0.0385, etc.)
`scale_lookbacks(params, multiplier)`: adjusts SMA/ATR/momentum lookback periods per timeframe.

**`modules/progress.py`** — `ProgressTracker`: writes `status.json` to output directory.
Tracks: stage name, completion %, per-dataset progress, promoted count, ETA.
Dashboard polls this file via SSH during active runs.

**`modules/heatmap.py`** — Generates pivot-table heatmaps of parameter performance.
Used for visualising hold_bars × stop_distance landscapes.

### Dashboard

**`dashboard.py`** — Streamlit 5-tab dashboard:
1. **Live Monitor**: KPI strip, per-dataset progress bars, promoted candidates table, log tail, 30s auto-refresh
2. **Results Explorer**: leaderboard table, equity curves (Plotly), annual PnL bar chart, correlation heatmap
3. **Ultimate Leaderboard**: cross-run strategy browser with multi-select filters
4. **Run History**: all runs table, run detail expander
5. **System**: storage overview, health checks, quick action commands

**`dashboard_utils.py`** — Pure helper functions:
- `discover_runs()`: scans storage for run directories
- `load_strategy_results()`: loads leaderboard CSV with parquet→CSV fallback
- `fetch_live_dataset_statuses()`: SSHs into compute VM during active runs
- `load_promoted_candidates()`: loads promoted_candidates.csv
- `format_duration_short()`, `status_color()`, `estimate_run_cost()`

### Cloud

**`cloud/launch_gcp_run.py`** — Full GCP orchestration:
1. Build run manifest (timestamp, config, datasets)
2. Bundle only config-required datasets
3. Stage under deterministic `/tmp` path on VM
4. Wait for engine to complete (polls status.json)
5. Download artifacts tarball
6. Verify preserved outputs before destroy
7. Destroy VM

**`paths.py`** — Shared constants: `REPO_ROOT`, `UPLOADS_DIR`, `RUNS_DIR`, `CONSOLE_STORAGE_ROOT`.
Auto-detects `~/strategy_console_storage` or falls back to repo-local path.

---

## Part 4: Complete Filter Inventory

### Quality Flag Definitions

| Flag | Condition | Meaning |
|------|-----------|---------|
| NO_TRADES | total = 0 | Strategy never triggered |
| LOW_IS_SAMPLE | is < 50, oos < 50 | Not enough data in either period |
| OOS_HEAVY | is < 50, oos ≥ 50 | Not enough in-sample data |
| EDGE_DECAYED_OOS | is ≥ 50, oos < 25 | Edge disappeared out-of-sample |
| REGIME_DEPENDENT | is_pf < 1.0, oos_pf ≥ 1.2 | Only works in certain regimes |
| BROKEN_IN_OOS | is_pf > 1.2, oos_pf < 1.0 | Overfit — fails out-of-sample |
| ROBUST | is_pf ≥ 1.15, oos_pf ≥ 1.15 | Strong in both periods |
| STABLE | is_pf ≥ 1.0, oos_pf ≥ 1.0 | Acceptable in both periods |
| MARGINAL | everything else | Weak or inconsistent |

### Trend Filters (10 total)

Entry signal: uptrending market, price pulls back, then recovers.

| Filter | Logic | Purpose |
|--------|-------|---------|
| `TrendDirectionFilter` | fast_sma > slow_sma | Uptrend regime gate — fast average above slow average |
| `PullbackFilter` | prev_close ≤ fast_sma | Price has pulled back to or below short-term average |
| `RecoveryTriggerFilter` | close > fast_sma | Price has crossed back above fast average (recovery trigger) |
| `VolatilityFilter` | atr > min_atr_threshold | Minimum volatility gate — enough movement to profit |
| `MomentumFilter` | close > close[N bars ago] | Upward momentum over lookback period |
| `TwoBarUpFilter` | close > prev_close AND prev_close > prev_prev_close | Two consecutive higher closes |
| `TrendSlopeFilter` | fast_sma rising over N bars | Fast SMA is trending upward (not just above slow) |
| `HigherLowFilter` | low > prev_low | Current bar's low is above previous bar's low |
| `UpCloseFilter` | close > open | Bullish bar — closed above open |
| `CloseAboveFastSMAFilter` | close > fast_sma | Price above short-term average at close |

### Mean Reversion Filters (11 total)

Entry signal: price has stretched below its mean, showing exhaustion, then starts reversing.

| Filter | Logic | Purpose |
|--------|-------|---------|
| `BelowFastSMAFilter` | close < fast_sma | Price is below short-term average (stretched) |
| `DistanceBelowSMAFilter` | fast_sma − close ≥ N × atr | Minimum stretch — not just barely below, meaningfully below |
| `DownCloseFilter` | close < prev_close | Selling pressure — closed lower than previous bar |
| `TwoBarDownFilter` | two consecutive down closes | Selling exhaustion signal — two bars of selling |
| `ThreeBarDownFilter` | three consecutive down closes | Stronger exhaustion — three bars of selling |
| `ReversalUpBarFilter` | close > open | Snapback trigger — bar closed above its open |
| `LowVolatilityRegimeFilter` | atr < max_atr_threshold | Calm market regime — MR works best in low vol |
| `AboveLongTermSMAFilter` | close > long_sma (200-period) | Macro uptrend — don't mean revert in downtrends |
| `CloseNearLowFilter` | close in bottom 35% of bar's H-L range | Price closed near the bar's low — weakness |
| `StretchFromLongTermSMAFilter` | long_sma − close ≥ N × atr | Price stretched below 200-period SMA (macro mean reversion) |
| `AbovePrevHighFilter` | close > prev_high | Breakout above previous bar's high (reversal confirmation) |

### Breakout Filters (9 total)

Entry signal: market has been compressing (low volatility), then breaks out with momentum.

| Filter | Logic | Purpose |
|--------|-------|---------|
| `CompressionFilter` | atr < historical_avg_atr | Squeeze building — ATR below its own average |
| `ExpansionBarFilter` | bar_range > avg_range × multiplier | Breakout bar — current bar larger than average |
| `BreakoutRetestFilter` | close > prior N-bar high | Resistance broken — price closed above recent swing high |
| `BreakoutTrendFilter` | fast_sma > slow_sma | Trend-aligned breakout only (not counter-trend) |
| `BreakoutCloseStrengthFilter` | close in top 60%+ of bar range | Strong close — committed breakout, not a fade |
| `PriorRangePositionFilter` | prev_close in top 50% of N-bar range | Previous close was already strong within range |
| `BreakoutDistanceFilter` | close > prior high by ≥ N × atr | Minimum breakout distance — not just barely through |
| `RisingBaseFilter` | lows are rising over N bars | Base forming — buying support visible |
| `TightRangeFilter` | bar_range < avg_range × 0.85 | Tight setup — current bar is narrow (pre-breakout) |

---

## Part 5: Current Weaknesses

### 1. Trade Count Too Thin

The best strategy produces ~3.4 trades/year. This is far too low for:
- Reliable statistical significance (< 20 OOS trades)
- Bootcamp pass rate (too few opportunities to recover from drawdowns)
- Portfolio diversification (correlated strategies don't help if none trade)

Root cause: conservative filter combinations, long hold bars, strict entry requirements.

### 2. Only Mean Reversion Works

Trend-following and breakout families consistently fail the acceptance gate in backtests.
Possible explanations:
- Exit logic is too simple (time-stop only) — trends need trailing stops to capture large moves
- Entry timing is off for trend (pullback entry works but filters may be too restrictive)
- Breakout entries may need volume confirmation (not available in current OHLCV data)

### 3. Filter Library is Small

8–11 filters per family. With C(n,k) combinations this gives limited sweep coverage.
More filters = more combinations = more candidates = higher chance of finding robust strategies.
But vectorization must come first (performance) before expanding the library.

### 4. Refinement Grid is Brute-Force

256 combinations per candidate, purely grid-based. Problems:
- Parameter plateaus poorly explored (grid might miss the true optimal region)
- Bayesian/adaptive methods (Optuna) would find optima in 50–100 evaluations instead of 256
- But: shouldn't invest in smarter search until exit architecture is richer

### 5. All Strategies are Long-Only

Systematic short-side bias missed entirely. In bear markets (2008, 2020, 2022),
long-only strategies draw down while short-side opportunities exist.
Short strategies would also reduce portfolio correlation to market beta.

### 6. Exit Logic is Simplistic

Only two exit mechanisms:
- **Time-stop**: hold for N bars then exit at close
- **Fixed stop-loss**: exit if adverse move exceeds N × ATR

What's missing:
- **Trailing stop**: follows price by N × ATR from highest high since entry (essential for trend)
- **Profit target**: exit at N × ATR profit (best for mean reversion — locks in the snap-back)
- **Signal exit**: exit when price crosses back below fast SMA (natural MR exit)

This single weakness probably explains why trend/breakout fail — they need trailing stops.

### 7. Single IS/OOS Split

Fixed 2019-01-01 split means OOS covers 2019–2024. Problems:
- COVID crash in 2020 distorts OOS stats
- No way to know if strategy is robust across different market regimes
- Walk-forward validation (rolling train/test windows) is the industry standard

### 8. No Bootcamp-Native Scoring

Current ranking: profit factor → net PnL → quality flag.
This maximises backtest returns, not Bootcamp pass probability.

Bootcamp-native scoring should weight:
- Monte Carlo pass rate (probability of hitting 6% before 5% DD)
- DD margin from 5% limit (strategies close to the limit are dangerous)
- Trade frequency (need enough trades to recover from early losses)
- Consistency across years (monthly income stability)
- Outlier dependency (does the strategy need one huge trade to show profit?)

### 9. Bar-by-Bar Python Loop is Slow

The trade execution engine iterates row-by-row using Python.
At 15m timeframe (18 years × 252 days × 26.5 bars/day ≈ 120,000 bars per run),
this is manageable but slow.

Once we expand to multiple instruments × multiple timeframes × larger filter libraries,
compute time will become a bottleneck.

Vectorizing filter computation (precompute all filters as boolean columns, combine with AND)
would give 50–100× speedup, enabling wider sweeps at the same cost.

### 10. No Regime Tagging

Strategies are evaluated on their overall statistics.
No mechanism to understand:
- Does this MR strategy only work in low-vol regimes?
- Does this trend strategy fail in 2011-2015 sideways chop?
- Which strategies complement each other in different market conditions?

Regime tagging (trending/ranging, high/low vol, bull/bear) would enable regime-aware
portfolio construction — only trading strategies whose regime is active.

---

## Part 6: Priority Improvements

Ranked by impact on Bootcamp pass probability:

1. **Exit architecture** — trailing stops + profit targets + signal exits.
   This alone may fix trend/breakout families and double trade quality for MR.
   Effort: 2 sessions. Impact: very high.

2. **Bootcamp-native scoring** — MC pass rate + DD margin as primary ranking.
   Changes what we optimise for, everything downstream improves.
   Effort: 1 session. Impact: high.

3. **Vectorization** — rewrite execution as pandas/numpy column operations.
   50–100× speedup unlocks wider sweeps, more filters, larger grids.
   Effort: 2 sessions. Impact: high (enables everything else).

4. **Short-side strategies** — mirror all filter families for short entry.
   Portfolio resilience in down markets, reduces market beta.
   Effort: 2 sessions. Impact: medium-high.

5. **Walk-forward validation** — rolling 6yr train / 1yr test windows.
   Proves robustness across regimes, not just one train/test split.
   Effort: 2 sessions. Impact: medium-high (confidence, not performance).

6. **New filters** — InsideBar, OutsideBar, ADX, ATRPercentile, Gap, VolumeSpike.
   Wider library = more combo diversity = more candidate strategies.
   Effort: 1–2 sessions per tier. Impact: medium (after vectorization).

7. **Trend subfamily split** — separate Pullback Continuation from Momentum/Breakout Trend.
   Currently trend family conflates two different strategies. Splitting may improve both.
   Effort: 1 session. Impact: medium.

8. **Multi-VM orchestration** — parallel VMs for CL/NQ alongside ES or walk-forward.
   Current GCP quota: 200 vCPU. Already using 96. Headroom for 2nd VM.
   Effort: 1 session. Impact: low (scale, not quality).

9. **Bayesian refinement** — replace 256-point grid with Optuna.
   Only valuable after exit architecture is richer (more parameters to optimise).
   Effort: 1 session. Impact: low-medium.

10. **Regime tagging** — classify bars as trending/ranging/high-vol/low-vol.
    Enables regime-conditional strategy selection and portfolio switching.
    Effort: 2 sessions. Impact: medium (future sophistication).
