# EXTERNAL_LLM_BRIEFING.md

> Single-page project briefing for external LLM consultations (ChatGPT, Gemini).
> Refresh this file at every checkpoint or session-end ritual.
> Paste the whole file into an external chat, then ask the consultation question.
>
> **Last refreshed:** 2026-05-01 (Codex briefing refresh: challenge realism tranche - cost-aware selector MC)
> **Maintained by:** Claude Code on Latitude

---

## 30-second elevator pitch

A **futures + CFD strategy discovery engine** that sweeps filter combinations and parameter ranges across multiple markets and timeframes to find statistically robust algorithmic strategies. Output: ranked leaderboards of accepted strategies plus a portfolio selector that builds prop-firm-ready combinations with realistic Monte Carlo pass rates.

It is **research, not a live trading system**. The output feeds Portfolio EAs deployed manually on a Contabo VPS via The5ers MT5.

---

## Current state (2026-05-01)

### Code state
- Historical futures corpus is preserved locally and in Drive: `Outputs/ultimate_leaderboard.csv` is a 649-row TradeStation futures archive, `Outputs/ultimate_leaderboard_bootcamp.csv` is the 526-row bootcamp-ranked subset, and Drive now keeps an explicit recovery copy at `ultimate_leaderboard_LEGACY_FUTURES_649rows_2026-04-04.csv`
- 12 strategy families: 3 long base (trend, MR, breakout) + 3 short + 9 subtypes
- Vectorized engine: 14-23x speedup, parity-tested at 1e-10 tolerance
- Active research leaderboards are now neutral, not Bootcamp-ranked: generic/futures canonical exports use `family_leaderboard_results.csv` / `master_leaderboard.csv` / `ultimate_leaderboard_FUTURES.csv` plus legacy alias `ultimate_leaderboard.csv`; CFDs use `family_leaderboard_results.csv` / `master_leaderboard_cfd.csv` / `ultimate_leaderboard_cfd.csv`
- Google Drive cold backup now also includes compact recovery exports under `strategy-data-backup/recovery/`, including `ultimate_leaderboard_*_recovery.csv` plus `recovery_manifest.json`; these preserve strategy-defining fields for disaster recovery, but they do **not** replace the repo/code for exact rebuild parity
- Portfolio selector: 3-layer correlation + Expected Conditional Drawdown + block bootstrap MC + regime survival gate
- 4 prop firm programs: Bootcamp $250K, High Stakes $100K, Pro Growth $5K, Hyper Growth $5K
- Post-ultimate gate is now live in the canonical finalize path and emits `*_post_gate_audit.csv` plus `*_gated.csv`; however, the current 88-row CFD pool passed through unchanged because the finalized run did not preserve `strategy_trades.csv` and the pool is too thin for neighbor-based fragility evidence
- Focused tests for the latest naming/mirror work are green; broader suite was 287/287 earlier in the 2026-04-30 session block

### Portfolio selector reality check (code, not aspiration)
- Live selector entrypoint is `modules/portfolio_selector.py::run_portfolio_selection()`
- The selector currently resolves prop-firm behavior from two config fields only: `prop_firm_program` and `prop_firm_target`, which map into `The5ersBootcampConfig`, `The5ersHighStakesConfig`, `The5ersHyperGrowthConfig`, or `The5ersProGrowthConfig`
- Program-specific rule differences that ARE implemented in code: step count, per-step profit targets, total drawdown, daily drawdown / pause behavior, leverage, minimum profitable days, funded-stage rules
- The selector currently runs this pipeline: hard filter -> return matrix -> raw trade list load -> daily correlation -> multi-layer correlation -> correlation dedup -> combinatorial sweep -> regime gate -> portfolio MC -> sizing optimization -> robustness test -> CSV report
- Selector hardening done today: `run_portfolio_selection()` can now explicitly prefer `*_gated.csv` inputs, and live hard-filtering now honors per-program `excluded_markets` from `PropFirmConfig` (The5ers configs now carry `W, NG, US, TY, RTY, HG`)
- New challenge-realism tranche now live: the selector can consume market cost data from `configs/cfd_markets.yaml` during Monte Carlo when rich per-trade artifacts exist. `generate_returns.py` now preserves richer `strategy_trades.csv` fields (`entry_time`, `exit_time`, `direction`, `entry_price`, `exit_price`, `bars_held`) so selector MC can model spread drag, overnight swap accrual, and weekend carry exposure instead of treating all trades as costless PnL vectors
- The selector now emits simple behavior diagnostics into portfolio reports too: max overnight-hold share, max weekend-hold share, and max swap-per-micro-per-night across chosen strategies. This is the first live safeguard against challenge-inappropriate behavior like expensive weekend oil holds slipping through unnoticed
- Important gap: several docs/spec ideas are still ahead of code. The live selector still does **not** currently implement a full explicit `selection_mode` or walk-forward pass/fail consumption inside `run_portfolio_selection()`, and cost-aware MC only activates when run artifacts are rich enough to support it
- Important consequence: CFD challenge recommendations are now less idealized than before, but still not fully complete until rich per-trade artifacts are reliably preserved for finalized runs and challenge-vs-funded scoring is explicit

### In-flight / latest cluster state
- The validated CFD run `2026-04-30_es_nq_validation` is finalized on c240 and mirrored into Drive with full run artifacts
- A later overnight ES full batch was monitored ad hoc across the cluster. `c240` (`ES:15m`), `gen8` (`ES:30m`), and `g9` (`ES:60m` plus a manually launched `ES:daily`) were complete; only `r630` remained active on the heavy `ES:5m` load
- Latest exact `r630` timing checkpoints for ETA baselines:
  - `2026-04-30T21:42:30+00:00`: `breakout` sweep `3294/16473` (20.0%), family ETA `133.7 min`
  - `2026-04-30T22:24:13+00:00`: `breakout` sweep `6588/16473` (40.0%), family ETA `112.7 min`
  - `2026-04-30T22:31:49+00:00`: host still healthy and CPU-saturated with many `master_strategy_engine.py` workers near 97% CPU
- Practical takeaway: compute is healthy, but the batch runner/orchestration layer still needs cleanup to make host-level work allocation less manual and less dependent on ad hoc operator intervention

### Recent additions (Sessions 76-83, this week)
- **BH-FDR family-aware promotion gate** (Benjamini-Hochberg multiple-testing correction over the sweep family) - opt-in via `promotion_gate.bh_fdr_alpha`
- **Deflated Sharpe Ratio** on master leaderboard (Bailey & Lopez de Prado 2014) - penalizes observed SR by trial count from sweep CSV row count
- **Walk-forward validation module** - rolling 3-year-train / 1-year-test windows, mean+min t-stat aggregation, opt-in gate at portfolio selection
- **Random-flip null permutation test** (n=5000) - robust z-statistic against a null that randomizes trade direction

### Live trading state
- Portfolio #3 EA on Contabo VPS: NQ Daily MR + YM Daily Short Trend + GC Daily MR + NQ 15m MR (0.01 lots)
- Portfolio #1 EA also live on the same VPS
- The5ers $5K High Stakes account 26213568
- First confirmed live trade: YM Daily Short Trend, SELL US30
- MT5 Hedge mode working, CFD symbols available

### Infrastructure state
- **Local cluster (4 always-on hosts, no cloud, no shutdowns):**
  - c240 (80 threads, data hub) - `/data/market_data/`, `/data/sweep_results/`, `/data/leaderboards/`
  - gen8 (48 threads, post-CPU-upgrade)
  - r630 (88 threads)
  - g9 (48 threads, 32 GB RAM) - not yet durably onboarded as a standard cluster member
- Total: about 264 threads available once g9 onboarding is formalized
- Latitude (Windows) is the dev machine; Claude Code in VS Code is the primary interface
- X1 Carbon hosts a parallel Claude Remote Control hub from phone
- The conservative MT5/The5ers-first 10-market CFD set (`ES NQ YM RTY DAX N225 FTSE STOXX CAC GC`) was verified present on `c240`, `gen8`, `r630`, and `g9` for `5m`, `15m`, `30m`, `60m`, and `daily`; spot-checked file sizes on c240 looked sane

### Known orchestration / naming bugs
1. `run_cluster_sweep.py` is misleadingly named - it is a single-host sequential batch runner. 3/4 cluster hosts can sit idle during sweeps unless work is manually split. Estimated 24-market sweep on c240 alone: 15-25h vs 4-6h with proper per-host dispatch. **Refactor needed before next big sweep.**
2. The Drive mirror originally overwrote an ambiguous historical `ultimate_leaderboard.csv` with the new canonical CFD-era export. This is now corrected by explicit naming plus a restored archival copy, but future work should continue avoiding ambiguous generic filenames in backups.

---

## Open questions / blockers (priority order)

1. **Per-trade artifacts are not reliably preserved into canonical run storage.** Without rich `strategy_trades.csv`, the new concentration gate cannot do real work and selector MC falls back to weaker return sources that cannot price swap / weekend carry cleanly.
2. **Cost-aware selector MC is now live, but only when rich trade artifacts exist.** This is the right direction, but current finalized CFD runs still underuse it because the artifact coverage is incomplete.
3. **Selector can now prefer gated inputs, but still defaults to raw ultimate unless configured.** This is intentional for now because the current CFD gate output is still evidence-thin.
4. **Walk-forward module exists but is not wired into live selector orchestration.** Threshold tuning is still open, but the first problem is that the current entrypoint does not consume walk-forward pass/fail fields.
5. **Challenge vs funded mode spec exists, but live selector does not yet implement `selection_mode` / recency-weighted challenge scoring.**
6. **Per-firm tradeable universe filtering is now live at hard-filter level, and basic CFD cost realism is partially live in MC.** The5ers market exclusions are enforced; spread/swap modeling exists when trade artifacts are rich enough; explicit challenge-mode scoring still does not.
7. **BH-FDR alpha selection.** Configurable but no operator-pre-registered value. With about 50 combos per sweep family, alpha=0.05 is reasonable but the trade-off vs power is untested.
8. **g9 onboarding to cluster** - repo clone, market_data sync, and `post_sweep.sh` deployment are still pending in the durable cluster sense, even though it was used ad hoc for a manual ES:daily catch-up job.
9. **Throughput refactor on `run_cluster_sweep.py`** - per-host dispatch needs implementation.
10. **Dashboard Live Monitor broken** - engine log + promoted candidates panels do not work during active runs.

---

## Things that should NOT be touched (working as intended, hard-won)

- **Vectorized engine** - 14-23x, parity-tested. Refactor only with parity preservation.
- **3-layer correlation** in portfolio selector - multi-LLM-validated (Session 58).
- **Block bootstrap MC** - preserves crisis clustering vs naive shuffle.
- **Position sizing fixed at initial_capital** - Session 45 critical fix; do NOT re-introduce compounding.
- **Vectorized filter masks** - pandas Series.rolling + numpy broadcast.

---

## Architectural decisions (load-bearing)

| Decision | Session | Why |
|----------|---------|-----|
| Local cluster, not cloud | 65-69 | Cheaper, no SPOT preemption, no SCP timeouts, no quotas |
| Dukascopy ticks for discovery, The5ers ticks for execution | 65 | Dukascopy: deep history. The5ers: real spreads at execution |
| Always-on hard rule for cluster | 73 | Small power savings cost too much ops time |
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
- `MASTER_HANDOVER.md` - current state, open issues, infrastructure
- `LOG.md` - append-only audit trail of every meaningful task
- `CLAUDE.md` - project bible, family inventory, filter inventory, contract specs
- `CHANGELOG_DEV.md` - session-by-session development history
- `docs/PROJECT_REVIEW_2026-04-26.md` - comprehensive 9-phase project review with lessons learned
- `docs/CFD_SWEEP_SETUP.md` - CFD pipeline (Dukascopy to engine format)

---

## How to use this file for a consultation round

1. **Refresh** this file (Claude does it automatically at session-end).
2. **Open** ChatGPT-5 (paid) or Gemini 2.5 Pro (paid) in a fresh chat.
3. **Paste** the whole file as the first message.
4. **Ask** the consultation question - what to prioritize, where blind spots are, alternative approaches.
5. **Capture** the response back into the next session's spec.

**Anti-convergence rule** (from betfair-trader project, validated 8x): when ChatGPT and Gemini converge on the same recommendation, that recommendation drops priority - convergence is anti-alpha in their hit-rate data. Divergence is where the real edges hide. (Note: 8 samples is small; treat as a heuristic, not a law.)

---

## Current consultation question to ask external LLMs

Use this exact question after pasting the briefing:

> We now have a working **post-ultimate gate** and a working but partially incomplete **portfolio selector**. Please review the current architecture and recommend the cleanest path from universal CFD/futures strategy pool -> gated candidate pool -> prop-firm-specific portfolio output.
>
> Current reality in code:
> 1. Post-ultimate gate exists and emits audited + survivor-only outputs, but the current 88-row CFD pool passed through unchanged because the finalized run did not preserve `strategy_trades.csv` and there were no fragility neighbors.
> 2. The portfolio selector already supports program-specific rule simulation via `prop_firm_program` + `prop_firm_target` -> `PropFirmConfig` factories for Bootcamp / High Stakes / Hyper Growth / Pro Growth.
> 3. The live selector now supports per-program `excluded_markets`, can prefer gated leaderboard inputs, and can apply spread/swap costs in MC when rich `strategy_trades.csv` artifacts exist, but it still does **not** clearly implement explicit `selection_mode` or walk-forward results in the main orchestration path.
>
> Design questions:
> - Should portfolio selection switch its default input from raw `ultimate_leaderboard_cfd.csv` to `ultimate_leaderboard_cfd_gated.csv`, or should that remain an explicit mode/flag for now?
> - What is the right implementation order for the remaining selector pieces: reliable rich trade-artifact preservation, walk-forward integration, challenge-vs-funded mode, and richer post-ultimate fragility?
> - Should per-firm tradeability constraints live in `PropFirmConfig`, separate YAML, or a higher-level selector config layer?
> - How should we think about selector architecture so one universal strategy pool can feed multiple prop firms cleanly without duplicating logic?
>
> Constraints:
> - We care about auditability and not losing visibility into what originally qualified.
> - We want universal discovery, but firm-specific portfolio construction.
> - We do not want CFD challenge pass rates that ignore swap/spread reality.
> - We do not want a fragile "one lucky optimum" or "one lucky regime" strategy reaching portfolio selection.
>
> Please recommend the cleanest architecture, the implementation order with the highest leverage, and any failure modes or blind spots you think we are missing.

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
