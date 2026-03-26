# SESSION HANDOFF 12
## Date
2026-03-26

## Purpose
Comprehensive handover covering sessions 36-37: speed optimisation sprint, single-VM constraint, full 5-timeframe run, and latest results.

---

## Executive Summary

The strategy discovery engine is now **fully vectorised and extremely fast**. A full 5-timeframe ES sweep (daily, 60m, 30m, 15m, 5m × 3 families) completed in **37.8 minutes** on a single n2-highcpu-96 VM at a cost of ~$2.20 on-demand. The previous equivalent (4 timeframes) took ~4 hours. We are running on a **single 96-core VM** due to a hard 100 vCPU global quota cap — dual-VM architecture exists but cannot be used until quota is upgraded.

A quota upgrade request to 200 vCPUs (global + multiple regions) was submitted but not yet approved.

The latest 5-timeframe run produced 8 accepted strategies. **30m MR is now the #1 bootcamp strategy** (ROBUST, PF 1.65, Bootcamp 71.1). 5m produced zero accepted strategies across all families.

---

## Speed Optimisation — What Was Done (Sessions 36-37)

### Previously completed (Sessions 31-35)
- All 30+ filters have vectorised `mask()` methods (~50x speedup on signal generation)
- `compute_combined_signal_mask()` in `modules/vectorized_signals.py` pre-computes the combined signal array once per combo
- Signal-skipping in engine trade loop: `np.searchsorted` jumps to next signal bar when no position open
- Numpy array pre-conversion: `close_arr`, `high_arr`, `low_arr`, `atr_arr` extracted from DataFrame once at start of `run()`
- Gemini added these optimisations in Session 36 — verified safe, 80/80 tests passing, committed

### Session 37 additions (this session)
**1. Timestamp pre-conversion (engine.py)**
- `ts_list = list(pd.DatetimeIndex(timestamps))` built once at start of `run()`
- Hot loop uses `ts_list[i]` instead of `pd.Timestamp(timestamps[i])` per bar
- Eliminates repeated Timestamp object construction across millions of bars

**2. Equity curve fill — double-entry bug fix + extend (engine.py)**
- Gemini's signal-skip fill loop had a bug: `range(i, next_signal_i)` included bar `i` which was already appended at the top of the loop → double-entry
- Fixed to `range(i+1, next_signal_i)`
- Replaced per-bar `append` with `list.extend` + list comprehension for the fill loops
- Same fix applied to the end-of-signals break path

**3. Initializer pattern for all 3 sweep workers**
- Previously: each sweep task pickled `(data, cfg, combo_classes)` → full DataFrame serialised once per task → for 5m data (1.3M bars, ~58 MB) × 600+ tasks = massive overhead
- Now: `ProcessPoolExecutor(initializer=_xx_worker_init, initargs=(data, cfg))` → data sent to each worker process once at startup, tasks carry only `combo_classes` (tiny)
- ~6-7x reduction in serialisation overhead for 5m data
- Applied to `MeanReversionStrategyType`, `TrendStrategyType`, `BreakoutStrategyType`
- Sequential fallback calls `_xx_worker_init(data, cfg)` before the loop

**Combined result: full 5-TF run in 37.8 minutes vs ~4+ hours previously (~6x+ overall speedup)**

---

## Single-VM Constraint (CRITICAL)

### Why we are on one VM
- GCP global CPU quota `CPUS_ALL_REGIONS`: **100 vCPU hard cap**
- n2-highcpu-96 uses 96 vCPUs — only one fits within quota
- Dual-VM parallel architecture was built (Sessions 34-35) but **cannot be used**
- `run_cloud_parallel.py` and split configs (`config_es_vm_a.yaml`, `config_es_vm_b.yaml`) exist but are blocked

### Quota upgrade requests submitted
- Global `CPUS_ALL_REGIONS`: 100 → 200 (pending)
- `us-west1`, `us-west2`, `us-west3`: 100 → 200 (pending)
- `australia-southeast1`: 100 → 200 (pending)
- Status: **not yet approved** — check GCP console → IAM & Admin → Quotas

### Implication
With the speed improvements, a single VM now completes the full 5-TF sweep in ~38 minutes. The dual-VM architecture would split this to ~20 minutes. It's no longer urgent — the single VM is fast enough.

---

## Current Best Results (Latest Run: strategy-sweep-20260326T035037Z)

### Master Leaderboard — Bootcamp Ranked

| Rank | TF | Family | Quality | PF | IS PF | OOS PF | Trades | Net PnL | Bootcamp |
|------|------|--------|---------|------|-------|--------|--------|---------|----------|
| 1 | **30m** | MR | **ROBUST** | 1.65 | 1.45 | 1.91 | 111 | $146K | **71.1** |
| 2 | daily | MR | STABLE_BL | 1.51 | 1.03 | 1.66 | 590 | $1.64M | 67.3 |
| 3 | daily | breakout | STABLE_BL | 1.30 | 1.03 | 1.52 | 366 | $245K | 58.9 |
| 4 | 60m | MR | **ROBUST** | 1.34 | 1.36 | 1.31 | 75 | $51K | 42.6 |
| 5 | daily | trend | REGIME_DEP | 1.18 | 0.93 | 1.49 | 376 | $142K | 42.0 |
| 6 | 30m | trend | REGIME_DEP | 1.10 | 0.82 | 1.26 | 724 | $77K | 33.2 |
| 7 | 15m | MR | REGIME_DEP | 1.10 | 0.65 | 1.27 | 288 | $48K | 28.8 |
| 8 | 60m | trend | REGIME_DEP | 1.02 | 0.87 | 1.32 | 297 | $5K | 26.1 |

### Key Observations
- **30m MR is now the standout** — ROBUST, best OOS PF (1.91), highest Bootcamp (71.1)
- **Two ROBUST strategies**: 30m MR and 60m MR — both use same filter combo (DistanceBelowSMA + TwoBarDown + ReversalUpBar), just different timeframes
- **5m produced zero accepted strategies** across all 3 families — too noisy at that resolution
- **15m MR made the leaderboard** for the first time (REGIME_DEPENDENT but accepted)
- Daily MR still best absolute PnL ($1.64M) but ranked #2 on Bootcamp scoring

### Best Strategies Detail

**#1 — 30m MR ROBUST**
- Filters: DistanceBelowSMAFilter + TwoBarDownFilter + ReversalUpBarFilter
- Refined: HB20, ATR 0.4, DIST 0.4, MOM 0
- IS PF: 1.45, OOS PF: 1.91, 111 trades, $146K

**#2 — Daily MR STABLE_BORDERLINE**
- Filters: DownCloseFilter + LowVolatilityRegimeFilter + StretchFromLongTermSMAFilter
- Refined: HB5, ATR 0.5, DIST 0.4, MOM 0
- IS PF: 1.03, OOS PF: 1.66, 590 trades, $1.64M

---

## Infrastructure State

### Cloud Architecture (unchanged)
```
Developer (Windows, VS Code + Claude Code CLI)
    ↓ git push
GitHub (robpitman1982-ux/python-master-strategy-creator)
    ↓ git pull
Strategy Console VM (e2-micro, us-central1-c, always-on)
    ↓ python3 run_cloud_sweep.py --fire-and-forget
Compute VM (n2-highcpu-96, created on demand)
    ↓ engine runs, uploads to GCS bucket, self-deletes
GCS Bucket (gs://strategy-artifacts-robpitman)
    ↓ python3 cloud/download_run.py --latest
Local machine (Windows, results in Outputs/runs/<run-id>/)
```

### GCP Quota Constraint
- **Global CPUS_ALL_REGIONS: 100 vCPUs** — hard cap, upgrade pending
- Single n2-highcpu-96 (96 vCPUs) is the maximum possible right now
- With speed improvements, single VM completes full 5-TF sweep in ~38 min — no longer a major issue

### SPOT Availability
- us-central1-a: exhausted (ZONE_RESOURCE_POOL_EXHAUSTED for both SPOT and on-demand)
- us-central1-c: on-demand reliable ✅, SPOT unavailable
- us-central1-f: SPOT available ✅ (but preemption possible on long runs)
- australia-southeast1-b: SPOT available but blocked by global quota

### Pricing
- n2-highcpu-96 SPOT us-central1-f: ~$0.72/hr → full 5-TF run ~$0.45
- n2-highcpu-96 on-demand us-central1-c: ~$3.31/hr → full 5-TF run ~$2.10
- With 38-min runtime, even on-demand is now very cheap

---

## What's Built and Working

### Engine
- [x] Three strategy families: Mean Reversion, Trend, Breakout
- [x] **Vectorised filters — all 30+ filters have `mask()` methods (~50x speedup)**
- [x] **Vectorised signal path wired into sweep and refinement pipelines**
- [x] **Signal-skipping in trade loop (np.searchsorted jumps dead bars)**
- [x] **Numpy array pre-conversion — close/high/low/atr arrays extracted once**
- [x] **Timestamp pre-conversion — ts_list built once, used throughout**
- [x] **Equity curve extend — list.extend + comprehension, double-entry bug fixed**
- [x] **Initializer pattern — data serialised once per worker, not per task**
- [x] Exit architecture (trailing stop, profit target, signal exit)
- [x] Bootcamp scoring + dual leaderboard (results + bootcamp ranked)
- [x] Timeframe-aware parameter scaling
- [x] IS/OOS split (2019-01-01), yearly consistency analysis
- [x] Quality scoring (ROBUST / STABLE_BORDERLINE / REGIME_DEPENDENT / MARGINAL)
- [x] Master leaderboard aggregation across datasets

### Cloud
- [x] Fire-and-forget bucket workflow (GCS-based, proven)
- [x] GCS staging for input bundles (avoids SCP preemption window)
- [x] Human-friendly run labels
- [x] download_run.py with --latest support + ultimate leaderboard generation
- [x] Dual-VM parallel launcher (run_cloud_parallel.py) — built but unusable due to quota
- [x] On-demand and SPOT config variants

### Key Cloud Configs
| Config | Timeframes | Zone | Provisioning | Est. Time | Est. Cost |
|--------|-----------|------|-------------|-----------|-----------|
| `config_es_all_5tf_ondemand_c.yaml` | all 5 | us-central1-c | STANDARD | ~38 min | ~$2.10 |
| `config_es_all_timeframes_spot_f.yaml` | 4 TF (no 5m) | us-central1-f | SPOT | ~25 min | ~$0.30 |
| `config_es_5m_spot_aus.yaml` | 5m only | australia-southeast1-b | SPOT | ~12 min | ~$0.15 |
| `config_es_daily_only.yaml` | daily only | us-central1-c | STANDARD | ~5 min | ~$0.30 |
| `config_es_daily_60m_ondemand.yaml` | daily + 60m | us-central1-c | STANDARD | ~10 min | ~$0.55 |

### Data
- ES daily: 4,500 bars (0.3 MB) ✅ in git
- ES 60m: 107K bars (6.3 MB) ✅ in git
- ES 30m: 215K bars (12.4 MB) ✅ in git
- ES 15m: 430K bars (24.3 MB) ✅ in git
- ES 5m: 1.3M bars (71.5 MB) ✅ on strategy-console uploads folder (NOT in git — too large)
- CL, NQ, GC: not yet exported from TradeStation

---

## What's NOT Working / Known Issues

1. **Dual-VM parallel runs blocked by 100 vCPU global quota** — upgrade pending
2. **5m produces zero accepted strategies** — all 3 families failed on 5m ES; too noisy at that timeframe
3. **5m data not in git** — stored on strategy-console only (`~/strategy_console_storage/uploads/`)
4. **SSH from local Windows via plink** — host key prompt blocks `gcloud compute ssh` commands from local machine; use strategy-console SSH to tail logs instead
5. **australia-southeast1 blocked** — same global quota issue; available once upgrade approved
6. **30m and 15m MR thin on trades** — 30m has 111 trades, 15m has 288; acceptable but worth watching

---

## Launch Commands (from strategy-console SSH)

**Full 5-timeframe run, on-demand, us-central1-c (recommended — reliable, ~$2):**
```bash
cd /home/robpitman1982/python-master-strategy-creator && git pull && python3 run_cloud_sweep.py --config cloud/config_es_all_5tf_ondemand_c.yaml --fire-and-forget
```

**Full 5-timeframe run, SPOT us-central1-f (cheapest — preemption possible):**
```bash
cd /home/robpitman1982/python-master-strategy-creator && git pull && python3 run_cloud_sweep.py --config cloud/config_es_all_timeframes_spot_f.yaml --fire-and-forget
```

**Daily only (fast validation, ~5 min):**
```bash
cd /home/robpitman1982/python-master-strategy-creator && git pull && python3 run_cloud_sweep.py --config cloud/config_es_daily_only.yaml --fire-and-forget
```

### Monitoring (from strategy-console SSH)
```bash
# Check VM alive
gcloud compute instances list --filter="name~strategy-sweep"

# Tail engine log
gcloud compute ssh strategy-sweep --zone=us-central1-c --command="tail -80 /tmp/strategy_engine_runs/*/logs/engine_run.log"

# Check bucket for results
gcloud storage ls gs://strategy-artifacts-robpitman/runs/
```

### Download Results (local Windows)
```bash
python3 cloud/download_run.py --latest
```

---

## Suggested Next Priorities

### Priority 1: Instrument Expansion (CL, NQ)
Now that runs are fast and cheap (~$2 for full sweep), expanding to new instruments is the logical next step.
- Export CL (crude oil) and NQ (Nasdaq) data from TradeStation
- Add to configs and run sweeps
- See `docs/TRADESTATION_EXPORT_GUIDE.md` for export steps

### Priority 2: Strategy Templates
Define sub-families within each strategy type to reduce search space further and focus on known-productive filter combinations. Makes runs even faster and more targeted.

### Priority 3: 5m — Investigate or Drop
5m produced zero results. Options:
- Investigate why (too many trades → filters too loose? bar resolution too fine for these filter types?)
- Adjust promotion gate thresholds for 5m specifically
- Accept that 5m doesn't work for these strategy families and exclude it

### Priority 4: Portfolio Construction
With 8 accepted strategies across multiple timeframes, start evaluating correlation and portfolio-level metrics to select the best 3-6 uncorrelated strategies for the target $25K MES account.

---

## Key Source Files
- `master_strategy_engine.py` — main engine
- `modules/engine.py` — trade loop with all speed optimisations
- `modules/filters.py` — all 30+ filters with vectorised `mask()` methods
- `modules/vectorized_signals.py` — `compute_combined_signal_mask()`
- `modules/strategy_types/mean_reversion_strategy_type.py` — MR sweep with initializer
- `modules/strategy_types/trend_strategy_type.py` — trend sweep with initializer
- `modules/strategy_types/breakout_strategy_type.py` — breakout sweep with initializer
- `cloud/launch_gcp_run.py` — GCP launcher with bucket workflow
- `cloud/download_run.py` — download from GCS, generate ultimate leaderboard

## Session Continuity
- `CLAUDE.md` — auto-read by Claude Code, master project reference
- `CHANGELOG_DEV.md` — session-by-session development log
- `SESSION_HANDOFF_*.md` files — cross-session context

---

## Important Principles (unchanged)
- **Sweep loose, refine strict, portfolio strictest**
- **Structural soundness before performance optimisation**
- **1m data permanently excluded** (HFT rules + compute cost)
- **5m excluded until further analysis** (zero results this run)
- **Claude Code for execution, Claude.ai for planning**
- **Git commits as checkpoints**
- **One command at a time** for PowerShell copy-paste

---

## Bottom Line

The engine is fast, cheap, and proven. A full 5-timeframe sweep costs ~$2 and takes 38 minutes. We have 8 accepted strategies with two ROBUST ones (30m MR and 60m MR). 5m is a dead end for now. The next phase is instrument expansion (CL, NQ) and portfolio construction from the existing strategy candidates.
