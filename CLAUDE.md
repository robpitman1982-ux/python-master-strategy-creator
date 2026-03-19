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
├── config.yaml                         # All pipeline configuration (datasets, engine, gates)
├── tests/
│   ├── __init__.py
│   └── test_smoke.py                  # 17 smoke tests (config, engine, filters, consistency, progress, leaderboard, timeframe, hybrid scaling, prop firm)
├── modules/
│   ├── __init__.py
│   ├── config_loader.py               # load_config() + get_nested() + get_timeframe_multiplier() + scale_lookbacks()
│   ├── master_leaderboard.py          # aggregate_master_leaderboard() — consolidates all dataset leaderboards
│   ├── consistency.py                 # analyse_yearly_consistency() — year-by-year PnL checks
│   ├── engine.py                       # MasterStrategyEngine, EngineConfig, trade execution
│   ├── data_loader.py                  # TradeStation CSV loader
│   ├── feature_builder.py             # Precomputed features (SMA, ATR, momentum, etc.)
│   ├── filters.py                     # All filter classes (trend, MR, breakout)
│   ├── strategies.py                  # Strategy classes (combo + refined variants)
│   ├── heatmap.py                     # Optimization heatmaps (pivot tables)
│   ├── optimizer.py                   # Grid search optimizer (legacy, being replaced by refiner)
│   ├── refiner.py                     # Refinement engine (parallel parameter sweep)
│   ├── portfolio_evaluator.py         # Portfolio metrics, Monte Carlo, stress tests
│   ├── prop_firm_simulator.py         # Prop firm challenge simulator (The5ers Bootcamp/HighStakes/HyperGrowth)
│   └── strategy_types/
│       ├── __init__.py
│       ├── base_strategy_type.py      # Abstract base — all families implement this
│       ├── trend_strategy_type.py     # Trend-following family
│       ├── mean_reversion_strategy_type.py  # Mean reversion family
│       ├── breakout_strategy_type.py  # Breakout family
│       └── strategy_factory.py        # Registry: get_strategy_type(), list_strategy_types()
├── docs/
│   └── TRADESTATION_EXPORT_GUIDE.md   # Step-by-step data export instructions
├── cloud/
│   ├── run_cloud.sh            # Linux/Mac cloud run script
│   ├── run_cloud.ps1           # Windows cloud run script
│   ├── config_full_es.yaml     # Full ES sweep config
│   ├── config_quick_test.yaml  # Quick test config
│   ├── config_es_all_timeframes_48core.yaml  # 4-dataset 48-core config
│   └── SETUP.md                # DigitalOcean setup guide
├── Dockerfile
├── requirements.txt
├── .dockerignore
├── Data/                              # .gitignored — TradeStation CSVs
├── Outputs/                           # .gitignored — per-dataset subdirectories (ES_60m/, etc.)
├── cloud_results/                     # .gitignored — downloaded results from cloud runs
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

**IS/OOS split date**: configurable via `config.yaml` → `pipeline.oos_split_date` (default: 2019-01-01)

## Key configuration (config.yaml)

All pipeline constants now live in `config.yaml`. Edit that file to change any settings.
The code reads from config with hardcoded fallback defaults if config.yaml is missing.

Key sections:
- `datasets`: list of CSV paths with market/timeframe labels (supports multi-dataset runs)
- `engine`: initial_capital, risk_per_trade, commission, slippage, tick_value, dollars_per_point
- `pipeline`: max_workers, oos_split_date, max_candidates_to_refine
- `promotion_gate`: min_pf, min_trades, min_trades_per_year, max_promoted_candidates
- `leaderboard`: final acceptance thresholds (min_pf, min_oos_pf, min_total_trades)

## Current filter inventory

**Trend filters**: TrendDirectionFilter, PullbackFilter, RecoveryTriggerFilter, VolatilityFilter, MomentumFilter, TwoBarUpFilter, TrendSlopeFilter, HigherLowFilter

**Mean reversion filters**: DistanceBelowSMAFilter, DownCloseFilter, TwoBarDownFilter, ReversalUpBarFilter, LowVolatilityRegimeFilter

**Breakout filters**: CompressionFilter, ExpansionBarFilter, BreakoutCloseStrengthFilter, TightRangeFilter

## Known issues and improvement priorities

<!-- UPDATE THIS SECTION EACH SESSION -->

### Critical (fix before cloud deployment)
- [x] Quality flag logic uses hard thresholds — BORDERLINE detection added, quality_score continuous metric added
- [x] Promotion gate too loose — capped at 20 candidates with composite ranking (quality_score × oos_pf × trades/yr)
- [ ] Refinement grid is brute-force (4×4×4×4=256) — needs adaptive/Bayesian approach for cloud
- [x] No deduplication of near-identical filter combos before refinement — lightweight dedup added
- [x] No compute budget estimator before launching runs — added before sweep and refinement
- [x] Cloud deployment: Dockerfile, requirements.txt, run scripts, cloud configs all created
- [x] Smoke test suite added — `python -m pytest tests/test_smoke.py -v` (12 tests, all fast)

### Important (before multi-instrument expansion)
- [x] Make dataset path configurable — now in config.yaml with multi-dataset loop support
- [x] OOS split date hardcoded — now configurable via config.yaml pipeline.oos_split_date
- [x] Add support for multiple datasets in single run — datasets list in config, per-dataset output dirs
- [ ] Add walk-forward validation as alternative to fixed IS/OOS split
- [x] Yearly stats show trend strategy lost money 9/11 years 2009-2018 — consistency module added: pct_profitable_years, max_consecutive_losing_years, consistency_flag in all results
- [ ] Test Docker build locally before first cloud run
- [ ] Add multi-timeframe data files for ES (daily, 30m, 15m) — see docs/TRADESTATION_EXPORT_GUIDE.md
- [ ] Add CL and NQ data exports from TradeStation
- [x] Master leaderboard aggregator — auto-runs after multi-dataset pipeline → Outputs/master_leaderboard.csv
- [x] Timeframe-aware refinement grids — hold_bars auto-scales with bar duration (5m → 12×, daily → 0.154×)
- [x] Hybrid filter parameter scaling — SMA/ATR/momentum lookbacks scale per timeframe in sweep phase too
- [x] 48-core cloud config created — cloud/config_es_all_timeframes_48core.yaml (4 datasets, 46 workers)
- [x] Memory estimation + auto-throttle — warns/reduces workers if parallel RAM estimate exceeds budget

### Prop firm system (System 2 — in progress)
- [x] Prop firm challenge simulator module — Monte Carlo pass rate, multi-step simulation, strategy ranking
- [x] The5ers Bootcamp $250K config with correct step balances ($100K/$150K/$200K)
- [x] The5ers High Stakes and Hyper Growth configs
- [ ] Integrate prop firm scoring into pipeline as alternative leaderboard ranking
- [ ] Create prop-firm-specific config YAML with softer gates and DD-based ranking
- [ ] Add prop firm evaluation to portfolio_evaluator.py output
- [ ] Daily drawdown simulation (for High Stakes / funded stage)
- [ ] Position sizing optimizer (max contracts given leverage + DD constraints)

### Nice to have
- [ ] Heatmap visualization of parameter plateaus
- [ ] Trade-list-level deduplication (detect when two filter combos produce same trades)
- [x] Progress logging with ETA for long runs
- [x] Config file (YAML/TOML) instead of hardcoded constants — config.yaml created
- [ ] Integrate status.json polling into run_cloud_job.py wait loop
- [ ] Bayesian/Optuna optimization for refinement grid (replace brute-force 256-point grid)

## Coding standards

- Python 3.11+, type hints everywhere
- `from __future__ import annotations` in every module
- Parallel execution via `ProcessPoolExecutor` (sweep) and `ThreadPoolExecutor` (refinement)
- All monetary parsing handles "$1,234.56" format from engine output
- Tests: `python -m pytest tests/test_smoke.py -v` — 12 smoke tests, all < 2s
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
2026-03-19 — Session 7: Prop firm challenge simulator (The5ers Bootcamp/HighStakes/HyperGrowth)
