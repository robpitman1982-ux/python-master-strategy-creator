# SESSION HANDOFF 11
## Date
2026-03-26

## Purpose
Comprehensive handover covering current state, recent sessions, and priorities for the next chat.

---

## Executive Summary

The strategy discovery engine is structurally complete and cloud-deployed. The fire-and-forget bucket workflow is proven. Vectorized filters (~50x speedup) are live. Two successful production runs have completed:

1. **ES 60m MR-only run** — 1 ROBUST strategy (PF 1.71, 61 trades)
2. **ES all-timeframes on-demand run** — 5 accepted strategies across daily and 60m

A dual-VM parallel architecture was built (Session 35) but **cannot be used** because Rob's GCP regional CPU quota is capped at 100 vCPUs (not 200 as initially assumed). Upgrade request was denied. This means runs must use a single 96-core VM.

The 5m timeframe was attempted but the SPOT VM was preempted after 30 minutes. 5m data is large (71.5MB CSV, ~1.3M bars) and will take longer to process, making it especially vulnerable to SPOT preemption.

**Cost and efficiency are now the primary constraints.** On-demand pricing (~$3.31/hr for n2-highcpu-96) makes long runs expensive (~$19 for 4+ hours). SPOT (~$0.72/hr) is cheap but preemption risk is high, especially for longer runs. Next priorities should focus on reducing runtime through further vectorization and smarter search strategies.

---

## Current Best Results

### Master Leaderboard (from all-timeframes on-demand run)

| Rank | TF | Family | Quality | PF | Trades | IS PF | OOS PF | Net PnL | Bootcamp |
|------|------|--------|---------|------|--------|-------|--------|---------|----------|
| 1 | daily | MR | STABLE_BORDERLINE | 1.51 | 590 | 1.03 | 1.66 | $1.64M | 67.25 |
| 2 | daily | breakout | STABLE_BORDERLINE | 1.30 | 366 | 1.03 | 1.52 | $245K | 58.87 |
| 3 | daily | trend | REGIME_DEPENDENT | 1.18 | 376 | 0.93 | 1.49 | $142K | 42.01 |
| 4 | 60m | MR | ROBUST | 1.34 | 75 | 1.36 | 1.31 | $51K | 42.58 |
| 5 | 60m | trend | REGIME_DEPENDENT | 1.02 | 297 | 0.87 | 1.32 | $5K | 26.05 |

Key observations:
- Daily MR is the standout (590 trades, $1.64M, Bootcamp 67.25)
- 60m MR is the only ROBUST strategy but thin on trades (75)
- 30m and 15m produced zero accepted strategies this run
- Daily breakout is viable as a portfolio diversifier
- 60m trend is barely breakeven (PF 1.02)

### Best Individual Strategy
- **Daily MR**: DownCloseFilter + LowVolatilityRegimeFilter + StretchFromLongTermSMAFilter
- Refined: HB5, ATR 0.5, DIST 0.4, MOM 0
- Different filter combo from the 60m MR winner (DistanceBelowSMA + TwoBarDown + ReversalUpBar)

---

## Infrastructure State

### Cloud Architecture
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

### Fire-and-Forget Bucket Workflow (proven working)
1. Launcher on strategy-console stages input bundle to GCS staging area
2. Creates compute VM
3. VM downloads bundle from GCS at bootstrap
4. Engine runs
5. On success: uploads artifacts.tar.gz + run_status.json to bucket
6. Verifies upload, then self-deletes
7. Results downloaded locally with `cloud/download_run.py --latest`

### GCP Quota Constraint (CRITICAL)
- **Regional CPU quota: 100 vCPUs** (us-central1)
- Upgrade request to 200 was **denied**
- Cannot run dual 96-core VMs simultaneously
- Single n2-highcpu-96 (96 vCPUs) fits within quota
- Other US regions (east1, east4, west1, west2) also have limited quota

### SPOT Availability by Zone
- us-central1-a: preempted twice rapidly, unreliable for long runs
- us-central1-c: SPOT unavailable (STOCKOUT), on-demand works
- us-central1-f: SPOT available (confirmed working), but preemption still possible
- Recommendation: use us-central1-f for SPOT, us-central1-c for on-demand fallback

### Pricing
- n2-highcpu-96 SPOT: ~$0.72/hr
- n2-highcpu-96 on-demand: ~$3.31/hr
- 4-hour all-timeframes run: ~$3-5 SPOT, ~$13-19 on-demand

---

## What's Built and Working

### Engine
- [x] Three strategy families: Mean Reversion, Trend, Breakout
- [x] Vectorized filters (~50x speedup) — all 30+ filters have mask() methods
- [x] Vectorized signal path wired into all sweep and refinement pipelines
- [x] Exit architecture (trailing stop, profit target, signal exit)
- [x] Bootcamp scoring + dual leaderboard
- [x] Timeframe-aware parameter scaling
- [x] IS/OOS split (2019-01-01), yearly consistency analysis
- [x] Quality scoring (ROBUST / STABLE_BORDERLINE / REGIME_DEPENDENT / MARGINAL)
- [x] Master leaderboard aggregation across datasets

### Cloud
- [x] Fire-and-forget bucket workflow (GCS-based, proven)
- [x] GCS staging for input bundles (avoids SCP preemption window)
- [x] Human-friendly run labels
- [x] download_run.py with --latest support
- [x] Dual-VM parallel launcher (run_cloud_parallel.py) — built but unusable due to quota
- [x] Split configs (vm_a, vm_b) — built but unusable due to quota
- [x] On-demand and SPOT config variants

### Dashboard
- [x] Streamlit dashboard on strategy-console (port 8501)
- [x] Live Monitor, Results Explorer, Run History, System tabs

### Data
- ES daily: 4,500 bars (0.3MB) ✅
- ES 60m: 107K bars (6.3MB) ✅
- ES 30m: 215K bars (12.4MB) ✅
- ES 15m: 430K bars (24.3MB) ✅
- ES 5m: ~1.3M bars (71.5MB) ✅ (uploaded to strategy-console, not in git)
- CL, NQ, GC: not yet exported from TradeStation

---

## What's NOT Working / Known Issues

1. **Dual-VM parallel runs blocked by 100 vCPU quota** — run_cloud_parallel.py exists but can't be used
2. **5m preemption risk** — 5m data is huge, runs take longer, SPOT preemption killed first attempt after 30 min
3. **30m and 15m produced zero strategies** in latest run (they did produce strategies in an earlier run with different code version)
4. **strategy-console has no pandas** — ultimate leaderboard aggregation was moved to download_run.py but verify it actually works there
5. **Dashboard stale-state** was fixed in Session 32 but hasn't been validated against a live dual-VM run
6. **5m data is not in git** — too large (~71.5MB), stored on strategy-console uploads folder only

---

## Suggested Next Priorities

Rob identified these as the key focus areas:

### Priority 1: Further Vectorization (reduce runtime, reduce preemption exposure)
The trade simulation loop is still bar-by-bar. This is the remaining bottleneck after filter vectorization. Vectorizing or optimizing it would:
- Reduce total runtime → cheaper runs
- Reduce SPOT preemption window → more likely to complete on SPOT
- Make 5m viable on SPOT

Possible approaches:
- Vectorize the position tracking / trade simulation loop
- Pre-filter: skip bars where no signal exists (already implicitly done by vectorized signals, but the engine may still iterate every bar)
- Batch trade evaluation using numpy

### Priority 2: Strategy Templates
Instead of searching the full combinatorial space for every family, define sub-families or templates within Trend, MR, and Breakout that focus the search on known-productive filter combinations. This would:
- Reduce the search space dramatically
- Allow more refinement depth on promising areas
- Make runs faster and cheaper

Examples:
- MR templates: "volatility dip" (LowVol + DistanceBelow + Reversal), "momentum exhaustion" (ThreeBarDown + StretchFromSMA + DownClose)
- Trend templates: "pullback continuation" (TrendDirection + Pullback + Recovery), "breakout momentum" (Slope + Momentum + UpClose)

### Priority 3: Make 5m Work on SPOT
The 5m run was preempted after 30 minutes. Options:
- Reduce 5m search space with templates (Priority 2)
- Add checkpointing so a preempted run can resume
- Use a smaller VM (e.g., n2-highcpu-48) for longer but cheaper runs
- Run 5m on on-demand as a one-off ($13-19)

### Priority 4: Instrument Expansion (CL, NQ)
Export data from TradeStation, add to configs, run sweeps. Lower priority until runtime/cost issues are addressed.

---

## Key Files and Commands

### Launch Commands (from strategy-console SSH)

Single VM, all timeframes, SPOT us-central1-f:
```bash
cd /home/robpitman1982/python-master-strategy-creator && git pull && python3 run_cloud_sweep.py --config cloud/config_es_all_timeframes_spot_f.yaml --fire-and-forget
```

Single VM, daily only (fast validation):
```bash
cd /home/robpitman1982/python-master-strategy-creator && git pull && python3 run_cloud_sweep.py --config cloud/config_es_daily_only.yaml --fire-and-forget
```

On-demand fallback (us-central1-c):
```bash
cd /home/robpitman1982/python-master-strategy-creator && git pull && python3 run_cloud_sweep.py --config cloud/config_es_all_timeframes_gcp96_ondemand.yaml --fire-and-forget
```

### Monitoring
```bash
# Check if VM is still running
gcloud compute instances list --filter="name~strategy-sweep"

# Check bucket for results
gcloud storage ls gs://strategy-artifacts-robpitman/runs/

# Tail engine log (while VM is running)
gcloud compute ssh strategy-sweep-a --zone=us-central1-f --command="tail -50 /tmp/strategy_engine_runs/*/logs/runner_stdout.log"
```

### Download Results (local Windows)
```bash
python3 cloud/download_run.py --latest
```

### Key Config Files
- `cloud/config_es_all_timeframes_spot_f.yaml` — 4 timeframes, SPOT, us-central1-f
- `cloud/config_es_all_timeframes_gcp96_ondemand.yaml` — 4 timeframes, on-demand
- `cloud/config_es_vm_a.yaml` — 5m only (unusable without quota increase)
- `cloud/config_es_vm_b.yaml` — daily+60m+30m+15m (unusable without quota increase)
- `cloud/config_es_daily_only.yaml` — fast validation

### Key Source Files
- `master_strategy_engine.py` — main engine
- `cloud/launch_gcp_run.py` — GCP launcher with bucket workflow
- `run_cloud_sweep.py` — top-level sweep wrapper
- `run_cloud_parallel.py` — dual-VM launcher (quota-blocked)
- `cloud/download_run.py` — download from GCS bucket
- `modules/filters.py` — all 30+ filters with vectorized mask() methods
- `modules/vectorized_signals.py` — compute_combined_signal_mask()
- `modules/bootcamp_scoring.py` — Bootcamp ranking
- `docs/EASYLANGUAGE_FILTER_MAP.md` — filter-to-EasyLanguage translation

### Session Continuity
- `CLAUDE.md` — auto-read by Claude Code, master project reference
- `CHANGELOG_DEV.md` — session-by-session development log
- `SESSION_HANDOFF_*.md` files — cross-session context

---

## Important Principles (unchanged)

- **Sweep loose, refine strict, portfolio strictest**
- **Structural soundness before performance optimization**
- **1m data permanently excluded** (HFT rules + compute cost)
- **Claude Code for execution, Claude.ai for planning**
- **Git commits as checkpoints**
- **One command at a time** for PowerShell copy-paste

---

## Bottom Line

The engine works. The cloud workflow works. Results are real. The constraint is now **cost and runtime** — the 100 vCPU quota cap and SPOT preemption risk make every run precious. The next phase should focus on making runs faster (vectorize trade loop, strategy templates) so they're cheaper and less exposed to preemption. Once runtime is under control, expand to 5m and new instruments.
