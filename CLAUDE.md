# CLAUDE.md — Strategy Discovery Engine

> Claude Code reads this file automatically at the start of every session.
> Keep it updated as the single source of truth for project state.

## Project overview

**Goal**: Build a highly robust, automated strategy discovery engine for futures trading. The system sweeps filter combinations and parameter ranges to find statistically robust algorithmic strategies. It is NOT a trading system yet — it is a research tool that produces candidates for future portfolio construction.

**Owner constraints** (for context, not for current implementation):
- Target deployment: $25k account on MES micro futures
- Risk rules: 30% max drawdown, 1% risk per trade
- Target: ~6 uncorrelated strategies across multiple instruments/timeframes
- Current phase: **get the engine right on ES 60m first**, then expand

**Expansion roadmap**:
1. ✅ ES 60m (current — getting pipeline solid)
2. ES across timeframes: 1m, 5m, 15m, 30m, daily
3. CL (crude oil) all timeframes
4. NQ (Nasdaq) all timeframes
5. Additional instruments as needed

## Repository structure

```
python-master-strategy-creator/
├── master_strategy_engine.py           # Main orchestrator — runs all families
├── modules/
│   ├── __init__.py
│   ├── engine.py                       # MasterStrategyEngine, EngineConfig, trade execution
│   ├── data_loader.py                  # TradeStation CSV loader
│   ├── feature_builder.py             # Precomputed features (SMA, ATR, momentum, etc.)
│   ├── filters.py                     # All filter classes (trend, MR, breakout)
│   ├── strategies.py                  # Strategy classes (combo + refined variants)
│   ├── heatmap.py                     # Optimization heatmaps (pivot tables)
│   ├── optimizer.py                   # Grid search optimizer (legacy, being replaced by refiner)
│   ├── refiner.py                     # Refinement engine (parallel parameter sweep)
│   ├── portfolio_evaluator.py         # Portfolio metrics, Monte Carlo, stress tests
│   └── strategy_types/
│       ├── __init__.py
│       ├── base_strategy_type.py      # Abstract base — all families implement this
│       ├── trend_strategy_type.py     # Trend-following family
│       ├── mean_reversion_strategy_type.py  # Mean reversion family
│       ├── breakout_strategy_type.py  # Breakout family
│       └── strategy_factory.py        # Registry: get_strategy_type(), list_strategy_types()
├── Data/                              # .gitignored — TradeStation CSVs
├── Outputs/                           # .gitignored — all run results
├── project_to_text.py                 # Utility: dump all .py to single text file
└── .gitignore
```

## Pipeline architecture

The engine runs a **funnel** for each strategy family (trend, mean_reversion, breakout):

```
1. SANITY CHECK
   └─ Run base strategy with all default filters → confirms data + engine work

2. FILTER COMBINATION SWEEP
   └─ Generate all C(n,k) filter combos (min_filters..max_filters)
   └─ Run each combo with default hold_bars + stop_distance
   └─ Record: PF, avg_trade, net_pnl, total_trades, IS/OOS splits, quality_flag

3. PROMOTION GATE
   └─ Filter combos by: min PF, min trades, min trades/year
   └─ Sort by net_pnl descending → promoted candidates

4. REFINEMENT (top N promoted candidates)
   └─ Grid search over: hold_bars × stop_distance × min_avg_range × momentum_lookback
   └─ Each combo re-run with full IS/OOS split + quality flag
   └─ Pool all accepted refinements, sort by net_pnl

5. LEADERBOARD
   └─ Compare best combo vs best refined per family
   └─ Choose leader (refined wins only if it improves net_pnl)
   └─ Final acceptance gate: min PF, min OOS PF, min trades

6. PORTFOLIO EVALUATION (across all accepted leaders)
   └─ Reconstruct trade histories for each winner
   └─ Calculate: IS/OOS PF, max DD, Monte Carlo (95th/99th DD)
   └─ Stress tests: 10% trade drop, extra slippage
   └─ Correlation matrix between strategy returns
   └─ Yearly breakdown per strategy
```

## Quality flag definitions (from engine.py)

| Flag | Condition | Meaning |
|------|-----------|---------|
| NO_TRADES | is+oos = 0 | Strategy never triggered |
| LOW_IS_SAMPLE / OOS_HEAVY | is < 50, oos >= 50 | Not enough in-sample data |
| EDGE_DECAYED_OOS | is >= 50, oos < 25 | Edge disappeared out-of-sample |
| REGIME_DEPENDENT | is_pf < 1.0, oos_pf >= 1.2 | Only works in certain regimes |
| BROKEN_IN_OOS | is_pf > 1.2, oos_pf < 1.0 | Overfit — fails out-of-sample |
| ROBUST | is_pf >= 1.15, oos_pf >= 1.15 | Strong both periods |
| STABLE | is_pf >= 1.0, oos_pf >= 1.0 | Acceptable both periods |
| MARGINAL | everything else | Weak or inconsistent |

**IS/OOS split date**: 2019-01-01 (hardcoded in engine.py)

## Key configuration (master_strategy_engine.py)

```python
CSV_PATH = Path("Data") / "ES_60m_2008_2026_tradestation.csv"
STRATEGY_TYPE_NAME = "all"        # or "trend", "mean_reversion", "breakout"
MAX_WORKERS_SWEEP = 10
MAX_WORKERS_REFINEMENT = 10
MAX_CANDIDATES_TO_REFINE = 3

# Final leaderboard acceptance gate
FINAL_MIN_NET_PNL = 0.0
FINAL_MIN_PF = 1.00
FINAL_MIN_OOS_PF = 1.00
FINAL_MIN_TOTAL_TRADES = 60
```

## Current filter inventory

**Trend filters**: TrendDirectionFilter, PullbackFilter, RecoveryTriggerFilter, VolatilityFilter, MomentumFilter, TwoBarUpFilter, TrendSlopeFilter, HigherLowFilter

**Mean reversion filters**: DistanceBelowSMAFilter, DownCloseFilter, TwoBarDownFilter, ReversalUpBarFilter, LowVolatilityRegimeFilter

**Breakout filters**: CompressionFilter, ExpansionBarFilter, BreakoutCloseStrengthFilter, TightRangeFilter

## Known issues and improvement priorities

<!-- UPDATE THIS SECTION EACH SESSION -->

### Critical (fix before cloud deployment)
- [ ] Quality flag logic uses hard thresholds with no boundary handling — strategies at 0.99 vs 1.01 IS PF get very different labels
- [ ] Promotion gate too loose — trend promoted 93 candidates, most are noise. Compute will explode at scale
- [ ] Refinement grid is brute-force (4×4×4×4=256) — needs adaptive/Bayesian approach for cloud
- [ ] No deduplication of near-identical filter combos before refinement
- [ ] No compute budget estimator before launching runs

### Important (before multi-instrument expansion)
- [ ] Make dataset path configurable (currently hardcoded to ES_60m)
- [ ] Add support for multiple timeframes in single run
- [ ] Add walk-forward validation as alternative to fixed IS/OOS split
- [ ] Yearly stats show trend strategy lost money 9/11 years 2009-2018 — engine should flag this pattern

### Nice to have
- [ ] Heatmap visualization of parameter plateaus
- [ ] Trade-list-level deduplication (detect when two filter combos produce same trades)
- [ ] Progress logging with ETA for long runs
- [ ] Config file (YAML/TOML) instead of hardcoded constants

## Coding standards

- Python 3.11+, type hints everywhere
- `from __future__ import annotations` in every module
- Parallel execution via `ProcessPoolExecutor` (sweep) and `ThreadPoolExecutor` (refinement)
- All monetary parsing handles "$1,234.56" format from engine output
- Tests: none yet (add before cloud)
- Git: commit after every meaningful change with descriptive messages

## Session workflow

1. Pull latest from GitHub
2. Claude Code reads this CLAUDE.md automatically
3. Check CHANGELOG_DEV.md for recent session history
4. Work on highest-priority items from the issues list above
5. Test changes locally: `python master_strategy_engine.py`
6. Update CLAUDE.md (especially the issues list) and CHANGELOG_DEV.md
7. Commit and push to GitHub

## Last updated
<!-- Claude: update this line each session -->
2026-03-16 — Initial creation. Pipeline producing first outputs on ES 60m. Two viable strategies found (trend: REGIME_DEPENDENT, MR: STABLE). Breakout rejected (BROKEN_IN_OOS).
