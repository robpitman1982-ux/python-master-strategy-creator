# HANDOVER.md — Session Continuity Document
# Last updated: 2026-04-16 (Session: R630 fully configured, c240 Ubuntu install, Gen9 CPU arrival, SP500 Dukascopy complete)
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

### CFD Tick Data Pipeline
- **Architecture decision:** Dukascopy tick data for strategy discovery (deep history, 2003+), The5ers tick data for execution validation (real spreads)
- **Dukascopy strategies are portable** across all CFD prop firms, not just The5ers
- **Pipeline:** Dukascopy ticks → tick-to-bar converter (with spread stats) → engine OHLC CSVs → sweep → MT5 Strategy Tester validation
- **dukascopy-python** v4.0.1 installed on Gen 9 ✅
- **Dukascopy symbol mapping (confirmed):** EUR/USD, USD/JPY, GBP/USD, AUD/USD, XAU/USD, XAG/USD, BTC/USD, ETH/USD, E_NQ-100, E_DAAX, E_Futsee-100, E_N225Jap
- **Dukascopy symbol mapping (MISSING — need investigation):** US30 (YM), WTI crude (CL)
- **SP500 Dukascopy download COMPLETE ✅** — 3.4GB, 2012-01 through 2026-04 (bid + ask parquets), stored at `/data/dukascopy/raw_ticks/sp500/` on Gen 9
- **Gen 9 storage ready:** `/data/dukascopy/raw_ticks/` and `/data/dukascopy/ohlc_bars/` created, 437 GB free
- **The5ers MT5 tick exports** (manual via Ctrl+U → Ticks → Export, saved to `Z:\market_data\mt5_ticks\`):
  - SP500: ✅ 3.1 GB, 76.5M ticks from 2022-05-23
  - NAS100: ✅ 10.6 GB, 245.8M ticks from 2022-05-23
  - US30 through UK100: in progress (manual export)
  - XAUUSD: only 5 days of data on The5ers — useless for backtesting, need Dukascopy
- **The5ers tick data depth varies wildly:** indices have ~4 years, XAUUSD has 5 days, FX unknown

### Home Lab Infrastructure

#### Lenovo Latitude (desktop-k2u9o61) — MAIN CONTROL & DEVELOPMENT MACHINE
- Windows 10 Pro, Tailscale 100.79.72.125
- Rob's primary laptop for scripting, development, and project building
- Used at home AND in the field — this is where Rob works day-to-day
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

#### Gen 9 (DL360, dl360g9) — ALWAYS-ON DATA HUB + COMPUTE
- Ubuntu 24.04, IP 192.168.68.69, Tailscale 100.121.107.49, iLO 192.168.68.75
- MAC: ec:eb:b8:97:83:00
- **ALWAYS ON.** ~$15-20/mo power. Auto-shutdown cron REMOVED
- SSH enabled at boot, key auth, WOL persistent via netplan
- ssh-recover.service (25s delayed restart), root crontab SSH fallback (45s)
- ARP flush on boot (cron)
- iLO power restore: Always Power On (set via iLO web UI AND ipmitool)
- ipmitool installed
- **CPU:** 2× E5-2673 v4 **ARRIVED** ✅ (20C/40T each @ 2.3GHz, turbo 3.5GHz). **Install tomorrow (under house).** Currently still running 1× E5-2603 v4.
- BIOS: HP P89 (Oct 2017) — supports E5-2673 v4 ✅, no update needed
- **RAM:** 1× 32GB DDR4-2400 ECC RDIMM 2Rx4 (HP 809083-091) in PROC 1 DIMM 12. **23 of 24 slots empty.** PROC 2 slots only available once second CPU installed.
- **Storage:** 7.3 TB disk, root LV extended to 500 GB (437 GB free), photos LV 3.0 TB, VG has 3.79 TiB free
- **REBOOT TEST PASSED** (2026-04-14): SSH, Samba, Tailscale, all data dirs survived
- **Data hub directories on root SSD:**
  - `/data/leaderboards/` — ultimate_leaderboard.csv + bootcamp (760KB)
  - `/data/sweep_results/runs/` — all sweep output runs (2.1GB)
  - `/data/market_data/` — 81 TradeStation CSVs (2.2GB) + mt5_ticks/ (The5ers exports)
  - `/data/dukascopy/raw_ticks/` — Dukascopy tick data (empty, ready for download)
  - `/data/dukascopy/ohlc_bars/` — converted OHLC bars for engine (empty, ready)
  - `/data/configs/` — 64 cloud config YAMLs + post_sweep.sh
  - `/data/portfolio_outputs/` — portfolio selector outputs
- **Samba shares** (user: rob, password: Ubuntu123.):
  - `\\192.168.68.69\data` — parent share (all strategy data)
  - `\\192.168.68.69\leaderboards`, `\\192.168.68.69\sweep_results`, `\\192.168.68.69\market_data`, `\\192.168.68.69\configs`
  - `\\192.168.68.69\photos` — 3TB LVM volume
  - Latitude mapped as Z: drive, X1 Carbon mapped
- **rclone** v1.60.1 installed, **OAuth authorized**, remote name: `gdrive`
- rclone backup script: `/usr/local/bin/rclone_backup.sh` — syncs leaderboards + sweep_results + portfolio_outputs
- rclone nightly cron: `0 2 * * *` in rob's crontab
- **dukascopy-python** v4.0.1 installed (pip3, --break-system-packages)
- SSH config has alias to gen8

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

#### Cisco C240 M4 — IN PROGRESS (COMPUTE WORKER)
- Ubuntu 24.04 install in progress (garage, April 16)
- Samsung SSD 118GB — MegaRAID 12G SAS controller requires virtual drive creation (RAID 0 single disk) + Fast Initialization before Ubuntu installer can see disk
- Hostname: c240, credentials: rob / Ubuntu123
- **TODO:** Complete Ubuntu install, SSH key push, full config (same as R630 process)
- MegaRAID note: always create virtual drive in BIOS before attempting Ubuntu install

#### HP ProLiant c240 (Hermes) — PENDING SETUP (COMPUTE WORKER)
- Ubuntu 24.04 install planned — same process as R630
- Will use same creds (rob / Ubuntu123), same SSH/Tailscale/WOL/post_sweep pattern
- Setup deferred to next session when Rob returns home

#### Pending Hardware
- **Dell R730 on eBay** (service tag 3TW3T92, Oakleigh VIC, $500 bid / $1000 BIN) — specs unknown, asked seller for CPU/RAM info. Mfg Jan 2016 (v3 Xeon era). NO HARD DRIVES. Don't bid without knowing specs.
- **RAM needed:** DDR4 ECC RDIMM 32GB sticks for Gen 9 (match 2Rx4 DDR4-2400 or faster). DDR3 for Gen 8.
- **Skip:** Anything DDR3 for Gen 9/R630. Only DDR4 ECC RDIMM.

### Network
- **New ISP:** Carbon Comms, 500/50 Mbps NBN, **static IP** (being connected)
- **Router:** XE75 Pro at 192.168.68.1
- Static IP enables: direct SSH from field, Hermes webhooks, dashboard access, Contabo push-to-home
- Recommendation: Keep Tailscale as primary remote access. Use static IP for specific services only.

### Cloud Infrastructure
- **GCP (Nikola's account):** project-c6c16a27-e123-459c-b7a, console IP 35.223.104.173
  - n2-highcpu-96, 100 vCPU quota cap (upgrade denied)
  - Bucket: gs://strategy-artifacts-nikolapitman/
  - Migrated from old GCP account (project-813d2513) in Session 56 after $424 credit exhausted
- To be decommissioned once local lab stable

### Strategy Engine Status
- **Ultimate leaderboard:** ~454 strategies (414 bootcamp-accepted) across 8 markets (ES, CL, NQ, SI, HG, RTY, YM, GC)
- **Vectorized engine:** 14-23x speedup, zero-tolerance parity confirmed. All cloud configs updated with `use_vectorized_trades: true`
- **12 strategy families:** 3 long (trend, MR, breakout) + 3 short + 9 subtypes (3 per family)
- **Portfolio selector:** 6-stage pipeline with 3-layer correlation, block bootstrap MC, regime survival gate
- **Prop firm system:** Bootcamp, High Stakes, Pro Growth, Hyper Growth — all with daily DD enforcement
- **CFD swap rates gathered:** CL=$0.70/micro/night (10x Fri!), SI=$4.05, GC=$2.20, indices near-zero, FX $0.10-0.26
- **9 new markets** (EC, JY, BP, AD, NG, US, TY, W, BTC) — configs ready, AD 30m+15m sweep completed
- **SPOT runner bug:** VMs launched from Claude sessions used on-demand instead of SPOT. Fixed by deleting VM. Must use `run_spot_resilient.py` from strategy-console for proper SPOT provisioning.

---

## Open Issues (Priority Order)

1. **CFD swap costs NOT modeled in MC simulator.** Must implement before trusting funding timelines.
2. **Dukascopy symbol mapping incomplete.** SP500 (ES), US30 (YM), WTI crude (CL) not found in dukascopy-python constants — need to investigate raw API instrument names.
3. **Dashboard Live Monitor broken.** Engine log and Promoted Candidates sections don't work during active runs.
4. **SPOT runner needs restart.** AD daily failed after 5 preemption attempts. Remaining markets (BP, EC, JY, NG, US, TY, W, BTC) not yet started.
5. **Session 61 test failure.** `test_daily_dd_breach` needs updating for pause-vs-terminate daily DD change.
6. **Provisioning model override bug** in `launch_gcp_run.py` line 2324 — YAML `STANDARD` can override CLI `SPOT` default.
7. **Gen 9 CPU install pending.** 2× E5-2673 v4 arriving 2026-04-15. Need to swap out E5-2603 v4, install both CPUs, verify 80 threads visible.
8. **Gen 8 CPU install pending.** 2× E5-2697 v2 arriving 2026-04-15.

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

### Key Architectural Decisions Made Along the Way
- **Fixed position sizing** (Session 45): initial_capital only, no compounding — matches prop firm rules
- **Dropped 5m timeframe** (Session 42): zero accepted strategies, ~50% of compute cost
- **Fire-and-forget via GCS** (Session 34): bundle staged to GCS before VM creation, eliminates SCP preemption window
- **Vectorized trades** (Session 61): numpy 2D arrays replace per-bar Python loop, 14-23x faster
- **Block bootstrap MC** (Session 58): preserves crisis clustering vs naive shuffle
- **3-layer correlation** (Session 58): active-day + DD-state + tail co-loss replaces simple Pearson
- **Dukascopy for discovery, The5ers for validation** (Session 63): tick data architecture separates strategy discovery (deep Dukascopy history) from execution validation (The5ers real spreads)

---

## Architecture Decision: Compute Cluster

```
Latitude (main control, home + field, SSH via Tailscale)
    │
    ├──► X1 Carbon (always-on, in drawer, Claude + Desktop Commander)
    │        └── SSH relay to all servers
    │
    ├──► Gen 9 (ALWAYS ON — data hub + compute, 80 threads after CPU upgrade)
    │     ├── holds master/ultimate leaderboards (local SSD)
    │     ├── holds market data — TradeStation, MT5 ticks, Dukascopy ticks (local SSD)
    │     ├── Samba share to X1 Carbon + Latitude
    │     ├── rclone → Google Drive (backup copies only, NOT for compute reads)
    │     ├── receives sweep results from Gen 8 / R630 via rsync
    │     ├── runs leaderboard updater + portfolio selector
    │     └── wakes Gen 8 / R630 via WOL when compute needed
    │
    ├──► Gen 8 (SLEEPS WHEN IDLE — compute worker, 48 threads after CPU upgrade)
    │     └── woken by Latitude / X1 Carbon / Gen 9 via WOL
    │
    └──► R630 (SLEEPS WHEN IDLE — compute worker, 88 threads)
          └── woken by Latitude / X1 Carbon / Gen 9 via WOL
```

- **Google Drive is backup/remote viewing ONLY — never used for compute reads**
- Market data + leaderboards stay on local SSD for speed
- Workers crunch sweeps, rsync results to Gen 9 over LAN
- Portfolio selector runs on Gen 9 (or R630), reads from local SSD
- Gen 9 NEVER sleeps (~$15-20/mo power). Workers sleep when idle.

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



- ~~**Dukascopy SP500 download**~~ ✅ COMPLETE — 3.4GB, 2012-2026 on Gen 9
- **Tick-to-bar converter** — aggregate SP500 Dukascopy parquets into OHLC bars, output TradeStation-compatible CSVs (next priority)
- **Gen 9 CPU install** — 2× E5-2673 v4 arrived, install tomorrow under house, verify 40 threads per socket (80 total)
- **Gen 8 CPU install** — 2× E5-2697 v2 arrived, install same session, verify 48 threads
- **Cisco C240 Ubuntu** — complete install (in progress), then full config same as R630
- **Thermal paste** — clean heatsinks with ethyl sanitiser, apply fresh paste before CPU install
- Implement CFD swap/overnight cost modeling in MC simulator
- **HP c240 (Hermes) Ubuntu setup** — install Ubuntu 24.04, same config as R630 (SSH, Tailscale, WOL, post_sweep.sh, auto-shutdown)
- ~~Dell R630 full setup~~ ✅
- Complete MT5 manual tick exports for remaining symbols (US30, XAGUSD, XTIUSD, EURUSD, USDJPY, GBPUSD, AUDUSD, BTCUSD, ETHUSD, DAX40, JPN225, UK100)
- Hermes Agent on Gen 9 for monitoring/alerting (Linux native, Telegram gateway)
- Strategy templates to reduce search space
- Static IP port forwarding setup once new ISP connected

---

## Connection Quick Reference

```
# SSH aliases (from Latitude or X1 Carbon)
ssh gen9          # Gen 9 Tailscale (100.121.107.49)
ssh gen8          # Gen 8 Tailscale (100.76.227.12)
ssh r630          # Dell R630 Tailscale (100.85.102.4)
ssh x1            # X1 Carbon Tailscale (100.86.154.65)

# Samba shares (user: rob, password: Ubuntu123.)
\\192.168.68.69\data           # All strategy data (Z: on Latitude)
\\192.168.68.69\leaderboards   # Ultimate leaderboards
\\192.168.68.69\sweep_results  # Sweep output runs
\\192.168.68.69\market_data    # TradeStation CSVs + mt5_ticks/
\\192.168.68.69\configs        # Cloud configs + post_sweep.sh
\\192.168.68.69\photos         # 3TB photo archive

# WOL (from Latitude)
C:\Users\Rob\wake-r630.bat      # MAC ec:f4:bb:ed:bf:00
C:\Users\Rob\wake-gen8.bat      # MAC ac:16:2d:6e:74:2c (on X1 Carbon)

# Server creds: rob / Ubuntu123. (all servers, including future Dell R630)
# GCP SSH: ssh -i C:\Users\Rob\.ssh\google_compute_engine pitman_nikola@35.223.104.173

# Sweep results pipeline (run on worker after sweep):
# post_sweep.sh <sweep_output_dir>   # rsync to Gen 9, trigger leaderboard update

# rclone backup (runs nightly at 2am from Gen 9, rob's crontab)
# Manual: rclone copy /data/leaderboards gdrive:strategy-data-backup/leaderboards/ --progress
# Backup script: /usr/local/bin/rclone_backup.sh

# iLO access
Gen 9 iLO: https://192.168.68.75 (Administrator / PVPT6M5H)
Gen 8 iLO: https://192.168.68.76 (old SSL - use Firefox, creds unknown)
R630 LAN:  192.168.68.78, Tailscale 100.85.102.4, MAC ec:f4:bb:ed:bf:00
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
