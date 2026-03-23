# CHANGELOG_DEV.md — Session-by-session development log

> Each session adds an entry at the TOP of this file.
> Format: date, what was done, what's next.

---

## 2026-03-23 - Session 22: Remote Python bootstrap fix for GCP quick runs

**What was done**:
- Confirmed the quick-test failure was in remote dependency bootstrap, not engine logic
- Confirmed the preserved remote `run_status.json` failed at `stage=pip`
- Traced the `numpy==2.1.4` install failure to a remote Python version mismatch during VM bootstrap
- Updated the launcher-generated remote runner to install and use `python3.12` explicitly for virtual environment creation
- Added explicit remote environment logging for `python3`, `python3.12`, `python`, and `pip` before dependency installation
- Added a dedicated `python_bootstrap` failure state when `python3.12` is unavailable on the remote VM
- Added local launcher tests covering the generated `python3.12` bootstrap path and environment logging

**Verified**:
- Local smoke and launcher validation to follow immediately after the runner bootstrap change
- Next operational step is a quick dry run followed by a quick real GCP validation run

**Next session priorities**:
1. Confirm the quick real run gets past `python_bootstrap` and `pip` on the sweep VM
2. Verify the engine starts successfully on the remote VM with the pinned Python 3.12 environment
3. Review preserved logs/artifacts only if the quick run still fails

---

## 2026-03-23 — Session 21: Infrastructure hardening, US region migration, auth fix, auto-deploy

**What was done**:
- Fixed strategy-console VM auth scopes (ACCESS_TOKEN_SCOPE_INSUFFICIENT) — resolved via GCP Cloud Shell `set-service-account --scopes=cloud-platform`; also authenticated strategy-console gcloud CLI with personal account as a fallback
- Migrated DEFAULT_ZONE from australia-southeast2-a to us-central1-a for better SPOT pricing and availability
- Made cloud zone/machine_type/provisioning_model/boot_disk_size/image_family configurable via YAML `cloud:` section — no more Python edits for region changes; CLI flags still override
- Added `cloud:` section to `config_quick_test.yaml` and `config_es_all_timeframes_gcp96.yaml`
- Fixed misleading stage labels in run_cloud_sweep.py wrapper (was printing VM LAUNCHING, SWEEP START, etc. unconditionally even on dry runs and early failures)
- Confirmed `paths.py` auto-detects `~/strategy_console_storage` without needing the env var set
- Cleaned up stale repo files: Windows path artifact (`ersRobDocumentsGIT Repospython-master-strategy-creator`), `QUICKFIX_TASKS.md`
- Improved GitHub Actions deploy workflow with static IP setup instructions as comments, clear secret requirements
- Updated CLAUDE.md: added `paths.py` to structure, new Deployment section, Session 21 fixes and new known issues

**Key discoveries**:
- The failed run (strategy-sweep-20260322T200637Z) was caused by insufficient VM auth scopes, not quota or code issues
- N2 CPU quotas are already 200 in us-central1, us-east1, us-east4, us-east5, us-south1, us-west4
- General CPU quota in us-central1 is 200 (199 available)
- SPOT pricing in US regions is significantly cheaper than Australia

**Verified**:
- Dry run passes with us-central1-a zone
- Dataset resolution from uploads/ directory works correctly
- gcloud auth working on strategy-console after personal login

**Next session priorities**:
1. Confirm quick test run completed successfully with real results
2. Run full ES 60m sweep across all strategy families
3. Run multi-timeframe sweep (daily, 60m, 30m, 15m)
4. Fix dashboard LargeUtf8 Arrow error
5. Reserve static IP for strategy-console and update GitHub secret
6. Begin multi-region parallel sweep architecture

---

## 2026-03-21 - Session 14: One-click GCP sweep wrapper + automatic VM lifecycle polish

**What was done**:
- Added `run_cloud_sweep.py` as the simplest project-root entry point for day-to-day GCP runs.
- Kept the wrapper thin by delegating directly to `cloud.launch_gcp_run` with a sensible default config and passthrough flags like `--dry-run`, `--keep-vm`, and `--keep-remote`.
- Hardened the launcher closeout flow so successful verified runs print a clear final summary including run outcome, VM outcome, verification status, local results path, and whether billing should now be stopped.
- Added a lightweight `cloud_results/LATEST_RUN.txt` pointer so the newest local run folder is easy to find and the dashboard can default to it more reliably.
- Made the dry-run path also write the latest-run pointer and final summary so the local handoff behavior is consistent even before a real VM is created.
- Extended launcher tests to cover the wrapper defaults and latest-run helper behavior.
- Updated the GCP runbook to make the wrapper-first one-click workflow explicit.

**Verified**:
- `python -m py_compile cloud/launch_gcp_run.py dashboard.py dashboard_utils.py run_cloud_sweep.py`
- `python -m pytest tests/test_smoke.py tests/test_cloud_launcher.py tests/test_dashboard_utils.py -v --basetemp=.tmp_pytest_run`

**Next session priorities**:
1. Execute the next real overnight sweep through `python run_cloud_sweep.py`.
2. Confirm the final console summary and latest-run pointer match the downloaded artifacts from a real GCP run.
3. Keep refining operational ergonomics without changing strategy logic.

---

## 2026-03-21 â€” Session 13: Dashboard upgrade + VM cost visibility

**What was done**:
- Upgraded `dashboard.py` from a simple file browser into a more operational control panel for cloud runs
- Added `dashboard_utils.py` with pure helper logic for launcher-run discovery, result-source grouping, badge mapping, cost estimation, dataset-progress summarization, and best-candidate file detection
- Cloud Monitor now highlights run identity, launcher state/stage/message, timestamps, instance/zone, run and VM outcomes, bundle size, local/remote paths, and launcher banners that make preserved-vs-destroyed VM status obvious
- Added an estimated VM cost panel using a small local machine-type pricing map plus elapsed runtime from launcher timestamps
- Dataset progress now shows per-dataset cards with market/timeframe, current family/stage, progress, ETA, elapsed time, and completed/remaining families, plus an overall progress summary
- Added a “Best Candidates So Far” panel that prefers `master_leaderboard.csv`, then `family_leaderboard_results.csv`, then `family_summary_results.csv`
- Results Explorer now uses grouped result sources (`cloud_results`, legacy `cloud_outputs*`, and local `Outputs`) with a smarter default selection and a file-presence summary
- Prop Firm Simulator now reuses the selected result source, shows source context, reports how many strategy return columns were found, and gives clearer feedback when return data or trade counts are insufficient
- Added lightweight dashboard helper tests in `tests/test_dashboard_utils.py`

**Verified**:
- `python -m py_compile dashboard.py dashboard_utils.py`
- `python -m pytest tests/test_dashboard_utils.py -v`

**Next session priorities**:
1. Exercise the upgraded dashboard against the first real overnight GCP launcher run
2. Refine the local hourly cost map once real VM durations are observed
3. Consider a lightweight action panel for opening result directories or surfacing launch commands

---

## 2026-03-20 — Session 11: Windows-first GCP orchestration redesign

**What was done**:
- Added `cloud/launch_gcp_run.py` as the new single-command GCP launcher for Windows-first use
- Launcher now parses the selected config, resolves only the datasets explicitly listed there, and builds `run_manifest.json`
- Launcher bundles the current repo snapshot plus only the required datasets into one `input_bundle.tar.gz` before upload
- Remote staging now uses deterministic absolute `/tmp/strategy_engine_runs/<run-id>/` paths instead of guessed Linux home directories
- Engine start now happens only after remote bundle, config, and manifest validation succeed
- Launcher monitors structured remote run status and existing dataset `status.json` progress updates during execution
- Retrieval is now tarball-first: remote logs, status, manifest, config, and outputs are preserved into `artifacts.tar.gz` before download
- VM destruction now happens only after preserved artifacts are downloaded and verified, unless `--keep-vm` is set
- `cloud/run_gcp_job.ps1` and `cloud/run_gcp_job.sh` now defer to the Python launcher instead of carrying separate orchestration logic
- Added focused tests for manifest resolution, bundle contents, and status parsing/summarization
- Added `cloud/GCP_WINDOWS_RUNBOOK.md` and updated docs to make the new single-command flow explicit

**Verified**:
- `python -m pytest tests/test_smoke.py tests/test_cloud_launcher.py -v`
- `python -m py_compile cloud/launch_gcp_run.py`

**Next session priorities**:
1. Run a full ES 4-timeframe sweep with the new launcher from Windows
2. Confirm preserved artifacts layout against a real GCP run
3. Point the dashboard cloud monitor at the new deterministic run root if needed
4. Expand the same manifest/bundle flow to future CL/NQ/GC runs

---

## 2026-03-20 — Session 10: GCP download reliability fix

**What was done**:
- Root cause of Session 8 empty download: GcpUser detected as "robpitman1982" but actual OS Login user was "Rob"
- All SCP/SSH paths using /home/robpitman1982/ silently failed, download got 0 files, then VM was destroyed
- Fix: detect username dynamically via `whoami` and `$HOME` after SSH is ready (not guessed from email)
- Added tar-based download fallback: if SCP download is empty, tar the outputs on VM and SCP the tarball
- Safety: if download is still empty after fallback, script refuses to destroy VM and prints manual commands
- Startup script now also copies outputs to /tmp/engine_outputs/ as a guaranteed fallback path
- Applied same fixes to both PowerShell and bash scripts

**Verified**:
- All 19 smoke tests still pass
- PowerShell script syntax validated

**Next session priorities**:
1. Run ES 4-timeframe sweep with fixed automation (should be fully unattended this time)
2. Analyze results with Streamlit dashboard
3. Run prop firm simulator
4. ES 5m, then CL/NQ/GC

---

## 2026-03-20 — Session 9: GCP automation bug fixes + Streamlit dashboard

**What was done**:
- Fixed 10 automation bugs found during Session 8 GCP run:
  1. SCP tilde expansion: use /home/<user>/uploads/ instead of ~/uploads/
  2. Working directory: Push-Location to project dir before SCP
  3. Wildcard cp: explicit file-by-file copy in startup script
  4. Config path: copy to repo root config.yaml, no --config flag needed
  5. gcloud.cmd: bypass gcloud.ps1 stderr routing issue
  6. ErrorActionPreference=Continue: benign warnings no longer kill script
  7. Race condition: startup script waits 60s after first CSV before proceeding
  8. Config detection: broader find pattern for uploaded config
  9. Log clearing: rm old log before engine restart
  10. GCP username detection: auto-detect from gcloud config, don't hardcode Rob
- Rewrote cloud/run_gcp_job.ps1 with all fixes applied
- Updated cloud/run_gcp_job.sh with same fixes
- Updated cloud/gcp_startup.sh with race condition fix
- Created dashboard.py — Streamlit app with 3 tabs:
  - Cloud Monitor: SSH into VM, parse status.json, show progress bars + ETA
  - Results Explorer: load master_leaderboard, portfolio review, correlations, yearly PnL charts, equity curves
  - Prop Firm Simulator: select strategy, run MC pass rate, display metrics
- Added streamlit and plotly to requirements.txt

**Verified**:
- All 19 existing smoke tests still pass
- Streamlit app imports without error: python -c 'import dashboard'

**Next session priorities**:
1. Analyze Session 8 re-run results (with fixed portfolio evaluator)
2. Run prop firm simulator on all accepted strategies
3. Portfolio assembly for The5ers Bootcamp
4. ES 5m run, then CL/NQ/GC

---

## 2026-03-20 — Session 8: Portfolio evaluator bug fix + GCP automation

**What was done**:
- CRITICAL BUG FIX: portfolio_evaluator.py now passes `timeframe` to `get_required_sma_lengths()`, `get_required_avg_range_lookbacks()`, `get_required_momentum_lookbacks()`, and `build_candidate_specific_strategy()` during trade reconstruction
  - Bug caused: Daily MR showed 149 trades/$41K in portfolio eval vs 351 trades/$3M in engine (73x gap)
  - Bug caused: Daily Breakout showed -$27K (losing) vs +$245K in engine (sign flip!)
  - Bug caused: Daily Trend missing entirely from portfolio evaluation
  - Root: `_rebuild_strategy_from_leaderboard_row()` never passed timeframe, so all strategies reconstructed with 60m SMA/ATR/momentum defaults
- Created `cloud/gcp_startup.sh` — VM boot script: installs deps, clones repo, waits for data uploads, runs engine, copies outputs
- Created `cloud/run_gcp_job.ps1` — fully automated PowerShell script: create VM → upload data → poll completion → download results → destroy VM
- Created `cloud/run_gcp_job.sh` — bash equivalent for Linux/Mac
- Key GCP gotchas handled: PuTTY SCP issues (uses native SSH), permission model (uploads to ~/uploads, startup script copies to /root/), SPOT preemption detection and restart
- Added 2 new smoke tests for portfolio evaluator timeframe parameter

**Output changes vs Session 7**:
- Portfolio evaluator now produces correct trade reconstructions for all timeframes
- Previous run's portfolio_review_table.csv, correlation_matrix.csv, yearly_stats_breakdown.csv were WRONG for non-60m — need re-run
- 19 smoke tests pass (was 17)
- GCP runs now fully automated with one command

**Verified**:
- All 19 smoke tests pass
- Portfolio evaluator signature accepts timeframe parameter
- GCP scripts have correct path handling and VM cleanup

**Impact on previous results**:
- Master leaderboard strategy rankings (from engine) are still valid
- Portfolio evaluation outputs (MC drawdowns, correlations, yearly stats) need re-running
- The 9 accepted strategies are still real — but their validated performance metrics need recalculation

**Next session priorities**:
1. Re-run ES all timeframes on GCP with fixed code to get correct portfolio evaluation
2. Run prop firm simulator on corrected trade lists
3. Build portfolio of 3-6 uncorrelated strategies for The5ers Bootcamp
4. Run ES 5m, then CL/NQ/GC

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
