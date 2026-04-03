# SESSION HANDOVER — Sessions 40-46

## Date: 2026-03-29

---

## PROJECT OVERVIEW

Rob is building an automated strategy discovery engine in Python, targeting The5ers $250K Bootcamp prop firm challenge. The Bootcamp requires passing three sequential evaluation steps, each requiring 6% profit before hitting a 5% maximum drawdown, using 1:7.5 leverage on indices.

The engine sweeps filter combinations across futures markets to find robust algorithmic strategies. The goal is to assemble ~6 uncorrelated strategies capable of reliably passing the Bootcamp.

**Repo**: `robpitman1982-ux/python-master-strategy-creator` (public GitHub)
**Infra**: GCP n2-highcpu-96 VMs (on-demand), strategy-console (e2-micro always-on), GCS bucket `strategy-artifacts-robpitman`
**Dashboard**: Streamlit at `http://35.232.131.181:8501`

---

## WHAT'S RUNNING RIGHT NOW

**Full 7-market rerun** is running overnight on strategy-console via `run_full_rerun.sh`:
- ES → CL → NQ → SI → HG → RTY → YM (sequential, one VM at a time)
- All using STANDARD provisioning (no SPOT preemption)
- All using Session 45's fixed position sizing (no compounding)
- All using Session 44's perf fixes (as_completed refinement, deferred portfolio eval)
- Launched from strategy-console: `nohup bash run_full_rerun.sh > full_rerun.log 2>&1 &`

**Check progress**:
```bash
# From strategy-console SSH
tail -30 /home/robpitman1982/python-master-strategy-creator/full_rerun.log

# Check VM status
gcloud compute instances list --filter="name=strategy-sweep"

# Check bucket for completed runs
gcloud storage ls gs://strategy-artifacts-robpitman/runs/ | grep 20260329
```

**Download results** (from Windows PowerShell):
```powershell
cd "C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator"
python cloud/download_run.py --latest
```
Run this multiple times or with specific run IDs to download each market's results.

---

## CRITICAL: OLD LEADERBOARDS CLEANED

All previous run directories were moved to `Outputs/runs_old_compounded/` because they had inflated dollar figures from the compounding position sizing bug. The `Outputs/runs/` directory is empty — tonight's rerun will build a fresh `ultimate_leaderboard.csv` from scratch with correct numbers.

**What was wrong**: The engine used `self.current_capital` (which grows with wins) to size positions. Over 18 years with PF 8.0 on NQ, this produced $20 BILLION PnL on a $250k account.

**What was fixed** (Session 45, commit `80d3fbc`): Changed to `self.initial_capital` for fixed position sizing. PF, quality flags, trade counts are UNAFFECTED (ratio-based). Only dollar figures (net_pnl, avg_trade, max_drawdown) changed.

---

## LEADERBOARD STATUS (pre-rerun, dollar figures tainted)

**127 accepted strategies across 3 markets** (PF and quality rankings are valid):
- NQ: 53 strategies (14 ROBUST) — best performer
- ES: 41 strategies
- CL: 33 strategies
- SI, HG, RTY, YM: not yet swept (running tonight)

**Top strategies by PF** (dollar figures need recalculation):

| Rank | Mkt | TF | Family | PF | OOS PF | Quality | Trades | Exit | BCS |
|------|-----|----|--------|-----|--------|---------|--------|------|-----|
| 1 | NQ | daily | MR mom_exhaustion | 8.04 | 8.05 | ROBUST | 411 | time_stop | 95.8 |
| 2 | NQ | daily | MR vol_dip | 5.18 | 5.19 | ROBUST | 537 | time_stop | 94.8 |
| 3 | NQ | daily | MR trend_pullback | 3.80 | 3.80 | ROBUST | 850 | time_stop | 94.3 |
| 4 | NQ | 30m | breakout | 2.10 | 2.27 | ROBUST | 239 | time_stop | 92.9 |
| 5 | NQ | daily | MR | 6.75 | 6.75 | ROBUST | 698 | time_stop | 91.3 |
| 6 | CL | 60m | short_MR | 2.20 | 4.44 | STABLE_BL | 67 | profit_target | 81.4 |
| 7 | CL | 60m | breakout | 1.86 | 2.19 | ROBUST | 239 | time_stop | 78.4 |
| 8 | CL | 30m | MR | 1.73 | 3.98 | STABLE | 102 | signal_exit | 76.9 |
| 9 | ES | 30m | MR mom_exhaustion | 2.34 | 2.76 | ROBUST | 100 | time_stop | 85.5 |
| 10 | ES | 30m | trend | 1.94 | 2.13 | ROBUST | 239 | time_stop | 82.9 |

**Key milestone**: ES 30m trend at PF 1.94 ROBUST is the first portfolio-grade trend strategy on ES.

**Exit type diversity achieved**:
- time_stop: 53, profit_target: 12, signal_exit: 6, trailing_stop: 3 (was all time_stop before)

---

## SESSIONS COMPLETED (40-46)

### Session 40 — Performance Caching (code committed but NEVER ENGAGED)
- Added dataset caching per timeframe + concurrent small-family execution
- Commits: `b0f3c42`, `ba45040`, `6bc15aa`, `c48bd26`
- **STATUS**: Code exists but families still reload CSV internally. Not fixed yet.

### Session 41 — Widen Exit Grids
- Trend trailing_stop_atr: [1.0-2.5] → [1.5, 2.5, 3.5, 5.0, 7.0]
- Breakout trailing_stop_atr: → [1.5, 2.5, 3.5, 5.0]
- MR profit_target_atr: → [0.5, 1.0, 1.5, 2.0, 3.0]
- **RESULT**: Trailing stops tested but still lost to time_stop on ES. Problem is ES trend filters, not exits.

### Session 42 — Expand Filters + Drop 5m + Multi-Market
- Added 7 new market-agnostic filters: InsideBar, OutsideBar, GapUp, GapDown, ATRPercentile, HigherHigh, LowerLow
- Created configs for all 8 markets (ES, NQ, CL, GC, SI, HG, RTY, YM)
- Dropped 5m timeframe permanently (zero accepted strategies, ~50% of runtime)
- **RESULT**: ES went from 27 → 41 accepted strategies with expanded filters

### Session 43 — Shared Worker Pool + Deferred Portfolio Eval
- Reuse ProcessPoolExecutor across families within dataset
- Made portfolio evaluation optional via `skip_portfolio_evaluation` config flag
- Added granular status stages (LOAD_DATA, PRECOMPUTE_FEATURES, etc.)
- Fixed SPOT provisioning bug: configs used `preemptible: false` but launcher expected `provisioning_model: "STANDARD"`

### Session 44 — Refinement Scheduling Fix
- Replaced ordered `executor.map()` with `submit()` + `as_completed()` in refinement
- Deduplicated refinement tasks before dispatch
- Created GC+SI runner script
- **NOTE**: Dataset caching (Step 1) was skipped by Claude Code — still not fixed

### Session 45 — Fixed Position Sizing (CRITICAL BUG FIX)
- Changed `calculate_position_size_contracts()` to use `self.initial_capital` instead of `self.current_capital`
- Sanity check: ES daily MR now shows $702k net PnL (was $20B+), PF 1.48 unchanged
- ALL previous dollar figures are wrong and need re-running (tonight's rerun)

### Session 46 — Dashboard Upgrade
- Added Max DD, exit type, market, BCS columns to Ultimate Leaderboard display
- Added market filter and Max DD slider filter
- Cleaned old leaderboard data (moved to `Outputs/runs_old_compounded/`)

---

## KNOWN ISSUES & BUGS

### 1. Dataset Caching Never Engaged (HIGH PRIORITY)
Session 40 added caching code but families still reload CSV internally. Each of the 15 families reloads and recomputes features per timeframe. This causes the CPU utilisation valleys visible in every run. Session 44 was supposed to fix this but Claude Code skipped Step 1.

**Fix needed**: Find where families load data inside their sweep/refinement methods. They should accept pre-loaded data passed from `_run_dataset()` instead of reloading from disk. A `SESSION_46_TASKS.md` exists in the repo with detailed instructions.

### 2. Dashboard Live Monitor Sections Broken
Engine log (last 30 lines) and Promoted Candidates sections show placeholder text even during active runs. Noted in memory for future fix.

### 3. Bootcamp Score Uses Dollar Components
BCS is primarily PF-weighted so rankings are mostly valid, but any components that use max_drawdown or net_pnl in dollar terms were affected by the compounding bug. After tonight's rerun, BCS will be fully accurate.

---

## INFRASTRUCTURE & OPERATIONS

### Cloud Workflow
1. SSH into strategy-console (always-on e2-micro)
2. Launch sweep: `python3 run_cloud_sweep.py --config cloud/config_XX_4tf_ondemand.yaml --fire-and-forget`
3. VM runs engine, uploads artifacts to GCS, self-deletes
4. Download: `python cloud/download_run.py --latest`
5. Ultimate leaderboard auto-regenerates on download

### Key Commands
```bash
# SSH to console (as robpitman1982)
gcloud compute ssh strategy-console --zone us-central1-c

# Check VM status
gcloud compute instances list --filter="name=strategy-sweep"

# Check bucket
gcloud storage ls gs://strategy-artifacts-robpitman/runs/

# Download latest
cd "C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator"
python cloud/download_run.py --latest

# Claude Code unattended
claude --dangerously-skip-permissions -p "Read SESSION_XX_TASKS.md and execute all steps..."
```

### SPOT vs STANDARD
- All `*_ondemand.yaml` configs now use `provisioning_model: "STANDARD"` (fixed in Session 43)
- Previous bug: configs used `preemptible: false` but launcher defaults `--provisioning-model` to `"SPOT"` and checks for `provisioning_model` key, not `preemptible`
- CL and NQ runs were lost to SPOT preemption before this was fixed

### Console VM Permissions
- Two users: `Rob` and `robpitman1982`
- Always launch runs as `robpitman1982`
- If SSH'd in as Rob: `sudo -u robpitman1982 bash -c 'cd /home/robpitman1982/...'`

### Data Location
- Local Windows: `C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator\Data\`
- Console VM: `/home/robpitman1982/python-master-strategy-creator/Data/` (copied from uploads)
- Data is in `.gitignore` — bundled by launcher from local `Data/` folder
- NQ files were renamed from `NQ_60_` to `NQ_60m_` format (both local and console)

---

## CONTRACT SPECS FOR ALL MARKETS

| Market | Symbol | $/point | Tick size | $/tick |
|--------|--------|---------|-----------|--------|
| ES | E-mini S&P 500 | $50 | 0.25 | $12.50 |
| NQ | E-mini Nasdaq | $20 | 0.25 | $5.00 |
| CL | Crude Oil | $1,000 | 0.01 | $10.00 |
| GC | Gold | $100 | 0.10 | $10.00 |
| SI | Silver | $5,000 | 0.005 | $25.00 |
| HG | Copper | $25,000 | 0.0005 | $12.50 |
| RTY | E-mini Russell 2000 | $50 | 0.10 | $5.00 |
| YM | E-mini Dow | $5 | 1.0 | $5.00 |

---

## NEXT PRIORITIES (in order)

### 1. Download overnight rerun results and validate
- Download all 7 market runs from bucket
- Upload ultimate_leaderboard_bootcamp.csv for analysis
- Verify dollar figures are now realistic (ES daily MR should be ~$700k not $20B)
- Check max drawdown figures are trustworthy for Bootcamp assessment

### 2. Fix dataset caching (SESSION_46_TASKS.md exists)
- The single biggest remaining performance bottleneck
- Each family reloads CSV independently — 15x redundant per timeframe
- Expected to collapse CPU valleys and cut runtime ~40%

### 3. Portfolio construction
- Pick best 6 uncorrelated strategies across markets
- Criteria: BCS 75+, ROBUST/STABLE quality, 100+ trades, max DD under 5%
- Run correlation analysis between candidates

### 4. Monte Carlo Bootcamp simulation
- Simulate 10,000 Bootcamp attempts with randomised trade sequences
- Measure pass rate for the selected 6-strategy portfolio
- Test with The5ers rules: 6% target, 5% max DD, 3 sequential steps

### 5. Position sizing optimiser
- Find optimal contract allocation per strategy
- Maximise profit while keeping combined portfolio DD under 5%
- Account for leverage constraint (1:7.5)

### 6. Future markets
- BTC futures config (deferred — need to verify contract specs)
- Re-run with dataset caching fix for faster iteration

---

## KEY LEARNINGS & PRINCIPLES

- **Exit architecture is NOT the main lever for ES** — trailing stops up to 7.0x ATR still lost to time_stop. ES trend filters are the bottleneck.
- **NQ produces the strongest strategies** — higher beta, bigger moves, cleaner trends. 14 ROBUST strategies.
- **CL provides diversity** — different market dynamics (commodity vs equity), breakout and short strategies work well.
- **Universal filter set works** — same filters find edge across all markets. Don't tailor per market.
- **5m timeframe is permanently excluded** — zero accepted strategies, ~50% of runtime.
- **SPOT preemption kills runs** — always use STANDARD provisioning for production runs.
- **Compounding position sizing produces meaningless results** — fixed sizing is essential for Bootcamp-relevant metrics.
- **Drawdown is the hardest Bootcamp constraint** — 5% DD limit is unforgiving. Portfolio correlation matters more than individual strategy drawdown.
- **OOS improvement is a positive signal** — best strategies show OOS PF > IS PF, suggesting genuine edge.

---

## FILE REFERENCE

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Auto-read by Claude Code, project context |
| `CHANGELOG_DEV.md` | Session history |
| `SESSION_46_TASKS.md` | Dataset caching fix (not yet executed) |
| `run_full_rerun.sh` | 7-market sequential runner (currently running) |
| `run_cl_nq.sh` | CL + NQ runner |
| `run_gc_si.sh` | GC + SI runner |
| `run_remaining_markets.sh` | SI + HG + RTY + YM runner |
| `run_all_markets.sh` | All 8 markets runner |
| `cloud/config_XX_4tf_ondemand.yaml` | Per-market 4TF configs (8 markets) |
| `dashboard.py` | Streamlit dashboard |
| `Outputs/runs_old_compounded/` | Archived runs with wrong dollar figures |
| `STRATEGY_ENGINE_COMPLETE_REFERENCE.md` | Full methodology doc for LLM consultation |
