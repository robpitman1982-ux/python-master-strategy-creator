# Session 58b Handover — Portfolio #1 Live + SPOT Runner + Leaderboard Fix

## Date: 2026-04-04 (Melbourne time)

## What happened this session

### 1. Portfolio #1 EA — FIRST LIVE TRADE CONFIRMED
- **S2 (YM Daily Short Trend)** opened SELL US30 at 46487.56, SL 47185.59, ticket 532066267, 0.01 lots
- EA running on Contabo VPS (89.117.72.49), The5ers account 26213568
- All 4 strategies initialized: NQ Daily MR, YM Daily Short Trend, GC Daily MR, ES 30m MR
- HB1 strategy — should close on next daily bar

### 2. New GCP Console (Nikola's account) — Code synced
- Console IP: 35.223.104.173 (strategy-console, us-central1-c)
- Project: project-c6c16a27-e123-459c-b7a
- Bucket: gs://strategy-artifacts-nikolapitman/
- Had to resolve git conflict on LATEST_RUN.txt (`git checkout -- strategy_console_storage/runs/LATEST_RUN.txt`)
- Launcher fixes committed and pulled successfully (config failsafe + startup bootstrap)

### 3. SPOT Runner — Running all 9 new markets × 4 timeframes
- Claude Code built sequential bash scripts: 60m → daily → 30m → 15m
- 60m batch: AD, BP, JY, EC completed. NG, TY, US, W, BTC queued
- Daily batch: auto-starts after 60m (8 runs — AD daily already done separately)
- 30m batch: auto-starts after daily (9 runs)
- 15m batch: auto-starts after 30m (9 runs)
- Total: 35 runs, estimated ~30 hours, all on-demand, self-deleting VMs
- PIDs: 30m runner=51004, 15m runner=51005

### 4. CRITICAL BUG FIXED: download_run.py leaderboard aggregation
**Problem:** The `download_run.py` aggregator looked for `master_leaderboard.csv` inside each run directory. The new SPOT runner runs never generate this file — they produce per-dataset `family_leaderboard_results.csv` files instead. Result: new market strategies were invisible to the leaderboard.

**Fix (commit 9e04ad1):** Added fallback in `find_leaderboard_in_dir()` that auto-merges all `family_leaderboard_results.csv` files from dataset subdirectories into a synthetic `master_leaderboard.csv` when the real one is missing. Also added `_merge_family_leaderboards()` helper function.

**Result:** Leaderboard jumped from 379 → **454 strategies**, with 414 bootcamp-accepted. Fix is committed and pushed.

### 5. Downloaded runs and analysis
Five completed runs downloaded to local:
- sweep-ad-daily-20260403T014822Z → AD daily (15 strategies, 12 accepted)
- sweep-60m-20260403T020854Z → AD 60m (15 strategies, 2 accepted)
- sweep-60m-20260403T034326Z → BP 60m (15 strategies, 6 accepted)
- sweep-60m-20260403T050719Z → JY 60m (15 strategies, 8 accepted)
- sweep-60m-20260403T062751Z → EC 60m (15 strategies, 7 accepted)

## Current State

### Leaderboard: 454 strategies (414 bootcamp-accepted)
- **Markets covered:** ES, CL, NQ, SI, HG, RTY, YM, GC (original 8) + AD, BP, JY, EC (new 4)
- **Still pending:** NG, TY, US, W, BTC (no runs completed yet)
- **Quality breakdown:** ROBUST: 98, ROBUST_BORDERLINE: 43, STABLE: 36, STABLE_BORDERLINE: 81

### Notable new strategies
- **JY 60m Breakout** — PF 2.27, IS 1.70, OOS 3.60, 89 trades, ROBUST, BCS 88.7 (top portfolio candidate)
- **JY 60m Trend** — PF 1.53, ROBUST, 129 trades
- **JY 60m Short Breakout** — PF 1.55, ROBUST, 306 trades
- **EC 60m Breakout** — PF 1.57, ROBUST, 177 trades
- **EC 60m Trend** — PF 1.55, ROBUST, 141 trades
- **AD 60m MR** — PF 1.66, ROBUST, 132 trades
- **AD daily Trend** — PF 2.30, ROBUST
- **AD daily Breakout Higher Low** — PF 1.91, ROBUST_BORDERLINE

### Live EA status
- Portfolio #1 EA on Contabo VPS, account 26213568
- First trade: S2 YM Short Trend SELL US30, currently in profit
- Other 3 strategies waiting for filter conditions
- Check Experts tab every 1-2 days

### SPOT runner status
- Running on Nikola's console (35.223.104.173)
- Monitor: `tail -f run_60m_after_start.log` (or whichever batch is active)
- Check VMs: `gcloud compute instances list --project="project-c6c16a27-e123-459c-b7a"`
- Download completed runs: `python cloud/download_run.py --latest` (locally)

## Pending / Next Session

### Immediate
- [ ] Monitor SPOT runner — check progress, download results as batches complete
- [ ] Monitor VPS EA — check for trade exits and new entries
- [ ] Download remaining runs as they complete (30+ more runs pending)

### Bugs still outstanding
- [ ] **Sizing optimizer DD constraint missing** — oversizes micros, pushing DD to 12-14%
- [ ] **source_capital hardcoded at $250K** — breaks Pro Growth and smaller accounts
- [ ] **Dashboard bug** — engine log + promoted candidates sections don't work on Live Monitor tab

### Roadmap
- [ ] Re-run portfolio selector once all 17 markets are in the leaderboard (JY Breakout is prime candidate)
- [ ] Session 60: Re-run Bootcamp $250K with upgraded selector
- [ ] Session 61: Fix source_capital scaling for smaller accounts
- [ ] Gate: 3-5 live trades confirmed → launch parallel evals (Bootcamp $250K + High Stakes $100K)
- [ ] Tune 3-layer correlation thresholds (too strict, rejected all combos)
- [ ] Walk-forward validation, trade loop vectorization, strategy templates (deferred)
- [ ] Darwinex Zero — wait for live trade proof, then spin up

## Key File Paths
- `EA/Portfolio1_The5ers.mq5` — Live EA on VPS
- `cloud/download_run.py` — Fixed aggregator (commit 9e04ad1)
- `cloud/launch_gcp_run.py` — Launcher with startup bootstrap fix
- `run_spot_resilient.py` — SPOT runner with queue management
- `Outputs/ultimate_leaderboard.csv` — 454 strategies
- `Outputs/ultimate_leaderboard_bootcamp.csv` — 414 accepted strategies
- `SESSION_58B_HANDOVER.md` — This file

## Commands cheat sheet
```bash
# Download latest run (local PowerShell)
python cloud/download_run.py --latest

# Check bucket contents
gcloud storage ls gs://strategy-artifacts-nikolapitman/runs/

# Check SPOT runner progress (on console)
tail -20 run_60m_after_start.log
tail -20 run_daily_after_60m.log
tail -20 run_30m_after_daily.log

# Check running VMs
gcloud compute instances list --project="project-c6c16a27-e123-459c-b7a"

# Kill orphaned VMs
gcloud compute instances delete sweep-60m --zone=us-central1-c --project="project-c6c16a27-e123-459c-b7a" --quiet
```
