# EXTERNAL_LLM_BRIEFING.md

> Single-page project briefing for external LLM consultations (ChatGPT, Gemini).
> Refresh this file at every checkpoint or session-end ritual.
> Paste the whole file into an external chat, then ask the consultation question.
>
> **Last refreshed:** 2026-04-30 (Session 79-83)
> **Maintained by:** Claude Code on Latitude

---

## 30-second elevator pitch

A **futures + CFD strategy discovery engine** that sweeps filter combinations and parameter ranges across multiple markets and timeframes to find statistically robust algorithmic strategies. Output: ranked leaderboards of accepted strategies + a portfolio selector that builds prop-firm-ready combinations with realistic Monte Carlo pass rates.

It is **research, not a live trading system**. The output feeds Portfolio EAs deployed manually on a Contabo VPS via The5ers MT5.

---

## Current state (2026-04-30)

### Code state
- ~454 strategies in ultimate leaderboard (414 bootcamp-accepted) across 8 markets (ES, CL, NQ, SI, HG, RTY, YM, GC)
- 12 strategy families: 3 long base (trend, MR, breakout) + 3 short + 9 subtypes
- Vectorized engine: 14-23x speedup, parity-tested at 1e-10 tolerance
- Portfolio selector: 3-layer correlation + Expected Conditional Drawdown + block bootstrap MC + regime survival gate
- 4 prop firm programs: Bootcamp $250K, High Stakes $100K, Pro Growth $5K, Hyper Growth $5K
- Test suite: 257+ tests passing across smoke, subtypes, parity, portfolio, prop firm, MC

### Recent additions (Sessions 76-83, this week)
- **BH-FDR family-aware promotion gate** (Benjamini-Hochberg multiple-testing correction over the sweep family) — opt-in via `promotion_gate.bh_fdr_alpha`
- **Deflated Sharpe Ratio** on master leaderboard (Bailey & Lopez de Prado 2014) — penalises observed SR by trial count from sweep CSV row count
- **Walk-forward validation module** — rolling 3-year-train / 1-year-test windows, mean+min t-stat aggregation, opt-in gate at portfolio selection
- **Random-flip null permutation test** (n=5000) — robust z-statistic against a null that randomises trade direction

### Live trading state
- Portfolio #3 EA on Contabo VPS: NQ Daily MR + YM Daily Short Trend + GC Daily MR + NQ 15m MR (0.01 lots)
- Portfolio #1 EA also live on the same VPS
- The5ers $5K High Stakes account 26213568
- First confirmed live trade: YM Daily Short Trend, SELL US30
- MT5 Hedge mode working, CFD symbols available

### Infrastructure state
- **Local cluster (4 always-on hosts, no cloud, no shutdowns):**
  - c240 (80 threads, data hub) — `/data/market_data/`, `/data/sweep_results/`, `/data/leaderboards/`
  - gen8 (48 threads, post-CPU-upgrade)
  - r630 (88 threads)
  - g9 (48 threads, 32 GB RAM) — **NOT yet onboarded** as cluster member
- Total: ~264 threads available once g9 onboarded
- Latitude (Windows) is the dev machine; Claude Code in VS Code is the primary interface
- X1 Carbon hosts a parallel Claude Remote Control hub from phone

### Known throughput bug (uncovered Session 76)
`run_cluster_sweep.py` is misleadingly named — it's a single-host sequential batch runner. 3/4 cluster hosts sit idle during sweeps. Estimated 24-market sweep on c240 alone: 15-25h vs 4-6h with proper per-host dispatch. **Refactor needed before next big sweep.**

---

## Open questions / blockers (priority order)

1. **CFD swap costs not modeled in MC simulator.** Cost profiles defined in `configs/cfd_markets.yaml` but not yet consumed by portfolio selector. Critical for trustworthy funding timelines for The5ers programs.
2. **Walk-forward gate threshold tuning.** Module is built; default thresholds (mean_test_t≥1.0, min_test_t≥-0.5) are reasonable but not empirically calibrated against real strategy results. May filter too strict or too loose.
3. **BH-FDR alpha selection.** Configurable but no operator-pre-registered value. With ~50 combos per sweep family, alpha=0.05 is reasonable but trade-off vs power is untested.
4. **g9 onboarding to cluster** — repo clone, market_data sync, post_sweep.sh deployment pending.
5. **Throughput refactor on `run_cluster_sweep.py`** — per-host dispatch needs implementation.
6. **Dashboard Live Monitor broken** — engine log + promoted candidates panels don't work during active runs.
7. **Per-trade DSR** — DSR uses leader's PF and trade count. Could become more accurate if it consumed per-trade PnL with skew/kurtosis from `strategy_trades.csv`.

---

## Things that should NOT be touched (working as intended, hard-won)

- **Vectorized engine** — 14-23x, parity-tested. Refactor only with parity preservation.
- **3-layer correlation** in portfolio selector — multi-LLM-validated (Session 58).
- **Block bootstrap MC** — preserves crisis clustering vs naive shuffle.
- **Position sizing fixed at initial_capital** — Session 45 critical fix; do NOT re-introduce compounding.
- **Vectorized filter masks** — pandas Series.rolling + numpy broadcast.

---

## Architectural decisions (load-bearing)

| Decision | Session | Why |
|----------|---------|-----|
| Local cluster, not cloud | 65-69 | Cheaper, no SPOT preemption, no SCP timeouts, no quotas |
| Dukascopy ticks for discovery, The5ers ticks for execution | 65 | Dukascopy: deep history. The5ers: real spreads at execution |
| Always-on hard rule for cluster | 73 | $5/mo savings cost too much ops time |
| Hermes/OpenClaw retired | 75 | Agent-driven ops added security surface for marginal gain over Claude Code |
| MASTER_HANDOVER.md not HANDOVER.md | 75 | Project-scoped naming prevents collision |

---

## Project rules (operator's standing instructions to Claude)

- Never `git add -A`. Stage by path.
- Never push without being asked.
- Never amend a published commit.
- ASCII-only output (Windows PowerShell breaks on emoji).
- MASTER_HANDOVER.md updated in place per session.
- LOG.md is append-only audit.
- Risk discipline: per-action confirmation for destructive/external-visibility actions.
- One project, one Claude, one CLAUDE.md. Cross-project reads only via this briefing file.

---

## Layered context (read deeper as needed)

For more detail beyond this brief:
- `MASTER_HANDOVER.md` — current state, open issues, infrastructure
- `LOG.md` — append-only audit trail of every meaningful task
- `CLAUDE.md` — project bible, family inventory, filter inventory, contract specs
- `CHANGELOG_DEV.md` — session-by-session development history (Sessions 0-75)
- `docs/PROJECT_REVIEW_2026-04-26.md` — comprehensive 9-phase project review with lessons-learned
- `docs/CFD_SWEEP_SETUP.md` — CFD pipeline (Dukascopy → engine format)

---

## How to use this file for a consultation round

1. **Refresh** this file (Claude does it automatically at session-end).
2. **Open** ChatGPT-5 (paid) or Gemini 2.5 Pro (paid) in a fresh chat.
3. **Paste** the whole file as the first message.
4. **Ask** the consultation question — what to prioritise, where blind spots are, alternative approaches.
5. **Capture** the response back into the next session's spec.

**Anti-convergence rule** (from betfair-trader project, validated 8x): when ChatGPT and Gemini converge on the same recommendation, that recommendation drops priority — convergence is anti-alpha in their hit-rate data. Divergence is where the real edges hide. (Note: 8 samples is small; treat as a heuristic, not a law.)

---

## Cross-project notes (betfair-trader)

This project has a sibling: `betfair-trader` (pre-match Betfair Exchange trading bot). The two projects share:
- Local compute cluster (c240, gen8, r630, g9)
- Operator (Rob, Latitude + X1 Carbon)
- Claude Code as primary dev interface
- MASTER_HANDOVER + LOG + memory persistence pattern

They diverge on:
- Domain (futures/CFDs vs Betfair markets)
- Sprint architecture (this project: monolithic sweeps; betfair: 4-15 probes per sprint with frozen pre-registration)
- Live execution (this: Contabo VPS + MT5; betfair: Lightsail Dublin)
- Risk gate severity (this: 6-element promotion gate; betfair: stricter Gate-J + DSR + walk-forward + random-flip + per-segment positivity)

When consulting externally, mention which project the question pertains to.
