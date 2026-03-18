# Strategy Discovery Engine — Session Handoff Summary 3
## Date: 2026-03-19 (handoff to new Claude developer account)

---

## READ THIS FIRST

Rob is moving this project from one Claude account to another (credits running low). This document is the complete state transfer. The new account will have:
1. This handoff document
2. The GitHub repo synced as project knowledge: `https://github.com/robpitman1982-ux/python-master-strategy-creator`
3. The CSV output files from cloud runs (attached to the project)

**The repo has `CLAUDE.md` at root** — that's the in-repo project bible. This handoff covers everything CLAUDE.md covers plus conversation context, decisions, and current status that isn't in the repo.

---

## What This Project Is

An automated strategy discovery engine for futures trading. It sweeps filter combinations and parameter ranges across historical data to find statistically robust algorithmic strategies. It is a **research tool** — not a trading system yet. It produces candidate strategies for future portfolio construction.

**Repo**: https://github.com/robpitman1982-ux/python-master-strategy-creator (public)

**Owner**: Rob, based in Melbourne, Australia. Trading futures, targeting prop firm funding (The5ers $250K Bootcamp).

---

## Current State — Where We Are Right Now

### All Development Complete Through Session 6

The engine code is **done and tested**. 12 smoke tests pass. The pipeline runs end-to-end. What we're waiting on is cloud compute access to run the big multi-timeframe sweep.

| Session | Date | What |
|---------|------|------|
| 0 | Mar 16 | Project review, CLAUDE.md + CHANGELOG_DEV.md created |
| 1 | Mar 16 | quality_score, BORDERLINE flags, promotion cap (20), compute budget, dedup |
| 2 | Mar 17 | config.yaml, consistency module, multi-dataset loop, OOS split configurable |
| 3 | Mar 17 | Dockerfile, cloud scripts, run_cloud_job.py, CLOUD_DEPLOYMENT_RUNBOOK |
| 4 | Mar 18 | ProgressTracker + status.json, cloud launcher timeout fix |
| 5 | Mar 18 | 11 smoke tests, master leaderboard aggregator, timeframe-aware refinement grids |
| 6 | Mar 18 | Hybrid filter scaling, 48-core cloud config, memory auto-throttle, TradeStation export guide |

### Cloud Runs Already Completed

Two DigitalOcean droplets were run on ES 60m data only (both destroyed):

**Droplet 1** (2-core, old code) — All 3 families on ES 60m → 17.4 hours
**Droplet 2** (2-core, new code) — MR-only on ES 60m → 8.7 hours (validated new code matches old)

### ES 60m Results — Only MR Survived

| Family | Result | Why |
|--------|--------|-----|
| **Mean Reversion** | **ROBUST — accepted** | IS PF 1.67, OOS PF 1.80 |
| Trend | REGIME_DEPENDENT — rejected | IS PF < 1.0 (only works in certain regimes) |
| Breakout | BROKEN_IN_OOS — rejected | Overfit — fails out-of-sample |

**The one winner: `RefinedMR_HB12_ATR0.5_DIST1.2_MOM0`**
- Filters: DistanceBelowSMA + TwoBarDown + ReversalUpBar
- Quality: ROBUST
- Full PF: 1.71 | IS PF: 1.67 | OOS PF: 1.80 | Recent 12m PF: 3.38
- Trades: 61 total (~3.4/year) — very thin
- Net PnL: $83,878 over 18 years
- Max DD: $44,361 | Monte Carlo 99th DD: $79,760
- Profitable in 8 of 18 years — makes money in big volatile moves (2010, 2018, 2019), bleeds in calm markets
- **Key insight**: ES 60m alone only produces MR. Multi-timeframe expansion is critical for portfolio diversity.

### Yearly Performance of the MR Winner

| Year | Trades | Net PnL | PF |
|------|--------|---------|----|
| 2008 | 4 | -$6,338 | 0.25 |
| 2009 | 1 | -$2,690 | 0.00 |
| 2010 | 9 | +$33,503 | 3.47 |
| 2011 | 3 | -$10,334 | 0.00 |
| 2012 | 1 | +$2,338 | ∞ |
| 2013 | 1 | -$3,977 | 0.00 |
| 2014 | 1 | -$3,262 | 0.00 |
| 2015 | 3 | -$9,877 | 0.00 |
| 2016 | 3 | -$2,356 | 0.64 |
| 2017 | 1 | -$3,338 | 0.00 |
| 2018 | 3 | +$38,641 | 14.91 |
| 2019 | 3 | +$14,379 | 5.45 |
| 2020 | 3 | +$2,652 | 1.44 |
| 2022 | 3 | -$8,278 | 0.00 |
| 2023 | 3 | +$2,040 | 1.60 |
| 2024 | 4 | -$11,857 | 0.00 |
| 2025 | 7 | +$4,350 | 1.37 |
| 2026 | 1 | +$7,497 | ∞ |

---

## IMMEDIATE PRIORITY: DigitalOcean 48/60-Core Run

### What's happening right now

Rob has applied to DigitalOcean for access to their Dedicated CPU 48 vCPU tier (or 60 vCPU). Waiting for approval. This is the **blocker** — everything else is ready.

### 48 vs 60 core comparison (already discussed)

| | 48-core | 60-core |
|---|---------|---------|
| Hourly rate | $1.95/hr | $2.44/hr |
| Estimated runtime | ~7 hours | ~5.6 hours |
| **Total cost** | **~$14** | **~$14** |
| Workers (leave 2 for OS) | 46 | 58 |

They cost the same total — 60-core just finishes faster. Rob will go with whichever tier DO approves. **Config YAML has not been created yet for 60-core** — Rob said to wait until DO responds before creating it.

### Config ready for 48-core

File: `cloud/config_es_all_timeframes_48core.yaml`
- 4 datasets: ES daily, 60m, 30m, 15m
- 46 workers sweep + refinement
- 5 candidates to refine per family
- 80 GB memory budget with auto-throttle
- All 3 strategy families (trend, MR, breakout)

### What to do when DO approves

1. If 48-core: use existing config as-is
2. If 60-core: create new config with `max_workers_sweep: 58`, `max_workers_refinement: 58`, `max_memory_gb: 100`
3. Fallback if neither approved: 16-core dedicated CPU (~$0.60/hr, ~21 hours for 4 timeframes)

### Data files needed on the droplet

All exported from TradeStation, sitting in Rob's local `Data/` folder:

| File | Size | Needed for first run? |
|------|------|-----------------------|
| ES_daily_2008_2026_tradestation.csv | 296 KB | ✅ Yes |
| ES_60m_2008_2026_tradestation.csv | 6.4 MB | ✅ Yes |
| ES_30m_2008_2026_tradestation.csv | 12.7 MB | ✅ Yes |
| ES_15m_2008_2026_tradestation.csv | 24.9 MB | ✅ Yes |
| ES_5m_2008_2026_tradestation.csv | 73.2 MB | ❌ Separate later run |
| ES_1m_2008_2026_tradestation.csv | 352 MB | ❌ Skip entirely |
| CL_daily through CL_1m | Various | ❌ Future runs |

**1m is permanently skipped** — too expensive, wrong architecture for filter strategies, The5ers forbids HFT.
**5m** is a separate run after the main 4-timeframe sweep.

### Upload process

The `run_cloud_job.py` script handles upload via SCP automatically, BUT it only uploads one CSV. For 4 files, use manual SCP (commands are in `CLOUD_DEPLOYMENT_RUNBOOK.md`):

```bash
scp Data/ES_daily_2008_2026_tradestation.csv root@<IP>:/root/python-master-strategy-creator/Data/
scp Data/ES_60m_2008_2026_tradestation.csv root@<IP>:/root/python-master-strategy-creator/Data/
scp Data/ES_30m_2008_2026_tradestation.csv root@<IP>:/root/python-master-strategy-creator/Data/
scp Data/ES_15m_2008_2026_tradestation.csv root@<IP>:/root/python-master-strategy-creator/Data/
```

### Run command

```bash
bash run_engine.sh --config cloud/config_es_all_timeframes_48core.yaml
```

### Monitor

```bash
cat Outputs/ES_daily/status.json
cat Outputs/ES_60m/status.json
cat Outputs/ES_30m/status.json
cat Outputs/ES_15m/status.json
tail -f Outputs/logs/run_*.log
```

### Download results and destroy

```bash
scp -r root@<IP>:/root/python-master-strategy-creator/Outputs cloud_outputs_48core
# Then immediately destroy droplet to stop billing
```

The money file: `cloud_outputs_48core/Outputs/master_leaderboard.csv`

---

## Pipeline Architecture

```
SANITY CHECK → FILTER COMBINATION SWEEP → PROMOTION GATE (cap 20)
→ REFINEMENT GRID (hold_bars × stop × avg_range × momentum)
→ LEADERBOARD → PORTFOLIO EVALUATION (Monte Carlo, stress tests, correlations)
→ MASTER LEADERBOARD (auto-aggregated across all datasets)
```

Each dataset (market + timeframe) runs independently: `Outputs/ES_60m/`, `Outputs/ES_15m/`, etc.

After all datasets complete, master leaderboard aggregator auto-runs and ranks all accepted strategies across timeframes → `Outputs/master_leaderboard.csv`.

---

## Key Design Decisions (don't revisit these)

### Filter adaptation across timeframes: HYBRID approach
- **Scale**: SMA lengths, ATR lookbacks, momentum lookbacks — multiply by timeframe ratio (e.g. 5m = 12× the 60m values)
- **Keep as-is**: Pattern filters (TwoBarDown, ReversalUpBar, HigherLow, etc.) — let the sweep decide if they're useful
- **Don't scale**: min_avg_range (absolute points, naturally different per timeframe), stop_distance when ATR-based

### Compute strategy: Single big droplet, sequential datasets
- One large dedicated CPU droplet running all 4 timeframes sequentially
- Simpler than managing multiple droplets
- 5m added later as separate run
- 1m skipped entirely

### $200 DigitalOcean credit budget allocation
- ES 4-timeframe run: ~$15
- ES 5m separate: ~$10
- NQ all timeframes: ~$15
- CL all timeframes: ~$15
- GC all timeframes: ~$15
- Re-runs after improvements: ~$30 buffer
- Total estimated: ~$100 of $200

---

## Key Files in the Repo

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Project overview, architecture, issues — read this first |
| `CHANGELOG_DEV.md` | Session-by-session dev log, newest at top |
| `config.yaml` | All pipeline settings (datasets, engine, gates, workers) |
| `master_strategy_engine.py` | Main orchestrator |
| `modules/progress.py` | ProgressTracker + status.json |
| `modules/engine.py` | MasterStrategyEngine, EngineConfig, trade execution, quality scoring |
| `modules/filters.py` | All filter classes (trend, MR, breakout) |
| `modules/refiner.py` | Refinement grid search (parallel) |
| `modules/consistency.py` | Yearly PnL analysis |
| `modules/portfolio_evaluator.py` | Monte Carlo, stress tests, correlations |
| `modules/master_leaderboard.py` | Cross-dataset leaderboard aggregator |
| `modules/config_loader.py` | Config + timeframe multiplier + scale_lookbacks() |
| `modules/strategy_types/` | Strategy family implementations (trend, MR, breakout) |
| `tests/test_smoke.py` | 12 smoke tests |
| `cloud/config_es_all_timeframes_48core.yaml` | 48-core multi-timeframe config (ready to use) |
| `docs/TRADESTATION_EXPORT_GUIDE.md` | Data export instructions |
| `run_cloud_job.py` | Automated DigitalOcean launcher |
| `CLOUD_DEPLOYMENT_RUNBOOK.md` | Step-by-step cloud run guide |

---

## The5ers Bootcamp — Target

**Plan**: $250K Bootcamp (3-step challenge)

| | Step 1 | Step 2 | Step 3 | Funded |
|---|--------|--------|--------|--------|
| Profit Target | 6% | 6% | 6% | 5% |
| Max Loss | 5% | 5% | 5% | 4% |
| Leverage (indices) | 1:7.5 | 1:7.5 | 1:7.5 | 1:7.5 |

Key constraint: Need 6% profit before hitting 5% drawdown. Portfolio of ~6 uncorrelated strategies to smooth equity curve.

---

## Roadmap After Multi-Timeframe Results

In priority order:

1. **Portfolio assembly**: Pick ~6 uncorrelated strategies from master leaderboard
2. **CL expansion**: Same pipeline on crude oil data (already exported to local Data/ folder)
3. **NQ + GC**: Export from TradeStation and run
4. **The5ers bootcamp simulator**: Replay strategy trade lists against evaluation rules (+6% before -5%)
5. **Walk-forward validation**: Alternative to fixed IS/OOS split (2019 cutoff)
6. **Bayesian/Optuna refinement**: Replace brute-force 256-point grid with adaptive search
7. **MetaTrader deployment**: Convert winning strategies to MT4/MT5 Expert Advisors on VPS

---

## Known Issues / Open Items

### Minor bugs (may or may not be committed — check git log)
- [ ] status.json doesn't show which refinement candidate number it's on (`current_candidate`, `total_candidates`, `candidate_name` fields)
- [ ] status.json doesn't update on first completed item (`done == 1` fix)
- [ ] Integrate status.json polling into run_cloud_job.py wait loop

### Engine improvements (future, not blocking)
- [ ] Refinement grid is brute-force 4×4×4×4=256 — needs Bayesian/Optuna for efficiency
- [ ] Walk-forward validation as alternative to fixed IS/OOS split
- [ ] Heatmap visualization of parameter plateaus (nice to have)
- [ ] Trade-list-level deduplication (nice to have)

### Results observations
- [ ] No trend or breakout strategies survived on ES 60m — need multi-timeframe diversity
- [ ] Trade count very low on best MR strategy (61 trades / 18 years)
- [ ] MR winner is regime-dependent — makes money in volatile years, bleeds in calm ones

---

## Rob's Working Style

- Based in Melbourne, Australia (AEST timezone)
- Conversational, casual tone — no need for formality
- Prefers concise answers with clear next actions
- Has TradeStation for data exports, uses Windows
- Claude Code (VS Code) available for direct code changes + git push
- Will upload screenshots of DO dashboard, terminal output, etc.
- Budget-conscious with cloud compute — always calculate cost before spinning up
- Wants to understand decisions, not just receive them

---

## CSV Files in the Project

These are the output files from the cloud runs. They should be attached to the project as knowledge files:

| File | What it shows |
|------|---------------|
| `family_summary_results.csv` | One row per strategy family with best combo + refined stats |
| `family_leaderboard_results.csv` | Leader per family with acceptance gate results |
| `portfolio_review_table.csv` | Final accepted strategies with Monte Carlo + stress tests |
| `correlation_matrix.csv` | Return correlation between accepted strategies |
| `yearly_stats_breakdown.csv` | Year-by-year PnL for each accepted strategy |
| `strategy_returns.csv` | Per-trade returns for correlation/portfolio analysis |
| `mean_reversion_filter_combination_sweep_results.csv` | All 792 MR filter combos tested |
| `mean_reversion_promoted_candidates.csv` | 9 MR combos that passed promotion gate |
| `mean_reversion_top_combo_refinement_results_narrow.csv` | 192 refinement grid results for top MR combos |

---

## Quick Start for New Claude Instance

1. Read `CLAUDE.md` in the repo (search project knowledge for it)
2. Read `CHANGELOG_DEV.md` for session history
3. Check `cloud/config_es_all_timeframes_48core.yaml` for the ready-to-go cloud config
4. Ask Rob about DigitalOcean approval status
5. When approved: help create config if 60-core, then guide through the cloud run process
6. After results: analyze master_leaderboard.csv and help with portfolio assembly
