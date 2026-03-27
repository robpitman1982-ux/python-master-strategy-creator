# CLAUDE.md — Strategy Discovery Engine

> Claude Code reads this file automatically at the start of every session.
> Keep it updated as the single source of truth for project state.

## Project overview

**Goal**: Build a highly robust, automated strategy discovery engine for futures trading. The system sweeps filter combinations and parameter ranges to find statistically robust algorithmic strategies. It is NOT a trading system yet — it is a research tool that produces candidates for future portfolio construction.

**Owner constraints** (for context, not for current implementation):
- Target deployment: $25k account on MES micro futures
- Risk rules: 30% max drawdown, 1% risk per trade
- Target: ~6 uncorrelated strategies across multiple instruments/timeframes
- Current phase: **operate the single-VM GCP sweep flow safely and repeatably**, then keep expanding datasets and dashboard ergonomics

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
├── dashboard.py                        # Streamlit 3-tab dashboard: Control Panel, Results Explorer, System
├── dashboard_utils.py                  # Pure helpers for dashboard run discovery, cost estimates, badges, result loading
├── run_cloud_sweep.py                  # One-click wrapper around cloud.launch_gcp_run (auto-detects storage path)
├── paths.py                            # Shared path constants: REPO_ROOT, UPLOADS_DIR, RUNS_DIR, CONSOLE_STORAGE_ROOT (auto-detected)
├── scripts/
│   ├── setup_dashboard_venv.sh        # One-time venv setup for strategy-console (picks python3.12/3.11)
│   └── strategy-dashboard.service     # systemd service file for the Streamlit dashboard
├── tests/
│   ├── __init__.py
│   ├── test_smoke.py                  # 22 smoke tests (config, engine, filters, consistency, progress, leaderboard, timeframe, hybrid scaling, prop firm, portfolio evaluator timeframe)
│   └── test_subtypes.py               # 4 smoke tests covering strategy subtype registration and validity
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
│   ├── cross_dataset_evaluator.py     # Cross-timeframe portfolio evaluation (runs after all datasets)
│   └── strategy_types/
│       ├── __init__.py
│       ├── base_strategy_type.py      # Abstract base — all families implement this
│       ├── trend_strategy_type.py     # Trend-following family
│       ├── mean_reversion_strategy_type.py  # Mean reversion family
│       ├── breakout_strategy_type.py  # Breakout family
│       ├── mean_reversion_subtypes.py     # 3 MR subtypes: vol_dip, mom_exhaustion, trend_pullback
│       ├── trend_subtypes.py              # 3 trend subtypes: pullback_continuation, mom_breakout, slope_recovery
│       ├── breakout_subtypes.py           # 3 breakout subtypes: compression_squeeze, range_expansion, higher_low
│       └── strategy_factory.py        # Registry: get_strategy_type(), list_strategy_types() — 12 types total
├── docs/
│   └── TRADESTATION_EXPORT_GUIDE.md   # Step-by-step data export instructions
├── cloud/
│   ├── run_cloud.sh            # Linux/Mac cloud run script (DigitalOcean)
│   ├── run_cloud.ps1           # Windows cloud run script (DigitalOcean)
│   ├── run_gcp_job.ps1         # PowerShell: fully automated GCP run (create → upload → poll → download → DESTROY)
│   ├── run_gcp_job.sh          # Bash equivalent of above for Linux/Mac
│   ├── launch_gcp_run.py       # Windows-first Python launcher: manifest → bundle → upload → monitor → tarball download → cleanup
│   ├── gcp_startup.sh          # VM boot script: install, clone, wait for data, run engine, copy outputs
│   ├── GCP_WINDOWS_RUNBOOK.md  # Single-command Windows guide for the new launcher
│   ├── config_full_es.yaml              # Full ES sweep config (legacy)
│   ├── config_quick_test.yaml           # Quick test config (mean_reversion only, n2-highcpu-8)
│   ├── config_es_60m_full_sweep.yaml    # ES 60m all 3 families, 94 workers, n2-highcpu-96 SPOT
│   ├── config_es_all_timeframes_48core.yaml  # 4-dataset 48-core DigitalOcean config
│   ├── config_es_all_timeframes_gcp96.yaml   # 4-dataset 96-core GCP Iowa SPOT config
│   ├── config_es_subtypes_daily_ondemand.yaml  # 9 subtypes on ES daily — fast validation (~$0.70 on-demand)
│   └── SETUP.md                         # DigitalOcean setup guide
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

**Short MR filters**: AboveFastSMAFilter, DistanceAboveSMAFilter, UpCloseShortFilter, TwoBarUpShortFilter, ReversalDownBarFilter, HighVolatilityRegimeFilter, StretchAboveLongTermSMAFilter

**Short Trend filters**: DowntrendDirectionFilter, RallyInDowntrendFilter, FailureToHoldFilter, LowerHighFilter, DownCloseShortFilter, DowntrendSlopeFilter

**Short Breakout filters**: DownsideBreakoutFilter, WeakCloseFilter

## Known issues and improvement priorities

<!-- UPDATE THIS SECTION EACH SESSION -->

### Critical (fix before cloud deployment)
- [x] Quality flag logic uses hard thresholds — BORDERLINE detection added, quality_score continuous metric added
- [x] Promotion gate too loose — capped at 20 candidates with composite ranking (quality_score × oos_pf × trades/yr)
- [ ] Refinement grid is brute-force (4×4×4×4=256) — needs adaptive/Bayesian approach for cloud
- [x] No deduplication of near-identical filter combos before refinement — lightweight dedup added
- [x] No compute budget estimator before launching runs — added before sweep and refinement
- [x] Cloud deployment: Dockerfile, requirements.txt, run scripts, cloud configs all created
- [x] Smoke test suite added — `python -m pytest tests/test_smoke.py -v`
- [x] Portfolio evaluator timeframe bug — `_rebuild_strategy_from_leaderboard_row()` now receives and passes `timeframe` to all get_required_*() and build_candidate_specific_strategy() calls
- [ ] Re-run ES all timeframes with fixed portfolio evaluator to get correct MC/correlation/yearly stats
- [x] Strategy-console VM auth scopes (ACCESS_TOKEN_SCOPE_INSUFFICIENT) — fixed via GCP Cloud Shell set-service-account --scopes=cloud-platform; also authenticated with personal gcloud account
- [x] DEFAULT_ZONE was hardcoded to australia-southeast2-a — now us-central1-a; also configurable per YAML via cloud.zone
- [x] run_cloud_sweep.py printed misleading stage labels unconditionally — fixed, wrapper now only prints config and exit code
- [x] Remote runner Python drift could break pinned dependencies — launcher now bootstraps python3.12 explicitly for remote GCP venv creation

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
- [x] 96-core GCP cloud config created — cloud/config_es_all_timeframes_gcp96.yaml (4 datasets, 94 workers, Iowa SPOT us-central1-a)
- [x] Memory estimation + auto-throttle — warns/reduces workers if parallel RAM estimate exceeds budget
- [x] GCP automation scripts — run_gcp_job.ps1 / run_gcp_job.sh: fully unattended create → upload → poll → download → DESTROY
- [x] GCP automation bug fixes (Session 9) — SCP tilde/paths, gcloud.cmd, user detection, race condition, log clearing, cwd
- [x] GCP download reliability — dynamic username detection via SSH whoami, tar fallback, safety gate (refuse destroy if 0 files)
- [x] Windows-first GCP orchestration redesign — `cloud/launch_gcp_run.py` now builds a run manifest, bundles only config-required datasets, stages under deterministic `/tmp`, validates inputs before engine start, downloads artifacts tarball-first, and verifies preserved outputs before destroy
- [x] One-click GCP sweep wrapper — `run_cloud_sweep.py` now provides the recommended project-root commands for dry run, safe first run, and normal unattended runs
- [x] Latest-run pointer — now handled via bucket listings or local `cloud_results/LATEST_RUN.txt`

### Dashboard / monitoring
- [x] Streamlit dashboard (dashboard.py) — Cloud Monitor (launcher summary, VM billing awareness, cost estimate, dataset progress, best candidates), Results Explorer (guided source selection, leaderboard/correlations/equity curves), Prop Firm Simulator (connected to selected result source)
- [x] Dashboard overhaul — 3-tab layout (Control Panel, Results Explorer, System), card metrics, plotly charts
- [x] Dashboard LargeUtf8 Arrow error — load_strategy_results() wraps all parquet reads in try/except with CSV fallback
- [x] Python 3.14 / numpy issues — scripts/setup_dashboard_venv.sh pins numpy<2.2, uses python3.12 preferred
- [ ] Dashboard: equity curve per strategy from trade-level data (equity curves now shown from strategy_returns.csv)
- [x] GCS bundle staging — in fire-and-forget mode, input bundle uploaded to GCS before VM creation; runner downloads it; eliminates SCP CalledProcessError from SPOT preemption during large (43MB) bundle upload
- [x] Parallel dual-VM split — VM-A (5m) + VM-B (daily/60m/30m/15m) run independently; `run_cloud_parallel.py` launches both; `download_run.py --latest-pair` merges results
- [x] Per-config instance names — `cloud.instance_name` in YAML overrides DEFAULT_INSTANCE_NAME so bucket paths don't collide
- [x] `download_run.py` merge + ultimate leaderboard — `--merge`/`--latest-pair` flags; pure stdlib CSV (no pandas); regenerates `ultimate_leaderboard.csv` after every download
- [x] Ultimate leaderboard moved from launcher to download script — `run_cloud_sweep.py` no longer needs pandas
- [ ] Quick real-run validation still needed (relaunch from strategy-console after Session 34 fix)
- [x] Strategy subtypes — 9 named subtypes across 3 families, each with tight semantically coherent filter pool
- [x] ultimate_leaderboard_bootcamp.csv — cross-run Bootcamp-ranked accepted strategies
- [x] Leaderboard enriched with calmar_ratio, is_oos_pf_ratio, win_rate, trades_per_year
- [x] Cross-dataset portfolio evaluation — all accepted strategies evaluated together, cross-timeframe correlation matrix, MC drawdowns for all strategies (Session 38)
- [x] Dashboard — new leaderboard columns (calmar, IS/OOS ratio, win%, max DD, prof yrs%), cross-TF correlation heatmap, bootcamp/classic toggle, subtype grouping in Live Monitor (Session 39)
- [x] Short-side strategies — ShortMR, ShortTrend, ShortBreakout with 15 new filters; direction wired through EngineConfig (Session 39)
- [ ] Run short validation config: `cloud/config_es_shorts_daily_ondemand.yaml`
- [x] Per-timeframe dataset caching — CSV loaded once and features precomputed once per timeframe, not 15x per family (Session 40)
- [x] Concurrent small-family execution — subtypes with <200 combos batched via ThreadPoolExecutor (concurrency=3) (Session 40)
- [x] Exit types active in refinement grids — all 3 base families merge exit parameter grids (trailing_stop, profit_target, signal_exit) into default refinement (verified Session 40)

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
- [x] Config file (YAML) instead of hardcoded constants — config.yaml created
- [ ] Integrate status.json polling into run_cloud_job.py wait loop
- [ ] Bayesian/Optuna optimization for refinement grid (replace brute-force 256-point grid)
- [ ] No static IP on strategy-console — IP changes on restart; reserve via gcloud compute addresses create
- [ ] status.json first-update delay — fix: `if done == 1 or done % step == 0` instead of `if done % step == 0`

## Coding standards

- Python 3.11+, type hints everywhere
- `from __future__ import annotations` in every module
- Parallel execution via `ProcessPoolExecutor` (sweep) and `ThreadPoolExecutor` (refinement)
- All monetary parsing handles "$1,234.56" format from engine output
- Tests: `python -m pytest tests/test_smoke.py tests/test_subtypes.py tests/test_cross_dataset_evaluator.py tests/test_cloud_launcher.py tests/test_parallel_vm.py -v` — 29+ tests fast, others require tmp dir permissions
- Dashboard: `streamlit run dashboard.py` (requires `streamlit` and `plotly`)
- Git: commit after every meaningful change with descriptive messages

## Session workflow

1. Pull latest from GitHub
2. Check CHANGELOG_DEV.md for recent changes
2. Claude Code reads this CLAUDE.md automatically
3. Check CHANGELOG_DEV.md for recent session history
4. Work on highest-priority items from the issues list above
5. Test changes locally: `python master_strategy_engine.py`
6. Update CLAUDE.md (especially the issues list) and CHANGELOG_DEV.md
7. Commit and push to GitHub

## Deployment

**Strategy Console**: GCP e2-micro, us-central1-c — always-on VM serving the Streamlit dashboard on port 8501 via systemd `strategy-dashboard` service. No static IP yet — update `STRATEGY_CONSOLE_HOST` secret if IP changes after restart.

**Compute VMs**: n2-highcpu-96 SPOT, us-central1-a (configurable via `cloud:` section in each sweep YAML). Created on demand, destroyed after results download.

**GitHub Actions**: auto-deploy on push to main via `.github/workflows/deploy_strategy_console.yml`. Requires secrets: `STRATEGY_CONSOLE_SSH_KEY`, `STRATEGY_CONSOLE_HOST`, `STRATEGY_CONSOLE_USER`.

**Dashboard**: `streamlit run dashboard.py` or `sudo systemctl restart strategy-dashboard` on the console VM.

**Canonical storage**: `~/strategy_console_storage/` on strategy-console — auto-detected by `paths.py` (override with `STRATEGY_CONSOLE_STORAGE` env var).

## Last updated
2026-03-27 — Session 40: 96-vCPU utilisation + exit grid activation
