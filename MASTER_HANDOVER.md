Last updated: 2026-05-01
Current status: Codex has now closed the loop between the canonical local-cluster publish path and the Google Drive cold backup. The validated CFD run `2026-04-30_es_nq_validation` is finalized on c240 under `/data/sweep_results/runs/2026-04-30_es_nq_validation`, the canonical latest exports on c240 are `master_leaderboard.csv`, `master_leaderboard_cfd.csv`, `ultimate_leaderboard.csv`, and `ultimate_leaderboard_cfd.csv` under `/data/sweep_results/exports/`, and those files plus the full latest run folder have been mirrored into `G:\My Drive\strategy-data-backup\` on Latitude. Codex also added `run_cluster_results.py mirror-backup`, which copies canonical `exports/` plus selected or all `runs/` into a backup root so Google Drive stays aligned with the new local-cluster architecture instead of the old legacy layout. Important disaster-recovery note: `ultimate_leaderboard*.csv` alone is not enough for trustworthy recovery or provenance; the backup must keep the matching `sweep_results/runs/<run_id>/` folders with `cluster_run_manifest.json`, per-host logs, and dataset output artifacts. Market data is still deliberately excluded from the Google Drive cold backup, so a total server loss would preserve published leaderboard state and run provenance, but not the full raw research corpus.

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
- **Converted data files:** 120 files on c240 at `/data/market_data/cfds/ohlc_engine/` (all 24 markets × 5 TFs)
- **dukascopy-python** v4.0.1 was installed on the OLD Gen 9 (pre-Session 66 decommissioning) for raw tick downloads. NOT installed on the current `g9` (which is a separate autonomous-business host).
- **SP500 Dukascopy download COMPLETE** — 3.4GB, 2012-01 through 2026-04 (bid + ask parquets), originally stored at `/data/dukascopy/raw_ticks/sp500/` on the OLD Gen 9. Data drives moved to c240 Session 66; specific path may or may not be preserved under the c240 /data restructure (Session 67).
- **Gen 9 storage notes (OLD Gen 9, pre-decommission):** `/data/dukascopy/raw_ticks/` and `/data/dukascopy/ohlc_bars/` existed with 437 GB free — historical reference only.
- **Converted data target (OLD plan):** `/data/market_data/dukascopy/` on Gen 9 — superseded. Current target is `/data/market_data/cfds/ohlc_engine/` on c240.
- **The5ers MT5 tick exports** (manual via Ctrl+U -> Ticks -> Export, saved to `Z:\market_data\mt5_ticks\`):
  - SP500: 3.1 GB, 76.5M ticks from 2022-05-23
  - NAS100: 10.6 GB, 245.8M ticks from 2022-05-23
  - US30 through UK100: in progress (manual export)
  - XAUUSD: only 5 days of data on The5ers — useless for backtesting, need Dukascopy
- **The5ers tick data depth varies wildly:** indices have ~4 years, XAUUSD has 5 days, FX unknown

### Home Lab Infrastructure

#### Power Policy (Session 72h/73, 2026-04-21) — ALL SERVERS ALWAYS-ON (HARD RULE)
- **HARD RULE: All cluster servers (c240, g9, gen8, r630) stay powered on 24/7. DO NOT SHUT DOWN ANY SERVER UNDER ANY CIRCUMSTANCES.** No auto-shutdown crons, no manual power-off, no suspend, no hibernate, no "just this once". The only acceptable power cycles are: (a) planned hardware installs requiring physical work, (b) unplanned power failure.
- **Rationale:** Rob has home solar + battery + off-peak AUD $0.08/kWh (00:00–06:00) and free solar 11:00–14:00. Idle cost ~AUD $0.50–$1/server/month — negligible vs. reliability pain of WOL failures, Gen 8's 5-min POST, r630's flaky first-WOL behaviour, and interrupted sweeps.
- **Implementation status:** c240 + g9 already always-on. **gen8 + r630 need auto-shutdown crons removed** (see Open Issue). Gen 8 joins the always-on pool when replacement fans arrive (~27 Apr–4 May 2026). WOL scripts retained as emergency wake-only fallback.

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
- **Dual Remote Control hubs live here now:** `betfair-trader` and `python-master-strategy-creator` run side-by-side as separate Claude Remote Control sessions. They do not share state.
- **Strategy hub paths (Session 74, 2026-04-24):** `C:\Users\rob_p\strategy-ops\strategy-hub-watchdog.ps1`, `C:\Users\rob_p\strategy-ops\logs\strategy-hub.log`, Startup entry `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\StrategyHubWatchdog.vbs`, scheduled pull task `StrategyRepoPull`, repo mirror `C:\Users\rob_p\Documents\GIT Repos\python-master-strategy-creator`.
- **Strategy pull automation:** `C:\Users\rob_p\strategy-ops\pull-repo.ps1` plus `pull-repo.bat` run every 5 minutes via Task Scheduler, but bail if the repo is dirty or not on `main`.
- **Dispatch path:** Claude mobile app -> X1 Carbon strategy hub -> SSH/Git actions -> c240/r630/gen8. Heavy compute stays on Linux; the X1 is only the control plane.
- SSH config at C:\Users\rob_p\.ssh\config with aliases: gen9, gen9-ts, gen8, gen8-ts, homepc, contabo
- WOL scripts: wake-gen9.bat, wake-gen8.bat, wake-all.bat in C:\Users\rob_p\
- Port 22 firewall opened for inbound SSH
- **Google Drive for Desktop** installed, syncing "Google Drive - Master Strat Creator" folder
- **Samba drive** mapped to `\\192.168.68.69\data`
- **Back online** (2026-04-14) — power supply had died, replaced

#### Gen 9 (DL360, `g9`) — COMPUTE WORKER (joining cluster)
- **Role (Session 75):** Compute worker, like c240/gen8/r630. Crunches sweeps when needed. Hermes/OpenClaw fully decommissioned and removed 2026-04-26.
- **Revived Session 71b (2026-04-19)** — bent CPU pins straightened, fresh Ubuntu install on new 128 GB SATA SSD boot drive.
- **Session 72g (2026-04-21):** Second CPU installed (E5-2650 v4 into CPU2 socket, bent pins fixed with pencil-spacer). Heat sink mounted. **Physical state: under house in final position.**
- **Session 72g/73 NETWORK FAULT — RESOLVED 2026-04-21.** Both possible root causes were actioned during the same trip: (a) Rob reseated the 2× SAS drives in Array B (had come partially unseated during under-house move; P440ar RAID controller can hang POST when unable to enumerate drives), and (b) cable position verified in leftmost port (eno1). **Lesson:** after a physical move, reseat storage *and* verify cable positions before blaming the network stack — symptoms overlap.
- **Hostname:** `g9`
- **OS:** Ubuntu 24.04.4 LTS, kernel 6.8.0-110
- **LAN IP:** `192.168.68.50/22` on `eno1` (DHCP)
- **Tailscale IP:** `100.71.141.89` (device name `g9`, auth user `robpitman1982@`)
- **CPU:** 2× Xeon E5-2650 v4 @ 2.20 GHz = **24 cores / 48 threads** (dual socket, Hyperthreading ON). `nproc` = 48.
- **RAM:** 32 GB + 4 GB swap (Session 72h/73; needs audit — was 16 GB before, mechanism of doubling unclear)
- **Storage — HP Smart Array P440ar:**
  - Array A: logicaldrive 1 (119.21 GB, RAID 0) — SATA SSD `1I:0:1` → `/dev/sda` (boot + `/` on LVM `ubuntu-vg/ubuntu-lv`, 58 GB used / 116 GB VG headroom)
  - Array B: logicaldrive 2 (273.40 GB, RAID 0) — 2× 146 GB SAS HDD `1I:0:2,1I:0:3` striped → `/dev/sdb` → LVM `data-vg/data-lv` → `/data` (269 GB ext4, fstab-persisted, owned by rob, UUID `0661ff58-9086-432e-b70b-51bc8a271cf1`)
- **Credentials:** `rob` / `Ubuntu123`; NOPASSWD sudo via `/etc/sudoers.d/rob-nopasswd`
- **SSH access from Latitude:**
  - Direct LAN SSH from Latitude Wi-Fi fails (client-isolation/ARP quirk) — use `ProxyJump c240` via `ssh g9` alias, or direct over Tailscale via `ssh g9-ts`.
  - `Host g9` in `C:\Users\Rob\.ssh\config` uses `ProxyJump c240`; `Host g9-ts` points at Tailscale IP.
  - Latitude `strategy-engine` pubkey in `~/.ssh/authorized_keys` on g9.
- **SSH services:** `ssh.socket` masked, `ssh.service` enabled + active, `ssh-recover.service` (25s delayed restart) enabled.
- **Always-on posture (per HARD RULE Session 73):** `sleep.target`, `suspend.target`, `hibernate.target`, `hybrid-sleep.target` all **masked**; `systemd-logind.conf.d/no-sleep.conf` sets lid/suspend/idle = ignore.
- **ARP-flush-on-boot:** `@reboot /usr/sbin/ip -s -s neigh flush all` in root crontab.
- **SSH keypair:** `~/.ssh/id_ed25519` (`rob@g9`) — pubkey installed on c240 `authorized_keys` for admin peer access.
- **Toolchain installed (Session 71b):**
  - Docker 29.1.3 (`docker.io` + `docker-compose-v2`, `rob` in `docker` group, daemon enabled)
  - Node.js v24.14.1 + npm 11.11.0
  - Python 3.12.3 + venv at `~/venv`
  - Tailscale 1.96.4
  - ssacli 6.45-8.0 (HP Smart Storage CLI)
  - rclone v1.60.1-DEV (config not done — see Open Issues)
  - Base: build-essential, git, curl, wget, jq, unzip, tmux, htop, iotop, net-tools, nfs-common, cifs-utils, wakeonlan, etherwake, ipmitool, ca-certificates, gnupg, software-properties-common
- **/data layout (Session 75 post-decommission):**
  ```
  /data/                          (269 GB ext4, noatime)
  ├── betfair-historical/         (rob — betfair sweep data, owned by rob)
  ├── backups/
  ├── logs/
  └── lost+found/                 (root:root, expected)
  ```
- **Pending compute-worker setup (Session 75 TODO):** repo clone, market_data sync, sweep scripts, samba membership, post_sweep.sh — not yet in place. g9 was never a backtesting member; the work to make it one is queued.
- **Hermes/OpenClaw decommission audit trail (Session 75 — 2026-04-26):**
  - Users `hermes` (uid 1001) and `openclaw` (uid 1002) deleted via `userdel -r`. Group `agents` (gid 1001) deleted.
  - Removed: `/data/hermes/` (~1.5 GB), `/data/openclaw/`, `/data/shared/` (entire tree), `/etc/cron.d/sync-handover`, `/etc/sudoers.d/agents`, `/usr/local/bin/sync-handover`, `/usr/local/bin/sync-betfair-handover`.
  - Hermes's pubkey `hermes-agent@g9-cluster` (fingerprint ending `JvbVaj`) removed from `rob@authorized_keys` on c240, gen8, r630. Backups taken to `~/.ssh/authorized_keys.bak-pre-hermes-removal-YYYYMMDD` on each host.
  - External retirement also complete (operator, 2026-04-26): GitHub deploy keys revoked on both `python-master-strategy-creator` and `betfair-trader` repos; Telegram bot `@pitmans_heremes_bot` deleted via @BotFather; Hermes Anthropic API key revoked in console. Hermes is fully gone, no remaining state anywhere.

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
- **Google Drive mirror for canonical cluster outputs (2026-05-01):** use `python run_cluster_results.py mirror-backup --storage-root <canonical_sweep_results_root> --backup-root "G:\\My Drive\\strategy-data-backup"` from any machine that can see the canonical storage root. This mirrors the active exports (`master_leaderboard.csv`, `master_leaderboard_cfd.csv`, `ultimate_leaderboard.csv`, `ultimate_leaderboard_cfd.csv`) into `strategy-data-backup\\leaderboards\\` and copies the selected or latest canonical run folder into `strategy-data-backup\\sweep_results\\runs\\`. Disaster recovery requires the run folders and manifests, not just the ultimate CSVs. The stale legacy `ultimate_leaderboard_bootcamp.csv` may still exist in Drive for history, but it is no longer part of the active pipeline.
- **Physical relocation (Session 67):** moved under house 2026-04-19. Shut down cleanly, auto-booted on power restore, all services + data + rclone config + cron intact. No RAID/disk errors.
- **NOT YET on c240:** Gen 9 data (leaderboards/sweep_results/portfolio_outputs from old disk - blocked until Gen 9 pins fixed, if at all - gdrive backup should be restored from instead once online)

#### Gen 8 (DL380p, dl380p) — COMPUTE WORKER (SLEEPS WHEN IDLE)
- Ubuntu 24.04, IP 192.168.68.71, Tailscale 100.76.227.12, iLO 192.168.68.76
- MAC: ac:16:2d:6e:74:2c
- **Session 72g CPU UPGRADE COMPLETE.** 2× E5-2697 v2 + 2 heat sinks installed successfully. 48 threads expected when back online (currently 12 with the v1 chip). Rob verified both CPUs seat properly; RAM reslotted for dual-socket balance (see RAM layout below).
- **RAM layout (Session 72g, per-socket balanced):**
  - CPU1: 16GB @ 1C + 16GB @ 2G + 8GB @ 7J = **40 GB**
  - CPU2: 16GB @ 12A + 16GB @ 11E + 8GB @ 6L = **40 GB**
  - **Total: 80 GB DDR3 ECC RDIMM.** 16GB sticks in outer slots (farthest from CPU), 8GB on inside. Different channels per letter — no same-channel size mixing.
- **FANS BLOCKER — waiting for 2× replacement fans.** Dual-CPU DL380p Gen 8 requires **6 fans** in bays 1-6. Rob currently has 4 (bays 1, 2, 5, 6 — split 2+2 across both sides for airflow). Bays 3 + 4 empty. Will boot with warnings + non-redundant cooling, WILL throttle under sweep load. **Ordered 2× HP 662520-001 from Interbyte Computers (eBay) AU$4 each + $11 postage. Est. delivery Mon 27 Apr – Mon 4 May 2026.** Seller asked re: combined postage.
- **Gen 8 powered OFF under house** until fans arrive. No access needed meantime.
- **Always-on once fans arrive (Session 72h/73 HARD RULE).** Auto-shutdown cron to be disabled when Gen 8 comes back online.
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
- SSH: socket disabled, service enabled, `ssh-recover.service` active, ARP flush + SSH fallback @reboot crons. **Auto-shutdown cron TO BE DISABLED** per Session 72h/73 always-on HARD RULE (pending implementation).
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
- Static IP enables: direct SSH from field, dashboard access, Contabo push-to-home
- Recommendation: Keep Tailscale as primary remote access. Use static IP for specific services only.

### Cloud Infrastructure (DELETED — Session 69)
- All GCP cloud code deleted in Session 69 (cloud/, run_spot_resilient.py, run_cloud_sweep.py, Dockerfile, .dockerignore, CI workflow, console scripts)
- ~10,000 LOC removed, 89 files deleted
- GCP project and strategy-console VM can be decommissioned at GCP console level when convenient

### Strategy Engine Status
- **Ultimate leaderboard:** ~454 strategies (414 bootcamp-accepted) across 8 markets (ES, CL, NQ, SI, HG, RTY, YM, GC)
- **Vectorized engine:** 14-23x speedup, zero-tolerance parity confirmed. All configs use `use_vectorized_trades: true`
- **12 strategy families:** 3 long (trend, MR, breakout) + 3 short + 9 subtypes (3 per family)
- **Leaderboard architecture (2026-04-30):** the active pipeline is now neutral across both universes. Futures runs write `family_leaderboard_results.csv`, `master_leaderboard.csv`, and `ultimate_leaderboard.csv`; CFD runs write `family_leaderboard_results.csv`, `master_leaderboard_cfd.csv`, and `ultimate_leaderboard_cfd.csv`. `bootcamp_score` and `*_bootcamp.csv` ranking views are no longer emitted by the active sweep pipeline.
- **Research ranking:** canonical leaderboard order now favors `accepted_final`, stronger `quality_flag`, higher `oos_pf`, higher `recent_12m_pf`, higher `calmar_ratio`, higher `deflated_sharpe_ratio` (where available), higher `leader_pf`, and smaller `leader_max_drawdown`, with net PnL and trade frequency as later tie-breakers.
- **Portfolio selector:** 6-stage pipeline with 3-layer correlation, block bootstrap MC, regime survival gate. Candidate gating no longer uses `bootcamp_score_min`; selector reads the neutral strategy pool and does program-specific ranking inside the selector/MC layer.
- **Prop firm system:** Bootcamp, High Stakes, Pro Growth, Hyper Growth — all with daily DD enforcement
- **CFD sweep infrastructure (Session 65):**
  - `run_local_sweep.py` — single-market local sweep runner (replaces GCP cloud runners)
  - `run_cluster_sweep.py` — batch orchestrator with manifest tracking + resume support
  - `configs/cfd_markets.yaml` — 24 CFD market configs with engine params + cost profiles
  - `configs/local_sweeps/` — 24 generated per-market sweep configs (all 5 timeframes each)
  - `scripts/convert_tds_to_engine.py` — TDS Metatrader CSV -> TradeStation format converter
  - `scripts/generate_sweep_configs.py` — generates sweep configs from market master config
- **CFD swap rates gathered:** CL=$0.70/micro/night (10x Fri!), SI=$4.05, GC=$2.20, indices near-zero, FX $0.10-0.26
- **Session 69 cleanup:** Cloud code deleted, ES config bugs fixed, test suite green (236 pass, 0 fail)
- **Session 70 first CFD sweep:** ES daily Dukascopy on c240, 7m runtime, 13 accepted strategies. Max PnL $1.0M (passed $20M critical threshold). Plausibility validated.

### r630 ES 5m sweep OOM postmortem (Session 72g, 2026-04-21)
- **Launched:** 19/04/26 21:08 UTC on r630 (ES 5m Dukascopy, all 15 strategy families)
- **Expected finish:** ~11 AM 21/04/26 (~62h runtime)
- **Actual end:** **OOM-killer at 20/04/26 06:26:40 UTC — 9h 18m in (~15% through plan)**
- **Auto-shutdown cron** then powered r630 off at 07:00 UTC once system went idle (working as designed)
- **Root cause:** `configs/local_sweeps/ES_5m.yaml` specified `max_workers_sweep: 82` and `max_workers_refinement: 82` (hard override of global `config.yaml` default of 2). r630 has only **62 GiB RAM + 8 GiB swap**. 82 × 5m dataset in parallel exhausted memory during REFINEMENT stage.
- **Progress at OOM** (from `status.json`):
  - Family 1 (mean_reversion): initial sweep ✅ complete (31,008 combos tested)
  - Family 1 refinement: 49.5% (190 / 384 items, 2/5 candidates)
  - Families 2-15: not started
- **Salvageable on disk** at `~/python-master-strategy-creator/Outputs/es_5m_dukascopy_v1/ES_5m/`:
  - `mean_reversion_filter_combination_sweep_results.csv` (21.5 MB, 31,008 rows)
  - `mean_reversion_promoted_candidates.csv` — **14 promoted candidates** with quality flags. Top pick `ComboMR_DownClose_ReversalUpBar_CloseNearLow_InsideBar_ATRExpansionRatio_CumulativeDecline` is ROBUST with IS PF 2.24 → OOS PF 2.59 → recent 12m PF 3.16 (improving OOS).
- **Dataset sizes on disk** (ES CFD Dukascopy, `/data/market_data/cfds/ohlc_engine/`):
  - daily 0.25 MB (1×)
  - 60m 4.3 MB (17×)
  - 30m 8.2 MB (33×)
  - 15m 16.1 MB (65×)
  - **5m 47.6 MB (192×)**
- **Worker review IN PROGRESS (incomplete Session 72g):**
  - ✅ Confirmed `ES_5m.yaml` workers=82 — not 2, not 88
  - ✅ Dataset sizes by TF captured
  - ⏸️ Per-worker memory measurement — `mem_probe.py` staged at `/tmp/mem_probe.py` on r630 (rewritten to use /proc/self/status, no psutil dep). Didn't run due to SSH/venv hiccups.
  - ⏸️ Nested parallelism check (grep engine modules for ProcessPool / Pool() inside workers) — would explain why OOM dump showed "30+" processes when config specified 82.
  - ⏸️ Prior 15m sweep search — Rob believes 15m succeeded; need to locate the output dir and confirm.
  - ⏸️ Concrete RAM + worker recommendation — needs measured per-worker footprint first.

---

## Open Issues (Priority Order)

1. **Delete Latitude's TDS source copy** (~33 GB) now that c240 has a verified full mirror at `/data/market_data/cfds/ticks_dukascopy_tds/` (130,239 files, matching source count). Free up Latitude disk:
   - Verify: `(Get-ChildItem 'C:\Users\Rob\Downloads\Tick Data Suite\Dukascopy' -Recurse -File).Count` should match `find /data/market_data/cfds/ticks_dukascopy_tds -type f \| wc -l` (130,238) + 121 top-level in ohlc/
   - Then: `Remove-Item 'C:\Users\Rob\Downloads\Tick Data Suite' -Recurse -Force`
2. **Clean up stale Tailscale device.** Old `c240` entry (100.104.66.48) still in tailnet. Remove via [Tailscale admin console](https://login.tailscale.com/admin/machines).
3. **CIMC network config for C240.** CIMC on dedicated port via DHCP; IP not captured. Check router ARP for MAC `00:A3:8E:8E:B3:84` or `nmap -sn 192.168.68.0/22`.
4. **Gen 8 CPU install DONE (Session 72g).** 2× E5-2697 v2 + heat sinks installed. RAM re-balanced 40GB per CPU (see Gen 8 section). **Now blocked on 2 missing fans (bays 3-4)** — ordered HP 662520-001 from Interbyte Computers eBay AU$19 total, est. Mon 27 Apr - Mon 4 May 2026. Gen 8 OFF under house until fans arrive. Do NOT power on with 4 fans under sweep load — will throttle.
5. **Disable auto-shutdown crons on gen8 + r630.** Required to implement Session 72h/73 always-on HARD RULE. Remove any cron entry that powers down on idle. Verify by leaving machines idle for 2+ hours and confirming they stay up. R630: action next convenient SSH session. Gen 8: action when it comes back online post-fans.
6. **R630 stale DHCP lease.** `eno1` shows both `192.168.68.78/22` (static) and `192.168.68.75/22` (stale DHCP). Clean via netplan when convenient — `sudo netplan try` to drop the DHCP lease.
7. **X1 Carbon offline** — also need to verify laptop SSH isolation when back online (inspect `C:\ProgramData\ssh\administrators_authorized_keys` AND `C:\Users\rob_p\.ssh\authorized_keys` — no server pubkeys should be present).
8. **CFD swap costs NOT modeled in MC simulator.** Must implement before trusting funding timelines. Cost profiles defined in `configs/cfd_markets.yaml` but not yet consumed by portfolio selector.
9. **Dashboard Live Monitor broken.** Engine log and Promoted Candidates sections don't work during active runs.
10. **g9 not yet a compute-cluster member.** Repo clone, market_data, sweep scripts, samba membership, post_sweep.sh all need to be set up before g9 can take cluster work.
11. **r630 5m sweep OOM'd with 82 workers (Session 72g).** See "r630 ES 5m sweep OOM postmortem" section in Strategy Engine Status. Need: (a) per-worker RAM measurement, (b) nested-pool audit in engine, (c) safe worker count derivation, (d) decide if `configs/local_sweeps/ES_5m.yaml` gets workers dropped from 82 → e.g. 20, or whether sweep needs to move to c240 (64 GiB same constraint) or r630 RAM gets upgraded. 14 promoted candidates from partial run ARE usable — don't discard.

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
- **Session 71 (2026-04-19):** Dukascopy conversion scale-out. All 120 TDS CSVs converted to engine format via `scripts/convert_tds_batch.py` on c240. Full CFD OHLC dataset engine-ready at `/data/market_data/cfds/ohlc_engine/`.
- **Session 71b (2026-04-19):** Gen 9 revived as standalone **autonomous business host** (`g9` at 192.168.68.75, Tailscale 100.71.141.89). Fresh Ubuntu 24.04.4 on new 128 GB SATA SSD boot drive. 2× 146 GB SAS drives configured as RAID0 logical drive via ssacli 6.45-8.0 → `/dev/sdb` → LVM `data-vg/data-lv` → `/data` (269 GB ext4). Installed: Docker 29.1.3, Node.js v24.14.1, Tailscale 1.96.4, Python 3.12.3 venv, ssacli, rclone. SSH via ProxyJump c240 (Latitude Wi-Fi ARP quirk) + direct Tailscale. NOPASSWD sudo, ssh-recover.service, ARP-flush cron, sleep/suspend/hibernate masked (always-on). `/data/{hermes,openclaw,backups,logs}/` layout. Backup script + 02:45 cron in place; rclone gdrive OAuth completed end-to-end (verified via test-marker sync). **g9 is NOT a backtesting cluster member** — deliberately isolated from sweep workflow.
- **Session 72 (2026-04-20) — RETIRED:** Hermes + OpenClaw deployed on g9 with full handover sync, deploy keys, Telegram bot, cluster SSH. **Fully decommissioned Session 75 (2026-04-26).** Transition path: Claude Code + Claude Remote Control replaced Hermes for ops; g9 redirected to compute-worker role.

### Key Architectural Decisions Made Along the Way
- **Fixed position sizing** (Session 45): initial_capital only, no compounding — matches prop firm rules
- **Dropped 5m timeframe** (Session 42): zero accepted strategies, ~50% of compute cost
- **Fire-and-forget via GCS** (Session 34): bundle staged to GCS before VM creation, eliminates SCP preemption window
- **Vectorized trades** (Session 61): numpy 2D arrays replace per-bar Python loop, 14-23x faster
- **Block bootstrap MC** (Session 58): preserves crisis clustering vs naive shuffle
- **3-layer correlation** (Session 58): active-day + DD-state + tail co-loss replaces simple Pearson
- **Dukascopy for discovery, The5ers for validation** (Session 63): tick data architecture separates strategy discovery (deep Dukascopy history) from execution validation (The5ers real spreads)
- **Local cluster replaces cloud** (Session 65): `run_local_sweep.py` + `run_cluster_sweep.py` replace GCP SPOT runners. Zero cloud dependencies. ~248 threads available locally once g9 joins (C240: 80, Gen 8: 48 post-CPU-upgrade, R630: 88, g9: 48 — Session 75 decommissioned Hermes and reassigned g9 to compute).
- **Hermes/OpenClaw decommissioned** (Session 75): one-week experiment retired. Claude Code + Claude Remote Control hub on X1 Carbon replaced agent-driven ops. Simpler, no API costs, no security surface from agent SSH access.

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
- **Session 74 control-plane update:** the X1 now exposes two independent Claude Remote Control entry points from Rob's phone: one for `betfair-trader`, one for `python-master-strategy-creator`. The strategy hub is dispatcher-only and should be treated as a parallel control path, not a shared session.

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

- **Session 73 PRIORITY (still deferred): ES sanity-check sweep across 4 TFs (daily / 60m / 30m / 15m). ES-only, no 5m.** Runs on c240 alone (~30–60 min), no WOL needed. Gated on worker review completion so we don't repeat the r630 OOM mistake at c240 scale. If clean: Session 74 fans out to 23 markets × 4 TFs.
- **Finish the r630 worker review** (carried over from Session 72g). Specifically: run `mem_probe.py` on r630 to get per-TF per-worker footprint, grep engine modules for nested ProcessPool, confirm whether 15m previously succeeded, then decide workers-per-machine (drop ES_5m.yaml workers from 82 to something safe, OR upgrade r630 RAM from 62 GiB → 128 GiB).
- **Bring g9 into the compute cluster** — clone repo, set up venv, sync market_data + configs from c240, install post_sweep.sh, decide on samba role.
- **Delete Latitude TDS source** (`C:\Users\Rob\Downloads\Tick Data Suite\`, ~33 GB) — c240 has verified full mirror at `/data/market_data/cfds/ticks_dukascopy_tds/`.
- **Capture C240 CIMC IP** — check router ARP for MAC `00:A3:8E:8E:B3:84`.
- **Clean up stale Tailscale `c240` device** (100.104.66.48) via admin console.
- **Gen 8 CPU install** — 2× E5-2697 v2 arrived, install under house, verify 48 threads.
- **R630 netplan cleanup** — drop stale `192.168.68.75` DHCP lease from eno1.
- **Full 24-market sweep (Session 74)** — `python run_cluster_sweep.py` (all markets × 4 TFs = 92 sweeps, 5m excluded) on c240 orchestrating gen8 + r630 + g9. Gated on Session 73 ES validation passing.
- Implement CFD swap/overnight cost modeling in MC simulator (cost profiles in `configs/cfd_markets.yaml`).
- **Challenge vs Funded mode** — implement spec in `docs/CHALLENGE_VS_FUNDED_SPEC.md`.
- Static IP port forwarding setup once new ISP connected.
- Strategy templates to reduce search space.

---

## Connection Quick Reference

```
# SSH aliases (from Latitude or X1 Carbon)
ssh c240          # Cisco C240 M4 — LAN 192.168.68.53, Tailscale 100.120.11.35 (device name c240-1)
ssh gen8          # Gen 8 Tailscale (100.76.227.12) — LAN 192.168.68.71
ssh r630          # Dell R630 Tailscale (100.85.102.4) — LAN 192.168.68.78
ssh x1            # X1 Carbon Tailscale (100.86.154.65)
#
# X1 strategy hub control plane (Session 74)
# C:\Users\rob_p\strategy-ops\strategy-hub-watchdog.ps1   # watchdog loop for Claude Remote Control in python-master-strategy-creator
# C:\Users\rob_p\strategy-ops\pull-repo.ps1               # main-only fast-forward pull helper
# C:\Users\rob_p\strategy-ops\pull-repo.bat               # Task Scheduler wrapper for the pull helper
# C:\Users\rob_p\strategy-ops\logs\strategy-hub.log       # watchdog exit log
# StrategyRepoPull                                        # scheduled task, every 5 min, IgnoreNew, battery-safe
# %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\StrategyHubWatchdog.vbs   # minimized-but-visible startup launcher
ssh g9            # Gen 9 autonomous business host — LAN 192.168.68.50 via ProxyJump c240 (was .75 pre-72)
ssh g9-ts         # Gen 9 Tailscale direct (100.71.141.89) — works from anywhere

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
/data/market_data/cfds/ticks_mt5_the5ers/
/data/market_data/cfds/ohlc_engine/             # Engine-ready converted CSVs (120/120 complete, Session 71)
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

# Hermes / OpenClaw — DECOMMISSIONED Session 75 (2026-04-26). All Hermes/OpenClaw users, data, scripts, cron, sudoers, and SSH keys removed from g9 and cluster. Replaced by Claude Code + X1 Carbon Claude Remote Control hub.

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
# Gen 9 iLO: https://192.168.68.69   Administrator / PVPT6M5H   (CONFIRMED WORKING Session 72g)
#            ipmitool example (run from c240 where ipmitool is installed):
#            ipmitool -I lanplus -H 192.168.68.69 -U Administrator -P PVPT6M5H chassis status
#            ipmitool -I lanplus -H 192.168.68.69 -U Administrator -P PVPT6M5H sdr type 'Power Supply'
#            ipmitool -I lanplus -H 192.168.68.69 -U Administrator -P PVPT6M5H sel list last 10
Gen 8 iLO: https://192.168.68.76 (old SSL - use Firefox, creds unknown)
R630 iDRAC: IP TBD
C240 CIMC: on dedicated port via DHCP, MAC 00:A3:8E:8E:B3:84, IP TBD — default admin/password
```

## Key Principles
- **ALL SERVERS ALWAYS ON — DO NOT SHUT DOWN ANY SERVER UNDER ANY CIRCUMSTANCES.** c240, g9, gen8, r630 run 24/7 permanently. No WOL cycles, no auto-shutdown, no suspend/hibernate, no "just this once". Power cycles only for planned hardware installs or unplanned outages. Solar + off-peak rates make idle cost irrelevant; reliability of the cluster is the binding constraint. (Session 72h/73 HARD RULE.)
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
