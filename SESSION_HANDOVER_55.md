# SESSION HANDOVER — For Next Claude Chat
## Date: 2026-04-01
## From: Session 54 (filter improvements, CFD mapping, The5ers setup)
## To: Session 55+ (cloud launcher fix, sweep execution, portfolio selection, EA build)

---

## WHAT THIS PROJECT IS

Rob is building an automated strategy discovery engine (`python-master-strategy-creator`) that sweeps filter combinations across futures markets, runs strategies through a quality pipeline, and selects optimal portfolios for The5ers prop firm challenges. The engine runs on GCP n2-highcpu-96 VMs.

**Repo**: `C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator\`
**GitHub**: `robpitman1982-ux/python-master-strategy-creator`

---

## CRITICAL: THE5ERS IS CFD, NOT FUTURES

Rob discovered during this session that The5ers' main programs (Bootcamp, High Stakes, Pro Growth) trade **CFDs on MT5**, not actual futures contracts. The futures program exists but is separate, on BlackArrow platform (no algo API), with brutal 3% DD limits.

**The decision: Trade CFDs on The5ers MT5 using the existing futures-backtested strategies.**

This works because CFDs track the same underlying instruments — SP500 CFD moves identically to ES futures. The backtested edge transfers directly. Only position sizing (lots vs contracts) differs.

### Rob's Live The5ers Account
- **Program**: $5K High Stakes (2-step, 10% DD, 5% daily DD, 8%+5% targets)
- **Account**: 26213568 on FivePercentOnline-Real (MT5)
- **Fee paid**: $52 (discounted from $98)
- **Status**: Active, Evaluation phase, 0 trades, 0/30 inactive days
- **Min profitable days**: 3
- **Platform**: MetaTrader 5 (installed, connected, live data flowing)

### Verified CFD Symbol Mapping (from MT5 Specifications)
| Futures | CFD Symbol | Contract Size | $/Point/Lot | Commission |
|---------|-----------|--------------|-------------|------------|
| ES | SP500 | 1 | $1/pt | None |
| NQ | NAS100 | 1 | $1/pt | None |
| YM | US30 | 1 | $1/pt | None |
| GC | XAUUSD | 100 | $100/pt | 0.001% |
| SI | XAGUSD | 5,000 | $5,000/pt | 0.001% |
| CL | XTIUSD | 100 | $100/pt | 0.03% |

**NOT available on The5ers**: RTY (Russell 2000), HG (Copper) — excluded from CFD portfolios.

**File**: `modules/cfd_mapping.py` — verified mapping with conversion functions, written to repo.

---

## SESSION 54 STATUS: CODE COMPLETE, SWEEP BLOCKED

### What Was Done (All Verified)

**17 Session 54 commits landed** (filter improvements + exit logic + portfolio fixes):
1. EfficiencyRatioFilter — trend quality (Kaufman proxy)
2. ATRExpansionRatioFilter — volatility transition detection
3. WickRejectionFilter — pin bar / rejection candle detection
4. CumulativeDeclineFilter — total decline measurement for MR
5. ConsecutiveNarrowRangeFilter — multi-bar compression
6. DistanceFromExtremeFilter — stretch from rolling high/low
7. FailedBreakoutExclusionFilter — first exclusion filter
8. Break-even stop modifier — move stop to entry after X ATR profit
9. Time-conditional early exit — cut losers faster
10. Trailing stop expanded to more families
11. Stop distance capped at 1.5 ATR for trend/breakout
12. MR profit target grid lowered for prop firm DD
13. Market concentration caps in portfolio selector (max 2 per market)
14. Drawdown overlap correlation gating in portfolio selector
15. DD constraint added to sizing optimizer
16. Verdict rating fixed for non-Bootcamp programs
17. Hardcoded step3 references replaced with dynamic step count

**Codex fixes also applied**: portfolio_selector.py and refiner.py patched for stable step columns, DD overlap using overlapping active days, capped sizing grid, refiner kwargs compatibility.

**242 tests passing** in 40.86 seconds.

**Filter counts after S54**:
- MR: 18 filters → 31,008 combinations (was 13 → 792)
- Trend: 15 filters → 9,373 combinations (was 12 → 672)
- Breakout: 19 filters → 16,473 combinations (was 15 → 582)
- Total per market-timeframe: ~57,708 combinations across all families

### What's Blocked: Cloud Launcher

The GCP cloud launcher (`cloud/launch_gcp_run.py`) fails with `remote_start_integrity_failed`. The VM creates, bundle uploads, but the remote runner script can't start the engine. This happened on both attempts (first batch of 8, then single ES retry).

**Error sequence from logs**: preflight_passed → prepared → instance_create → ssh_wait → remote_stage → upload → validate_remote → remote_start → remote_start_integrity_failed → vm_preserved_for_inspection

**Root cause**: Unknown — needs SSH into a VM to inspect the actual error. Likely the new S54 code has a dependency or import that fails in the cloud runner environment.

**The VM was deleted** — no billing leak.

---

## IMMEDIATE PRIORITIES (in order)

### Priority 1: Fix Cloud Launcher
The sweep can't run until this is fixed. Steps:
1. Launch a test VM with `--keep-vm` flag
2. SSH in and inspect the remote runner script error
3. Check if it's a Python import error, missing dependency, or path issue
4. Fix and test with a single-market run (ES daily+60m)
5. Once ES works, run all 8 markets sequentially

**Launch command for each market** (run one at a time, wait for completion):
```
cd "C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator"
$env:PYTHONPATH="."
python cloud/launch_gcp_run.py --config cloud/config_s54_test_es.yaml --zone us-central1-c --provisioning-model STANDARD --instance-name s54-es
```
Configs exist for all 8: `cloud/config_s54_test_{es,nq,cl,gc,si,hg,rty,ym}.yaml`
All use 12 workers (set for local), need changing to 94 for cloud.

### Priority 2: Run the Sweep (after launcher fix)
8 markets × 2 timeframes (daily + 60m) × 15 strategy families.
~57,708 combos per market-timeframe pair. ~1-2 hours per market on 96-core.
Use STANDARD (on-demand) VMs in us-central1-c. One VM at a time (100 vCPU quota).

### Priority 3: Portfolio Selection for CFD
After sweep results come back:
1. Refresh ultimate leaderboard
2. Run portfolio selector with:
   - `prop_firm_program: "high_stakes"`
   - `prop_firm_target: 100000` (or 5000 for the current eval)
   - Filter to CFD-available markets only (ES, NQ, YM, GC, SI, CL — exclude RTY, HG)
3. Generate CFD execution guide using `cfd_mapping.py`

### Priority 4: Finish Session 54B Tasks
- Task 2: Add CFD prop firm config aliases to portfolio_selector.py
- Task 3: Add CFD execution guide CSV output to portfolio selector report
- Task 4: Add `execution_mode: "cfd"` to config.yaml
(Task 1 done — cfd_mapping.py written. Task 5 done — MT5 specs verified by Rob.)

### Priority 5: Build MT5 EA
Translate portfolio selector output into an MQL5 Expert Advisor that:
- Reads signals from Python engine (file-based or socket)
- Places orders with visible SL/TP on The5ers MT5
- Manages positions per strategy rules (hold_bars, break-even, trailing)
- Respects The5ers EA rules (no HFT, no latency arb, visible stop losses)

---

## KEY FILES

| File | Purpose |
|------|---------|
| `modules/filters.py` | All filters including 7 new S54 filters |
| `modules/engine.py` | Backtest engine with break-even stop + early exit |
| `modules/portfolio_selector.py` | 6-stage pipeline with DD overlap + market caps |
| `modules/prop_firm_simulator.py` | PropFirmConfig factories for all programs |
| `modules/cfd_mapping.py` | **NEW** — verified CFD instrument mapping |
| `modules/strategy_types/` | All 15 strategy families |
| `cloud/config_s54_test_*.yaml` | Per-market cloud/local configs (8 files) |
| `cloud/launch_gcp_run.py` | GCP launcher (BROKEN — needs fix) |
| `config.yaml` | Main config |
| `SESSION_54_TASKS.md` | Completed task file (17 tasks) |
| `SESSION_54_PRE_REVIEW.md` | Pre-execution review (10 issues caught) |
| `SESSION_54B_TASKS.md` | CFD pivot tasks (partially done) |
| `CLAUDE.md` | Engine orientation for Claude Code |
| `CHANGELOG_DEV.md` | Session-by-session dev log |

---

## CLOUD INFRASTRUCTURE

- **Compute**: GCP n2-highcpu-96 on-demand VMs (100 vCPU quota, one VM at a time)
- **Zone**: us-central1-c (on-demand) or us-central1-f (SPOT)
- **Strategy console**: e2-micro in us-central1-c (IP: 35.232.131.181)
- **GCS bucket**: strategy-artifacts-robpitman
- **SSH**: Use robpitman1982 user

---

## THE5ERS PROGRAM RULES (for simulator config)

### CFD Programs (MT5/cTrader)
| Program | Account | Steps | Max DD | Daily DD | Target |
|---------|---------|-------|--------|----------|--------|
| High Stakes $5K | $5,000 | 2 | 10% | 5% | 8%+5% |
| High Stakes $100K | $100,000 | 2 | 10% | 5% | 8%+5% |
| Bootcamp $250K | $250,000 | 3 | 5% | None | 6%×3 |
| Pro Growth $20K | $20,000 | 1 | 6% | 3% | 10% |

### Futures Program (BlackArrow — NOT for algo trading yet)
| Program | Max DD | Daily DD | Target | Consistency |
|---------|--------|----------|--------|-------------|
| Basecamp $25K | 3% | 3% EOD | 6% | 30% rule |

---

## WORKFLOW PATTERN

- **Planning**: Claude.ai (this chat) for architecture and session design
- **Execution**: Claude Code (`claude --dangerously-skip-permissions`) or Codex for unattended work
- **Session files**: `SESSION_XX_TASKS.md` committed to repo
- **Handover**: `SESSION_HANDOVER_XX.md` for context transfer between chats
- **Orientation**: Claude Code reads `CLAUDE.md` and `CHANGELOG_DEV.md` before executing

## KEY PRINCIPLES

- No patches — full fixes only
- One commit per task step
- Upfront review before Claude Code sessions prevents costly mistakes
- Decisions grounded in actual data
- `ultimate_leaderboard_bootcamp.csv` is the authoritative source for portfolio construction
- Futures engine stays untouched — CFD is an overlay, not a replacement
- When Rob eventually trades own futures account, engine already produces futures-native output
