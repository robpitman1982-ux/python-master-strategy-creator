# Strategy Discovery Engine — Full Project Summary
## For Cross-LLM Consultation | March 2026

---

## What We Are Building

An automated algorithmic strategy discovery engine for ES futures (E-mini S&P 500).
The goal is to find ~6 uncorrelated, robust trading strategies to run on a $25K MES
(Micro E-mini) account targeting The5ers $250K Bootcamp prop challenge (6% profit target,
5% max drawdown, 3-step path to funded).

This is NOT a live trading system yet. It is a research pipeline that finds, tests, and
ranks strategy candidates systematically.

---

## How the Search Works — End to End

### 1. Data
- TradeStation CSV exports of ES futures OHLCV data from 2008 to 2026
- Timeframes tested simultaneously: daily, 60m, 30m, 15m (5m was tried — zero results)
- ~18 years of data per timeframe
- IS/OOS split: pre-2019 = In-Sample, post-2019 = Out-of-Sample

### 2. Feature Pre-computation
Before any search begins, `feature_builder.py` pre-computes reusable columns on the
full dataset: SMAs (fast/slow/long-term), ATR values, momentum diffs, bar range, true
range, average range. These are stored as DataFrame columns so filters can read them
cheaply without recomputing per bar.

### 3. Strategy Families (3 total)
The engine searches across three conceptually distinct strategy types:

**Mean Reversion (MR)** — looks for oversold bars that bounce back to the mean.
- Core idea: price has moved too far from its SMA and a reversal is likely.
- Entries: long when multiple filters confirm an oversold, reversal setup.
- Exits: time-based (hold N bars) with fixed ATR stop.

**Trend Following** — looks for trend continuation after a pullback.
- Core idea: established trend, price pulls back, recovery trigger fires entry.
- Exits: time-based or trailing stop.

**Breakout** — looks for compression followed by expansion.
- Core idea: price consolidates in a tight range then breaks out with momentum.
- Exits: time-based or trailing stop.

### 4. The Filter Library (30 filters total, ~10 per family)

Every entry signal requires ALL selected filters to pass simultaneously on the same bar.
Filters are binary — a bar either passes or fails each one.

**Trend filters (10):**
TrendDirectionFilter, PullbackFilter, RecoveryTriggerFilter, VolatilityFilter,
MomentumFilter, TwoBarUpFilter, TrendSlopeFilter, HigherLowFilter, UpCloseFilter,
CloseAboveFastSMAFilter

**Mean Reversion filters (10):**
DistanceBelowSMAFilter, LowVolatilityRegimeFilter, StretchFromLongTermSMAFilter,
DownCloseFilter, TwoBarDownFilter, ThreeBarDownFilter, ReversalUpBarFilter,
BelowFastSMAFilter, AboveLongTermSMAFilter, CloseNearLowFilter

**Breakout filters (10):**
CompressionFilter, TightRangeFilter, RangeBreakoutFilter, ExpansionBarFilter,
BreakoutRetestFilter, BreakoutTrendFilter, BreakoutCloseStrengthFilter,
PriorRangePositionFilter, BreakoutDistanceFilter, RisingBaseFilter

All 30 filters have vectorised `mask()` methods — instead of evaluating bar by bar,
they apply numpy operations across the full price array at once (~50x faster).

### 5. Combinatorial Filter Sweep (Stage 1)

For each family, the engine generates every valid combination of filters using
`itertools.combinations()`:
- MR: C(10,3) through C(10,6) = 792 combinations
- Trend: C(10,4) through C(10,6) = 672 combinations
- Breakout: C(10,3) through C(10,5) = 582 combinations

Each combination is run as a standalone backtest with default parameters.
The engine records: profit factor, average trade, net PnL, IS/OOS trade counts,
IS/OOS PF, quality flag, quality score, yearly consistency metrics.

### 6. Promotion Gate (Filter between Stage 1 and Stage 2)

After the sweep, results are filtered by:
- Minimum profit factor (loose — ~1.0)
- Minimum total trades (50+)
- Minimum trades per year (3+)

Top candidates are capped at 20 per family. This is intentionally loose — the goal
is to keep interesting candidates alive for deeper testing, not kill them early.

### 7. Parameter Refinement Grid (Stage 2)

Each promoted candidate is re-run across a parameter grid:
- `hold_bars` — how many bars to hold the position
- `stop_distance_points` — ATR multiplier for the stop
- `min_avg_range` — minimum volatility filter (ATR-based)
- `momentum_lookback` — lookback for the MomentumFilter (trend only)

Grid sizes per family:
- MR: up to 8×6×6×1 = 288 variants per candidate
- Trend: up to 8×6×7×5 = 1,680 variants per candidate
- Breakout: up to 7×6×5×1 = 210 variants per candidate

All parameters scale automatically with timeframe (e.g. hold_bars on 5m = 12× the
60m default).

### 8. Quality Scoring & Quality Flags

After every backtest (sweep or refinement), the engine assigns:

**Quality Flag** (tier classification):
- ROBUST — IS PF > 1.2 AND OOS PF > 1.2, consistent across years
- STABLE_BORDERLINE — broadly positive but IS or OOS is marginal
- REGIME_DEPENDENT — only works in certain market conditions (IS PF < 1.0 but OOS OK)
- MARGINAL — barely profitable
- BROKEN_IN_OOS — IS great, OOS fails (overfit)
- LOW_IS_SAMPLE — not enough pre-2019 trades to evaluate IS

**Bootcamp Score** (0-100, prop-firm-aligned):
- 30 pts: profitability (PF above 1.0)
- 25 pts: OOS stability (OOS PF, recent 12m PF, IS PF)
- 20 pts: drawdown control (max_drawdown / net_pnl ratio)
- 15 pts: trade count and frequency
- 10 pts: yearly consistency (% profitable years, max losing streak)
- minus up to 15 pts: quality flag penalties

### 9. Leaderboard Selection

For each family+timeframe, the engine compares:
- Best sweep combo
- Best refined combo (wins only if net PnL improves)

The family leader must pass a final acceptance gate:
- net PnL > 0
- PF >= 1.0
- OOS PF >= 1.0
- total trades >= 60

Only accepted leaders flow forward.

### 10. Portfolio Evaluation (Stage 3)

Accepted strategies are reconstructed and evaluated together:
- Monte Carlo drawdown at 95th and 99th percentile
- Stress tests: 10% trade drop scenario, extra slippage scenario
- Correlation matrix between strategy equity curves
- Yearly PnL breakdown
- Calmar ratio, IS/OOS PF ratio

### 11. Two Leaderboards Per Run

**master_leaderboard.csv** — classic research ranking (quality then PnL)
**master_leaderboard_bootcamp.csv** — re-ranked by bootcamp_score (prop-firm lens)

### 12. Cross-Run Aggregation

After downloading results from GCP:
- `ultimate_leaderboard.csv` — all accepted strategies across ALL historical runs,
  deduplicated by (strategy_type, dataset, filter_class_names), keeping highest PF
- `ultimate_leaderboard_bootcamp.csv` — same, filtered to accepted-only, sorted by
  bootcamp_score

---

## Current Best Results (ES, Latest Run)

| Rank | TF | Family | Quality | PF | IS PF | OOS PF | Trades | Net PnL |
|---|---|---|---|---|---|---|---|---|
| 1 | daily | MR | STABLE_BL | 2.16 | 1.03 | 2.39 | 351 | $3.01M |
| 2 | daily | trend | REGIME_DEP | 1.86 | 0.85 | 2.57 | 212 | $481K |
| 3 | 30m | MR | **ROBUST** | 2.11 | 2.40 | 1.94 | 126 | $386K |
| 4 | daily | breakout | STABLE_BL | 1.30 | 1.03 | 1.52 | 366 | $245K |
| 5 | 30m | trend | REGIME_DEP | 1.19 | 0.68 | 1.52 | 698 | $113K |
| 6 | 60m | MR | **ROBUST** | 1.71 | 1.67 | 1.80 | 61 | $84K |
| 7 | 60m | trend | REGIME_DEP | 1.13 | 0.83 | 1.71 | 285 | $59K |
| 8 | 30m | breakout | REGIME_DEP | 1.15 | 0.98 | 1.23 | 209 | $46K |
| 9 | 15m | MR | LOW_IS | 1.22 | 0.74 | 1.25 | 206 | $36K |

Best filter combos:
- 30m MR ROBUST: DistanceBelowSMA + TwoBarDown + ReversalUpBar
- daily MR: DownClose + LowVolatilityRegime + StretchFromLongTermSMA
- daily breakout: Compression + PriorRangePosition + TightRange

---

## Cloud Infrastructure

### Architecture
```
Developer (Windows, VS Code + Claude Code CLI)
    ↓ git push
GitHub repo
    ↓ git pull
Strategy Console VM (GCP e2-micro, us-central1-c, always-on, ~$5/mo)
    ↓ python3 run_cloud_sweep.py --config <config> --fire-and-forget
Compute VM (n2-highcpu-96, 96 cores, created on demand)
    ↓ engine runs all timeframes in ~38 minutes
    ↓ uploads artifacts.tar.gz to GCS bucket
    ↓ self-deletes
GCS Bucket (gs://strategy-artifacts-robpitman)
    ↓ python3 cloud/download_run.py --latest
Local machine (Windows)
```

### Launch Command (canonical, from strategy-console SSH)
```bash
cd /home/robpitman1982/python-master-strategy-creator && git pull && \
python3 run_cloud_sweep.py --config cloud/config_es_all_5tf_ondemand_c.yaml --fire-and-forget
```

### Cost
- On-demand: ~$2.10 per full 5-timeframe run (~38 min)
- SPOT: ~$0.45 per run (preemption possible, zone availability varies)
- Full 5-TF ES sweep: 38 minutes (down from 4+ hours before vectorisation)

### Viewing Results — After Download
Run locally on Windows after `python3 cloud/download_run.py --latest`:

Results land in `strategy_console_storage/runs/<run-id>/artifacts/Outputs/`

Key files:
- `master_leaderboard.csv` — top strategies this run
- `master_leaderboard_bootcamp.csv` — bootcamp-ranked version
- `ultimate_leaderboard.csv` — cumulative across ALL runs (auto-regenerated)
- `ultimate_leaderboard_bootcamp.csv` — cumulative, bootcamp-ranked
- `ES_daily/portfolio_review_table.csv` — MC drawdowns + stress tests per dataset
- `ES_daily/correlation_matrix.csv` — equity curve correlations per dataset
- `ES_daily/yearly_stats_breakdown.csv` — year-by-year PnL breakdown

The Streamlit dashboard on the strategy-console shows all of these live:
```
http://<strategy-console-ip>:8501
```

### Quota Constraint
- Global vCPU cap: 100 vCPUs
- n2-highcpu-96 uses 96 — only one VM at a time possible
- Dual-VM parallel code exists but is blocked by quota

---

## Speed — How Vectorisation Works

The key breakthrough was giving every filter a `mask()` method that returns a numpy
boolean array across ALL bars at once. The sweep then:

1. Pre-computes the combined signal array for each filter combo once
2. Uses `np.searchsorted` in the trade loop to skip dead bars (no signal)
3. Converts all price arrays to numpy once at the start of each backtest
4. Uses `ProcessPoolExecutor` with an initialiser pattern — data sent to each
   worker process ONCE at startup, not once per task

Result: 38 minutes for 5 timeframes × 3 families = 45,000+ backtests. Previously 4+ hours.

---

## What's Next (Sessions Already Planned)

**Immediately next (Session 37 — in progress):**
- Fix dashboard + add shorts
- Add strategy subtypes (3 per family = 9 named subtypes with semantically coherent
  filter pools, reducing search space by ~4x while being more meaningful)
- Enrich leaderboard with calmar_ratio, is_oos_pf_ratio, win_rate, max_drawdown
- Fix ultimate_leaderboard_bootcamp.csv generation

**The 3 sessions after that are what we are asking LLMs to design.**

---

## Key Design Principles

- Sweep loose, refine strict, portfolio strictest
- 1m data permanently excluded (HFT territory)
- Long-only for now (shorts coming next)
- Claude Code for execution, Claude.ai for planning
- Git commits as checkpoints after every step
- One instrument (ES) until the engine is mature, then CL, NQ, GC
