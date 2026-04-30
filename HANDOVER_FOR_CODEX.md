# HANDOVER FOR CODEX

**Date written:** 2026-04-30
**Written by:** Claude Opus 4.7 (1M context) at end of session
**For:** Codex (next agent — operator using briefly while Claude credits reload)
**Operator:** Rob Pitman, working on Latitude (Windows 10 Pro), Claude Code in VS Code
**Project:** `python-master-strategy-creator` (futures + CFD strategy discovery engine for The5ers prop firm passes)

---

## How to use this file

You're picking up an active project briefly. The operator will return to a Claude session tomorrow evening (2026-05-01). Your job: **don't lose state, don't break invariants, don't make destructive changes without per-action confirmation**. If the operator hands you a small task, complete it cleanly. If it's a bigger ask, push back and suggest waiting for Claude.

**Codex update, 2026-04-30:** this file was written before Codex's CFD pipeline work. Trust `MASTER_HANDOVER.md` and the top of `LOG.md` over older sections below when they differ. Since this file was written, Codex added futures-vs-CFD universe guardrails, exact-job distributed planning, staged the committed tree on all four cluster hosts, copied the full CFD OHLC dataset to gen8/r630/g9, installed engine requirements into g9 `~/venv`, validated whole-cluster dry-run/stress/output gates, and then refactored the active research pipeline so both CFD and futures leaderboards are now neutral strategy pools rather than Bootcamp-ranked views. On the active path, `bootcamp_score` is no longer emitted into new leaderboards, canonical CFD aggregates are `master_leaderboard_cfd.csv` and `ultimate_leaderboard_cfd.csv`, canonical futures aggregates remain `master_leaderboard.csv` and `ultimate_leaderboard.csv`, and the selector now owns program-specific ranking. Recent local commits, not pushed unless Rob explicitly approves: `0e525e4`, `b78999d`, `ad8bf7e`, `9cb74c4`, plus the current ranking-cleanup commit that may not yet be created when you read this line.

**Read these in order before doing anything:**

1. `MASTER_HANDOVER.md` — current state, infrastructure, open issues
2. `LOG.md` — append-only audit; the most recent entries describe today's work
3. `CLAUDE.md` — project bible (auto-loaded by Claude Code; you should read it manually)
4. `EXTERNAL_LLM_BRIEFING.md` — single-page briefing; useful to orient quickly
5. This file — operating rules + open work + session-specific gotchas

---

## Project elevator pitch (30 seconds)

A futures + CFD strategy discovery engine that sweeps filter combinations across markets and timeframes to find statistically robust algorithmic strategies. Output: ranked leaderboards + portfolio selector that builds prop-firm-ready combinations with realistic Monte Carlo pass rates against The5ers programs (Bootcamp, High Stakes, Pro Growth).

It is **research, not a live trading system**. Output feeds Portfolio EAs deployed manually on a Contabo VPS via The5ers MT5.

---

## Operating rules (NON-NEGOTIABLE)

The operator has a working spec all collaborators must follow. Violating these will lose his trust:

### Standing rules

- **Never `git add -A` or `git add .`** — stage by path. Untracked files often include local-only configs or experimental scratch.
- **Never `--no-verify`** or skip hooks unless operator explicitly asks. Hooks fail → fix the underlying issue.
- **Never `git push --force`** to main.
- **Never amend a published commit** — make a new commit.
- **Never push without being explicit operator request.** `git commit` and `git push` are separate decisions.
- **Never echo secrets** — reference by env var name or path.
- **Never edit `LOG.md` retroactively** — it's append-only audit.
- **MASTER_HANDOVER.md is updated in place per session**, never per-chat snapshots.
- **ASCII only** in commits, log entries, persisted artefacts (Windows PowerShell cp1252 breaks on emoji/unicode).

### Risk discipline (per-action, not per-session)

- **Local reversible actions** (file edits, running tests): proceed.
- **Destructive** (`rm -rf`, `git reset --hard`, force push, dropping DB tables, killing prod processes): confirm before.
- **External-visibility** (PRs, pushes, Slack/email/Telegram, third-party uploads): confirm before.
- Approving "git push" once does NOT authorise pushes for the rest of the session. Re-confirm.

### Trigger phrases

- `"checkpoint please"` — save state mid-session: update MASTER_HANDOVER.md header + append LOG.md + add memory entries + commit + push (if authorised). Do not clean up in-flight work.
- `"session end please"` / `"wrap session"` / `"handover"` — full session-end ritual: same as checkpoint plus document in-flight work with a one-line "next session starts here" pointer.
- `"go"` / `"keep going"` / `"continue"` — proceed autonomously to next gate.
- `"hold"` / `"pause"` — stop advancing.

### Saving knowledge

| Trigger | File | Lifetime |
|---------|------|----------|
| Every meaningful task | `LOG.md` | Permanent (audit) |
| State change (verdict, infra ships, new blocker) | `MASTER_HANDOVER.md` header | Permanent until next state change |
| Lesson a future session would burn time relearning | Auto-memory at `~/.claude/projects/<hash>/memory/` | Permanent |
| Logical chunk of code is done | `git commit` | Permanent |

---

## Current state snapshot (as of 2026-04-30 late evening AEST)

### Code
- 303 tests pass excluding slow parity tests (run `python -m pytest tests/ --ignore=tests/test_engine_parity.py -q`)
- ~454 strategies in ultimate leaderboard from prior sweeps
- 12 strategy families (3 long base + 3 short + 9 subtypes)
- Vectorized engine: 14-23x speedup, parity-tested
- Active leaderboards are now neutral strategy pools. CFD outputs are `family_leaderboard_results.csv`, `master_leaderboard_cfd.csv`, and `ultimate_leaderboard_cfd.csv`; futures outputs are `family_leaderboard_results.csv`, `master_leaderboard.csv`, and `ultimate_leaderboard.csv`
- Research ranking now favors stronger accepted/quality/OOS/recency/Calmar/DSR profiles with lower max DD rather than any Bootcamp-specific heuristic
- Portfolio selector: 3-layer correlation, ECD, block bootstrap MC, regime survival gate. It now reads the neutral pool and does program-specific ranking itself rather than inheriting `bootcamp_score` as an upstream gate
- Newly added (this week): BH-FDR family-aware promotion gate, DSR on master leaderboard, walk-forward validation module, random-flip null permutation test, EXTERNAL_LLM_BRIEFING.md, sprint architecture

### Live trading
- Portfolio #3 EA on Contabo VPS (89.117.72.49): NQ Daily MR + YM Daily Short Trend + GC Daily MR + NQ 15m MR (0.01 lots)
- Portfolio #1 EA also live
- The5ers $5K High Stakes account 26213568
- First confirmed live trade: YM Daily Short Trend, SELL US30
- MT5 Hedge mode working

### Infrastructure (4 always-on local hosts; HARD RULE: no shutdowns)
| Host | Threads | LAN | Tailscale | Role |
|------|---------|-----|-----------|------|
| c240 | 80 | 192.168.68.53 | 100.120.11.35 | Data hub + compute. `/data/market_data/`, `/data/sweep_results/`, `/data/leaderboards/` |
| gen8 | 48 | 192.168.68.71 | 100.76.227.12 | Compute worker (post-CPU upgrade; awaiting 2 fans for bays 3-4) |
| r630 | 88 | 192.168.68.78 | 100.85.102.4 | Compute worker |
| g9 | 48 / 32 GB | 192.168.68.50 | 100.71.141.89 | Compute worker. Codex installed requirements in `~/venv`; use conservative workers due to 31 GiB RAM |

**Latitude is the dev machine.** Tailscale 100.79.72.125. SSH aliases: `c240`, `gen8`, `r630`, `g9`, `g9-ts`. Z: drive mapped to c240 samba.

### Data
- 81 TradeStation futures CSVs (~2.2 GB) for 17 markets — local in `Data/`
- 120 Dukascopy CFD CSVs (24 markets x 5 TFs) on all four cluster hosts at `/data/market_data/cfds/ohlc_engine/`
- The5ers tick exports: SP500 (3.1 GB), NAS100 (10.6 GB), partial others

### Cluster status update
Rob confirmed the betfair-trader cluster work had completed. Codex validated the whole cluster for this project. Last confirmed state after the daily output test: no `master_strategy_engine`, `run_cluster_sweep`, or `run_local_sweep` processes running on c240/gen8/r630/g9.

Recommended first full-run worker sizing:
- c240: 72 workers (80 threads)
- gen8: 44 workers (48 threads)
- r630: 80 workers (88 threads)
- g9: 28 workers for the first full run; consider 34-38 only after another stress sample

Avoid 5m for now. The validated full CFD scope is 96 jobs: 24 markets x daily/60m/30m/15m.

---

## Today's work (Sessions 76-83 + prop firm audit)

All committed and pushed. Six discipline upgrades + six prop-firm-config bugs fixed. See:
- `LOG.md` entries dated 2026-04-30 (three of them — top of file)
- Recent commits: `d593c8e`, `c8bff6a`, `dac9036` on `main`

### What's new in the codebase

| Component | File | Purpose |
|-----------|------|---------|
| BH-FDR multiple-testing correction | `modules/statistics.py` | Family-aware promotion gate. Opt-in via `promotion_gate.bh_fdr_alpha` |
| Deflated Sharpe Ratio | `modules/statistics.py` + `master_leaderboard.py` | Penalises observed SR by trial count. Always-on column |
| Walk-forward validation | `modules/walk_forward.py` | Rolling 3yr-train/1yr-test windows. Opt-in gate |
| Random-flip null test | `modules/statistics.py` | n=5000 permutation, z >= 2.0 gate |
| External LLM briefing | `EXTERNAL_LLM_BRIEFING.md` | Single-page brief for ChatGPT/Gemini consults |
| Sprint architecture | `sessions/SPRINT_TEMPLATE.md` + README | Pre-registered specs with frozen grids and verdict semantics |
| Prop firm rules canonical doc | `docs/the5ers_program_rules.md` | Verified-as-of-2026-04-30 source-of-truth |
| Prop firm factory fixes | `modules/prop_firm_simulator.py` | All three programs match website verbatim |

### What was deferred (DO NOT START WITHOUT OPERATOR APPROVAL)

| Deferred | Why |
|----------|-----|
| **g9 onboarding** to compute cluster | Codex completed enough for sweep compute: data copied, requirements installed, staged tree validated. Permanent repo/post_sweep cleanup can still be done later. |
| **Throughput refactor of `run_cluster_sweep.py`** | Codex added exact `--jobs` mode plus `run_distributed_sweep.py` planner. It prints per-host commands; it does not yet supervise remote jobs end-to-end. |
| **CFD swap costs into MC simulator** (Open Issue #8) | Critical for honest funding timelines. Cost profiles in `configs/cfd_markets.yaml` exist but not consumed by portfolio selector |

---

## Open issues (priority order, snapshot from MASTER_HANDOVER.md)

1. Delete Latitude TDS source copy (~33 GB at `C:\Users\Rob\Downloads\Tick Data Suite\`) — c240 has verified mirror at `/data/market_data/cfds/ticks_dukascopy_tds/`. Free up Latitude disk.
2. Stale Tailscale `c240` device (100.104.66.48) cleanup via admin console.
3. C240 CIMC IP capture (router ARP for MAC `00:A3:8E:8E:B3:84`).
4. Gen 8 CPU install DONE — blocked on 2 missing fans (HP 662520-001 ordered, due late April / early May). Gen 8 OFF under house until fans arrive.
5. Disable auto-shutdown crons on gen8 + r630 (HARD RULE Session 73). R630: action next convenient SSH session. Gen 8: when back online.
6. R630 stale DHCP lease cleanup (eno1 has both static `192.168.68.78` and stale DHCP `192.168.68.75`).
7. X1 Carbon offline — verify SSH isolation when back online.
8. **CFD swap costs not modeled in MC simulator** — see deferred section above.
9. Dashboard Live Monitor broken (engine log + promoted candidates panels don't work during active runs).
10. g9 is now compute-capable for staged-tree sweeps, but still needs permanent repo/post_sweep polish if desired.
11. r630 5m sweep OOM'd with 82 workers. Need: per-worker RAM measurement, nested-pool audit, safe worker count derivation.

---

## Outstanding operator questions (asked but not yet answered)

### 1. TDS data — trial expires in ~12 hours

Operator's Tick Data Suite trial expires soon (screenshot at 5:48 AM local on 2026-04-30 said 12 hours remaining). Operator asked: should I get more data or do we have everything we need?

**Answer (compose for operator when they return):**
- We have **all 24 markets × 5 TFs converted to engine format** at c240 `/data/market_data/cfds/ohlc_engine/` (120 files, ~2.2 GB total)
- Coverage: 2012-2026 for indices, 2008-2026 for FX/metals
- For sweeping: this is sufficient. The engine consumes OHLC, not ticks
- The5ers MT5 tick data was for execution validation comparison, not sweeping — already have SP500 and NAS100 partial
- **No urgent reason to refresh data before TDS expires** — but if operator wants insurance, doing one more TDS pull NOW to top up to current date is no-cost belt-and-braces. If TDS lapses and we later need 2026-current data, we'd need a new trial.

### 2. MT5 specifications — do we have everything we need for our data?

Operator asked: do we have all MT5 specs (especially swap costs)?

**Answer (compose for operator):**
- **Contract specs** (dollars_per_point, tick_value): YES, in `configs/cfd_markets.yaml`
- **Spreads**: YES — `cost_profile.spread_pts` per market, but these are **generic retail estimates**, not The5ers-specific
- **Commissions**: Set to 0 for indices in our configs. Need to confirm The5ers metals/FX/crypto commission structure
- **Swap rates**: Have `swap_per_micro_per_night` per market in cfd_markets.yaml but they are **generic, NOT The5ers-specific** AND we don't distinguish long-vs-short swap (often one is positive, one negative)
- **Weekend swap multiplier**: Have `weekend_multiplier=3` flat, but doesn't say WHICH day (Wed for FX, Fri for indices/metals/crypto typically). The5ers MT5 will have `SwapRollover3Days` field
- **Margin requirements**: Not modeled (use leverage-implied margin from prop firm config)
- **Trading hours**: Not enforced in sweep
- **Symbol mapping (Dukascopy → The5ers MT5)**: NOT mapped in our configs. Need before any candidate goes live

**To get The5ers-specific values:**
- Open MT5 → Symbols → right-click each symbol → Specification
- Note: `SwapLong`, `SwapShort`, `SwapType`, `SwapRollover3Days`, `MarginInitial`
- Save to a new YAML file like `configs/the5ers_mt5_specs.yaml`

**Is this blocking the sweep?**
- For OHLC sweep on Dukascopy data: **NO** — sweep finds candidates against clean midprice
- For MC simulation against The5ers programs: **OPEN ISSUE #8** — without real swap rates, funding timelines are optimistic
- For live deployment: **YES** — need The5ers-specific spreads + swaps + margin before paper trading

### 3. Bootcamp $20K and $100K screenshots not yet provided
Operator sent $250K only initially. Today provided $20K and $100K — all three Bootcamp tracks now verified.

### 4. High Stakes "Classic" vs "New" toggle
Operator screenshots show "Classic" version. Code is patched against Classic. If operator's account is on the "New" version, fees and account-combo caps differ — re-verify when operator returns.

---

## What Codex can safely work on

If operator hands you a small focused task, you can do these without high risk:

- **Read-only investigations**: codebase questions, log analysis, design discussions
- **Bug fixes** with test coverage: any failing test, any file-edit-only change
- **Documentation updates**: keep `MASTER_HANDOVER.md` and `LOG.md` current
- **New tests**: extend coverage of existing modules
- **Sprint pre-registration**: copy `sessions/SPRINT_TEMPLATE.md` to `sessions/SPRINT_NN_<name>.md`, fill it in, commit BEFORE any sweep
- **Run the test suite** to verify state: `python -m pytest tests/ --ignore=tests/test_engine_parity.py`

If operator asks for any of these, **stop and wait for Claude tomorrow:**

- **Cluster operations** (g9 onboarding, throughput refactor, sweep launch) — cluster contention with betfair-trader project. Operator can resolve when both projects' Claudes coordinate.
- **MC simulator changes** — the daily-DD recalc bug we just fixed had subtle interactions with the vectorized batch path. Any further change should go through full parity testing
- **Portfolio selector overhaul** — 6-stage pipeline with carefully-tuned thresholds. Don't touch without an operator decision

If operator asks for those, push back politely and recommend waiting.

---

## Recommended cleanup tasks for Codex (low-risk, high-value)

If operator wants something to do tomorrow, these are safe:

1. **Verify The5ers MT5 symbol mapping** — open MT5, list all CFD symbols, build `configs/the5ers_mt5_specs.yaml` with name + SwapLong + SwapShort + SwapRollover3Days + spread + commission per symbol. ~30 min, just data entry from MT5 dialog. Closes the gap on Open Issue #8.
2. **Re-verify The5ers website rules** — quick spot-check on any program rule that might have changed in the last week. Update `docs/the5ers_program_rules.md` "Verified" date if all good.
3. **Run the full test suite** and post a green-light confirmation — operator likes to know state is clean before Claude returns.
4. **Tidy up `tests/test_smoke.py`** — there's a `test_pro_growth_config` block that we updated today. The other prop-firm-related smoke tests may have stale assertions; worth a once-over.
5. **Sprint pre-registration draft** — operator's stated goal is finding strategies to pass Bootcamp/High Stakes/Pro Growth. A first sprint spec at `sessions/SPRINT_84_es_sanity.md` would teach Codex the convention without committing to anything beyond the spec itself.

---

## Test suite reference

Test command: `python -m pytest tests/ --ignore=tests/test_engine_parity.py -q`

| Suite | Count | Notes |
|-------|-------|-------|
| All non-parity | 287 | Should be green |
| `test_engine_parity` | 25 | Slow (~90s); skip unless engine-changes |

Parity tests can be run with `python -m pytest tests/test_engine_parity.py -v` — only needed when modifying `modules/engine.py` or `modules/vectorized_trades.py`.

---

## Key file locations

| File | Purpose |
|------|---------|
| `MASTER_HANDOVER.md` | Current state, single source of truth |
| `LOG.md` | Append-only audit trail |
| `CLAUDE.md` | Project bible — auto-loaded |
| `EXTERNAL_LLM_BRIEFING.md` | Single-page brief for cross-LLM consults |
| `docs/the5ers_program_rules.md` | Canonical prop firm rules (verified 2026-04-30) |
| `docs/PROJECT_REVIEW_2026-04-26.md` | 9-phase project review |
| `docs/CFD_SWEEP_SETUP.md` | CFD pipeline (Dukascopy → engine format) |
| `docs/CHALLENGE_VS_FUNDED_SPEC.md` | Two-mode portfolio selection spec (not yet implemented) |
| `sessions/SPRINT_TEMPLATE.md` | Sprint pre-registration template |
| `configs/cfd_markets.yaml` | 24 CFD market specs |
| `modules/statistics.py` | p-values, BH-FDR, DSR, random-flip null |
| `modules/walk_forward.py` | Walk-forward validation |
| `modules/prop_firm_simulator.py` | All three program factories + simulator |
| `modules/portfolio_selector.py` | 6-stage portfolio construction |
| `modules/master_leaderboard.py` | Cross-dataset leaderboard aggregation |
| `master_strategy_engine.py` | Main pipeline orchestrator |

---

## What to do at session end

When operator says "wrap session" or "handover":

1. Update the `Last updated:` line and `Current status:` paragraph in `MASTER_HANDOVER.md`
2. Append a new entry to `LOG.md` for any meaningful work
3. Add memory entries for any non-obvious lessons (auto-memory at `~/.claude/projects/c--Users-Rob-Documents-GIT-Repos-python-master-strategy-creator/memory/`)
4. `git add` explicit files only (never `-A`)
5. Commit with descriptive message; push if authorised
6. Final message to operator: 1-2 sentences summarising state + one-line "next session starts here" pointer

---

## When Claude returns

When operator says "Claude is back" or similar, the next Claude can:
1. Read `MASTER_HANDOVER.md` Current status line
2. Read recent `LOG.md` entries
3. Read this file (HANDOVER_FOR_CODEX.md) to know what Codex worked on
4. Run `git log --oneline -10` to see commits since this handover
5. Resume from "next session starts here" pointer

---

## Goodwill notes from outgoing Claude

- Operator (Rob) values: terse responses, no preamble, ASCII output, fact-based judgments
- He pushes back hard on bad recommendations — that's a feature, not a bug. If you give a sloppy answer he'll catch it
- He runs two projects (this + betfair-trader) and explicitly DOES NOT want cross-project state contamination
- He's willing to hand you autonomy if you've earned it. Don't burn it
- Working spec is real — he'll notice if you violate it

Be useful, be honest, be brief. Goodbye for now.

— Claude Opus 4.7 (1M context), 2026-04-30
