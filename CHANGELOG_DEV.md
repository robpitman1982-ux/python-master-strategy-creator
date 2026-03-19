# CHANGELOG_DEV.md — Session-by-session development log

> Each session adds an entry at the TOP of this file.
> Format: date, what was done, what's next.

---

## 2026-03-19 — Session 7: Prop firm challenge simulator

**What was done**:
- Created `modules/prop_firm_simulator.py` — complete prop firm challenge simulation module
- Supports The5ers Bootcamp ($20K/$100K/$250K), High Stakes, and Hyper Growth programs
- `PropFirmConfig` dataclass: generic, supports any prop firm with configurable rules
- `The5ersBootcampConfig()` factory: correct step balances from The5ers website (Mar 2026)
  - $250K: Steps at $100K → $150K → $200K, 6% target, 5% static DD, no daily DD during eval
- `simulate_challenge()`: runs trade list through all steps chronologically
- `monte_carlo_pass_rate()`: shuffles trade order N times to estimate pass probability
- `compute_challenge_score()`: composite 0-1 score (pass rate 50%, DD margin 25%, speed 15%, consistency 10%)
- `rank_strategies_for_prop()`: score and rank multiple strategies
- Added 5 smoke tests: config verification, pass/fail simulation, MC stats, challenge score range
- Self-test runs successfully with synthetic data

**Design decisions**:
- System 2 (prop firm) shares codebase with System 1 (best edge finder)
- Only configs, gates, and ranking criteria differ
- Trade PnL scaled as percentage of source capital → applied to step balance
- Bootcamp chosen as primary target: no daily DD during eval, unlimited time, algo-friendly
- High Stakes secondary: 5% daily loss limit makes it harder for automated strategies

**Output changes vs Session 6**:
- `python -m modules.prop_firm_simulator` runs self-test
- 17 smoke tests pass (was 12)

**Verified**:
- All 17 smoke tests pass
- Bootcamp $250K config: steps = [$100K, $150K, $200K], target = $250K
- Synthetic strategy: 95.9% MC pass rate on Bootcamp

**Next session priorities**:
1. Wait for DigitalOcean 48/60-core approval
2. When approved: run multi-timeframe sweep with existing System 1 config
3. After results: run prop firm simulator on all accepted strategies' trade lists
4. Create prop-firm-specific config YAML with modified gates for System 2 pipeline
5. Add daily drawdown simulation for High Stakes / funded stage scoring

---

## 2026-03-18 — Session 6: Multi-timeframe expansion prep

**What was done**:
- Implemented hybrid filter parameter scaling: `scale_lookbacks()` added to `config_loader.py`; `get_required_sma_lengths()`, `get_required_avg_range_lookbacks()`, `get_required_momentum_lookbacks()` in all 3 strategy types now accept `timeframe` param and return scaled values. `build_filter_objects_from_classes()` and `build_candidate_specific_strategy()` receive scaled SMA/ATR/lookback lengths based on timeframe multiplier. Pattern filters (TwoBarDown, etc.) stay as-is.
- Threaded timeframe through refinement factories (`_MRRefinementFactory`, `_TrendRefinementFactory`, `_BreakoutRefinementFactory`) and combo case functions — sweep-phase filters now also scale
- Updated `master_strategy_engine.py` helpers `get_required_*()` to pass timeframe; feature precomputation now uses timeframe-scaled lookbacks
- Created `cloud/config_es_all_timeframes_48core.yaml` — 4 datasets (daily, 60m, 30m, 15m), 46 workers sweep+refinement, 5 candidates to refine, 80 GB memory budget
- Removed hardcoded `sed` max_workers replacements from `run_cloud_job.py` cloud-init; added `--config` CLI arg to `start_engine()`
- Created `docs/TRADESTATION_EXPORT_GUIDE.md` — step-by-step data export instructions with file naming and verification commands
- Added master leaderboard auto-run at end of multi-dataset pipeline — prints ranked table and saves `Outputs/master_leaderboard.csv`
- Added memory estimation and auto-throttle in `run_single_family()` — prints per-copy and parallel estimate; auto-reduces workers if `pipeline.max_memory_gb` is set and would be exceeded; warns if > 60 GB even without limit
- Updated `CLOUD_DEPLOYMENT_RUNBOOK.md` with complete 48-core run instructions
- Updated `CLAUDE.md` (issues list, structure, test count) and this CHANGELOG

**Output changes vs Session 5**:
- Feature precomputation uses timeframe-scaled SMA/ATR/momentum lookbacks (e.g., 15m → 4× the 60m lengths)
- Filter constructors receive scaled SMA lengths in both sweep and refinement phases
- Memory estimate printed before each family sweep: `Data: N bars, X.X MB per copy`
- Master leaderboard printed automatically after multi-dataset runs
- 12 smoke tests pass (was 11)

**Verified**:
- All 12 smoke tests pass including new `test_hybrid_filter_scaling`
- 15m SMA lengths confirmed ~4x the 60m values; daily confirms smaller than 60m
- Config validates correctly for 4-dataset setup

**Next session priorities**:
1. Export ES daily/30m/15m data from TradeStation (see `docs/TRADESTATION_EXPORT_GUIDE.md`)
2. Destroy old 2-core droplets after downloading results
3. Create 48-core droplet, upload 4 data files, launch full sweep
4. Download master leaderboard results
5. Begin portfolio assembly from cross-timeframe candidates

---

## 2026-03-18 — Session 5: Smoke tests, master leaderboard, timeframe grids

**What was done**:
- Created `tests/__init__.py` and `tests/test_smoke.py` — 11 smoke tests covering: config_loader, feature_builder, EngineConfig, engine run, consistency module, filter combination generation, strategy type factory, quality score range, progress tracker, master leaderboard aggregator, timeframe multiplier
- Created `modules/master_leaderboard.py` — scans all `Outputs/*/family_leaderboard_results.csv`, filters to `accepted_final=True`, extracts market/timeframe from directory name, adds rank column, returns consolidated DataFrame. Runnable standalone: `python -m modules.master_leaderboard`
- Added `TIMEFRAME_BAR_MINUTES` dict and `get_timeframe_multiplier()` to `modules/config_loader.py`
- Added `timeframe: str = "60m"` field to `EngineConfig` dataclass
- Updated `get_active_refinement_grid_for_combo()` in all 3 strategy types to accept `timeframe` parameter and scale `hold_bars` (and `momentum_lookback` for trend) proportionally — e.g., 5m multiplier=12.0×, daily multiplier≈0.154×
- Threaded `timeframe` through: `_run_dataset()` → `EngineConfig` → `run_single_family()` → strategy type refinement grids
- Compute budget output now prints scaled hold_bars grid and timeframe multiplier note
- Added `pytest>=8.0.0` to `requirements.txt`

**Output changes vs Session 4**:
- `python -m pytest tests/test_smoke.py -v` runs 11 smoke tests in < 2s
- `python -m modules.master_leaderboard` produces `Outputs/master_leaderboard.csv`
- Refinement grids now auto-scale hold_bars and momentum_lookback based on dataset timeframe
- Compute budget output shows: `hold_bars (scaled): [24, 36, 48, ...]` when timeframe ≠ 60m

**Verified**:
- All 11 smoke tests pass
- No regressions on existing tests

**Next session priorities**:
1. Download and analyze results from DigitalOcean droplets (destroy droplets after)
2. Export ES 5m/15m/30m/daily data from TradeStation
3. Run multi-timeframe sweep on cloud
4. Walk-forward validation (alternative to fixed IS/OOS split)
5. Bayesian/Optuna optimization for refinement grid

---

## 2026-03-18 — Session 4: Structured logging + cloud launcher fix

**What was done**:
- Created `modules/progress.py` — ProgressTracker class with timestamped log lines and status.json output
- Integrated ProgressTracker into master_strategy_engine.py pipeline — all stage transitions and sweep/refinement progress now logged
- Added optional `progress_callback` parameter to sweep and refinement functions (backward compatible)
- Fixed `run_cloud_job.py` start_engine timeout issue (was 60s, now handles nohup startup properly)
- status.json written to each dataset's output directory, updated every 10% of sweep/refinement progress

**Output changes vs Session 3**:
- Log output now has structured timestamps and stage prefixes
- `Outputs/ES_60m/status.json` created during runs — instant progress check via `cat status.json`
- run_cloud_job.py can now start the engine without SSH timeout errors

**Verified**:
- ProgressTracker unit test passed (manual quick test)
- All imports OK
- Existing pipeline behaviour unchanged (progress_callback is optional)

**Next session priorities**:
1. Run updated engine on new DigitalOcean droplet to test structured logging
2. Analyze results from current cloud run (still in progress on 209.38.86.189)
3. Expand to additional ES timeframes (5m, 15m, 30m, daily)
4. Design master leaderboard aggregator for multi-dataset runs

---

## 2026-03-17 — Session 3: Cloud deployment preparation

**What was done**:
- Created `Dockerfile` (python:3.11-slim based, gcc/g++ for numpy/pandas)
- Created `requirements.txt` (numpy, pandas, pyyaml)
- Created `.dockerignore` (excludes Data/, Outputs/, .git, pycache, etc.)
- Created `cloud/run_cloud.sh` — bash script: create droplet → upload → build Docker → run → download results → destroy
- Created `cloud/run_cloud.ps1` — PowerShell equivalent for Windows
- Created `cloud/config_full_es.yaml` — full ES 60m sweep config (all 3 families, 5 candidates to refine, 7 workers)
- Created `cloud/config_quick_test.yaml` — quick single-family (mean_reversion) test config
- Created `cloud/SETUP.md` — DigitalOcean setup guide with doctl install, SSH key setup, droplet size/cost reference
- Added `--config` CLI argument to `master_strategy_engine.py` via argparse
- Config is now reloaded from CLI arg in `__main__`, re-deriving all module-level constants
- Added `cloud_results/` to `.gitignore`
- Region set to `syd1` (Sydney — closest to Melbourne) in all scripts

**Cloud workflow**:
1. `run_cloud.ps1` creates a c-8 droplet in syd1
2. Uploads code + data via SCP/rsync
3. Builds Docker image on droplet
4. Runs pipeline inside container with config mounted
5. Downloads results to `cloud_results/<droplet-name>/`
6. Destroys droplet
Total estimated cost: $0.30-0.50 per full ES run on c-8

**Next session priorities**:
1. Test Docker build locally: `docker build -t strategy-engine .`
2. First cloud test run: `.\cloud\run_cloud.ps1 -ConfigFile cloud\config_quick_test.yaml`
3. Export additional TradeStation data (ES 5m/15m/30m/daily, CL, NQ)
4. Create multi-instrument config and run

---

## 2026-03-17 — Session 2: Config, consistency, multi-dataset

**What was done**:
- Created `config.yaml` — single source of truth for all pipeline constants (datasets, engine, gates, oos_split_date)
- Created `modules/config_loader.py` — `load_config()` and `get_nested()` helpers; falls back to hardcoded defaults if yaml missing
- Updated `master_strategy_engine.py` to load all settings from config (CSV path, workers, leaderboard gates, EngineConfig fields)
- Created `modules/consistency.py` — `analyse_yearly_consistency()`: yearly PnL aggregation, pct_profitable_years, max_consecutive_losing_years, consistency_flag (CONSISTENT/MIXED/INCONSISTENT/INSUFFICIENT_DATA)
- Integrated consistency into `engine.results()` — three new return fields: Pct Profitable Years, Max Consecutive Losing Years, Consistency Flag
- Factored consistency into `calculate_quality_score()` as 6th component (weight 0.15); adjusted other weights to still sum to 1.0
- Propagated new fields through all 3 strategy type sweep result dicts and `RefinementResult`/`_run_refinement_case()` in refiner.py
- Added `oos_split_date` field to `EngineConfig` dataclass; replaced hardcoded `"2019-01-01"` in engine.py results()
- Updated `portfolio_evaluator.py`: `calculate_metrics_split()` and `evaluate_portfolio()` now accept `oos_split_date` parameter
- Updated `__main__` block in master_strategy_engine.py: iterates over `datasets` list from config; calls new `_run_dataset()` helper; each dataset gets its own output subdir (`Outputs/ES_60m/`, etc.)
- Fixed Unicode/emoji output issue in config_loader.py for Windows cp1252 terminals

**Output changes vs Session 1**:
- Config loading prints "[OK] Loaded config from config.yaml" at startup
- Results now include consistency_flag, pct_profitable_years, max_consecutive_losing_years
- quality_score weights slightly adjusted (consistency now 0.15, others reduced proportionally)
- Output directory structure changed: `Outputs/ES_60m/` instead of `Outputs/` flat
- Dataset header printed before each run: "DATASET 1/1: ES 60m"

**Verified**:
- All imports OK, smoke test passed (engine.results() returns all new fields correctly)
- consistency module tested with mock trades: CONSISTENT/INCONSISTENT/INSUFFICIENT_DATA all correct

**Next session priorities**:
1. Cloud deployment prep: Dockerfile, requirements.txt, run scripts
2. Walk-forward validation as alternative to fixed IS/OOS split
3. Bayesian/Optuna optimization for refinement grid (replace brute-force 256-point grid)
4. Actual full pipeline run to verify end-to-end with new directory structure

---

## 2026-03-16 — Session 1: Foundation hardening

**What was done**:
- Added `quality_score` (0.0–1.0 continuous metric) to `engine.py` results; weighted on avg PF strength, IS/OOS balance, trade count confidence, recent PF, OOS trade presence
- Added `BORDERLINE` suffix detection: any ROBUST/STABLE/MARGINAL flag within 0.05 of a threshold boundary gets `_BORDERLINE` appended
- Propagated `quality_score` through sweep results (all 3 strategy types) and `RefinementResult` dataclass in `refiner.py`
- Capped promotion gate at max 20 candidates using composite ranking (quality_score × 0.4 + oos_pf × 0.3 + trades/yr × 0.3)
- Added `estimate_compute_budget()` — prints eval count and estimated minutes before sweep and refinement
- Added `deduplicate_promoted_candidates()` — removes near-duplicates by matching total_trades + PnL within 1%

**Output changes vs baseline**:
- Trend family: was 93 promoted → now capped at 20
- BORDERLINE flags will appear on strategies near PF thresholds
- Compute budget printed before each sweep and refinement stage
- Dedup report printed after promotion gate

**Next session priorities**:
1. Walk-forward validation as alternative to fixed IS/OOS split
2. Make dataset path configurable (prep for multi-timeframe)
3. Add yearly consistency check (flag strategies that lose money >60% of years)
4. Consider Bayesian optimization (Optuna) for refinement grid

---

## 2026-03-16 — Session 0: Project review and workflow setup

**What happened**:
- Full pipeline review with Claude (claude.ai project chat)
- Analyzed first run outputs: trend (REGIME_DEPENDENT), MR (STABLE), breakout (BROKEN_IN_OOS)
- Identified key issues: quality flag boundary logic, loose promotion gate, brute-force refinement grid
- Created CLAUDE.md for session continuity
- Created this CHANGELOG_DEV.md
- Established GitHub commit workflow

**Key findings from first run**:
- ES 60m data: 107,149 bars, 2008-01-02 to 2026-03-04
- Trend: 672 combos → 93 promoted → best refined PF 1.13, IS PF 0.83 (below 1.0), OOS PF 1.71
- MR: 792 combos → 27 promoted → best refined PF 1.42, IS PF 1.09, OOS PF 1.86
- Breakout: 582 combos → 37 promoted → best refined PF 0.82, BROKEN_IN_OOS
- Correlation between trend & MR: -0.0005 (excellent)

**Next session priorities**:
1. Fix quality flag boundary logic (make continuous/scored)
2. Tighten promotion gate or add secondary screening
3. Add compute budget estimator
4. Add filter-combo deduplication before refinement
