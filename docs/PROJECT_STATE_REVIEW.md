# Project State Review — April 2026

**Status:** Pre-cleanup snapshot. The next session (68) is a full-repo audit + cleanup planning session. Sweep execution resumes after cleanup.

---

## 1. Executive summary

A solo algorithmic trading project building a fully-automated strategy discovery and portfolio assembly engine, targeting **CFD prop firm evaluations as the primary capital-efficiency path**. The long-term goal is using prop firm payouts to seed personal futures trading capital — but the entire build order is deliberately CFD-first because prop firm allocations scale faster than self-funded futures and carry far less downside risk during validation.

Strategy discovery runs on a **fully-local compute cluster** (Melbourne home lab, three servers, ~216 threads total). The only cloud dependency is **Google Drive for backup** via rclone. Live execution runs on **Contabo VPS in New York** (necessary for MT5 proximity to The5ers' broker server — this is external, not "cloud compute").

Current live deployment: Portfolio #3 on The5ers $5K High Stakes account (MT5, account 26213568). Projected 99.6% pass rate, ~13.4 months to fund — though this estimate has a known gap (CFD swap costs not yet modeled), so real funding timeline is likely longer until that lands.

---

## 2. Strategic trajectory

### Phase 1 — CFD prop firm evaluations (NOW, months 0–12)

**Goal:** Pass evaluations and get funded on multiple CFD prop firms.

**Rationale:**
- Capital efficiency: $95 evaluation fee gets access to $5K–$100K+ in funded capital
- Downside cap: worst case is evaluation fee, not six-figure drawdowns on personal capital
- Parallelism: multiple firms can be pursued simultaneously
- Forces discipline on cost modeling (CFDs have real swaps, spreads, slippage that must be respected)

**Firms in priority order:**
1. **The5ers** — primary, unlimited time, most flexible rules, overnight holds OK, 15m/daily compatible
2. **FTMO** — secondary, static drawdown model, Swing account variant for overnight
3. **Darwinex Zero** — long-game DARWIN track record, investor capital allocation
4. **FundedNext CFD** — backup, similar to FTMO

**Explicitly excluded:** Topstep, Apex, FundedNext Futures. No overnight hold = incompatible with 5-bar daily strategies.

### Phase 2 — Scale CFD allocations (months 6–24)

- Multiple funded accounts across 2–4 firms simultaneously
- Each funded account trading a portfolio of 3–5 uncorrelated strategies
- Payouts reinvested into: (a) more evaluation attempts, (b) cluster expansion, (c) cash reserves
- Expected: six-figure AUD annual payouts at scale (CFD prop firm returns typically 4–10% monthly on funded capital, 80% paid to trader)

### Phase 3 — Self-funded futures trading (months 18+)

- Use CFD payout reserves to fund personal futures accounts
- Futures strategies already validated via existing 454-strategy TradeStation futures leaderboard
- Lower cost structure than CFDs (no swaps, tighter spreads, known commissions)
- Larger position sizing flexibility on personal capital
- This is the long-term endgame, NOT the entry path

### Phase 4 — Compute rental side hustle (optional, month 12+)

- Cluster has idle capacity outside sweep windows
- Target market: retail quants, ML students, researchers needing GPU-adjacent CPU compute
- Requires network isolation (VLAN), Docker containerization, Stripe billing
- Scalable: each $350 used-server addition adds ~60 threads, pays back in 6 weeks
- Tax-deductible capex

---

## 3. Current position (April 2026)

### Live trading
- **Account:** The5ers 26213568, FivePercentOnline-Real, $5K High Stakes, MT5 Hedge mode
- **VPS:** Contabo Cloud VPS 10, 89.117.72.49, Windows Server, US East (New York), $17.66/mo
- **Portfolio #3 live:** NQ daily MR + YM daily Short Trend + GC daily MR + NQ 15m MR — all 0.01 lot
- **Portfolio #1 also live** on same VPS
- **First live trade confirmed:** YM Daily Short Trend (SELL US30)
- **Projected:** 99.6% pass rate, 6.9% P95 DD, ~13.4 months to fund (**optimistic — no swap costs modeled**)

### Strategy engine
- **Ultimate leaderboard:** ~454 strategies, 414 bootcamp-accepted, across 8 futures markets
- **Built on:** TradeStation futures data (2008–2026), 4 timeframes (daily/60m/30m/15m)
- **Performance:** vectorized engine 14–23× speedup with zero-tolerance parity, validated
- **Strategy families:** 12 total — 3 long families × 3 subtypes + 3 short families × 3 subtypes
- **Portfolio selector:** 6-stage pipeline with 3-layer correlation (active-day, DD-state, tail co-loss), block bootstrap MC preserving crisis clustering, regime survival gate

### CFD discovery pipeline (Session 65 build, not yet exercised)
- **Format converter:** `scripts/convert_tds_to_engine.py` handles 24 markets, 5 timeframe codes
- **Engine loader:** updated to recognize Dukascopy "Vol" column header
- **24 CFD market configs:** `configs/cfd_markets.yaml` with per-market engine params + cost profiles
- **Local sweep runners:** `run_local_sweep.py` (single market) + `run_cluster_sweep.py` (batch orchestrator with resume)
- **Status:** infrastructure built, only ES daily Dukascopy actually converted so far. 92 more conversions pending.

### Known silent bug (discovered today, pre-Session-68)
- Existing `configs/local_sweeps/ES_daily_cfd_v1.yaml` has futures engine params (`dollars_per_point: 50.0`) but points to Dukascopy SP500 CFD data. Would have produced P&L inflated 50× if executed.
- Fix captured in `SESSION_68_PIPELINE_REVIEW.md` — applied in Session 69+ after cleanup.

---

## 4. Infrastructure — fully local, zero cloud compute

### Design principle
**No cloud compute. No cloud dependencies except Google Drive for cold backup.** Every compute cycle, every byte of data, every sweep result lives on hardware owned by Rob in Melbourne. This is deliberate:
- Zero recurring cloud costs at scale (sweep volumes would be $1k+/mo on GCP)
- No SPOT preemption uncertainty
- No cross-region egress fees
- Full data sovereignty
- Tax-deductible capex
- Cluster doubles as rental side-hustle substrate (Phase 4)

The GCP infrastructure built in Sessions 6–62 is **deprecated**. `cloud/`, `run_spot_resilient.py`, `run_cloud_sweep.py`, and the strategy-console VM are pending deletion once local sweeps are proven.

### Compute cluster

| Node | Role | State | CPU | RAM | Storage | Notes |
|---|---|---|---|---|---|---|
| **Latitude** (Lenovo) | Control + dev | Always on (mobile) | — | — | — | Primary dev laptop, SSH hub, TDS exports |
| **X1 Carbon** | Claude hub | Drawer, lid down | — | — | — | Always-on Claude.ai endpoint |
| **c240** (Cisco C240 M4) | Data hub + compute | **Always on** | 2× E5-2673 v4, 40C/80T | 64 GB | 10.9 TB SAS | Under house, holds all data, nightly gdrive backup |
| **Gen 8** (DL380p) | Worker | Sleeps when idle | 12T (pre-upgrade); 48T after | 80 GB DDR3 | — | CPU upgrade pending |
| **R630** (Dell) | Worker | Sleeps when idle | 2× E5-2699 v4, 44C/88T | — | 838 GB SSD | Largest worker |

**Total compute when all on:** ~216 threads (80 + 48 + 88)

### Connectivity
- **LAN:** 192.168.68.x, XE75 Pro router (192.168.68.1)
- **VPN:** Tailscale for remote access (authenticated to robpitman1982@gmail.com)
- **ISP:** Carbon Comms, 500/50 Mbps NBN, **static IP** (being connected)
- **SSH mesh:** c240 ↔ gen8 ↔ r630 full bidirectional, all use `rob`/`Ubuntu123` + key auth
- **Shares:** Samba `//192.168.68.53/data` from c240 to Latitude + X1

### Data flow (steady state)

```
Dukascopy (via TDS on Latitude)
    ↓  robocopy over Samba
c240 /data/market_data/cfds/ohlc/  (raw)
    ↓  convert_tds_to_engine.py
c240 /data/market_data/cfds/ohlc_engine/  (engine-ready)
    ↓  run_cluster_sweep.py orchestrates
Workers (gen8, r630) do sweeps  →  rsync results back
    ↓
c240 /data/sweep_results/  +  /data/leaderboards/
    ↓  nightly at 02:30 via rclone
Google Drive: gdrive:c240_backup/  (COLD BACKUP ONLY — never read for compute)

c240 leaderboards/portfolio_outputs
    ↓  portfolio_selector pipeline
Selected portfolio
    ↓  manual EA deploy
Contabo VPS (external, MT5-proximity, NOT cloud compute)
    ↓  MT5 execution
The5ers broker server
```

### Cloud touches — explicit list

The ONLY cloud footprint in steady state:

1. **Google Drive (backup):** `rclone` nightly sync from c240 to `gdrive:c240_backup/`. Cold storage only. Never read for compute.
2. **Contabo VPS (execution, not compute):** MT5 needs Windows + broker-server proximity. $17.66/mo. Runs the EA, nothing else.
3. **Tailscale (VPN):** coordination plane only, no data transit through their servers.
4. **GitHub:** source control and handover docs. No data, no secrets.

**Deprecated / pending deletion:**
- GCP project `project-c6c16a27-e123-459c-b7a` (Nikola's account, strategy-console VM)
- GCS bucket `gs://strategy-artifacts-nikolapitman/`
- All `cloud/` code in repo
- `run_spot_resilient.py`, `run_cloud_sweep.py`, `launch_gcp_run.py`
- Cloud VPC, SPOT configs

---

## 5. Data architecture — canonical

See `SESSION_68_PIPELINE_REVIEW.md` for the full detail. Summary:

### Three-naming system (kept deliberate for a reason)
| Role | Used by | Example |
|---|---|---|
| **Canonical project identifier** | Engine, leaderboards, configs | `ES`, `NQ`, `YM`, `GC` |
| **The5ers CFD symbol** | MT5 execution | `SP500`, `NAS100`, `US30`, `XAUUSD` |
| **Dukascopy filename stem** | Raw data files | `USA_500_Index`, `USA_100_Technical_Index` |

Mapping lives in `modules/cfd_mapping.py`. The canonical identifier (futures ticker) is used everywhere the engine sees; the other two only exist at boundaries.

### Data locations on c240

```
/data/market_data/
├── futures/                    TradeStation futures CSVs (87 files, reference)
├── cfds/
│   ├── ohlc/                   Dukascopy raw exports (120 files, 24 symbols × 5 TFs)
│   ├── ohlc_engine/            Engine-ready converted CSVs (ONLY ES daily so far)
│   ├── ticks_dukascopy_tds/    Raw .bfc tick cache (32 GB, for re-export)
│   ├── ticks_dukascopy_raw/    Future: dukascopy-python parquet
│   └── ticks_mt5_the5ers/      The5ers MT5 tick exports (SP500 + NAS100 done)
```

### Discovery vs execution data
- **Discovery:** Dukascopy CFD OHLC — deep history (2012+), closest proxy for The5ers price series, includes CFD cost economics
- **Execution validation:** The5ers MT5 tick exports — real spreads as they arrive on the live account
- **Futures backtests:** archived, reference only, do NOT use for new discovery (cost structure mismatch)

### Sweep universe vs portfolio universe (architectural principle)
**Strategy discovery sweeps run on ALL 24 Dukascopy CFD markets. Per-prop-firm `excluded_markets` filtering is applied ONLY at portfolio selection time, NOT at sweep time.**

Rationale:
- Strategies are portable across CFD prop firms — a strong SP500 mean-reversion strategy works for The5ers, FTMO, Darwinex, or FundedNext. Compute spent discovering it is reused across all four firm targets.
- Filtering at sweep time would waste compute and reduce option-value when we add new firms.
- The portfolio selector is the correct layer for firm-specific decisions: it reads a per-firm config, picks the best combination from the universal leaderboard subject to that firm's tradeable-market constraints, rule set (daily DD, total DD, target), and cost structure.
- The5ers excluded markets (W, NG, US, TY, RTY, HG) are filtered IN the portfolio selector, NOT removed from the leaderboard. Other firms may trade some of these; keeping them in the leaderboard preserves optionality.

---

## 6. Prop firm hierarchy and constraints

**Scope note:** The tables below describe what each prop firm permits at *execution* time. Strategy *discovery* is firm-agnostic and runs on the full 24-market Dukascopy CFD universe. Firm-specific tradeability is enforced in the portfolio selector via a per-firm `excluded_markets` config.

| Firm | Tier | Account | Key rule | Compatible with daily strategies? |
|---|---|---|---|---|
| The5ers | 1 | $5K High Stakes | Unlimited time, 4% daily DD, 6% total DD | ✅ |
| FTMO | 2 | Swing | Static drawdown, 10% total, 5% daily | ✅ (Swing variant only) |
| Darwinex Zero | 2 | N/A (€38/mo) | DARWIN track record for investor allocation | ✅ long game |
| FundedNext CFD | 3 | TBD | Similar to FTMO | ✅ |
| Topstep | ❌ | — | No overnight holds | ❌ |
| Apex | ❌ | — | No overnight holds | ❌ |
| FundedNext Futures | ❌ | — | No overnight holds | ❌ |

### The5ers tradeable markets (CFDs on MT5)
**Execution universe on The5ers:** SP500, NAS100, US30, XAUUSD, XAGUSD, XTIUSD + FX pairs (EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD)

**The5ers `excluded_markets` (used by portfolio selector):** W, NG, US, TY, RTY, HG — these remain in the universal leaderboard but are never selected into The5ers portfolios.

Other prop firms (FTMO, Darwinex, FundedNext) have different `excluded_markets` lists — their own canonical tradeable universes. These live in per-firm config files (to be inventoried in Session 68 audit).

### Critical swap cost structure (The5ers, per micro lot)
| Market | $/micro/night | Friday × | Notes |
|---|---|---|---|
| CL (XTIUSD) | $0.70 | 10× | Weekend holds effectively unusable |
| SI (XAGUSD) | $4.05 | normal | Expensive |
| GC (XAUUSD) | $2.20 | normal | Expensive |
| Indices (SP500/NAS100/US30) | ~0 | — | Essentially free |
| FX (JY/EC/BP/AD) | $0.10–0.26 | — | Cheap |

**Implication:** The5ers structurally favors short-duration index + FX strategies. CL weekend holds at 50 micros would cost $350 — 72% of a Pro Growth $500 profit target in one overnight. This is why Portfolio #3 avoids CL entirely.

---

## 7. Gaps blocking progress (ranked)

### Critical (blocks accurate forecasting)
1. **CFD swap costs not in MC simulator.** Cost profiles defined in `configs/cfd_markets.yaml` but not consumed by portfolio selector. Every funding-timeline estimate is optimistic until this lands.

### Important (blocks scale)
2. **23 markets × 4 TFs = 92 Dukascopy conversions pending.** Only ES daily is converted to engine format. Without these, local sweep coverage is one market.
3. **Silent bug in existing ES CFD config** — futures params on CFD data — fixed spec in SESSION_68_PIPELINE_REVIEW.md but not yet applied.
4. **FX 15m/30m sweeps not done.** JY/EC/BP/AD could be competitive on The5ers swap profile but haven't been swept at short TF.

### Moderate (technical debt)
5. **Dashboard Live Monitor broken** (engine log + promoted candidates panels).
6. **`test_daily_dd_breach`** failing (needs update for pause-vs-terminate logic from Session 61).
7. **Cloud code still in repo** (`cloud/`, GCP runners) — pending deletion after local sweeps proven.
8. **`ES_daily_cfd_v1.yaml` legacy bug config** — to be deleted or clearly marked deprecated.
9. **Stale Tailscale `c240` entry** (100.104.66.48 from abandoned Hermes pivot).
10. **R630 stale DHCP lease** on eno1 (192.168.68.75 alongside static .78).

### Infrastructure pending (hardware)
11. **Gen 8 CPU upgrade** — 2× E5-2697 v2 on hand, install under house.
12. **C240 CIMC IP** — not captured, needs router ARP lookup.
13. **Gen 9 revival** as optional Hermes box (bent pin repair underway).

---

## 8. Near-term execution plan

### Session 68 — Full repo audit + cleanup planning (THIS SESSION)
- Claude Code does comprehensive audit of repo state, produces `AUDIT_REPORT.md`
- Output: factual inventory of everything (modules, configs, scripts, tests, dead code, data, cloud leftovers)
- No code changes. No sweeps. Just measurement.
- Deliverable consumed by NEXT session planning.

### Session 69 — Cleanup execution
- Delete cloud infrastructure code (`cloud/`, GCP runners, strategy-console config)
- Delete / archive buggy configs (`ES_daily_cfd_v1.yaml`)
- Reorganize data paths to canonical layout
- Remove dead modules identified in audit
- Update documentation
- Commit-per-subtask, full test run

### Session 70 — First clean CFD sweep
- Execute SESSION_68_PIPELINE_REVIEW.md plan (now renumbered)
- ES daily Dukascopy, c240 only, validated end-to-end
- Scope unchanged from original Session 68 spec

### Session 71 — Dukascopy conversion scale-out
- Convert remaining 92 Dukascopy market/TF combinations
- Validate each conversion with spot checks
- Populate `/data/market_data/cfds/ohlc_engine/`

### Session 72 — Full 24-market sweep (distributed)
- Wake gen8 + r630
- `run_cluster_sweep.py` against all available markets/TFs
- Exercise the post_sweep.sh rsync + c240 inbox pattern
- Produce first CFD-native leaderboard

### Session 73 — Swap cost modeling in MC
- Implement swap cost consumption in portfolio selector
- Re-run portfolio selection against CFD leaderboard with accurate costs
- New Portfolio candidates ranked by realistic funding timelines

### Session 74 — Deploy next portfolio
- Select best CFD-native portfolio from Session 73
- Build EA, deploy to Contabo
- Run alongside Portfolio #3

---

## 9. Medium-term (6–12 months)

- Pass The5ers High Stakes evaluation (get funded account)
- Add second prop firm: either FTMO Swing or Darwinex Zero
- Begin DARWIN track record on Darwinex for investor allocation
- Implement challenge-vs-funded EA mode toggle (spec in `docs/CHALLENGE_VS_FUNDED_SPEC.md`)
- Static IP port forwarding for Contabo monitoring from home
- Hermes agent on c240 for Telegram alerts (strategy status, fills, DD warnings)

## 10. Long-term (12–24 months)

- Multiple funded prop firm accounts in parallel
- First payout cycles complete
- Compute rental side hustle MVP (VLAN isolation + Docker + Stripe)
- Begin funding personal futures accounts from payout reserves
- Evaluate additional prop firms as market evolves
- Consider moving from Contabo to dedicated colo if VPS becomes limiting

---

## 11. Cleanup priorities (for Session 68 audit to confirm / expand)

### Delete outright (cloud leftovers)
- `cloud/` directory
- `run_spot_resilient.py`, `run_cloud_sweep.py`, `launch_gcp_run.py`
- GCP-specific documentation in `docs/`
- Any `.tf` Terraform or cloud-init files

### Delete after replacement proven
- `configs/local_sweeps/ES_daily_cfd_v1.yaml` (buggy — replace with `ES_daily.yaml`)
- Any `_all_timeframes.yaml` configs that bake wrong engine params

### Audit & possibly delete (depends on audit findings)
- `Data/` dir in repo (36 CSVs) — redundant copy of subset of c240 `/data/market_data/`
- Any module not imported by another module (dead code)
- Any script in `scripts/` not referenced by runners or docs
- Any test that's disabled or skipped indefinitely

### Reorganize (not delete)
- Move session handover docs into `docs/handovers/`
- Move one-off analysis scripts into `scripts/archive/`
- Ensure `configs/` has clear subdirs: `cfd_markets/`, `local_sweeps/`, `engine/`, `prop_firms/`

### Document (currently implicit)
- The three-naming system in a prominent place (`docs/NAMING_CONVENTIONS.md`)
- The canonical data layout (`docs/DATA_LAYOUT.md` — could be extracted from this review)
- The cluster architecture (`docs/CLUSTER_ARCHITECTURE.md`)
- The deploy pipeline (strategy → portfolio → EA → VPS → The5ers)
- **Per-prop-firm tradeable universes (`docs/PROP_FIRM_UNIVERSES.md`)** — canonical source of `excluded_markets` for The5ers (W/NG/US/TY/RTY/HG), FTMO (TBD), Darwinex Zero (TBD), FundedNext CFD (TBD). Read by portfolio selector. Sweep engine ignores these entirely (sweeps are firm-agnostic).

---

## 12. What this review is NOT

- It is not a commitment to specific dates. Session 68 is "after audit completes", not "next Tuesday".
- It is not a plan to touch live trading. Portfolio #3 stays deployed throughout cleanup.
- It is not a rewrite. The engine is good. Cleanup is about surroundings, not core.
- It is not comprehensive on everything — infrastructure and data architecture are the focus because those are the areas most likely to hide silent bugs (as today proved).

---

**Next:** Claude Code runs the audit tasks in `SESSION_68_AUDIT_TASKS.md` and produces `docs/AUDIT_REPORT.md`. I read that in the next session and we plan cleanup execution.
