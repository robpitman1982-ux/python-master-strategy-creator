# CLAUDE.md â€” Strategy Discovery Engine

> Claude Code reads this file automatically at the start of every session.
> Keep it updated as the single source of truth for project state.

## Project overview

**Goal**: Build a highly robust, automated strategy discovery engine for futures trading. The system sweeps filter combinations and parameter ranges to find statistically robust algorithmic strategies. It is NOT a trading system yet â€” it is a research tool that produces candidates for future portfolio construction.

**Owner constraints** (for context, not for current implementation):
- Target deployment: $25k account on MES micro futures
- Risk rules: 30% max drawdown, 1% risk per trade
- Target: ~6 uncorrelated strategies across multiple instruments/timeframes
- Current phase: **operate the single-VM GCP sweep flow safely and repeatably**, then keep expanding datasets and dashboard ergonomics

**Expansion roadmap**:
1. âœ… ES 60m (current â€” getting pipeline solid)
2. ES across timeframes: 1m, 5m, 15m, 30m, daily
3. CL (crude oil) all timeframes
4. NQ (Nasdaq) all timeframes
5. Additional instruments as needed

## Repository structure

```
python-master-strategy-creator/
â”œâ”€â”€ master_strategy_engine.py           # Main orchestrator â€” runs all families
â”œâ”€â”€ config.yaml                         # All pipeline configuration (datasets, engine, gates)
â”œâ”€â”€ dashboard.py                        # Streamlit 3-tab dashboard: Control Panel, Results Explorer, System
â”œâ”€â”€ dashboard_utils.py                  # Pure helpers for dashboard run discovery, cost estimates, badges, result loading
â”œâ”€â”€ run_cloud_sweep.py                  # One-click wrapper around cloud.launch_gcp_run (auto-detects storage path)
â”œâ”€â”€ paths.py                            # Shared path constants: REPO_ROOT, UPLOADS_DIR, RUNS_DIR, CONSOLE_STORAGE_ROOT (auto-detected)
â”œâ”€â”€ scripts/
â”‚   â”œâ”€â”€ setup_dashboard_venv.sh        # One-time venv setup for strategy-console (picks python3.12/3.11)
â”‚   â””â”€â”€ strategy-dashboard.service     # systemd service file for the Streamlit dashboard
â”œâ”€â”€ tests/
â”‚   â”œâ”€â”€ __init__.py
â”‚   â””â”€â”€ test_smoke.py                  # 19 smoke tests (config, engine, filters, consistency, progress, leaderboard, timeframe, hybrid scaling, prop firm, portfolio evaluator timeframe)
â”œâ”€â”€ modules/
â”‚   â”œâ”€â”€ __init__.py
â”‚   â”œâ”€â”€ config_loader.py               # load_config() + get_nested() + get_timeframe_multiplier() + scale_lookbacks()
â”‚   â”œâ”€â”€ master_leaderboard.py          # aggregate_master_leaderboard() â€” consolidates all dataset leaderboards
â”‚   â”œâ”€â”€ consistency.py                 # analyse_yearly_consistency() â€” year-by-year PnL checks
â”‚   â”œâ”€â”€ engine.py                       # MasterStrategyEngine, EngineConfig, trade execution
â”‚   â”œâ”€â”€ data_loader.py                  # TradeStation CSV loader
â”‚   â”œâ”€â”€ feature_builder.py             # Precomputed features (SMA, ATR, momentum, etc.)
â”‚   â”œâ”€â”€ filters.py                     # All filter classes (trend, MR, breakout)
â”‚   â”œâ”€â”€ strategies.py                  # Strategy classes (combo + refined variants)
â”‚   â”œâ”€â”€ heatmap.py                     # Optimization heatmaps (pivot tables)
â”‚   â”œâ”€â”€ optimizer.py                   # Grid search optimizer (legacy, being replaced by refiner)
â”‚   â”œâ”€â”€ refiner.py                     # Refinement engine (parallel parameter sweep)
â”‚   â”œâ”€â”€ portfolio_evaluator.py         # Portfolio metrics, Monte Carlo, stress tests
â”‚   â”œâ”€â”€ prop_firm_simulator.py         # Prop firm challenge simulator (The5ers Bootcamp/HighStakes/HyperGrowth)
â”‚   â”œâ”€â”€ exit_validation_report.py      # Exit-style validation summary utility for refinement outputs
â”‚   â”œâ”€â”€ ultimate_leaderboard.py        # Cross-run strategy aggregator: deduplicates and ranks accepted strategies from all runs
â”‚   â””â”€â”€ strategy_types/
â”‚       â”œâ”€â”€ __init__.py
â”‚       â”œâ”€â”€ base_strategy_type.py      # Abstract base â€” all families implement this
â”‚       â”œâ”€â”€ trend_strategy_type.py     # Trend-following family
â”‚       â”œâ”€â”€ mean_reversion_strategy_type.py  # Mean reversion family
â”‚       â”œâ”€â”€ breakout_strategy_type.py  # Breakout family
â”‚       â””â”€â”€ strategy_factory.py        # Registry: get_strategy_type(), list_strategy_types()
â”œâ”€â”€ docs/
â”‚   â”œâ”€â”€ STRATEGY_ENGINE_ANALYSIS.md    # Complete system analysis: files, filters, pipeline, weaknesses
â”‚   â”œâ”€â”€ IMPROVEMENT_ROADMAP.md         # Phased improvement plan targeting The5ers Bootcamp
â”‚   â”œâ”€â”€ FILTER_SUMMARY.md              # Complete filter inventory, search space analysis, feature dependencies
â”‚   â””â”€â”€ TRADESTATION_EXPORT_GUIDE.md   # Step-by-step data export instructions
â”œâ”€â”€ cloud/
â”‚   â”œâ”€â”€ run_cloud.sh            # Linux/Mac cloud run script (DigitalOcean)
â”‚   â”œâ”€â”€ run_cloud.ps1           # Windows cloud run script (DigitalOcean)
â”‚   â”œâ”€â”€ run_gcp_job.ps1         # PowerShell: fully automated GCP run (create â†’ upload â†’ poll â†’ download â†’ DESTROY)
â”‚   â”œâ”€â”€ run_gcp_job.sh          # Bash equivalent of above for Linux/Mac
â”‚   â”œâ”€â”€ launch_gcp_run.py       # Windows-first Python launcher: manifest â†’ bundle â†’ upload â†’ monitor â†’ tarball download â†’ cleanup
â”‚   â”œâ”€â”€ gcp_startup.sh          # VM boot script: install, clone, wait for data, run engine, copy outputs
â”‚   â”œâ”€â”€ GCP_WINDOWS_RUNBOOK.md  # Single-command Windows guide for the new launcher
â”‚   â”œâ”€â”€ config_full_es.yaml              # Full ES sweep config (legacy)
â”‚   â”œâ”€â”€ config_quick_test.yaml           # Quick test config (mean_reversion only, n2-highcpu-8)
â”‚   â”œâ”€â”€ config_es_60m_full_sweep.yaml    # ES 60m all 3 families, 94 workers, n2-highcpu-96 SPOT
â”‚   â”œâ”€â”€ config_es_all_timeframes_48core.yaml  # 4-dataset 48-core DigitalOcean config
â”‚   â”œâ”€â”€ config_es_all_timeframes_gcp96.yaml   # 4-dataset 96-core GCP Iowa SPOT config
â”‚   â””â”€â”€ SETUP.md                         # DigitalOcean setup guide
â”œâ”€â”€ Dockerfile
â”œâ”€â”€ requirements.txt
â”œâ”€â”€ .dockerignore
â”œâ”€â”€ Data/                              # .gitignored â€” TradeStation CSVs
â”œâ”€â”€ Outputs/                           # .gitignored â€” per-dataset subdirectories (ES_60m/, etc.)
â”œâ”€â”€ cloud_results/                     # .gitignored â€” downloaded results from cloud runs
â”œâ”€â”€ project_to_text.py                 # Utility: dump all .py to single text file
â””â”€â”€ .gitignore
```

## Pipeline architecture

The engine runs a **funnel** for each strategy family (trend, mean_reversion, breakout):

```
1. SANITY CHECK
   â””â”€ Run base strategy with all default filters â†’ confirms data + engine work

2. FILTER COMBINATION SWEEP
   â””â”€ Generate all C(n,k) filter combos (min_filters..max_filters)
   â””â”€ Run each combo with default hold_bars + stop_distance
   â””â”€ Record: PF, avg_trade, net_pnl, total_trades, IS/OOS splits, quality_flag

3. PROMOTION GATE
   â””â”€ Filter combos by: min PF, min trades, min trades/year
   â””â”€ Sort by net_pnl descending â†’ promoted candidates

4. REFINEMENT (top N promoted candidates)
   â””â”€ Grid search over: hold_bars Ã— stop_distance Ã— min_avg_range Ã— momentum_lookback
   â””â”€ Each combo re-run with full IS/OOS split + quality flag
   â””â”€ Pool all accepted refinements, sort by net_pnl

5. LEADERBOARD
   â””â”€ Compare best combo vs best refined per family
   â””â”€ Choose leader (refined wins only if it improves net_pnl)
   â””â”€ Final acceptance gate: min PF, min OOS PF, min trades

6. PORTFOLIO EVALUATION (across all accepted leaders)
   â””â”€ Reconstruct trade histories for each winner
   â””â”€ Calculate: IS/OOS PF, max DD, Monte Carlo (95th/99th DD)
   â””â”€ Stress tests: 10% trade drop, extra slippage
   â””â”€ Correlation matrix between strategy returns
   â””â”€ Yearly breakdown per strategy
```

## Quality flag definitions (from engine.py)

| Flag | Condition | Meaning |
|------|-----------|---------|
| NO_TRADES | is+oos = 0 | Strategy never triggered |
| LOW_IS_SAMPLE / OOS_HEAVY | is < 50, oos >= 50 | Not enough in-sample data |
| EDGE_DECAYED_OOS | is >= 50, oos < 25 | Edge disappeared out-of-sample |
| REGIME_DEPENDENT | is_pf < 1.0, oos_pf >= 1.2 | Only works in certain regimes |
| BROKEN_IN_OOS | is_pf > 1.2, oos_pf < 1.0 | Overfit â€” fails out-of-sample |
| ROBUST | is_pf >= 1.15, oos_pf >= 1.15 | Strong both periods |
| STABLE | is_pf >= 1.0, oos_pf >= 1.0 | Acceptable both periods |
| MARGINAL | everything else | Weak or inconsistent |

**IS/OOS split date**: configurable via `config.yaml` â†’ `pipeline.oos_split_date` (default: 2019-01-01)

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

See `docs/FILTER_SUMMARY.md` for comprehensive details on all filters, their parameters,
timeframe scaling behaviour, feature dependencies, and combinatorial search space analysis.

**Trend filters**: TrendDirectionFilter, PullbackFilter, RecoveryTriggerFilter, VolatilityFilter, MomentumFilter, TwoBarUpFilter, TrendSlopeFilter, HigherLowFilter

**Mean reversion filters**: DistanceBelowSMAFilter, DownCloseFilter, TwoBarDownFilter, ReversalUpBarFilter, LowVolatilityRegimeFilter

**Breakout filters**: CompressionFilter, ExpansionBarFilter, BreakoutCloseStrengthFilter, TightRangeFilter

## Known issues and improvement priorities

<!-- UPDATE THIS SECTION EACH SESSION -->

### Critical (fix before cloud deployment)
- [x] Quality flag logic uses hard thresholds â€” BORDERLINE detection added, quality_score continuous metric added
- [x] Promotion gate too loose â€” capped at 20 candidates with composite ranking (quality_score Ã— oos_pf Ã— trades/yr)
- [ ] Refinement grid is brute-force (4Ã—4Ã—4Ã—4=256) â€” needs adaptive/Bayesian approach for cloud
- [x] No deduplication of near-identical filter combos before refinement â€” lightweight dedup added
- [x] No compute budget estimator before launching runs â€” added before sweep and refinement
- [x] Cloud deployment: Dockerfile, requirements.txt, run scripts, cloud configs all created
- [x] Smoke test suite added â€” `python -m pytest tests/test_smoke.py -v` (22 tests total across smoke + cloud launcher coverage)
- [x] Portfolio evaluator timeframe bug â€” `_rebuild_strategy_from_leaderboard_row()` now receives and passes `timeframe` to all get_required_*() and build_candidate_specific_strategy() calls
- [ ] Re-run ES all timeframes with fixed portfolio evaluator to get correct MC/correlation/yearly stats
- [x] Exit architecture foundation completed â€” strategies now carry explicit exit config and the engine/refiner support `time_stop`, `trailing_stop`, `profit_target`, and `signal_exit`
- [x] Session 29 local exit validation completed Ã¢â‚¬â€ breakout improved on 30m with `trailing_stop`, trend remained `time_stop`, and mean reversion was inconclusive in the reduced local run
- [ ] Re-run exit validation on a broader cloud/full-history sample before changing any family default exits
- [x] Bootcamp-native scoring and dual leaderboard output added - family and master leaderboards now emit Bootcamp-ranked companions plus `bootcamp_score`
- [ ] Recover and analyse the live Session 30 Bootcamp VM run (strategy-sweep-20260324T071642Z) after remote completion
- [ ] Long-only â€” short-side strategies needed for portfolio resilience
- [x] Strategy-console VM auth scopes (ACCESS_TOKEN_SCOPE_INSUFFICIENT) â€” fixed via GCP Cloud Shell set-service-account --scopes=cloud-platform; also authenticated with personal gcloud account
- [x] DEFAULT_ZONE was hardcoded to australia-southeast2-a â€” now us-central1-a; also configurable per YAML via cloud.zone
- [x] run_cloud_sweep.py printed misleading stage labels unconditionally â€” fixed, wrapper now only prints config and exit code
- [x] Remote runner Python drift could break pinned dependencies â€” launcher now bootstraps python3.12 explicitly for remote GCP venv creation
- [x] Fire-and-forget SSH host key hang â€” all gcloud SSH/SCP calls now use StrictHostKeyChecking=no, ConnectTimeout=30, and CLOUDSDK_CORE_DISABLE_PROMPTS=1; upload retries 3 times before preserving VM, and success now requires `master_leaderboard.csv` to exist in the console run folder before self-delete

### Important (before multi-instrument expansion)
- [x] Make dataset path configurable â€” now in config.yaml with multi-dataset loop support
- [x] OOS split date hardcoded â€” now configurable via config.yaml pipeline.oos_split_date
- [x] Add support for multiple datasets in single run â€” datasets list in config, per-dataset output dirs
- [ ] Add walk-forward validation as alternative to fixed IS/OOS split
- [ ] Single IS/OOS split â€” walk-forward validation needed
- [x] Yearly stats show trend strategy lost money 9/11 years 2009-2018 â€” consistency module added: pct_profitable_years, max_consecutive_losing_years, consistency_flag in all results
- [ ] Test Docker build locally before first cloud run
- [ ] Add multi-timeframe data files for ES (daily, 30m, 15m) â€” see docs/TRADESTATION_EXPORT_GUIDE.md
- [ ] Add CL and NQ data exports from TradeStation
- [x] Master leaderboard aggregator â€” auto-runs after multi-dataset pipeline â†’ Outputs/master_leaderboard.csv
- [x] Timeframe-aware refinement grids â€” hold_bars auto-scales with bar duration (5m â†’ 12Ã—, daily â†’ 0.154Ã—)
- [x] Hybrid filter parameter scaling â€” SMA/ATR/momentum lookbacks scale per timeframe in sweep phase too
- [x] 48-core cloud config created â€” cloud/config_es_all_timeframes_48core.yaml (4 datasets, 46 workers)
- [x] 96-core GCP cloud config created â€” cloud/config_es_all_timeframes_gcp96.yaml (4 datasets, 94 workers, Iowa SPOT us-central1-a)
- [x] Memory estimation + auto-throttle â€” warns/reduces workers if parallel RAM estimate exceeds budget
- [x] GCP automation scripts â€” run_gcp_job.ps1 / run_gcp_job.sh: fully unattended create â†’ upload â†’ poll â†’ download â†’ DESTROY
- [x] GCP automation bug fixes (Session 9) â€” SCP tilde/paths, gcloud.cmd, user detection, race condition, log clearing, cwd
- [x] GCP download reliability â€” dynamic username detection via SSH whoami, tar fallback, safety gate (refuse destroy if 0 files)
- [x] Windows-first GCP orchestration redesign â€” `cloud/launch_gcp_run.py` now builds a run manifest, bundles only config-required datasets, stages under deterministic `/tmp`, validates inputs before engine start, downloads artifacts tarball-first, and verifies preserved outputs before destroy
- [x] One-click GCP sweep wrapper â€” `run_cloud_sweep.py` now provides the recommended project-root commands for dry run, safe first run, and normal unattended runs
- [x] Latest-run pointer + final launcher summary â€” `cloud_results/LATEST_RUN.txt` plus explicit run outcome / VM outcome / billing messaging at the end of launcher runs

### Dashboard / monitoring
- [x] Streamlit dashboard (dashboard.py) â€” Cloud Monitor (launcher summary, VM billing awareness, cost estimate, dataset progress, best candidates), Results Explorer (guided source selection, leaderboard/correlations/equity curves), Prop Firm Simulator (connected to selected result source)
- [x] Dashboard overhaul â€” 3-tab layout (Control Panel, Results Explorer, System), card metrics, plotly charts
- [x] Dashboard LargeUtf8 Arrow error â€” load_strategy_results() wraps all parquet reads in try/except with CSV fallback
- [x] Python 3.14 / numpy issues â€” scripts/setup_dashboard_venv.sh pins numpy<2.2, uses python3.12 preferred
- [ ] Dashboard: equity curve per strategy from trade-level data (equity curves now shown from strategy_returns.csv)
- [ ] Quick real-run validation still needed after Session 22 python3.12 remote bootstrap fix

- [x] Bootcamp reporting utility added - python -m modules.bootcamp_report --outputs-dir <OutputsDir> prints the top Bootcamp-ranked strategies

### Prop firm system (System 2 â€” in progress)
- [x] Prop firm challenge simulator module â€” Monte Carlo pass rate, multi-step simulation, strategy ranking
- [x] The5ers Bootcamp $250K config with correct step balances ($100K/$150K/$200K)
- [x] The5ers High Stakes and Hyper Growth configs
- [ ] Integrate prop firm scoring into pipeline as alternative leaderboard ranking
- [ ] Ranking uses PF/PnL â€” Bootcamp-native scoring (DD-adjusted) needed
- [ ] Create prop-firm-specific config YAML with softer gates and DD-based ranking
- [ ] Add prop firm evaluation to portfolio_evaluator.py output
- [ ] Daily drawdown simulation (for High Stakes / funded stage)
- [ ] Position sizing optimizer (max contracts given leverage + DD constraints)

### Nice to have
- [ ] Heatmap visualization of parameter plateaus
- [ ] Trade-list-level deduplication (detect when two filter combos produce same trades)
- [x] Progress logging with ETA for long runs
- [x] Config file (YAML/TOML) instead of hardcoded constants â€” config.yaml created
- [ ] Integrate status.json polling into run_cloud_job.py wait loop
- [ ] Bayesian/Optuna optimization for refinement grid (replace brute-force 256-point grid)
- [x] Bar-by-bar Python loop â€” filter-level vectorization done (Session 31); trade loop vectorization is Session 32 scope
- [ ] No static IP on strategy-console â€” IP changes on restart; reserve via gcloud compute addresses create
- [ ] GCP vCPU quota: 200 in us-central1 â€” constrains multi-VM parallelism
- [x] status.json first-update delay â€” FIXED (done == 1)

## Current project state

- Session 29 exit validation is complete.
- Exit architecture is partially validated:
  - breakout showed a meaningful local 30m win for `trailing_stop`
  - trend did not improve enough to justify a default exit change
  - mean reversion still needs a broader validation run with more trades
- Next priority remains Bootcamp-native scoring / dual leaderboard.

## Improvement roadmap

See `docs/IMPROVEMENT_ROADMAP.md` for the full phased plan. Summary:

- **Phase 1**: Exit architecture foundation completed; next focus is Bootcamp-native scoring and validation sweeps for the new exit styles
- **Phase 2**: Short-side strategies, trend subfamily split, new filters, vectorization
- **Phase 3**: Walk-forward validation, perturbation tests, regime tagging
- **Phase 4**: Portfolio-level optimisation for Bootcamp
- **Phase 5**: Adaptive refinement, multi-VM orchestration (200 vCPU quota)

Key principle: exits before filters, filters before vectorization, vectorization before walk-forward.

## Coding standards

- Python 3.11+, type hints everywhere
- `from __future__ import annotations` in every module
- Parallel execution via `ProcessPoolExecutor` (sweep) and `ThreadPoolExecutor` (refinement)
- All monetary parsing handles "$1,234.56" format from engine output
- Tests: `python -m pytest tests/ -v` â€” exit architecture coverage now includes dedicated exit and smoke checks alongside the existing launcher/dashboard suites
- Dashboard: `streamlit run dashboard.py` (requires `streamlit` and `plotly`)
- Git: commit after every meaningful change with descriptive messages

## Quick commands

```bash
# Run all tests (72+ tests)
python -m pytest tests/test_smoke.py tests/test_cloud_launcher.py tests/test_dashboard_utils.py tests/test_vectorized_filters.py -v

# Launch ES all-timeframes sweep (daily/60m/30m/15m, all families, 96-core SPOT)
python3 run_cloud_sweep.py --config cloud/config_es_all_timeframes_96core.yaml

# Dry run (no VM created)
python3 run_cloud_sweep.py --config cloud/config_es_all_timeframes_96core.yaml --dry-run

# Fire-and-forget run (from strategy-console SSH):
python3 run_cloud_sweep.py --config cloud/config_es_daily_only.yaml --fire-and-forget
```

## Session workflow

1. Pull latest from GitHub
2. Claude Code reads this CLAUDE.md automatically
3. Check CHANGELOG_DEV.md for recent session history
4. Work on highest-priority items from the issues list above
5. Test changes locally: `python master_strategy_engine.py`
6. Update CLAUDE.md (especially the issues list) and CHANGELOG_DEV.md
7. Commit and push to GitHub

## Deployment

**Strategy Console**: GCP e2-micro, us-central1-c â€” always-on VM serving the Streamlit dashboard on port 8501 via systemd `strategy-dashboard` service. No static IP yet â€” update `STRATEGY_CONSOLE_HOST` secret if IP changes after restart.

**Compute VMs**: n2-highcpu-96 SPOT, us-central1-a (configurable via `cloud:` section in each sweep YAML). Created on demand, destroyed after results download.

**GitHub Actions**: auto-deploy on push to main via `.github/workflows/deploy_strategy_console.yml`. Requires secrets: `STRATEGY_CONSOLE_SSH_KEY`, `STRATEGY_CONSOLE_HOST`, `STRATEGY_CONSOLE_USER`.

**Dashboard**: `streamlit run dashboard.py` or `sudo systemctl restart strategy-dashboard` on the console VM.

**Canonical storage**: `~/strategy_console_storage/` on strategy-console â€” auto-detected by `paths.py` (override with `STRATEGY_CONSOLE_STORAGE` env var).

**Ultimate leaderboard**: `~/strategy_console_storage/ultimate_leaderboard.csv` â€” written by `modules/ultimate_leaderboard.py` after every sweep and viewable in the dashboard's 5th tab.

**Dashboard tabs**: Live Monitor | Results | Ultimate Leaderboard | Run History | System

## Last updated
2026-03-25 - Session 32B: Fire-and-forget SSH host key fix; retry logic; config_es_daily_only.yaml added


