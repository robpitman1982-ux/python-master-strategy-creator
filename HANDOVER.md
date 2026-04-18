# HANDOVER.md — Session Continuity Document
# Last updated: 2026-04-19 (Session 69 complete: cleanup execution — cloud deleted, configs fixed, tests green)
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
- **Provenance:** ex-corporate machine; BIOS + CIMC factory-reset at start of Session 66 (cleared VLAN 303, hostname `splcbr02-5i-rac.sge.insitec.local`, old subnet 10.254.1.x)
- **CIMC:** management controller reset to factory defaults, set to DHCP/dedicated port; MAC `00:A3:8E:8E:B3:84`, CIMC IP TBD (needs separate setup)
- **Credentials:** `rob` / `Ubuntu123` (system + Samba); NOPASSWD sudo via `/etc/sudoers.d/rob-nopasswd`
- **SSH:** key auth working (Latitude `id_ed25519` in `~/.ssh/authorized_keys`); alias `c240` in `C:\Users\Rob\.ssh\config`
- **Tailscale 1.96.4** installed and authed as `robpitman1982@`
- **Samba:** `smbd`/`nmbd` enabled; shares `[photos]` → `/data/photos`, `[data]` → `/data` (rw, force user rob)
  - Default `/etc/samba/smb.conf` backed up to `/etc/samba/smb.conf.orig`
- **Packages installed (Session 67):** `python3-venv`, `python3.12-venv`, `python3-pip`, `ipmitool`, `rclone`, `wakeonlan`, `etherwake`, `iotop`, `net-tools`, `nfs-common`, `cifs-utils`, `build-essential`, `jq`, `unzip`, `zip`
- **SSH services (Session 67):** `ssh.socket` masked, `ssh.service` enabled + active, `ssh-recover.service` installed (25s delayed restart fallback, matches Gen 8/R630 pattern)
- **ARP-flush-on-boot:** `@reboot /usr/sbin/ip -s -s neigh flush all` in root crontab
- **Repo:** `~/python-master-strategy-creator` cloned via HTTPS, HEAD tracks `origin/main`
- **Python env:** `~/venv` (Python 3.12.3); `requirements.txt` + `dukascopy-python 4.0.1` installed
- **Shell env:** `.bashrc` exports `PSC_VENV`, `PSC_REPO`, alias `psc-activate` (activates venv + cd repo + sets `PYTHONPATH=.`)
- **SSH keypair:** `~/.ssh/id_ed25519` (`rob@c240`) — pubkey authorised on gen8 and r630
- **SSH authorized_keys:** holds keys from Latitude (`strategy-engine`), Gen 8 (`dl380p-deploy`), R630 (`rob@r630`)
- **SSH config:** `~/.ssh/config` aliases for gen8, gen8-ts, r630, r630-ts, x1, latitude
- **WOL scripts:** `/usr/local/bin/wake-gen8.sh`, `/usr/local/bin/wake-r630.sh`, `/usr/local/bin/wake-all.sh` (5-burst pattern, 3 broadcast addresses)
- **post_sweep.sh template:** `/usr/local/bin/post_sweep.sh` (worker-side — rsyncs `$SWEEP_DIR` → `c240:/data/sweep_results/_inbox/`)
- **/data tree (Session 67 restructure):**
  ```
  /data/                          (10 TiB ext4, root owns lost+found)
  ├── backups/                    rclone→gdrive target (empty, needs OAuth)
  ├── configs/
  ├── leaderboards/
  ├── logs/                       (rclone_backup_YYYYMMDD.log lives here)
  ├── photos/                     Samba [photos] share - personal photos, unrelated to project
  ├── portfolio_outputs/
  ├── sweep_results/_inbox/       worker rsync target
  └── market_data/
      ├── futures/                2.2 GB, 87 CSVs (TradeStation: ES, CL, NQ, GC, SI, RTY, YM, HG, AD, BP, EC, JY, BTC, NG, US, TY, W × daily/5m/15m/30m/60m/1m)
      └── cfds/
          ├── ohlc/               2.1 GB, 120 CSVs + 1 .bcf (Dukascopy TDS exports, 24 symbols × D1/H1/M30/M15/M5)
          ├── ticks_dukascopy_tds/   32 GB, 130,238 .bfc files (24 symbol subdirs × YYYY/MM-DD.bfc, TDS proprietary binary)
          ├── ticks_dukascopy_raw/   empty - future dukascopy-python parquet downloads
          ├── ticks_mt5_the5ers/     empty - future MT5 tick exports from The5ers
          └── tds.db              5.2 MB (TDS settings database)
  ```
- **Samba `[data]` share** covers entire `/data/` tree - Latitude can remap Z: to `\\192.168.68.53\data` any time
- **rclone v1.60.1-DEV** installed; `~/.config/rclone/rclone.conf` configured with `gdrive` remote (OAuth done via `rclone authorize` on Latitude, token pasted back into headless config Session 67)
- **Nightly backup:** `/usr/local/bin/backup_to_gdrive.sh` + user cron `30 2 * * *` — syncs `leaderboards/`, `portfolio_outputs/`, `sweep_results/`, `configs/` to `gdrive:c240_backup/`. Deliberately excludes market data + photos (regenerable/personal). **End-to-end verified** — test marker `.backup_test_marker` synced to `gdrive:c240_backup/configs/`.
- **Physical relocation (Session 67):** moved under house 2026-04-19. Shut down cleanly, auto-booted on power restore, all services + data + rclone config + cron intact. No RAID/disk errors.
- **NOT YET on c240:** Gen 9 data (leaderboards/sweep_results/portfolio_outputs from old disk - blocked until Gen 9 pins fixed, if at all - gdrive backup should be restored from instead once online)

#### Gen 8 (DL380p, dl380p) — COMPUTE WORKER (SLEEPS WHEN IDLE)
- Ubuntu 24.04, IP 192.168.68.71, Tailscale 100.76.227.12, iLO 192.168.68.76
- MAC: ac:16:2d:6e:74:2c
- **Threads: 12** (pre-CPU-upgrade). 2× E5-2697 v2 chips **ARRIVED**, install pending under house → 48 threads.
- BIOS: HP P70 (Feb 2014) — supports E5-2697 v2 ✅, no update needed
- **RAM: DDR3 ECC RDIMM** — NOT DDR4! Cannot share DIMMs with Gen 9 or R630.
- SSH: socket disabled, service enabled, `ssh-recover.service` at 25s, `@reboot sleep 45` root cron fallback
- WOL persistent via netplan, ARP flush on boot (cron), auto-shutdown 30min idle (cron), iLO power policy always-on
- **Session 67 rework:**
  - `~/.ssh/config` rewritten — gen9/gen9-ts removed, c240/c240-ts/r630/r630-ts/latitude/x1 added
  - `/usr/local/bin/post_sweep.sh` retargeted from `gen9:/data/sweep_results/runs/` → `c240:/data/sweep_results/_inbox/`
  - Repo pulled from `e4b4a82` → `6189bd2`
  - Venv created at `~/venv` (was missing); requirements.txt + `dukascopy-python 4.0.1` installed
  - `.bashrc` has `psc-activate` alias
  - c240 pubkey added to `~/.ssh/authorized_keys`; Gen 8's pubkey (`dl380p-deploy`) pushed to c240 and r630
- **KNOWN TIMING QUIRK:** SSH may take 5+ min to come up after reboot — slow HP BIOS POST, not a config issue. See "Server timing notes".

#### Dell R630 — COMPUTE WORKER (SLEEPS WHEN IDLE)
- Ubuntu 24.04.4 LTS, hostname `r630`, IP 192.168.68.78 (+ stale DHCP lease .75 on eno1, clean via netplan when convenient), Tailscale 100.85.102.4
- Credentials: rob / Ubuntu123
- **Threads: 88** (dual E5-2699 v4, 44C/88T)
- **Storage:** 838 GB SSD, LVM expanded to 823 GB root (778 GB free)
- SSH: socket disabled, service enabled, `ssh-recover.service` active, auto-shutdown cron, ARP flush + SSH fallback @reboot crons
- WOL: MAC **ec:f4:bb:ed:bf:00** (eno1), netplan wakeonlan set, `wake-r630.bat` on Latitude + `wake-r630.sh` on c240
- **Session 67 rework:**
  - `~/.ssh/config` written (was empty) — c240/c240-ts/gen8/gen8-ts/latitude/x1 aliases
  - `/usr/local/bin/post_sweep.sh` retargeted to c240 `_inbox` pattern
  - Repo cloned via HTTPS (HEAD `6189bd2`)
  - `python3.12-venv` + `python3-pip` + `ipmitool` + `rclone` + `wakeonlan` packages installed
  - Venv rebuilt at `~/venv`; requirements.txt + `dukascopy-python 4.0.1` installed
  - `.bashrc` has `psc-activate` alias
  - SSH keypair generated (`rob@r630`); pubkey pushed to c240 + gen8
  - c240 pubkey added to `authorized_keys`
  - Smoke test passes: numpy 2.1.3, pandas 2.2.2, engine modules import cleanly
- **KNOWN TIMING QUIRK:** can fail first WOL attempt (older Dell NIC behaviour). Usually responds on 2nd burst 90s later. See "Server timing notes".

#### Pending Hardware
- **Dell R730 on eBay** (service tag 3TW3T92, Oakleigh VIC, $500 bid / $1000 BIN) — specs unknown, asked seller for CPU/RAM info. Mfg Jan 2016 (v3 Xeon era). NO HARD DRIVES. Don't bid without knowing specs.
- **RAM needed:** DDR4 ECC RDIMM 32GB sticks for Gen 9 (match 2Rx4 DDR4-2400 or faster). DDR3 for Gen 8.
- **Skip:** Anything DDR3 for Gen 9/R630. Only DDR4 ECC RDIMM.

### Network
- **New ISP:** Carbon Comms, 500/50 Mbps NBN, **static IP** (being connected)
- **Router:** XE75 Pro at 192.168.68.1
- Static IP enables: direct SSH from field, Hermes webhooks, dashboard access, Contabo push-to-home
- Recommendation: Keep Tailscale as primary remote access. Use static IP for specific services only.

### Cloud Infrastructure (DELETED — Session 69)
- All GCP cloud code deleted in Session 69 (cloud/, run_spot_resilient.py, run_cloud_sweep.py, Dockerfile, .dockerignore, CI workflow, console scripts)
- ~10,000 LOC removed, 89 files deleted
- GCP project and strategy-console VM can be decommissioned at GCP console level when convenient

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
- **Session 69 cleanup:** Cloud code deleted, ES config bugs fixed (futures params on CFD data), test suite green (236 pass, 0 fail)

---

## Open Issues (Priority Order)

1. **Export remaining TDS data.** Only ES, AD, NZDUSD have converted CSVs in the engine repo. Need to export all 24 markets × 5 timeframes via TDS. The raw .bfc tick caches for all 24 symbols now live on c240 at `/data/market_data/cfds/ticks_dukascopy_tds/`, so re-exports can happen locally on c240 if TDS ever gets a Linux path — currently still requires Latitude-side TDS app.
2. **Delete Latitude's TDS source copy** (~33 GB) now that c240 has a verified full mirror at `/data/market_data/cfds/ticks_dukascopy_tds/` (130,239 files, matching source count). Free up Latitude disk:
   - Verify: `(Get-ChildItem 'C:\Users\Rob\Downloads\Tick Data Suite\Dukascopy' -Recurse -File).Count` should match `find /data/market_data/cfds/ticks_dukascopy_tds -type f \| wc -l` (130,238) + 121 top-level in ohlc/
   - Then: `Remove-Item 'C:\Users\Rob\Downloads\Tick Data Suite' -Recurse -Force`
3. **Clean up stale Tailscale device.** Old `c240` entry (100.104.66.48, from abandoned Hermes pivot) still in tailnet. Remove via [Tailscale admin console](https://login.tailscale.com/admin/machines).
4. **CIMC network config for C240.** CIMC on dedicated port via DHCP; IP not captured. Check router ARP for MAC `00:A3:8E:8E:B3:84` or `nmap -sn 192.168.68.0/22`.
5. **Gen 8 CPU install pending.** 2× E5-2697 v2 arrived. Install under house, verify 48 threads. (Currently 12 threads with E5-2640 v1.)
6. **Gen 9 revival (optional).** Rob is straightening bent CPU pins to turn Gen 9 into a new Hermes autonomous-agent server. If successful, data migration from Gen 9's old SAS array is moot (drives are already in c240). Gen 9 becomes a new role, not a restored one.
7. **R630 stale DHCP lease.** `eno1` shows both `192.168.68.78/22` (static) and `192.168.68.75/22` (stale DHCP). Clean via netplan when convenient — `sudo netplan try` to drop the DHCP lease.
8. **X1 Carbon offline ~20h** (noted Session 67 post-relocation tailscale check). Not blocking — wake and verify when next needed as a Claude/Desktop-Commander endpoint.
9. **CFD swap costs NOT modeled in MC simulator.** Must implement before trusting funding timelines. Cost profiles defined in `configs/cfd_markets.yaml` but not yet consumed by portfolio selector.
10. **First local sweep validation.** ES daily CFD sweep on c240 with corrected config. **Session 70 priority.**
12. **Dashboard Live Monitor broken.** Engine log and Promoted Candidates sections don't work during active runs.

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

### Phase 7: Local Cluster & CFD Pipeline (Sessions 63-67, Apr 14-19 2026)
- **Session 63:** Dukascopy architecture decision, SP500 tick download, The5ers MT5 exports, home lab network setup
- **Session 65:** CFD data pipeline built end-to-end: TDS format converter (24 markets), engine loader "Vol" support, 24 CFD market configs, local sweep runner, batch cluster sweep launcher with resume, config generator (24 sweep YAMLs). Cloud infrastructure deprecated.
- **Session 66 (2026-04-18):** Gen 9 decommissioned. Cisco C240 M4 commissioned at 192.168.68.53. 2× E5-2673 v4 (40C/80T), 64 GB RAM, 10.9 TB SAS (ex-Gen 9 drives). Ubuntu 24.04.4, LVM layout: / 100 GB + /data 10 TiB ext4. SSH key auth, NOPASSWD sudo, Tailscale 100.120.11.35, Samba [photos] share live.
- **Session 67 (2026-04-19):** c240 full buildout + cluster onboarding + tick data migration + restructure + rclone + relocation.
  - c240: all packages installed, ssh-recover.service, ARP-flush cron, repo cloned, venv with dukascopy-python, SSH keypair + config + WOL scripts + post_sweep.sh template, [data] Samba share added.
  - Gen 8 + R630 fix-ups: ssh config rewritten (gen9 refs gone), post_sweep.sh retargeted c240, repos updated, venvs built, full bidirectional SSH mesh c240↔gen8↔r630 verified.
  - Tick data transfer: 33.4 GB / 130,359 files from Latitude TDS cache → c240 via robocopy over Samba (1h 4m, 538 MB/min). 
  - `/data` restructure: `market_data/tradestation/` → `market_data/futures/`; `tick_data/dukascopy_tds/*.csv` → `market_data/cfds/ohlc/`; `tick_data/dukascopy_tds/<SYMBOL>/` → `market_data/cfds/ticks_dukascopy_tds/`; stale empty scaffolding removed.
  - 7.3 GB wrong-path duplicate (`/data/market_data/tick_data/` from earlier crashed chat) deleted after per-file twin verification (zero unique content lost except 7-byte `.writetest` marker).
  - rclone gdrive OAuth completed (headless flow: `rclone authorize` on Latitude, paste token into c240 config). First backup run successful — `gdrive:c240_backup/configs/.backup_test_marker` verified on remote. Nightly cron live at 02:30.
  - Latitude Z: drive remapped from dead `\\192.168.68.69\data` → `\\192.168.68.53\data` (persistent, credentials saved).
  - c240 physically relocated under house. Powered back on cleanly — health check confirms all services, /data mount, rclone config, cron, tailscale intact. No RAID or disk errors.

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

## Server Timing Notes

**Don't assume "not responding" means broken.** These servers each have quirks that look like failure but are normal:

| Server | Wake/Boot Behaviour | What looks like failure but isn't | Action |
|---|---|---|---|
| **Gen 8** (HP DL380p) | Slow HP BIOS POST — SSH can take **5+ minutes** after power-on | Connection refused / timeout for first 5 min | Wait. Second attempt at T+5min works. |
| **R630** (Dell) | Often ignores **first WOL burst**. Second burst 60-90s later reliably wakes it. | No ARP entry, ping "destination unreachable" | Re-send WOL (`wake-r630.bat` / `wake-r630.sh`), wait 90s, retry SSH |
| **C240** (Cisco) | POST is fast, SSH within ~90s. CIMC takes longer to come up on dedicated port. | Tailscale may show offline for up to 2 min post-boot | Wait 2 min, Tailscale re-registers |
| **All** | `ssh-recover.service` is a **25-second delayed restart** of `ssh.service` after boot | First SSH attempt during window T+0 to T+25s fails | Wait 30s after any reboot before first SSH |
| **All** | `@reboot sleep 45` root cron is a **final fallback** — restarts SSH at T+45s | Only triggers if earlier methods failed | Baseline recovery |

**Robocopy over Samba** to c240 runs ~**538 MB/min** over gigabit LAN with `/MT:16`. A 33 GB tick-data migration = ~1h. Silent during transfer (`/NFL /NDL` flags mean "no file list / no dir list"). Check progress via destination size (`ssh c240 "du -sh /data/..."`), not log file.

**WOL pattern:** 5 bursts × 3 broadcast addresses (`192.168.68.255`, `192.168.71.255`, `255.255.255.255`) × ports 7 + 9 every 1 second. See `/usr/local/bin/wake-gen8.sh`, `wake-r630.sh`, `wake-all.sh` on c240 and `C:\Users\Rob\wake-*.bat` on Latitude.

**If WOL fails, use IPMI:**
```
ssh gen8 "sudo ipmitool -I lanplus -H 192.168.68.76 -U Administrator -P <pw> power on"   # Gen 8 iLO
# R630: iDRAC IP TBD, same pattern
```

---

## On the Horizon

- **SESSION 70 PRIORITY: First clean CFD sweep.** ES daily on c240 using corrected `configs/local_sweeps/ES_daily.yaml`. Validate end-to-end before scaling.
- **Delete Latitude TDS source** (`C:\Users\Rob\Downloads\Tick Data Suite\`, ~33 GB) — c240 has verified full mirror at `/data/market_data/cfds/ticks_dukascopy_tds/`.
- **Export all TDS data** — currently only ES, AD, NZDUSD have converted-to-engine CSVs. 21 markets pending × 5 timeframes each.
- **Copy converted CSVs to c240** — when TDS converts more markets: destination is now `/data/market_data/cfds/ohlc/` (or run converter directly on c240 once it reads from `ticks_dukascopy_tds/`).
- **Capture C240 CIMC IP** — check router ARP for MAC `00:A3:8E:8E:B3:84`.
- **Clean up stale Tailscale `c240` device** (100.104.66.48) via admin console.
- **Gen 8 CPU install** — 2× E5-2697 v2 arrived, install under house, verify 48 threads.
- **Gen 9 revival as Hermes box** (optional) — bent pins being straightened.
- **R630 netplan cleanup** — drop stale `192.168.68.75` DHCP lease from eno1.
- **Full 24-market sweep** — `python run_cluster_sweep.py` (all markets, all timeframes) on c240 orchestrating gen8 + r630.
- Implement CFD swap/overnight cost modeling in MC simulator (cost profiles in `configs/cfd_markets.yaml`).
- **Challenge vs Funded mode** — implement spec in `docs/CHALLENGE_VS_FUNDED_SPEC.md`.
- Static IP port forwarding setup once new ISP connected.
- Hermes Agent on c240 for monitoring/alerting (Linux native, Telegram gateway).
- Strategy templates to reduce search space.

---

## Connection Quick Reference

```
# SSH aliases (from Latitude or X1 Carbon)
ssh c240          # Cisco C240 M4 — LAN 192.168.68.53, Tailscale 100.120.11.35 (device name c240-1)
ssh gen8          # Gen 8 Tailscale (100.76.227.12) — LAN 192.168.68.71
ssh r630          # Dell R630 Tailscale (100.85.102.4) — LAN 192.168.68.78
ssh x1            # X1 Carbon Tailscale (100.86.154.65)
# ssh gen9        # DECOMMISSIONED Session 66

# SSH mesh (c240 ↔ gen8 ↔ r630) — all bidirectional, verified Session 67
# Each box can ssh to any other without password prompt

# Samba shares on c240 (user: rob, password: Ubuntu123)
\\192.168.68.53\photos         # /data/photos — personal photos, separate concern
\\192.168.68.53\data           # /data root — full tree (rw, force_user=rob). Map Z: here.
# \\192.168.68.69\*            # DECOMMISSIONED with Gen 9

# Data layout on c240 (Session 67)
/data/market_data/futures/                      # TradeStation OHLC (87 CSVs, 2.2 GB)
/data/market_data/cfds/ohlc/                    # Dukascopy TDS OHLC (120 CSVs, 2.1 GB)
/data/market_data/cfds/ticks_dukascopy_tds/     # Raw .bfc tick cache (130k files, 32 GB)
/data/market_data/cfds/ticks_dukascopy_raw/     # Future: dukascopy-python parquet
/data/market_data/cfds/ticks_mt5_the5ers/       # Future: The5ers MT5 tick exports
/data/leaderboards/                             # Master leaderboards
/data/sweep_results/_inbox/                     # Worker rsync target
/data/portfolio_outputs/                        # Portfolio selector outputs

# WOL (from Latitude)
C:\Users\Rob\wake-r630.bat      # MAC ec:f4:bb:ed:bf:00 — often needs 2nd burst
C:\Users\Rob\wake-gen8.bat      # MAC ac:16:2d:6e:74:2c — 5 min POST delay normal

# WOL (from c240)
/usr/local/bin/wake-gen8.sh     # MAC ac:16:2d:6e:74:2c
/usr/local/bin/wake-r630.sh     # MAC ec:f4:bb:ed:bf:00
/usr/local/bin/wake-all.sh      # both

# Server creds: rob / Ubuntu123 (all servers)
# C240 sudo: NOPASSWD via /etc/sudoers.d/rob-nopasswd
# GCP SSH: ssh -i C:\Users\Rob\.ssh\google_compute_engine pitman_nikola@35.223.104.173

# Sweep results pipeline (run on worker after sweep):
# /usr/local/bin/post_sweep.sh <sweep_output_dir>
#   -> rsyncs to c240:/data/sweep_results/_inbox/<basename>/
#   -> touches c240:/data/sweep_results/_inbox/.new_result_<basename> as marker

# rclone nightly backup (scheduled, needs one-time OAuth)
# Script: /usr/local/bin/backup_to_gdrive.sh
# Cron:   30 2 * * *
# Targets: leaderboards/ portfolio_outputs/ sweep_results/ configs/ -> gdrive:c240_backup/
# Logs:   /data/logs/rclone_backup_YYYYMMDD.log (14-day retention)

# Quick activate (on any cluster server)
psc-activate        # sources venv + cd to repo + sets PYTHONPATH=.

# iLO / CIMC access
# Gen 9 iLO: DECOMMISSIONED
Gen 8 iLO: https://192.168.68.76 (old SSL - use Firefox, creds unknown)
R630 iDRAC: IP TBD
C240 CIMC: on dedicated port via DHCP, MAC 00:A3:8E:8E:B3:84, IP TBD — default admin/password
```

## Key Principles
- Always use Desktop Commander before Windows MCP (Windows MCP hangs)
- **Server timing:** see "Server Timing Notes" — Gen 8 needs 5 min post-boot, R630 often needs 2 WOL bursts, give all SSH 30s after reboot
- Full fixes only — no patches
- Drawdown is the binding constraint on The5ers
- Skip DDR3 servers (R710, R610) — only R630/R730 and above
- Gen 8 uses DDR3 RAM, Gen 9 and R630 use DDR4 — do NOT mix
- **Windows↔c240 transfers:** use robocopy over Samba UNC path `\\192.168.68.53\data\` — 538 MB/min, resumable via `/XC /XN /XO` skip flags
- **Large transfers:** robocopy is silent with `/NFL /NDL`. Check progress from dest side (`du -sh`), not logs.
- SPOT zone: us-central1-f; on-demand fallback: us-central1-c (legacy cloud only)
- Dukascopy for strategy discovery, The5ers tick data for execution cost validation
