# SESSION HANDOFF 13
## Date: 2026-03-27
## For: Claude Opus (new session)

---

## Who Is Rob
Futures trader in Melbourne, Australia. Building an automated strategy discovery engine
for ES/CL/NQ futures. Target: The5ers $250K Bootcamp prop firm challenge (6% profit
target, 5% max drawdown, 3-step path to funded account).

GitHub repo: `robpitman1982-ux/python-master-strategy-creator` (public)
Uses Claude.ai for planning/architecture, Claude Code CLI for unattended execution.

---

## Executive Summary — Where We Are Right Now

The engine is **fully vectorised, fast, and producing real results**. A full 5-timeframe
ES sweep (daily, 60m, 30m, 15m × all families) runs in ~38 minutes on a single
n2-highcpu-96 GCP VM costing ~$2.10 on-demand.

Sessions 37, 38, and 39 have just been completed (or are in progress). The ultimate
leaderboard now has **24 unique accepted strategies** from ES alone, including 5 ROBUST
and 3 ROBUST_BORDERLINE strategies. Short-side strategies and a cross-dataset portfolio
evaluator have been added. The next major milestone is a full sweep to test everything
together, then CL + NQ instrument expansion.

---

## Sessions Completed This Chat (Sessions 37–39)

### Session 37 — Leaderboard Enrichment + Strategy Subtypes
**Status: COMPLETE**

What was done:
- Added `calmar_ratio`, `is_oos_pf_ratio`, `leader_win_rate`, `leader_trades_per_year`,
  `leader_max_drawdown`, `leader_pct_profitable_years` to master_leaderboard.csv
- Added `ultimate_leaderboard_bootcamp.csv` to download pipeline (accepted-only,
  bootcamp-ranked, generated automatically after every `download_run.py --latest`)
- Implemented 9 strategy subtypes across 3 families:
  - MR: `mean_reversion_vol_dip`, `mean_reversion_mom_exhaustion`,
    `mean_reversion_trend_pullback`
  - Trend: `trend_pullback_continuation`, `trend_momentum_breakout`,
    `trend_slope_recovery`
  - Breakout: `breakout_compression_squeeze`, `breakout_range_expansion`,
    `breakout_higher_low_structure`
- Registered all 9 subtypes in `strategy_factory.py` (originals kept for backward compat)
- Created `cloud/config_es_subtypes_daily_ondemand.yaml` for fast subtype validation
- Added `tests/test_subtypes.py` — 4 tests

Key result: The subtypes immediately found new ROBUST strategies. The leaderboard grew
from 9 to 24 strategies with the first subtype run.

### Session 38 — Cross-Dataset Portfolio Evaluation
**Status: COMPLETE**

What was done:
- Created `modules/cross_dataset_evaluator.py` — runs after all per-dataset evaluations,
  collects ALL accepted strategies across ALL timeframes, normalises to daily PnL,
  computes cross-timeframe N×N correlation matrix and MC drawdowns for all strategies
- Wired into `master_strategy_engine.py` after the dataset loop (try/except wrapped —
  cannot crash the main run)
- Dashboard updated to show `cross_timeframe_correlation_matrix.csv` when available
- New outputs per run:
  - `Outputs/cross_timeframe_correlation_matrix.csv`
  - `Outputs/cross_timeframe_portfolio_review.csv`
  - `Outputs/cross_timeframe_yearly_stats.csv`
- Added `tests/test_cross_dataset_evaluator.py` — 3 tests

Key result: The next full sweep will produce a complete N×N cross-timeframe correlation
matrix for all accepted strategies — the missing data needed for eventual portfolio
selection.

### Session 39 — Dashboard Modernisation + Short-Side Strategies
**Status: IN PROGRESS / JUST COMPLETED**

What was done:
- Dashboard improvements:
  - Results tab shows new columns (calmar_ratio, is_oos_pf_ratio, win_rate,
    trades_per_year, max_drawdown) with proper formatting
  - Cross-timeframe correlation matrix shown first when available
  - Ultimate Leaderboard tab: Classic/Bootcamp toggle, summary stats row
  - Live Monitor: subtypes grouped by parent family for cleaner progress display
- Short-side strategies:
  - Added `direction` field to `EngineConfig` (default "long")
  - Added 15 short-side filter mirrors in `modules/filters.py`:
    - Short MR: AboveFastSMA, DistanceAboveSMA, UpCloseShort, TwoBarUpShort,
      ReversalDownBar, HighVolatilityRegime, StretchAboveLongTermSMA
    - Short Trend: DowntrendDirection, RallyInDowntrend, FailureToHold,
      LowerHigh, DownCloseShort, DowntrendSlope
    - Short Breakout: DownsideBreakout, WeakClose
  - Created `modules/strategy_types/short_strategy_types.py`:
    `ShortMeanReversionStrategyType`, `ShortTrendStrategyType`,
    `ShortBreakoutStrategyType`
  - Registered 3 short types in `strategy_factory.py`
  - Created `cloud/config_es_shorts_daily_ondemand.yaml` for validation
  - Added `tests/test_short_strategies.py` — 4 tests
- Total strategy types registered: **15** (3 original + 9 subtypes + 3 short)

---

## Current Ultimate Leaderboard (24 strategies, ES only)

| Rank | TF | Type | Quality | PF | IS PF | OOS PF | R12m | Trades | Net PnL | Bootcamp |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 30m | MR VolDip | ROBUST | 2.10 | 2.44 | 1.94 | 1.92 | 67 | $179K | 84.5 |
| 2 | 30m | MR (orig) | ROBUST | 1.65 | 1.45 | 1.91 | 5.65 | 111 | $146K | 71.1 |
| 3 | 30m | MR MomExhaust | ROBUST | 2.34 | 1.46 | 2.76 | 6.08 | 100 | $129K | 85.5 |
| 4 | 60m | MR (orig) | ROBUST | 1.34 | 1.36 | 1.31 | 2.16 | 75 | $51K | 42.6 |
| 5 | 60m | MR VolDip | ROBUST | 1.34 | 1.36 | 1.31 | 2.16 | 75 | $51K | 42.6 |
| 6 | 60m | MR MomExhaust | STABLE | 1.42 | 1.09 | 1.86 | 5.53 | 68 | $48K | 56.7 |
| 7 | daily | MR MomExhaust | REGIME_DEP | 1.62 | 0.95 | 1.93 | 2.37 | 223 | $488K | 70.8 |
| 8 | daily | Trend PullbackCont | REGIME_DEP | 1.36 | 0.99 | 1.69 | 2.60 | 468 | $399K | 57.9 |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |
| 17 | daily | MR VolDip | ROBUST_BL | 2.21 | 1.22 | 2.65 | 1.93 | 302 | $1.6M | 83.3 |
| 21 | 30m | MR TrendPullback | ROBUST_BL | 1.71 | 1.19 | 1.96 | 4.23 | 120 | $108K | 68.9 |

Full 24-strategy leaderboard is in `ultimate_leaderboard.csv` and
`ultimate_leaderboard_bootcamp.csv`.

**Key insight from new `is_oos_pf_ratio` column:**
- 30m MR MomExhaust: ratio 1.89 — OOS stronger than IS (extremely rare, very good)
- Daily Trend SlopeRecovery: ratio 2.55 — OOS-heavy, treat with caution
- 30m MR VolDip: ratio 0.80 — balanced (IS slightly stronger, normal and fine)

---

## Cloud Infrastructure

### Architecture
```
Developer (Windows, VS Code + Claude Code CLI)
    ↓ git push
GitHub (robpitman1982-ux/python-master-strategy-creator)
    ↓ git pull
Strategy Console VM (GCP e2-micro, us-central1-c, always-on)
    ↓ python3 run_cloud_sweep.py --config <config> --fire-and-forget
Compute VM (n2-highcpu-96, created on demand, ~38 min, self-deletes)
    ↓ uploads artifacts.tar.gz to GCS bucket
GCS Bucket (gs://strategy-artifacts-robpitman)
    ↓ python3 cloud/download_run.py --latest (run locally on Windows)
Local: strategy_console_storage/runs/<run-id>/artifacts/Outputs/
```

### Canonical Launch Command (from strategy-console SSH — bash only)
```bash
cd /home/robpitman1982/python-master-strategy-creator && git pull && \
python3 run_cloud_sweep.py --config cloud/config_es_all_5tf_ondemand_c.yaml \
--fire-and-forget
```
~38 min, ~$2.10, reliable, on-demand us-central1-c.

### SPOT Alternative (cheaper but zone availability varies)
Check SPOT availability first:
```bash
for zone in us-central1-a us-central1-b us-central1-c us-central1-f; do
  result=$(gcloud compute instances create "spot-probe-$$" --zone=$zone \
    --machine-type=n2-highcpu-96 --provisioning-model=SPOT \
    --no-restart-on-failure --maintenance-policy=TERMINATE \
    --boot-disk-size=10GB --image-family=ubuntu-2404-lts-amd64 \
    --image-project=ubuntu-os-cloud 2>&1)
  if echo "$result" | grep -q "RUNNING\|created"; then
    echo "$zone: SPOT AVAILABLE ✅"
    gcloud compute instances delete "spot-probe-$$" --zone=$zone --quiet
  else
    echo "$zone: $(echo "$result" | grep -oE \
      'STOCKOUT|ZONE_RESOURCE_POOL_EXHAUSTED|quota' | head -1 || echo 'unavailable')"
  fi
done
```
Then launch with SPOT config for available zone:
```bash
python3 run_cloud_sweep.py --config cloud/config_es_all_5tf_spot_a.yaml --fire-and-forget
```

### Monitoring
```bash
gcloud compute instances list --filter="name~strategy-sweep"
gcloud compute ssh strategy-sweep --zone=us-central1-c \
  --command="tail -80 /tmp/strategy_engine_runs/*/logs/engine_run.log"
gcloud storage ls gs://strategy-artifacts-robpitman/runs/
```

### Download Results (local Windows PowerShell)
```powershell
python3 cloud/download_run.py --latest
```

### If Run Shows `unexpected_launcher_failure`
This is a known false alarm — the run usually completed fine. Check the bucket:
```bash
gcloud storage ls gs://strategy-artifacts-robpitman/runs/
```
Then `python3 cloud/download_run.py --latest` to recover.

### GCP Quota Constraint
- Global CPUS_ALL_REGIONS: 100 vCPU hard cap — one n2-highcpu-96 at a time
- Quota upgrade to 200 vCPU submitted but not yet approved
- Single VM is fast enough (~38 min) — not a blocker

---

## Key Output Files (after each run + download)

Located in `strategy_console_storage/runs/<run-id>/artifacts/Outputs/`:

| File | What it shows |
|---|---|
| `master_leaderboard.csv` | All accepted strategies this run, classic-ranked |
| `master_leaderboard_bootcamp.csv` | Same, bootcamp-scored ranked |
| `cross_timeframe_correlation_matrix.csv` | N×N correlation matrix (NEW — Session 38) |
| `cross_timeframe_portfolio_review.csv` | MC drawdowns for all strategies (NEW) |
| `ES_daily/family_leaderboard_results.csv` | Per-dataset per-family results |
| `ES_daily/portfolio_review_table.csv` | MC + stress tests for that dataset |
| `ES_daily/correlation_matrix.csv` | Per-dataset correlation |
| `ES_daily/yearly_stats_breakdown.csv` | Year-by-year PnL |

Cumulative (updated after every download):
| File | Location | What it shows |
|---|---|---|
| `ultimate_leaderboard.csv` | `strategy_console_storage/` | ALL accepted strategies ever, deduped by signature, sorted by quality+PF |
| `ultimate_leaderboard_bootcamp.csv` | `strategy_console_storage/` | Same, filtered to accepted-only, sorted by bootcamp_score |

**Important dedup note for portfolio selection time**: The ultimate leaderboard keeps
the highest PF version of each unique strategy signature. If an older run had inflated
PF through luck and a newer run's lower PF is more realistic, we'd be keeping the wrong
one. At portfolio selection time, cross-check the `run_id` column and verify recent
runs confirm older PF numbers before trusting them.

---

## Current Strategy Type Registry (15 total)

```
Original families (3):
  mean_reversion, trend, breakout

MR subtypes (3):
  mean_reversion_vol_dip, mean_reversion_mom_exhaustion, mean_reversion_trend_pullback

Trend subtypes (3):
  trend_pullback_continuation, trend_momentum_breakout, trend_slope_recovery

Breakout subtypes (3):
  breakout_compression_squeeze, breakout_range_expansion, breakout_higher_low_structure

Short families (3):  ← NEW in Session 39
  short_mean_reversion, short_trend, short_breakout
```

Verify with:
```bash
python -c "from modules.strategy_types import list_strategy_types; print(list_strategy_types())"
```

---

## Session Roadmap (What Comes Next)

| Session | Theme | Status |
|---|---|---|
| 37 | Leaderboard enrichment + subtypes | ✅ DONE |
| 38 | Cross-dataset portfolio evaluation | ✅ DONE |
| 39 | Dashboard + shorts | ✅ DONE (just finished) |
| **40** | **Regime veto layer** | Next |
| 41 | CL + NQ instrument expansion | After 40 |
| Future | Portfolio selection | When leaderboard has 60-100+ strategies |

### Session 40 — Regime Veto Layer
Theme: Block entries in structurally hostile market conditions (ADX-based)

Key deliverables:
- `modules/regime_calculator.py` — vectorised ADX computation, adds boolean columns:
  `is_chop` (ADX < 20), `is_trending` (ADX > 25), `is_high_vol`, `is_low_vol`
- `modules/feature_builder.py` — call `compute_regime_states()` in
  `add_precomputed_features()`
- `modules/strategy_types/base_strategy_type.py` — add `hostile_regimes: list[str]`
- Strategy types: Breakout/Trend → `hostile_regimes = ['is_chop']`
  MR → `hostile_regimes = ['is_trending', 'is_high_vol']`
- `modules/vectorized_signals.py` — apply veto as numpy bitwise AND (zero cost)
- New column in results: `regime_filtered_pct`

Why: 4 of 9 original strategies are REGIME_DEPENDENT. Breakout lost money almost every
year 2010-2018. Regime veto addresses the root cause at zero compute cost.

### Session 41 — CL + NQ Instrument Expansion
Theme: Export CL (crude oil) and NQ (Nasdaq) data from TradeStation, run full sweeps

Key steps:
- Export daily, 60m, 30m, 15m data from TradeStation (see `docs/TRADESTATION_EXPORT_GUIDE.md`)
- Create `cloud/config_cl_all_5tf_ondemand_c.yaml` and `config_nq_all_5tf_ondemand_c.yaml`
- Set correct contract specs:
  - CL: `dollars_per_point: 1000.0`, `tick_value: 10.0`
  - NQ: `dollars_per_point: 20.0`, `tick_value: 5.0`
- Run both sweeps, download results — new strategies added to ultimate leaderboard

### Future — Portfolio Selection (no session number yet)
When the ultimate leaderboard has 60-100+ strategies across ES/CL/NQ (after shorts + 
regime filtering + instrument expansion), bring the full `ultimate_leaderboard.csv` to
Claude.ai for a dedicated portfolio selection discussion:
- Full correlation matrix review
- Select 3-6 uncorrelated strategies for The5ers Bootcamp
- Position sizing ($25K account, 1 MES/MCL/MNQ per strategy)
- Monte Carlo Bootcamp pass rate simulation
- EasyLanguage conversion for TradeStation live trading

---

## How to Write Next Session Task File

After Session 39 finishes, write `SESSION_40_TASKS.md` using the regime veto spec
above. Key implementation details for Session 40:

ADX vectorised computation:
```python
# In regime_calculator.py
def compute_adx_vectorised(high, low, close, lookback=14):
    # Standard Wilder smoothed ATR and DM calculation
    # Returns numpy array of ADX values
```

Hostile regimes applied in `compute_combined_signal_mask()`:
```python
for regime_col in strategy_type.hostile_regimes:
    if regime_col in data.columns:
        signal_mask &= ~data[regime_col].values
```

This is one numpy bitwise AND per regime column — zero meaningful cost added to the sweep.

Acceptance criteria for Session 40:
- [ ] `regime_filtered_pct` in all sweep/refinement CSVs
- [ ] Breakout average max_drawdown reduces by >20% on next run
- [ ] At least 1 REGIME_DEPENDENT strategy improves quality flag
- [ ] ADX computation < 0.5s on 215K bars (30m dataset)
- [ ] All tests pass + 3 new tests in `test_regime_calculator.py`

---

## Important Principles (Unchanged)

- **Collect strategies aggressively** — ultimate leaderboard has no cap, keep growing it
- **Correlation and portfolio selection come later** — after 60-100+ candidates
- **Sweep loose, refine strict, portfolio strictest**
- **1m data permanently excluded** (HFT territory)
- **Claude Code for execution, Claude.ai for planning**
- **Git commits as checkpoints after every step**
- **One command at a time in PowerShell** (`&&` doesn't work — use separate lines)

## PowerShell Note (Windows)
`&&` does NOT work in PowerShell. Run commands separately:
```powershell
cd "C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator"
git pull
claude --dangerously-skip-permissions -p "Read CLAUDE.md..."
```

---

## Key Source Files
- `master_strategy_engine.py` — main orchestrator
- `modules/engine.py` — trade loop, all speed optimisations
- `modules/filters.py` — all 45+ filters (30 long + 15 short) with vectorised mask()
- `modules/vectorized_signals.py` — compute_combined_signal_mask()
- `modules/cross_dataset_evaluator.py` — NEW: cross-TF portfolio evaluation
- `modules/strategy_types/short_strategy_types.py` — NEW: 3 short families
- `modules/strategy_types/mean_reversion_subtypes.py` — 3 MR subtypes
- `modules/strategy_types/trend_subtypes.py` — 3 trend subtypes
- `modules/strategy_types/breakout_subtypes.py` — 3 breakout subtypes
- `cloud/launch_gcp_run.py` — GCP launcher
- `cloud/download_run.py` — download from GCS, regenerate ultimate leaderboards
- `dashboard.py` — Streamlit dashboard (strategy-console port 8501)

## Session Continuity Files
- `CLAUDE.md` — auto-read by Claude Code, master project reference
- `CHANGELOG_DEV.md` — session-by-session log
- `SESSION_HANDOFF_*.md` — cross-session context
- `docs/SESSIONS_38_41_ROADMAP.md` — full roadmap for Sessions 38-41
