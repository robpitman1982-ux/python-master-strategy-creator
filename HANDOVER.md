# HANDOVER.md — Session Continuity Document
# Last updated: 2026-04-18 (Session 66: Gen 9 decommissioned; C240 commissioned as new workhorse)
# Auto-updated by Claude at end of each session, pushed to GitHub

---

## Current State

### Live Trading
- **Portfolio #3 EA** deployed on Contabo VPS (89.117.72.49, Windows Server, US East)
  - Strategies: NQ Daily MR + YM Daily Short Trend + GC Daily MR + NQ 15m MR (all 0.01 lots)
  - First live trade confirmed: YM Daily Short Trend, SELL US30
  - Projected: 99.6% pass rate, 6.9% DD, ~13.4 months to fund
- **Portfolio #1 EA** also live on same VPS
- **The5ers** account 26213568 on FivePercentOnline-Real (MT5), $5K High Stakes
- **MT5 on Contabo:** Hedge mode working ✅, CFD symbols available, portfolio running

### CFD Data Pipeline (Session 65 — NEW)
- **Architecture decision:** Dukascopy tick data for strategy discovery (deep history, 2003+), The5ers tick data for execution validation (real spreads)
- **Dukascopy strategies are portable** across all CFD prop firms, not just The5ers
- **Pipeline:** TDS Metatrader exports (Dukascopy via Tick Data Suite) -> `scripts/convert_tds_to_engine.py` -> TradeStation-format CSVs -> engine sweep -> MT5 Strategy Tester validation
- **Format converter built (Session 65):** `scripts/convert_tds_to_engine.py` handles 24 markets, 5 timeframe codes, verified with OHLC exact match. 26 tests passing.
- **Engine loader updated:** `load_tradestation_csv()` now recognizes "Vol" column header from converted Dukascopy files
- **24 CFD market configs:** `configs/cfd_markets.yaml` with engine params, cost profiles, OOS split dates
- **Local sweep infrastructure:** `run_local_sweep.py` (single market) + `run_cluster_sweep.py` (batch orchestrator with resume) + `scripts/generate_sweep_configs.py` (24 configs generated in `configs/local_sweeps/`)
- **TDS export location (Latitude):** `C:\Users\Rob\Downloads\Tick Data Suite\Dukascopy\`
- **TDS symbol naming:** `{SYMBOL}_GMT+0_NO-DST_{TIMEFRAME}.csv` (e.g., `USA_500_Index_GMT+0_NO-DST_H1.csv`)
- **Converted data files:** 15 files available for ES (5 TFs), AD (2 TFs), NZDUSD (5 TFs) — rest pending TDS export
- **dukascopy-python** v4.0.1 installed on Gen 9 (for raw tick downloads, separate from TDS path)
- **SP500 Dukascopy download COMPLETE** — 3.4GB, 2012-01 through 2026-04 (bid + ask parquets), stored at `/data/dukascopy/raw_ticks/sp500/` on Gen 9
- **Gen 9 storage ready:** `/data/dukascopy/raw_ticks/` and `/data/dukascopy/ohlc_bars/` created, 437 GB free
- **Gen 9 new data target:** `/data/market_data/dukascopy/` for converted CSVs
- **The5ers MT5 tick exports** (manual via Ctrl+U -> Ticks -> Export, saved to `Z:\market_data\mt5_ticks\`):
  - SP500: 3.1 GB, 76.5M ticks from 2022-05-23
  - NAS100: 10.6 GB, 245.8M ticks from 2022-05-23
  - US30 through UK100: in progress (manual export)
  - XAUUSD: only 5 days of data on The5ers — useless for backtesting, need Dukascopy
- **The5ers tick data depth varies wildly:** indices have ~4 years, XAUUSD has 5 days, FX unknown

### Home Lab Infrastructure

#### Lenovo Latitude (desktop-k2u9o61) — MAIN CONTROL & DEVELOPMENT MACHINE
- Windows 10 Pro, Tailscale 100.79.72.125
- Rob's primary laptop for scripting, development, and project building
- Used at home AND in the field — this is where Rob works day-to-day
- **Modern Standby disabled** (registry: PlatformAoAcOverride=0) — prevents random wake/sleep issues
- OpenSSH Server installed, key auth working, firewall port 22 open
- **Google Drive for Desktop** installed, syncing "Google Drive - Master Strat Creator" folder
- **Z: drive** mapped to `\\192.168.68.69\data` (Gen 9 Samba, creds: rob/Ubuntu123.)
- **rclone** installed via winget (used for headless OAuth token generation)
- **MT5** installed, connected to The5ers (Hedge mode) — used for manual tick data exports

#### X1 Carbon (desktop-2kc70vg) — ALWAYS-ON NETWORK HUB
- Windows 10 Pro, IP 192.168.68.70, Tailscale 100.86.154.65
- In a drawer, lid down, permanently connected to home LAN
- Always-on Claude.ai + Desktop Commander endpoint
- SSH config at C:\Users\rob_p\.ssh\config with aliases: gen9, gen9-ts, gen8, gen8-ts, homepc, contabo
- WOL scripts: wake-gen9.bat, wake-gen8.bat, wake-all.bat in C:\Users\rob_p\
- Port 22 firewall opened for inbound SSH
- **Google Drive for Desktop** installed, syncing "Google Drive - Master Strat Creator" folder
- **Samba drive** mapped to `\\192.168.68.69\data`
- **Back online** (2026-04-14) — power supply had died, replaced

#### Gen 9 (DL360, dl360g9) — DECOMMISSIONED (Session 66)
- **Decommissioned 2026-04-18.** Role transferred to C240 (see below).
- 12TB SAS drive array moved to C240. E5-2673 v4 CPUs (that were pending install) moved to C240.
- Tailscale alias `100.121.107.49` still listed — remove from Tailscale admin when convenient.
- Old Samba shares `\\192.168.68.69\*` OFFLINE. Latitude Z: drive will fail to mount until remapped to c240.

#### Cisco C240 M4 (c240) — ALWAYS-ON DATA HUB + COMPUTE (Gen 9 replacement)
- Ubuntu 24.04.4 LTS, kernel 6.8.0-110, hostname `c240`
- **LAN IP:** 192.168.68.53/22 on eno1 (DHCP)
- **Tailscale IP:** 100.120.11.35 (device name `c240-1` in tailnet — old `c240` at 100.104.66.48 is a stale entry, clean up in admin console)
- **CPU:** 2× Xeon E5-2673 v4 @ 2.3 GHz = **40 cores / 80 threads** (Broadwell, v4) ✅
- **RAM:** 64 GB (2× 32 GB DDR4-2400 RDIMM), 62 GiB usable
- **Storage:** 10.9 TB SAS array on LSI MegaRAID SAS-3 3108 (inherited from Gen 9)
- **LVM layout:**
  - `ubuntu-vg` (11 173 GiB total)
  - `/` → `ubuntu-lv` 100 GB (11 GB used)
  - `/data` → `data-lv` **10 TiB ext4** (UUID `95cd8cf3-d070-447a-bc1f-f18d3800ad18`, fstab-persisted)
  - VG headroom: 834 GiB free for snapshots/growth
- **NICs:** 2× Cisco VIC (10G) + 6× Intel i350 Gigabit
- **CIMC:** management controller reset to factory defaults, set to DHCP/dedicated port; MAC `00:A3:8E:8E:B3:84`, CIMC IP TBD (needs separate setup)
- **Credentials:** `rob` / `Ubuntu123` (system + Samba); NOPASSWD sudo via `/etc/sudoers.d/rob-nopasswd`
- **SSH:** key auth working (Latitude `id_ed25519` in `~/.ssh/authorized_keys`); alias `c240` in `C:\Users\Rob\.ssh\config`
- **Tailscale 1.96.4** installed and authed as `robpitman1982@`
- **Samba:** `smbd`/`nmbd` enabled; share `[photos]` → `/data/photos`, valid users `rob`
  - Default `/etc/samba/smb.conf` backed up to `/etc/samba/smb.conf.orig`
- **NOT YET MIGRATED from Gen 9:** leaderboards, sweep_results, market_data, configs, portfolio_outputs, rclone gdrive backup cron, dukascopy data, post_sweep.sh, ssh-recover.service, auto-shutdown behaviour (c240 is always-on, so not needed)

#### Gen 8 (DL380p, dl380p) — COMPUTE WORKER (SLEEPS WHEN IDLE)
- Ubuntu 24.04, IP 192.168.68.71, Tailscale 100.76.227.12, iLO 192.168.68.76
- MAC: ac:16:2d:6e:74:2c
- **CPU upgrade: 2× E5-2697 v2 **ARRIVED** ✅ (12C/24T each @ 2.7GHz, turbo 3.5GHz). **Install tomorrow (under house).** 
- BIOS: HP P70 (Feb 2014) — supports E5-2697 v2 ✅, no update needed
- **RAM: DDR3 ECC RDIMM** — NOT DDR4! Cannot share DIMMs with Gen 9 or R630.
- SSH enabled at boot, key auth, WOL persistent via netplan
- ssh-recover.service (25s delayed restart), root crontab SSH fallback (45s)
- Auto-shutdown 30min idle (cron), ARP flush on boot (cron)
- iLO power restore: Always Power On (set via ipmitool chassis policy always-on)
- iLO was on wrong subnet (192.168.20.233), FIXED to 192.168.68.76
- Duplicate netplan FIXED (removed 50-cloud-init.yaml DHCP conflict)
- **rsync to Gen 9 TESTED AND WORKING**
- **post_sweep.sh deployed** at `/usr/local/bin/post_sweep.sh`
- **ISSUE: SSH may take 5+ min to come up after reboot (slow BIOS POST). Not a config problem.**
- SSH config has alias to gen9

#### Dell R630 — COMPUTE WORKER (SLEEPS WHEN IDLE)
- Ubuntu 24.04.4 LTS, hostname: r630, IP 192.168.68.78, Tailscale 100.85.102.4
- Credentials: rob / Ubuntu123 (same as cluster)
- SSH key auth working (Latitude key), SSH alias: `r630`
- **Storage:** 838 GB SSD, LVM expanded to 823 GB root volume (778 GB free)
- System updated, packages: htop, iotop, net-tools, curl, wget, git, python3-pip, Tailscale installed
- SSH service configured (socket disabled, service enabled) — same pattern as Gen 8/Gen 9
- NOPASSWD sudoers set for rob
- `ssh-recover.service` enabled, auto-shutdown cron (30 min idle), ARP flush + SSH fallback @reboot crons
- WOL: MAC **ec:f4:bb:ed:bf:00** (eno1), netplan wakeonlan set, `wake-r630.bat` on Latitude
- `post_sweep.sh` deployed at `/usr/local/bin/post_sweep.sh`
- Gen 9 SSH alias `r630` pointing to 192.168.68.78, Gen 9 key authorised on r630 ✅
- **FULLY CONFIGURED** — ready to run sweeps

#### Cisco C240 M4 — AUTONOMOUS AGENT SERVER (ALWAYS ON)
- Ubuntu 24.04, hostname: c240, **static IP 192.168.68.79** (netplan configured), Tailscale 100.104.66.48
- Credentials: rob / Ubuntu123, SSH alias: `c240`
- **Purpose: Standalone autonomous agent/Hermes server — NOT part of backtest cluster**
- Runs 24/7 on passive income projects: Amazon affiliate, AI agents, autonomous workflows
- **Storage:** 118GB SSD, LVM expanded to 115GB root (97GB free)
- System updated, packages: htop, curl, wget, git, python3 3.12, pip, venv, nodejs 18, npm, Docker 29.1.3
- Docker enabled and running, rob added to docker group
- SSH service configured (socket off, service on), ssh-recover.service enabled
- NOPASSWD sudoers set, WOL via netplan (eno1)
- Tailscale operator set for rob (no sudo needed for tailscale)
- **FULLY CONFIGURED ✅**
- MegaRAID note: required virtual drive creation (RAID 0) + Fast Initialization in BIOS before Ubuntu could see disk

#### Pending Hardware
- **Dell R730 on eBay** (service tag 3TW3T92, Oakleigh VIC, $500 bid / $1000 BIN) — specs unknown, asked seller for CPU/RAM info. Mfg Jan 2016 (v3 Xeon era). NO HARD DRIVES. Don't bid without knowing specs.
- **RAM needed:** DDR4 ECC RDIMM 32GB sticks for Gen 9 (match 2Rx4 DDR4-2400 or faster). DDR3 for Gen 8.
- **Skip:** Anything DDR3 for Gen 9/R630. Only DDR4 ECC RDIMM.

### Network
- **New ISP:** Carbon Comms, 500/50 Mbps NBN, **static IP** (being connected)
- **Router:** XE75 Pro at 192.168.68.1
- Static IP enables: direct SSH from field, Hermes webhooks, dashboard access, Contabo push-to-home
- Recommendation: Keep Tailscale as primary remote access. Use static IP for specific services only.

### Cloud Infrastructure (DEPRECATED — migrating to local cluster)
- **GCP (Nikola's account):** project-c6c16a27-e123-459c-b7a, console IP 35.223.104.173
  - n2-highcpu-96, 100 vCPU quota cap (upgrade denied)
  - Bucket: gs://strategy-artifacts-nikolapitman/
  - Migrated from old GCP account (project-813d2513) in Session 56 after $424 credit exhausted
- **Status: DEPRECATED.** Local sweep infrastructure built in Session 65. Cloud files (`cloud/`, `run_spot_resilient.py`, `run_cloud_sweep.py`) pending manual deletion once local sweeps proven.
- **Strategy console** (strategy-console-2, 35.223.104.173) can be decommissioned after dashboard migrated to local

### Strategy Engine Status
- **Ultimate leaderboard:** ~454 strategies (414 bootcamp-accepted) across 8 markets (ES, CL, NQ, SI, HG, RTY, YM, GC)
- **Vectorized engine:** 14-23x speedup, zero-tolerance parity confirmed. All configs use `use_vectorized_trades: true`
- **12 strategy families:** 3 long (trend, MR, breakout) + 3 short + 9 subtypes (3 per family)
- **Portfolio selector:** 6-stage pipeline with 3-layer correlation, block bootstrap MC, regime survival gate
- **Prop firm system:** Bootcamp, High Stakes, Pro Growth, Hyper Growth — all with daily DD enforcement
- **CFD sweep infrastructure (Session 65):**
  - `run_local_sweep.py` — single-market local sweep runner (replaces GCP cloud runners)
  - `run_cluster_sweep.py` — batch orchestrator with manifest tracking + resume support
  - `configs/cfd_markets.yaml` — 24 CFD market configs with engine params + cost profiles
  - `configs/local_sweeps/` — 24 generated per-market sweep configs (all 5 timeframes each)
  - `scripts/convert_tds_to_engine.py` — TDS Metatrader CSV -> TradeStation format converter
  - `scripts/generate_sweep_configs.py` — generates sweep configs from market master config
- **CFD swap rates gathered:** CL=$0.70/micro/night (10x Fri!), SI=$4.05, GC=$2.20, indices near-zero, FX $0.10-0.26
- **Cloud services deprecated:** GCP SPOT runner (`run_spot_resilient.py`), GCP launcher (`launch_gcp_run.py`), cloud configs (`cloud/`) — all pending deletion once local sweeps proven. Do NOT delete yet.
- **SPOT runner bug (legacy):** VMs launched from Claude sessions used on-demand instead of SPOT. No longer relevant — sweeps moving to local cluster.

---

## Open Issues (Priority Order)

1. **Export remaining TDS data.** Only ES, AD, NZDUSD exported via Tick Data Suite. Need to export all 24 markets x 5 timeframes. Some markets (BTCUSD, LIGHTCMDUSD, etc.) have subdirectories but no exported CSVs yet.
2. **Migrate Gen 9 data → C240.** `/data/leaderboards`, `/data/sweep_results`, `/data/market_data`, `/data/dukascopy`, `/data/configs`, `/data/portfolio_outputs` all need to be copied from Gen 9 (if still powered on) or restored from rclone/gdrive backup to `/data/` on c240. Re-create non-photos Samba shares on c240. Remap Latitude Z: drive to `\\192.168.68.53\data`.
3. **Restore services on C240.** rclone + gdrive OAuth, nightly backup cron, post_sweep.sh, ssh-recover.service, ipmitool, dukascopy-python, WOL netplan config. Gen 9 SSH alias needs to be redirected or removed.
4. **Clean up stale Tailscale device.** Old `c240` entry (100.104.66.48, last seen 7h ago) is a dead registration from the Hermes-pivot attempt — remove via Tailscale admin console.
5. **CIMC network config for C240.** Management controller is on dedicated port with DHCP but CIMC IP has not been captured/documented. `nmap -sn 192.168.68.0/22` or check router ARP for MAC `00:A3:8E:8E:B3:84`.
6. **Gen 8 CPU install pending.** 2x E5-2697 v2 arrived. Install under house, verify 48 threads. (Gen 9 CPUs went into C240 instead.)
7. **CFD swap costs NOT modeled in MC simulator.** Must implement before trusting funding timelines. Cost profiles defined in `configs/cfd_markets.yaml` but not yet consumed by portfolio selector.
8. **First local sweep validation.** Run `python run_cluster_sweep.py --markets ES --timeframes daily --dry-run` then a real single-market sweep to validate the full pipeline end-to-end.
9. **Session 61 test failure.** `test_daily_dd_breach` needs updating for pause-vs-terminate daily DD change.
10. **Dashboard Live Monitor broken.** Engine log and Promoted Candidates sections don't work during active runs.
11. **Cloud decommission.** Once local sweeps proven: delete `cloud/`, `run_spot_resilient.py`, `run_cloud_sweep.py`, strategy-console VM. Keep `download_run.py` for existing results access.

---

## Project History (Sessions 0-62)

### Phase 1: Foundation (Sessions 0-5, Mar 16-18 2026)
- **Session 0:** Project review, first ES 60m run analyzed (trend REGIME_DEPENDENT, MR STABLE, breakout BROKEN_IN_OOS), created CLAUDE.md
- **Session 1:** Quality scoring (0-1 continuous), BORDERLINE detection, promotion gate capped at 20, compute budget estimator, candidate dedup
- **Session 2:** Config.yaml (single source of truth), yearly consistency analysis, multi-dataset loop support, OOS split date configurable
- **Session 3:** Cloud deployment prep — Dockerfile, requirements.txt, DigitalOcean run scripts, Sydney region
- **Session 4:** Structured logging (ProgressTracker + status.json), cloud launcher timeout fix
- **Session 5:** 11 smoke tests, master leaderboard aggregator, timeframe-aware refinement grids (hold_bars auto-scales)

### Phase 2: Cloud Infrastructure (Sessions 6-14, Mar 18-21 2026)
- **Session 6:** Hybrid filter parameter scaling (SMA/ATR/momentum scale per timeframe), 48-core cloud config, memory estimation
- **Session 7:** Prop firm challenge simulator — The5ers Bootcamp/HighStakes/HyperGrowth configs, Monte Carlo pass rate
- **Session 8:** CRITICAL BUG FIX — portfolio evaluator now passes timeframe to feature builders. GCP automation scripts created.
- **Session 9:** 10 GCP automation bugs fixed (SCP paths, race conditions, username detection). Streamlit dashboard created.
- **Session 10:** GCP download reliability — dynamic username via `whoami`, tar fallback, safety gate (refuse destroy if 0 files)
- **Session 11:** Windows-first GCP launcher redesign (`cloud/launch_gcp_run.py`) — manifest, bundle, deterministic paths, tarball retrieval
- **Session 13:** Dashboard upgrade — VM cost visibility, dataset progress, best candidates panel, result source grouping
- **Session 14:** One-click `run_cloud_sweep.py` wrapper, `LATEST_RUN.txt` pointer

### Phase 3: Multi-Timeframe & Quality (Sessions 21-34, Mar 23-26 2026)
- **Session 21:** Migrated from Australia to US regions (better SPOT pricing), zone/machine configurable via YAML `cloud:` section
- **Session 22:** Fixed remote Python bootstrap (python3.12 explicit for venv creation)
- **Session 24:** Dashboard overhaul — 3-tab layout (Control Panel, Results Explorer, System), plotly charts
- **Session 33:** Pre-flight validation, vectorized filter status check (not yet implemented)
- **Session 34:** CRITICAL FIX — GCS bundle staging for fire-and-forget mode (43MB SCP was hitting SPOT preemption window)
- **Session 35:** Multi-VM split (VM-A + VM-B), `download_run.py` with merge and ultimate leaderboard

### Phase 4: Strategy Expansion (Sessions 37-45, Mar 26-29 2026)
- **Session 37:** 9 strategy subtypes (3 per family), leaderboard enriched with calmar/win_rate/trades_per_year
- **Session 38:** Cross-dataset portfolio evaluation — all accepted strategies evaluated together, cross-TF correlation matrix
- **Session 39:** Short-side strategies (15 new filters, 3 short families), direction wired through engine
- **Session 40:** Per-timeframe dataset caching, concurrent small-family execution, exit types verified active in refinement
- **Session 41:** Widened exit grids — trend trailing_stop_atr up to 7.0, breakout up to 5.0, MR profit_target up to 3.0
- **Session 42:** 7 universal filters (InsideBar, OutsideBar, GapUp/Down, ATRPercentile, HigherHigh, LowerLow), dropped 5m (zero accepted)
- **Session 43:** Shared ProcessPoolExecutor across families, optional portfolio evaluation, granular status stages
- **Session 44:** Refinement as_completed() (30%→80%+ CPU), task dedup before dispatch
- **Session 45:** CRITICAL BUG FIX — position sizing used current_capital (compounding) instead of initial_capital. All dollar figures were wrong.

### Phase 5: Portfolio Selection (Sessions 47-53, Mar 31 2026)
- **Session 47:** Portfolio selector module — 6-stage pipeline with C(n,k) sweep, Pearson correlation gate, MC pass rate, sizing optimizer
- **Session 48:** Rebuild fix (fallback to filter_class_names), parallelized evaluator, MC step rate bug fix
- **Session 49:** Rebuild 0-trade root cause (min_avg_range misused as filter param), all 20/20 market/TF combos verified
- **Session 50:** Portfolio MC fixes — step rate mixing, daily-resampled trades, correlation dedup, micro contract sizing, time-to-fund
- **Session 51:** Portfolio overhaul — OOS PF threshold lowered, sizing optimizer minimizes time-to-fund, strategy_trades.csv
- **Session 52:** Multi-program prop firm (per-step targets, daily DD enforcement, Pro Growth config, configurable program selector)
- **Session 53:** Parallelized generate_returns.py with ThreadPoolExecutor + data file caching

### Phase 6: Cloud Migration & Advanced MC (Sessions 56-62, Apr 2-4 2026)
- **Session 56:** Migrated to new GCP account (Nikola), new console VM, bucket, SSH keys
- **Session 58:** Portfolio selector upgrades — 3-layer correlation, Expected Conditional Drawdown, block bootstrap MC, regime survival gate
- **Session 59:** Bulletproof SPOT runner (`run_spot_resilient.py`), 9 new market configs (EC, JY, BP, AD, NG, US, TY, W, BTC)
- **Session 60:** Vectorized portfolio MC (numpy 2D arrays), parallel combinatorial sweep, multi-program runner
- **Session 61:** Vectorized trade simulation loop (14-23x speedup, zero-tolerance parity), prop firm config fixes (daily DD pause vs terminate)
- **Session 62:** Repo reorganization for Claude Desktop compatibility, archived 93 session files + 60 temp dirs, fixed .gitignore

### Phase 7: Local Cluster & CFD Pipeline (Sessions 63-66, Apr 14-18 2026)
- **Session 63:** Dukascopy architecture decision, SP500 tick download, The5ers MT5 exports, home lab network setup
- **Session 65:** CFD data pipeline built end-to-end: TDS format converter (24 markets), engine loader "Vol" support, 24 CFD market configs, local sweep runner, batch cluster sweep launcher with resume, config generator (24 sweep YAMLs). Cloud infrastructure deprecated.
- **Session 66 (2026-04-18):** Gen 9 decommissioned. Cisco C240 M4 commissioned as new always-on workhorse at 192.168.68.53. 2× E5-2673 v4 (40C/80T), 64 GB RAM, 10.9 TB SAS (ex-Gen 9 drives). Ubuntu 24.04.4, LVM layout: / 100 GB + /data 10 TiB ext4 + 834 GiB VG headroom. SSH key auth, NOPASSWD sudo, Tailscale 100.120.11.35 (device name c240-1), Samba [photos] share live. Initial Hermes plan on C220/old-c240 abandoned mid-session due to MegaRAID drive visibility issue — pivoted to this C240 hardware. Gen 9 data migration and non-photos Samba shares still pending.

### Key Architectural Decisions Made Along the Way
- **Fixed position sizing** (Session 45): initial_capital only, no compounding — matches prop firm rules
- **Dropped 5m timeframe** (Session 42): zero accepted strategies, ~50% of compute cost
- **Fire-and-forget via GCS** (Session 34): bundle staged to GCS before VM creation, eliminates SCP preemption window
- **Vectorized trades** (Session 61): numpy 2D arrays replace per-bar Python loop, 14-23x faster
- **Block bootstrap MC** (Session 58): preserves crisis clustering vs naive shuffle
- **3-layer correlation** (Session 58): active-day + DD-state + tail co-loss replaces simple Pearson
- **Dukascopy for discovery, The5ers for validation** (Session 63): tick data architecture separates strategy discovery (deep Dukascopy history) from execution validation (The5ers real spreads)
- **Local cluster replaces cloud** (Session 65): `run_local_sweep.py` + `run_cluster_sweep.py` replace GCP SPOT runners. Zero cloud dependencies. ~216 threads available locally (Gen 9: 80, Gen 8: 48, R630: 88).

---

## Architecture Decision: Compute Cluster

```
Latitude (main control, home + field, SSH via Tailscale)
    │
    ├──► X1 Carbon (always-on, in drawer, Claude + Desktop Commander)
    │        └── SSH relay to all servers
    │
    ├──► C240 M4 (ALWAYS ON — data hub + compute, 80 threads — Gen 9 replacement)
    │     ├── holds master/ultimate leaderboards (local 10 TiB /data)
    │     ├── holds market data — TradeStation, MT5 ticks, Dukascopy ticks
    │     ├── Samba share to X1 Carbon + Latitude (photos live, data shares pending migration)
    │     ├── rclone → Google Drive (pending setup)
    │     ├── receives sweep results from Gen 8 / R630 via rsync (pending)
    │     ├── runs leaderboard updater + portfolio selector
    │     └── wakes Gen 8 / R630 via WOL when compute needed
    │
    ├──► Gen 8 (SLEEPS WHEN IDLE — compute worker, 48 threads after CPU upgrade)
    │     └── woken by Latitude / X1 Carbon / C240 via WOL
    │
    └──► R630 (SLEEPS WHEN IDLE — compute worker, 88 threads)
          └── woken by Latitude / X1 Carbon / C240 via WOL
```

- **Google Drive is backup/remote viewing ONLY — never used for compute reads**
- Market data + leaderboards stay on local SSD/SAS for speed
- Workers crunch sweeps, rsync results to C240 over LAN
- Portfolio selector runs on C240 (or R630), reads from local SAS
- C240 NEVER sleeps. Workers sleep when idle.

---

## Compute Rental Side Hustle (Future — Post Trading Stable)

**Concept:** Rent idle cluster compute to retail quants, ML students, researchers.

**Two tiers:**
- Tier 1: Raw CPU rental ($0.04 AUD/thread-hour), fully automated, no support
- Tier 2: Managed QuantSweep Service — customer uploads strategy, gets results in 24hrs, higher margin

**Economics:** 240 threads, $3.20 AUD/day electricity, ~$2K AUD/month net at 30-40% utilisation. Scalable — each $350 server adds ~60 threads, pays for itself in 6 weeks. Tax deductible capex.

**Implementation order:**
1. VLAN isolation — rental network must be completely separate from MT5/trading network (security critical)
2. Docker containerisation — customer code can't break out to host
3. Best-effort SLA (no liability for interruptions)
4. Python job queue + Stripe payments + AI chatbot support
5. Beta: 3 customers at discount, 3 months, then go public

**Positioning:** "Quant Sweep Infrastructure as a Service" — not generic compute rental
**Timeline:** Start after trading stable and generating. ~2 weeks setup, month 3 launch.

---



## On the Horizon

- **Export all TDS data** — run Tick Data Suite exports for remaining 21 markets (24 total - 3 done). Each market needs 5 timeframes (D1, H1, M30, M15, M5). Then run converter: `python scripts/convert_tds_to_engine.py --input-dir "C:/path/to/exports/" --output-dir Data/`
- **Migrate Gen 9 data to C240** — copy `/data/*` from Gen 9 (or restore from gdrive) to c240 `/data/`. Rebuild non-photos Samba shares. Remap Latitude Z: drive to `\\192.168.68.53\data`.
- **Restore C240 services** — rclone + gdrive OAuth + nightly backup cron, post_sweep.sh, ssh-recover.service, ipmitool, dukascopy-python, WOL netplan.
- **Capture C240 CIMC IP** — CIMC is on DHCP via dedicated port, IP not yet documented. Check router ARP for MAC `00:A3:8E:8E:B3:84`.
- **Clean up stale Tailscale `c240` device** (100.104.66.48, offline 7h) via admin console.
- **Gen 8 CPU install** — 2x E5-2697 v2 arrived, install under house, verify 48 threads.
- **First local sweep** — `python run_cluster_sweep.py --markets ES --timeframes daily` to validate full pipeline
- **Copy converted CSVs to C240** — `scp Data/*_dukascopy.csv c240:/data/market_data/dukascopy/`
- **Full 24-market sweep** — `python run_cluster_sweep.py` (all markets, all timeframes) on C240
- Implement CFD swap/overnight cost modeling in MC simulator (cost profiles in `configs/cfd_markets.yaml`)
- **Challenge vs Funded mode** — implement spec in `CHALLENGE_VS_FUNDED_SPEC.md` (recency weighting, cost profiles, mode-specific scoring)
- **Cloud decommission** — delete cloud/ directory, run_spot_resilient.py, run_cloud_sweep.py, strategy-console VM
- Static IP port forwarding setup once new ISP connected
- Hermes Agent on C240 for monitoring/alerting (Linux native, Telegram gateway)
- Strategy templates to reduce search space

---

## Connection Quick Reference

```
# SSH aliases (from Latitude or X1 Carbon)
ssh c240          # Cisco C240 M4 — LAN 192.168.68.53, Tailscale 100.120.11.35 (device name c240-1)
ssh gen8          # Gen 8 Tailscale (100.76.227.12)
ssh r630          # Dell R630 Tailscale (100.85.102.4) — backtest cluster
ssh x1            # X1 Carbon Tailscale (100.86.154.65)
# ssh gen9        # DECOMMISSIONED Session 66

# Samba shares (user: rob, password: Ubuntu123)
\\192.168.68.53\photos         # C240 photos share (10 TiB /data/photos)
# \\192.168.68.69\*            # DECOMMISSIONED with Gen 9 — remap Latitude Z: drive
# Non-photos shares (leaderboards/sweep_results/market_data/configs/data) pending migration to c240

# WOL (from Latitude)
C:\Users\Rob\wake-r630.bat      # MAC ec:f4:bb:ed:bf:00
C:\Users\Rob\wake-gen8.bat      # MAC ac:16:2d:6e:74:2c (on X1 Carbon)

# Server creds: rob / Ubuntu123 (all servers)
# C240 sudo: NOPASSWD via /etc/sudoers.d/rob-nopasswd
# GCP SSH: ssh -i C:\Users\Rob\.ssh\google_compute_engine pitman_nikola@35.223.104.173

# Sweep results pipeline (run on worker after sweep):
# post_sweep.sh <sweep_output_dir>   # rsync to C240 (pending migration), trigger leaderboard update

# rclone backup — pending migration from Gen 9 to C240

# iLO / CIMC access
# Gen 9 iLO: DECOMMISSIONED Session 66
Gen 8 iLO: https://192.168.68.76 (old SSL - use Firefox, creds unknown)
R630 LAN:  192.168.68.78, Tailscale 100.85.102.4, MAC ec:f4:bb:ed:bf:00
C240 CIMC: on dedicated port via DHCP, MAC 00:A3:8E:8E:B3:84, IP TBD — username admin, password Ubuntu123
```

## Key Principles
- Always use Desktop Commander before Windows MCP (Windows MCP hangs)
- Full fixes only — no patches
- Drawdown is the binding constraint on The5ers
- Skip DDR3 servers (R710, R610) — only R630/R730 and above
- Gen 8 uses DDR3 RAM, Gen 9 and R630 use DDR4 — do NOT mix
- SPOT zone: us-central1-f; on-demand fallback: us-central1-c
- Always use `run_spot_resilient.py` from strategy-console for SPOT sweeps — never launch manually
- Dukascopy for strategy discovery, The5ers tick data for execution cost validation
