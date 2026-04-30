# Project Review — python-master-strategy-creator

**Date:** 2026-04-26
**Author:** Claude Opus 4.7 (1M context), at Rob's direction
**Purpose:** Comprehensive snapshot at the transition from Claude Desktop + Desktop Commander → Claude Code in VS Code on Latitude. Also intended for cross-reading by the betfair-trader project's Claude so it can build a parallel ops doc and identify operational improvements applicable to that project.

---

## 1. What This Project Is

A futures + CFD strategy discovery engine. The system sweeps filter combinations and parameter ranges across multiple markets and timeframes to find statistically robust algorithmic strategies. Output: ranked leaderboards of accepted strategies plus a portfolio selector that builds prop-firm-ready combinations with realistic Monte Carlo pass rates.

It is **not a trading system**. It is a research tool that produces candidates which are then deployed manually as Portfolio EAs running on a Contabo VPS via The5ers MT5.

**Operator constraints driving design:**
- Target prop firm: The5ers (currently $5K High Stakes account live; $250K Bootcamp aspirational)
- Risk: 30% max drawdown overall, 1% per trade
- Goal: ~6 uncorrelated strategies across markets and timeframes

---

## 2. Where We've Been — the journey in 9 phases

### Phase 1: Foundation (Sessions 0-5, Mar 16-18 2026)
First ES 60m run analysed: trend = REGIME_DEPENDENT, MR = STABLE, breakout = BROKEN_IN_OOS. Established the funnel architecture: filter sweep → promotion gate → refinement → leaderboard. Built quality scoring (continuous 0-1 metric), BORDERLINE detection at PF thresholds, full configurability via `config.yaml`. 11 smoke tests, master leaderboard aggregator, timeframe-aware refinement grids.

### Phase 2: Cloud Era (Sessions 6-14, Mar 18-21 2026)
Cloud-first development era. Docker, DigitalOcean → GCP. Built `cloud/launch_gcp_run.py` as the central launcher. Added Streamlit dashboard. Prop firm simulator integrated (Session 7).

**Critical bug found Session 8**: portfolio evaluator wasn't passing `timeframe` to feature builders. All non-60m results were silently wrong. Fixed by threading timeframe through all `get_required_*()` and `build_candidate_specific_strategy()` calls.

GCP automation hardened (Sessions 9-10): 10 bugs fixed, dynamic username detection via `whoami`, tar-based download fallback. One-click `run_cloud_sweep.py` wrapper landed Session 14.

### Phase 3: Multi-Timeframe & Quality (Sessions 21-34, Mar 23-26 2026)
Migrated from Australia to US regions for SPOT pricing. Made cloud config zone/machine/provisioning configurable via YAML. Pinned remote Python 3.12 explicitly to avoid bootstrap mismatch.

**Critical fix Session 34**: GCS bundle staging for fire-and-forget mode. The 43 MB SCP of input bundles was hitting SPOT preemption windows; moved bundle upload to GCS pre-VM-creation, leaving only manifest + runner script for SCP. Daily runs (small bundle) had been working; multi-TF runs (large bundle) were silently failing.

Multi-VM split architecture (Session 35): VM-A and VM-B running disjoint timeframes in parallel. Dashboard 3-tab overhaul. Ultimate leaderboard cross-run aggregation.

### Phase 4: Strategy Expansion (Sessions 37-45, Mar 26-29 2026)
- 9 strategy subtypes (3 per family — `mean_reversion_vol_dip`, `mean_reversion_mom_exhaustion`, `mean_reversion_trend_pullback`, etc.)
- Cross-dataset portfolio evaluation: all accepted strategies evaluated together with cross-TF correlation matrix
- Short-side strategies: 15 new short filters, 3 short families, `direction` field threaded through engine
- 7 universal filters: InsideBar, OutsideBar, GapUp/Down, ATRPercentile, HigherHigh, LowerLow
- Widened exit grids — trend trailing_stop_atr [1.5, 2.5, 3.5, 5.0, 7.0]; breakout [1.5, 2.5, 3.5, 5.0]; MR profit_target_atr [0.5, 1.0, 1.5, 2.0, 3.0]
- Performance: shared ProcessPoolExecutor across families, refinement `as_completed()` (CPU 30% → 80%+)

**Critical bug Session 45**: position sizing was using `current_capital` (compounding), producing $20 BILLION PnL on $250K accounts over 18 years at PF 8.0. Fixed to use fixed `initial_capital` only. Matches prop firm rules. **All previous dollar metrics were wrong** — PF rankings still valid (ratio-based), but every dollar-denominated comparison up to that session was inflated.

### Phase 5: Portfolio Selection (Sessions 47-53, Mar 31 2026)
Full portfolio selector pipeline at `modules/portfolio_selector.py`. Six stages:
1. Hard filter gate (ROBUST/STABLE, OOS PF, trade count, dedup, cap)
2. Per-trade return extraction + daily resampling + true Pearson correlation
3. Combinatorial sweep C(n,3..8), reject pairs over correlation threshold
4. Portfolio Monte Carlo (10,000 sims, independent per-strategy shuffle + interleave)
5. Position sizing optimiser
6. Time-to-fund estimation

Sessions 50-51 were heavy debugging:
- Step rate mixing bug (final MC with optimised weights now reports all step rates consistently)
- Daily-resampled returns destroying intraday trade granularity (raw per-trade `strategy_trades.csv` introduced)
- Sizing optimizer always picked minimum weight (safest); reframed objective from "maximize pass rate subject to DD constraint" → "minimize time-to-fund subject to ≥40% pass rate"
- Micro contract sizing grid widened [0.1..1.0] = 1-10 micros
- Multi-program prop firm support (Bootcamp $250K, High Stakes $100K, Hyper Growth $5K, Pro Growth $5K)
- Daily DD enforcement in `simulate_single_step` with `trades_per_day` grouping

### Phase 6: Cloud Migration & Advanced MC (Sessions 56-62, Apr 2-4 2026)
Old GCP account exhausted ($424 credit consumed). Migrated to Nikola's account. New console VM, new bucket (`strategy-artifacts-nikolapitman`), new SSH keys.

**Major upgrade Session 58 — Portfolio selector realism:**
- 3-layer correlation replacing simple Pearson: active-day correlation, drawdown-state correlation, tail co-loss probability
- Expected Conditional Drawdown (ECD) replacing binary DD overlap
- Block bootstrap Monte Carlo replacing shuffle-interleave (preserves crisis clustering)
- Regime survival gate (PF ≥ 0.8 across 2022 / 2023 / 2024-2025)
- 12 new tests for the above

**Vectorized engine (Sessions 60-61)**: replaced per-bar Python trade loop with numpy 2D array operations in `modules/vectorized_trades.py`. **14-23x speedup** with zero-tolerance parity (1e-10) verified against scalar path across 22 test cases. ES daily 14.3x, ES 60m 21.8x, ES 15m 22.8x. Full 15m sweep dropped from ~45 hrs → ~2 hrs on 96-core. `use_vectorized_trades: true` set in all cloud configs.

Bulletproof SPOT runner `run_spot_resilient.py` (Session 59): queue-based, multi-region zone rotation, auto-retry on preemption.

### Phase 7: Cloud Decommissioning (Sessions 65-69, Apr 14-19 2026)
**Major architectural pivot: cloud → local.** GCP credit was about to exhaust again. Local cluster proven cheaper, more reliable, no SPOT preemption.

- CFD data pipeline built: Dukascopy ticks via Tick Data Suite → `scripts/convert_tds_to_engine.py` → 24 markets × 5 TFs in TradeStation-format CSVs
- 24 CFD market configs at `configs/cfd_markets.yaml`
- `run_local_sweep.py` (single market) + `run_cluster_sweep.py` (batch orchestrator with resume) replace GCP SPOT runners
- Cloud code deleted Session 69. Strategy console VM, GCS bucket, all GCP-specific files gone.

### Phase 8: Local Cluster Hardening (Sessions 70-74, Apr 18-24 2026)
- Cluster: c240 (Cisco C240 M4, 80 threads, data hub), gen8 (DL380p, 48 threads post-CPU-upgrade), r630 (Dell, 88 threads)
- Always-on policy adopted as **HARD RULE Session 73** — no more shutdowns. All four hosts always-on.
- g9 (DL360) revived Session 71b — initially as Hermes/OpenClaw autonomous business host, later (Session 75) reassigned to compute worker
- X1 Carbon parallel Claude Remote Control hub for both projects
- HANDOVER.md renamed to MASTER_HANDOVER.md (Session 75) for project-scoped naming

### Phase 9: Hermes Experiment + Retirement (Sessions 72-75, Apr 20-26 2026)
- Sessions 72-72d: Hermes Agent (NousResearch/hermes-agent) + OpenClaw deployed on g9 with handover sync, GitHub deploy keys, Telegram bot, cluster SSH access
- Session 75: **Hermes/OpenClaw fully decommissioned** after 1-week experiment. Claude Code + Claude Remote Control hub on X1 Carbon replaced agent-driven ops. Simpler, no API costs, no security surface from agent SSH access. g9 reassigned to compute worker role. Server-side teardown, cluster authorized_keys cleanup, GitHub deploy keys revoked, Telegram bot deleted, Anthropic API key revoked. Fully gone.

---

## 3. Where We Are Now — current state snapshot

### Code state
- **~454 strategies** in ultimate leaderboard (414 bootcamp-accepted) across 8 markets (ES, CL, NQ, SI, HG, RTY, YM, GC)
- **12 strategy families**: 3 long base (trend, mean_reversion, breakout) + 3 short (short_trend, short_mean_reversion, short_breakout) + 9 subtypes (3 per long family)
- **Vectorized engine** (14-23x speedup, parity-tested) — every cloud config has `use_vectorized_trades: true`
- **Leaderboard architecture** now uses neutral canonical pools: futures rank in `family_leaderboard_results.csv`, `master_leaderboard.csv`, `ultimate_leaderboard.csv`; CFDs rank in `family_leaderboard_results.csv`, `master_leaderboard_cfd.csv`, `ultimate_leaderboard_cfd.csv`
- **Portfolio selector** with 3-layer correlation, ECD, block bootstrap MC, regime survival gate; now owns program-specific ranking directly rather than inheriting `bootcamp_score` from any leaderboard layer
- **4 prop firm programs** configured with daily DD enforcement (Bootcamp, High Stakes, Pro Growth, Hyper Growth)
- **Test suite**: 261+ tests passing (smoke, subtypes, parity, portfolio selector, prop firm configs, cross-dataset evaluator)
- **In-flight validation batch (2026-04-30):** first real ES/NQ CFD cluster sweep launched across c240/gen8/r630/g9 for `daily`, `60m`, and `30m`, with neutral CFD aggregates intentionally starting empty

### Live trading state
- **Portfolio #3 EA** on Contabo VPS (89.117.72.49, Windows Server, US East): NQ Daily MR + YM Daily Short Trend + GC Daily MR + NQ 15m MR (all 0.01 lots). Projected 99.6% pass rate, 6.9% DD, ~13.4 months to fund.
- **Portfolio #1 EA** also live on the same VPS
- **The5ers** account 26213568 on FivePercentOnline-Real (MT5), $5K High Stakes
- **First confirmed live trade**: YM Daily Short Trend, SELL US30
- MT5 Hedge mode working, CFD symbols available, no blockers

### Infrastructure state

**Compute cluster (4 always-on hosts, HARD RULE):**
| Host | Hardware | Threads | LAN | Tailscale | Role |
|------|----------|---------|-----|-----------|------|
| c240 | Cisco C240 M4 | 80 | 192.168.68.53 | 100.120.11.35 | Data hub + compute, /data/market_data + sweep_results live here |
| gen8 | HP DL380p | 48 | 192.168.68.71 | 100.76.227.12 | Compute worker (post-CPU upgrade; awaiting fans bays 3-4) |
| r630 | Dell R630 | 88 | 192.168.68.78 | 100.85.102.4 | Compute worker |
| g9 | HP DL360 | 48 / 32 GB | 192.168.68.50 | 100.71.141.89 | **Compute worker — not yet onboarded** (no repo, market_data, sweep scripts) |

**Total available: ~264 threads** once g9 is onboarded.

**Control plane:**
- **Latitude** (this machine) — main dev. Claude Code in VS Code. Tailscale 100.79.72.125. Z: drive mapped to c240 samba.
- **X1 Carbon** (always-on, in drawer) — parallel Claude Remote Control hub from phone for both betfair-trader and python-master-strategy-creator. Each project has its own session, separate state.
- **Contabo VPS** — live trading only, no dev/compute.

### Repo state
- Root: 4 .md files (CLAUDE.md, MASTER_HANDOVER.md, LOG.md, README.md), 16 .py files, 10 dirs
- Working spec compliance (adopted Session 74, fully active Session 75): MASTER_HANDOVER.md with `Last updated:` / `Current status:` paragraph, append-only LOG.md, project-scoped naming
- 93+ historical session files archived under `archive/sessions/`
- Cloud code deleted Session 69
- Hermes scripts/docs deleted Session 75

### Data state
- **81 TradeStation futures CSVs** (~2.2 GB) for 17 markets: ES, CL, NQ, SI, HG, RTY, YM, GC, EC, JY, BP, AD, NG, US, TY, W, BTC
- **120 Dukascopy CFD CSVs** (Tick Data Suite → engine format) at c240 `/data/market_data/cfds/ohlc_engine/` — 24 markets × 5 TFs
- **The5ers tick data**: SP500 (3.1 GB / 76.5M ticks), NAS100 (10.6 GB / 245.8M ticks), partial others. XAUUSD only 5 days (useless for backtesting; need Dukascopy)
- **Latitude TDS source copy** (~33 GB at `C:\Users\Rob\Downloads\Tick Data Suite\`) verified mirrored to c240, can be deleted

---

## 4. Where We're Going — roadmap

### Immediate (Session 76, the next session)
1. **g9 onboarding to compute cluster.** Concrete steps:
   - SSH g9, clone repo into `~/python-master-strategy-creator`
   - Set up Python 3.12 venv, install `requirements.txt`
   - Mount `/data/market_data` via samba from c240 (or rsync local copy if samba membership not yet decided)
   - Drop `post_sweep.sh` into `/usr/local/bin/`
   - Test with a single ES 60m sweep, verify rsync-back to c240 works
2. **Worker review** carried over from Session 72g — `mem_probe.py` on r630, audit nested ProcessPool in engine modules, decide ES_5m worker count or whether r630 needs RAM upgrade (62 → 128 GiB).
3. **Session 73 ES sanity-check sweep** — 4 TFs (daily / 60m / 30m / 15m) on c240 alone, ~30-60 min. Gates the 24-market fan-out.

### Near-term (Sessions 77-80)
4. **Full 24-market sweep** (Session 74 plan) — `run_cluster_sweep.py` orchestrating c240 + gen8 + r630 + g9 = 92 sweeps total (4 TFs × 23 markets, 5m excluded).
5. **CFD swap costs into MC simulator** — cost profiles defined in `configs/cfd_markets.yaml` but not yet consumed by portfolio selector. **Critical for trustworthy funding timelines.** Without this, MC pass rates against The5ers programs are optimistic even though the CFD leaderboard layer is now neutral.
6. **Challenge vs Funded mode** — implement spec at `docs/CHALLENGE_VS_FUNDED_SPEC.md`.

### Medium-term
7. Walk-forward validation as alternative to fixed IS/OOS split (long-pending)
8. Bayesian/Optuna optimization for refinement grid (replace 256-point brute force)
9. Strategy templates to reduce search space
10. Dashboard Live Monitor fix — engine log + promoted candidates broken during active runs

### Pending hardware/admin
- Gen 8 fans (HP 662520-001 ordered, due late April / early May)
- R630 netplan cleanup (drop stale `192.168.68.75` DHCP lease)
- C240 CIMC IP capture (router ARP for MAC `00:A3:8E:8E:B3:84`)
- Tailscale device cleanup (stale `c240` 100.104.66.48)
- Static IP from Carbon Comms ISP (in progress)
- Latitude TDS source delete (~33 GB freed)
- X1 Carbon SSH isolation verify when next online

---

## 5. The Operating System — how we work

This section is the most directly transferable to the betfair-trader project.

### The control plane
- **Latitude (Windows 10 Pro)**: primary dev. Claude Code in VS Code is the development interface. SSH-able to all cluster hosts via Tailscale. Strategy code is written, tested, reviewed here.
- **X1 Carbon (always-on, in drawer)**: parallel Claude Remote Control hub. Phone app → X1 → SSH/Git → cluster. Heavy compute stays on Linux; X1 is dispatcher only. Has both project hubs side-by-side as separate sessions, no shared state.
- **Contabo VPS**: live trading only. Not dev, not compute.

### The cluster
- 4 always-on Linux hosts (c240, gen8, r630, g9). HARD RULE: no shutdowns.
- c240 is the data hub: holds `/data/market_data/`, `/data/sweep_results/`, `/data/leaderboards/`, `/data/configs/`. Samba shares to other hosts.
- Workers crunch sweeps. `post_sweep.sh` rsyncs results back to c240. Leaderboard regeneration runs on c240.
- No more cloud. No more SPOT runners. No more SCP timeouts. Local LAN, no preemption.

### The session protocol (the working spec)

**Per-project files** (all at repo root):
- **MASTER_HANDOVER.md** — single source-of-truth for current state. Line 1: `Last updated:`. Line 2: `Current status:` paragraph. Updated in place, never per-session snapshots.
- **LOG.md** — append-only audit log. Every meaningful task gets an entry: date, status, what, outcome, files, next.
- **CLAUDE.md** — project bible. Auto-loaded into every session.

**Global files** (at `~/.claude/`):
- **CLAUDE.md** — operator profile, time zone, output encoding, tone preferences, standing rules.
- **projects/<hash>/memory/** — auto-memory directory, persistent across sessions per project. Index at MEMORY.md.

### Trigger phrases (operator → Claude)
- `"checkpoint please"` — save state mid-session: update MASTER_HANDOVER.md header + append LOG.md + add memory entries + commit + push (if authorised). Do not clean up in-flight work.
- `"session end please"` / `"wrap session"` / `"handover"` — full session-end ritual: same as checkpoint plus document in-flight work with a one-line "next session starts here" pointer.
- `"go"` / `"keep going"` / `"continue"` — proceed autonomously through the current plan; pause only at gates needing operator decision.
- `"hold"` / `"pause"` — stop advancing; ask before resuming.

### Standing rules (non-negotiable)
- Never `git add -A` or `git add .` — stage by path.
- Never `--no-verify` or bypass signing.
- Never `git push --force` to main.
- Never amend a published commit — always make a new commit.
- Never push without being asked. (`git commit` and `git push` are separate decisions.)
- Never echo secrets — reference by env var name or path.
- Never modify per-chat handover snapshots; MASTER_HANDOVER.md is updated in place.
- Never edit LOG.md retroactively — append-only audit.

### Risk discipline
- **Local reversible actions** (file edits, running tests): proceed without asking.
- **Destructive actions** (`rm -rf`, `git reset --hard`, force push, dropping DB tables, killing prod processes): confirm before.
- **External-visibility actions** (PR comments, pushes to remote, Slack/email/Telegram, third-party uploads): confirm before.
- **Per-action authorization** is the default. Approving "git push" once does NOT mean approving it for the rest of the session. Re-confirm.

### Pre-flight verification
- Memory entries are point-in-time claims. Before recommending from memory, verify the named file/function/flag still exists.
- Trust the repo over the memory when they disagree, and update the memory.
- Memory is for non-obvious lessons that future sessions would burn time relearning. Not for current state of work (that goes in MASTER_HANDOVER.md), not for audit facts (that goes in LOG.md).

### What gets saved where
| Trigger | Layer | Lifetime |
|---------|-------|----------|
| Every meaningful task | LOG.md | Permanent |
| State changes (verdict, infra ships, new blocker) | MASTER_HANDOVER.md header | Permanent until next state change |
| Lesson a future session would burn time relearning | Auto-memory | Permanent across all chats |
| Logical chunk of code done | git commit (push if authorised) | Permanent |
| Multi-step task in flight | TodoWrite | This chat only |

### Communication style
- One sentence before the first tool call stating intent.
- Short progress updates at key moments: finding something, changing direction, hitting a blocker.
- No narrating internal deliberation.
- End-of-turn summary: 1-2 sentences max.
- File references: `[file.py:42](relative/path.py#L42)` format.
- ASCII only in commits, log entries, and persisted artefacts (Windows PowerShell cp1252 breaks on emoji/unicode).
- Match response weight to task. Simple question → direct answer.

---

## 6. What We've Got to Do — concrete next steps

### Session 76 priority (next session starts here)
1. **Onboard g9 to compute cluster** (above)
2. **Worker review** for r630 (above)
3. **ES sanity-check sweep** on c240 (above)

### Session 77 conditional on 76 passing
4. **Full 24-market sweep** kicked off via `run_cluster_sweep.py`

### Recurring discipline going forward
- LOG.md entry for every meaningful task — including failures
- MASTER_HANDOVER.md updated per session, in place
- Memory entries for non-obvious lessons
- Commit at logical chunk boundaries, push when explicitly asked
- Pre-flight verify before recommending from memory

### Things that should NOT be touched (working as intended, hard-won)
- **Vectorized engine** — 14-23x speedup, parity-tested 1e-10. Don't refactor without preserving parity.
- **3-layer correlation** in portfolio selector — multi-LLM-validated (Session 58).
- **Block bootstrap MC** — preserves crisis clustering, validated against real 2022/2023/2024 regimes.
- **Position sizing fixed at initial_capital** — Session 45 critical fix, do NOT re-introduce compounding.
- **Vectorized filter masks** — pandas Series.rolling + numpy broadcast.
- **Exit grid widths** (Session 41) — narrower grids killed trend strategies; keep them wide.

---

## 7. Lessons Transferable to betfair-trader

These are observations from this project's evolution that may apply to your project.

### 1. Cloud was a detour, not a destination
GCP burned ~$424 in credit before we admitted local was cheaper, more reliable, and faster (no SPOT preemption windows, no SCP timeouts, no CPU quotas to negotiate, no us-region trips). If your project still has cloud dependencies, ask honestly whether a local cluster is viable. The architectural simplification of going local was worth the migration cost.

### 2. Hermes was a 1-week experiment, then retired
We deployed Hermes Agent (voice/Telegram → cluster via Anthropic API) thinking it would be a force multiplier for autonomous ops. It added: an LLM cost layer ($30/mo budget), a security surface (deploy keys, cluster SSH, API keys, Telegram bot), and operational complexity (sync-handover scripts, Memory.md drift, multiple symlinks). It produced marginal benefit over Claude Code + simple SSH. We retired it Session 75 after confirming Claude Code + Claude Remote Control hub on X1 Carbon covered everything Hermes did, with less surface area.

**Lesson:** don't add agents until you've proven Claude Code + simple SSH isn't enough. The threshold for "it's not enough" is high — most ops don't actually need autonomous agents.

### 3. Critical bugs lurk in the boring parts
Two bugs made it through many sessions because nobody questioned the boring "obviously correct" arithmetic:
- **Session 8**: portfolio evaluator wasn't passing timeframe to feature builders. All non-60m results were silently wrong for many sessions.
- **Session 45**: position sizing was compounding (using `current_capital`). Produced $20B PnL on $250K accounts at PF 8.0 over 18 years. **Every dollar metric in the project up to that session was inflated.**

**Lesson:** re-validate dollar metrics against a sanity-check baseline periodically. If a strategy reports astronomical returns, the bug is in your code, not in the strategy.

### 4. Per-chat handover snapshots fragment context
We had 93 SESSION_*_TASKS.md files cluttering the repo before consolidation. Each one was a snapshot of one session's work, slowly drifting from current truth. Single MASTER_HANDOVER.md (in place, current state) + append-only LOG.md (audit trail of what happened) beats per-session files for both readability and operator cognitive load.

### 5. Working spec adoption pays off immediately
Once Rob set the working spec (Session 74), session start time dropped to <60 seconds and context drift across chats stopped. The spec is at `docs/PROJECT_REVIEW_2026-04-26.md` section 5 — copy it into your project's CLAUDE.md if you don't already have similar discipline.

### 6. MASTER_HANDOVER not HANDOVER
Project-scoped naming prevents collision when an agent or operator tool loads multiple projects. We learned this when planning Hermes ingest — both this project and betfair-trader had `HANDOVER.md`, and Hermes auto-loaded both into memory, conflating state. Use `MASTER_HANDOVER.md` (or `BETFAIR_HANDOVER.md`) so handovers are always project-scoped.

### 7. Latitude → cluster via Tailscale is enough
No bastion, no VPN gateway. Tailscale ssh aliases + ProxyJump for the one host with ARP weirdness. Adding more abstraction would add brittleness without improving anything.

### 8. Always-on hard rule for cluster hosts
Auto-shutdown crons were saving ~$5/mo per host but causing real ops friction (waking machines, slow BIOS POST, lost time). Session 73 made always-on a HARD RULE. Total cluster power cost is ~$60-80/mo, which is dwarfed by the ops time saved.

### 9. Vectorize ruthlessly when bar-by-bar Python is in the hot path
Session 60-61 vectorized engine: 14-23x speedup, zero-tolerance parity. Full 15m sweep dropped from 45 hrs → 2 hrs on 96-core. **Always write a parity test harness first**, then refactor against it. Without parity tests, you can't confidently swap implementations.

### 10. Risk discipline is per-action, not per-session
Approving `git push` once doesn't authorise pushes for the rest of the session. Approving `rm -rf /data/foo` doesn't authorise other rm -rfs. Re-confirm at every destructive boundary. The cost of pausing is low; the cost of an unauthorised destructive action can be very high.

---

## End of review

For: Rob's reference + cross-project sharing with the betfair-trader project's Claude.

If you are the betfair-trader Claude reading this: build a parallel review doc for your project at `docs/PROJECT_REVIEW_<DATE>.md`, focusing on what's working, what's not, and where the ops divergence with this project (python-master-strategy-creator) creates opportunities to align or specialise. Identify any of the 10 lessons above that apply to your project but haven't been internalised yet.
