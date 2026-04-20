# HANDOVER.md — Session Continuity Document
# Last updated: 2026-04-20 (Session 72e: housekeeping — cost tracking gap documented, multi-LLM panel-review + API spend cap added to horizon. Session 73 still queued: ES sanity-check × 4 TFs.)
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

#### Gen 9 (DL360, `g9`) — ALWAYS-ON AUTONOMOUS BUSINESS HOST (Hermes/OpenClaw)
- **Role:** Standalone autonomous-business host. NOT a backtesting cluster member. Runs Hermes + OpenClaw agent workloads. Always on.
- **Revived Session 71b (2026-04-19)** — bent CPU pins straightened, fresh Ubuntu install on new 128 GB SATA SSD boot drive.
- **Hostname:** `g9`
- **OS:** Ubuntu 24.04.4 LTS, kernel 6.8.0-110
- **LAN IP:** `192.168.68.50/22` on `eno1` (DHCP lease changed from .75 → .50 after Session 71b relocation/power-cycle; stale .75 no longer valid)
- **Tailscale IP:** `100.71.141.89` (device name `g9`, auth user `robpitman1982@`). Session 72: `sudo tailscale up --reset` applied to fix stale offline state; `--ssh` disabled to avoid browser-auth dependency for regular OpenSSH
- **CPU:** 1× Xeon E5-2650 v4 @ 2.20 GHz = **12 cores / 12 threads** (single socket, HT off)
- **RAM:** 16 GB + 4 GB swap
- **Storage — HP Smart Array P440ar:**
  - Array A: logicaldrive 1 (119.21 GB, RAID 0) — SATA SSD `1I:0:1` → `/dev/sda` (boot + `/` on LVM `ubuntu-vg/ubuntu-lv`, 58 GB used / 116 GB VG headroom)
  - Array B: logicaldrive 2 (273.40 GB, RAID 0) — 2× 146 GB SAS HDD `1I:0:2,1I:0:3` striped → `/dev/sdb` → LVM `data-vg/data-lv` → `/data` (269 GB ext4, fstab-persisted, owned by rob, UUID `0661ff58-9086-432e-b70b-51bc8a271cf1`)
- **Credentials:** `rob` / `Ubuntu123`; NOPASSWD sudo via `/etc/sudoers.d/rob-nopasswd`
- **SSH access from Latitude:**
  - Direct LAN SSH from Latitude Wi-Fi fails (client-isolation/ARP quirk) — use `ProxyJump c240` via `ssh g9` alias, or direct over Tailscale via `ssh g9-ts`.
  - `Host g9` in `C:\Users\Rob\.ssh\config` uses `ProxyJump c240`; `Host g9-ts` points at Tailscale IP.
  - Latitude `strategy-engine` pubkey in `~/.ssh/authorized_keys` on g9.
- **SSH services:** `ssh.socket` masked, `ssh.service` enabled + active, `ssh-recover.service` (25s delayed restart) enabled — matches cluster pattern even though g9 is not a cluster member.
- **Always-on posture:** `sleep.target`, `suspend.target`, `hibernate.target`, `hybrid-sleep.target` all **masked**; `systemd-logind.conf.d/no-sleep.conf` sets lid/suspend/idle = ignore.
- **ARP-flush-on-boot:** `@reboot /usr/sbin/ip -s -s neigh flush all` in root crontab.
- **SSH keypair:** `~/.ssh/id_ed25519` (`rob@g9`) — pubkey installed on c240 `authorized_keys` for admin peer access (c240 can ssh to g9; g9→c240 not yet configured, intentionally minimal).
- **Toolchain installed (Session 71b):**
  - Docker 29.1.3 (`docker.io` + `docker-compose-v2`, `rob` in `docker` group, daemon enabled)
  - Node.js v24.14.1 + npm 11.11.0 (via NodeSource `setup_lts.x`)
  - Python 3.12.3 + venv at `~/venv` (latest pip/setuptools/wheel)
  - Tailscale 1.96.4
  - ssacli 6.45-8.0 (HP Smart Storage CLI, from HPE MCP repo with `[trusted=yes]` — GPG key `E3FE26E774C3A4A2` not in published keyfiles, bypass is intentional)
  - rclone v1.60.1-DEV (config not yet done — see Open Issues)
  - Base: `build-essential`, `git`, `curl`, `wget`, `jq`, `unzip`, `tmux`, `htop`, `iotop`, `net-tools`, `nfs-common`, `cifs-utils`, `wakeonlan`, `etherwake`, `ipmitool`, `ca-certificates`, `gnupg`, `software-properties-common`
- **/data layout (expanded Session 72):**
  ```
  /data/                          (269 GB ext4, noatime)
  ├── hermes/                     (hermes:agents — Hermes Agent install + state)
  │   ├── hermes-agent/           git clone NousResearch/hermes-agent + uv venv Python 3.11
  │   ├── agents/  state/  logs/  workspace/  skills_cache/
  ├── openclaw/                   (openclaw:agents — dormant backup)
  │   ├── venv/  logs/  workspace/  sandbox/
  ├── shared/                     (hermes:agents, setgid 2775 — cross-agent workspace)
  │   ├── credentials/            (openclaw_gateway_token, mode 640)
  │   └── logs/ skills/ task_queue/ results/ artifacts/
  ├── backups/
  ├── logs/
  └── lost+found/                 (root:root, expected)
  ```
- **Backup: DISABLED Session 72** — rclone user cron removed per Rob's decision ("no backup until we know what we're doing"). Script preserved at `/usr/local/bin/backup_to_gdrive.sh`, rclone config at `~/.config/rclone/rclone.conf` still valid. Re-enable after Phase 1 Hermes validation (~1–2 weeks) once retention semantics are settled.
- **Not installed deliberately:** Samba (not a data-sharing cluster member), sweep scripts, market_data, `dukascopy-python`, repo clone, `psc-activate` alias. g9 is isolated from backtesting workflow.
- **Env marker:** `.bashrc` exports `G9_ROLE="hermes_autonomous_host"` + alias `venv-activate` (sources `~/venv/bin/activate`).
- **iLO:** not yet configured (DHCP on management port expected).
- **Audit log:** `/tmp/g9_audit.log` on box, full final state.
- **Session 72 additions (2026-04-20) — Hermes + OpenClaw deployment:**
  - **Hermes Agent LIVE** — systemd user service `hermes-gateway.service` under `user@1001.service` (linger enabled for hermes). Auto-starts on boot.
    - Source: `git clone --recurse-submodules https://github.com/NousResearch/hermes-agent /data/hermes/hermes-agent` → `uv venv venv --python 3.11` → `uv pip install -e ".[all]"` (45s install, includes python-telegram-bot, faster-whisper, sounddevice).
    - Wrapper patched: `/data/hermes/hermes-agent/hermes` shebang set to `#!/data/hermes/hermes-agent/venv/bin/python` (system python3.12 grab avoided). Symlink `~hermes/.local/bin/hermes`.
    - Config: `~hermes/.hermes/config.yaml` (model=claude-sonnet-4-6, tts.provider=edge, stt.provider=local). `.env` (mode 600, 283 bytes) has `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`.
    - Brain: Claude Sonnet 4.6 via Anthropic API. STT: local faster-whisper (CPU). TTS: Edge TTS (Microsoft cloud, free, no key). Telegram bot: `@pitmans_heremes_bot` (typo in handle is intentional at this point — created with it, not renaming).
    - Project manifest: `/home/hermes/.hermes/memories/PROJECT_MANIFEST.md` (26 KB, hermes:hermes 640) — full project briefing; Hermes absorbed into MEMORY.md + USER.md via voice/text command.
    - Voice roundtrip VALIDATED — Rob sent voice memo, Hermes transcribed, replied as audio.
  - **OpenClaw STOPPED + DISABLED** (installed, onboarded, then stopped):
    - Install: `npm install -g openclaw@latest` as openclaw user (npm prefix `~/.npm-global`). Onboarded loopback-bind / token-auth / Anthropic API key flow.
    - Config: `/home/openclaw/.openclaw/openclaw.json`. Gateway token at `/data/shared/credentials/openclaw_gateway_token` (hermes:agents, 640).
    - Service unit: `/etc/systemd/system/openclaw-gateway.service` (root-owned, **system-level** — chosen over `systemctl --user` because OpenClaw's Node wrapper dropped bus context on re-spawn, "Permission denied" errors. System-level bypasses `systemctl --user` entirely). User=openclaw, Group=agents. Logs to `/data/openclaw/logs/gateway.{stdout,stderr}.log`.
    - Smoke test passed before stop: gateway reachable on `ws://127.0.0.1:18789`, probe 72 ms, 5 plugins loaded (acpx, browser, device-pair, phone-control, talk-voice).
    - Re-enable: `sudo systemctl start openclaw-gateway.service && sudo systemctl enable openclaw-gateway.service`.
    - **Known fix needed if re-enabled:** default model is `anthropic/claude-opus-4-7` but SDK warmup fails "Unknown model". Change to `anthropic/claude-sonnet-4-6` via `openclaw config set agents.defaults.model.primary anthropic/claude-sonnet-4-6` before re-starting.
  - **Users/dirs:** users `hermes` (uid 1001) + `openclaw` (uid 1002), both in group `agents` (gid 1001) + `docker`. Passwords: `Ubuntu123`. `loginctl enable-linger` for both — user systemd managers persist across logout.
  - **Scoped sudoers:** `/etc/sudoers.d/agents` — hermes + openclaw NOPASSWD on `systemctl start/stop/restart/status` of their own services only.
  - **Decision:** running Hermes solo for Phase 1 (1–2 weeks). OpenClaw dormant as hot-swap backup. Re-evaluate based on real usage — Hermes has native `delegation`, `terminal`, `code_execution`, `cronjob`, `skills` tools which may be sufficient. See Phase plan in PROJECT_MANIFEST.md section 12.
- **Session 72b additions (2026-04-20) — Handover → Hermes auto-ingest:**
  - Goal: HANDOVER.md content flows to Hermes automatically so conversations started with Claude (desktop/road) carry over to the next Hermes chat.
  - Ingest script: `/usr/local/bin/ingest-handover` (root:root 0755) — repo-tracked at `scripts/ingest-handover.sh`. Overwrites `/data/shared/handover/HANDOVER.md` (hermes:agents 640) and refreshes symlink `/home/hermes/.hermes/memories/HANDOVER.md` → canonical.
  - Trigger: last step of handover PowerShell on Latitude is now `scp HANDOVER.md g9-ts:/tmp/HANDOVER.md ; ssh g9-ts "sudo /usr/local/bin/ingest-handover"` after `git push`.
  - Auto-load: file lives inside hermes's `~/.hermes/memories/` so it becomes part of context on next Hermes session start — no manual "read the handover" prompt needed.
  - Policy: latest-only, overwrite each time. No archive dir. Re-evaluate if history becomes useful.
  - Verified end-to-end Session 72b: `sudo -u hermes cat /home/hermes/.hermes/memories/HANDOVER.md` returns full file through the symlink.
- **Session 72c additions (2026-04-20) — Bidirectional handover + Hermes cluster SSH:**
  - **Hermes can now write to HANDOVER.md + push to GitHub.** Clone at `/data/hermes/psc-handover/` (hermes:agents, setgid 2775). Git remote set to SSH: `git@github.com:robpitman1982-ux/python-master-strategy-creator.git`. git user = "Hermes Agent <hermes-agent@g9.local>".
  - **Deploy key on GitHub:** repo Settings → Deploy keys → "Hermes Agent (g9)" with write access. Pubkey `ssh-ed25519 AAAAC3...EawZR hermes-agent@g9` at `/home/hermes/.ssh/id_ed25519_github`. Confirmed via `ssh -T git@github.com` → "Hi robpitman1982-ux/python-master-strategy-creator!".
  - **Symlink repointed:** `/home/hermes/.hermes/memories/HANDOVER.md` → `/data/hermes/psc-handover/HANDOVER.md` (was → `/data/shared/handover/` in 72b, now → the live git clone).
  - **Old ingest retired.** `/usr/local/bin/ingest-handover` removed. Replaced by `/usr/local/bin/sync-handover` (repo-tracked at `scripts/sync-handover.sh`) which does `git fetch` + `git merge --ff-only origin/main`. Old `scripts/ingest-handover.sh` deleted from repo.
  - **Sync triggers:**
    - Explicit (Latitude after Claude pushes): `ssh g9-ts "sudo /usr/local/bin/sync-handover"`
    - Safety net (root cron): `/etc/cron.d/sync-handover` runs `*/5 * * * *` with `--quiet`, logs to `/var/log/sync-handover.log`.
  - **Hermes cluster SSH (Phase 2 gate crossed):** generated separate `/home/hermes/.ssh/id_ed25519_cluster` keypair. Pubkey `ssh-ed25519 AAAAC3...JvbVaj hermes-agent@g9-cluster` appended to rob's authorized_keys on c240, gen8, r630. Hermes's `~/.ssh/config` has `c240`/`gen8`/`r630` aliases (Tailscale IPs) — **deliberately no `latitude` or `x1` aliases.** Hermes logs in as rob (NOPASSWD sudo inherited). Tested: Hermes → c240 ✅, → gen8 ✅, → r630 ✅.
  - **Laptop isolation verified:** Latitude's `administrators_authorized_keys` only contains Latitude's own key + X1 Carbon's key. No server pubkeys present. Empirical test — `sudo -u hermes ssh rob@100.79.72.125` → `Permission denied (publickey,password,keyboard-interactive)` ✅.
  - **X1 Carbon unverified** (offline at audit time) — must inspect its `administrators_authorized_keys` and `~/.ssh/authorized_keys` next time it's online to confirm no server pubkeys present. See Open Issue #7.
  - **Phase 1 validation scope changed.** Hermes now has repo-write + cluster SSH, which was scoped for "Phase 2" in the original plan. Trust level elevated at Rob's direction per Session 72c decision.
- Hermes self-test passed 2026-04-20
- **Hermes Protocol — READ THIS, HERMES (the agent reading its memories/HANDOVER.md symlink):**
  - You edit HANDOVER.md directly. No buffer file. One source of truth, committed to git.
  - Workflow every time you need to record a change:
    1. `cd /data/hermes/psc-handover`
    2. `git pull --ff-only` (pick up anything Claude/Rob pushed from Latitude)
    3. Edit `HANDOVER.md` — update "Last updated" line in the header, update the relevant section, update Open Issues / On The Horizon if applicable. Preserve existing structure.
    4. `git add HANDOVER.md`
    5. `git commit -m "hermes: <concise summary of what changed>"`
    6. `git push`
  - Commit messages: always prefix with `hermes:` so Rob/Claude can see who made the change in `git log`.
  - If `git push` is rejected (someone else pushed meanwhile): `git pull --rebase origin main`, resolve conflicts if any, retry `git push`.
  - Never commit anything other than HANDOVER.md via this clone without asking Rob first. This clone is scoped to handover maintenance, not full development.
  - When you make infrastructure changes on c240/gen8/r630 (packages installed, configs changed, services started), update the relevant server section in HANDOVER.md. That's how Rob's next Claude chat stays current on what you've done.
  - Do not modify `HANDOVER.md` during conversations unless something concrete happened worth recording. Casual chats don't need handover entries.
- **Session 72d additions (2026-04-20) — Hermes skills + reconcile cron + memory filter discovered:**
  - **Two skills created by Hermes** in `/home/hermes/.hermes/skills/productivity/`:
    - `handover-update/SKILL.md` (4 KB) — documents the pull → edit → commit → push workflow, commit-message conventions, what-to-edit decision table, pitfalls. Invoke when updating HANDOVER from a Hermes session.
    - `handover-memory-reconcile/SKILL.md` (4.8 KB) — SHA-based skip logic, section-focused reading strategy, memory-filter workaround documented, state-file path. Invoked by the hourly cron below.
  - **Cron job `3fbca7f44580`** registered via Hermes's native `cronjob` tool at `/home/hermes/.hermes/cron/jobs.json`. Runs `handover-memory-reconcile` skill every 60 minutes, reports to Rob's Telegram only if MEMORY needed updating (silent on no-op). Reads `/data/shared/handover/LAST_CHANGE` (written by sync-handover when git repo fast-forwards) and compares against `/home/hermes/.hermes/state/last_reconciled_sha`. First run: 09:43 UTC 2026-04-20.
  - **Memory tool security filter — BY DESIGN, not a bug.** `tools/memory_tool.py` has a regex blocklist on all memory writes:
    - `authorized_keys` → tagged `ssh_backdoor`
    - `~/.ssh` or `$HOME/.ssh` → tagged `ssh_access`
    - `~/.hermes/.env` → tagged `hermes_env`
    Intent: prevent the LLM-managed memory store from ever holding pointers to credential artifacts. If memory leaks via context stuffing or cross-session carry-over, no credential locations go with it. **Workaround (the intended pattern):** keep memory entries high-level and abstract ("Hermes can SSH to cluster servers as rob with sudo"), and put key paths / credential-bearing specifics in HANDOVER.md only. HANDOVER.md loads fresh each session via the symlink, so detail is always current without needing durable memory.
  - **MEMORY.md drift fixed.** Session 72c changes (cluster SSH, deploy key, bidirectional flow) are now reflected in the 4-entry memory store (1343 bytes total, ~60% of budget). The stale "Phase 1 NOW: no SSH to cluster" line is gone.
  - **LAST_CHANGE marker wired into sync-handover.** When `sync-handover` detects a real fast-forward (not a no-op pull), it writes `/data/shared/handover/LAST_CHANGE` with fields `sha`, `timestamp`, `previous_sha`. hermes:agents 640. Enables both Hermes's cron and future external triggers to know what actually changed via `git diff --name-only $previous_sha $sha`.
  - **First cross-agent git sync verified.** Hermes commit `485e3a1` (self-test) was pulled by Latitude before Claude pushed `5c71e28`/`5ba9235`. Round-trip works both directions. No conflicts.
  - **Session still `memory_flushed: false`** in sessions.json — Hermes's periodic LLM-driven flush hasn't fired (needs ≥6 turns at current config). Not blocking: the explicit `+memory:` tool calls captured what mattered.

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
- **Session 69 cleanup:** Cloud code deleted, ES config bugs fixed, test suite green (236 pass, 0 fail)
- **Session 70 first CFD sweep:** ES daily Dukascopy on c240, 7m runtime, 13 accepted strategies. Max PnL $1.0M (passed $20M critical threshold). Plausibility validated.

---

## Open Issues (Priority Order)

1. **Phase 1 Hermes validation period (1–2 weeks from 2026-04-20).** Drive with Hermes daily. Report: voice roundtrip reliability, task extraction quality, context retention across days, skill auto-promotion (target: ≥3 skills). Go/no-go for Phase 2 (cluster SSH) based on real use.
2. **Delete Latitude's TDS source copy** (~33 GB) now that c240 has a verified full mirror at `/data/market_data/cfds/ticks_dukascopy_tds/` (130,239 files, matching source count). Free up Latitude disk:
   - Verify: `(Get-ChildItem 'C:\Users\Rob\Downloads\Tick Data Suite\Dukascopy' -Recurse -File).Count` should match `find /data/market_data/cfds/ticks_dukascopy_tds -type f \| wc -l` (130,238) + 121 top-level in ohlc/
   - Then: `Remove-Item 'C:\Users\Rob\Downloads\Tick Data Suite' -Recurse -Force`
3. **Clean up stale Tailscale device.** Old `c240` entry (100.104.66.48, from abandoned Hermes pivot) still in tailnet. Remove via [Tailscale admin console](https://login.tailscale.com/admin/machines).
4. **CIMC network config for C240.** CIMC on dedicated port via DHCP; IP not captured. Check router ARP for MAC `00:A3:8E:8E:B3:84` or `nmap -sn 192.168.68.0/22`.
5. **Gen 8 CPU install pending.** 2× E5-2697 v2 arrived. Install under house, verify 48 threads. (Currently 12 threads with E5-2640 v1.)
6. **R630 stale DHCP lease.** `eno1` shows both `192.168.68.78/22` (static) and `192.168.68.75/22` (stale DHCP). Clean via netplan when convenient — `sudo netplan try` to drop the DHCP lease.
7. **X1 Carbon offline ~20h** (noted Session 67 post-relocation tailscale check). Not blocking — wake and verify when next needed as a Claude/Desktop-Commander endpoint. **When back online, also verify laptop SSH isolation:** inspect `C:\ProgramData\ssh\administrators_authorized_keys` AND `C:\Users\rob_p\.ssh\authorized_keys` on X1 and confirm no server pubkeys are present (Latitude was audited clean in Session 72c; X1 was offline at audit time).
8. **CFD swap costs NOT modeled in MC simulator.** Must implement before trusting funding timelines. Cost profiles defined in `configs/cfd_markets.yaml` but not yet consumed by portfolio selector.
9. **Dashboard Live Monitor broken.** Engine log and Promoted Candidates sections don't work during active runs.
10. **Hermes cost tracking shows $0.00 / "unknown" in sessions.json.** Token counters aren't populating (`input_tokens: 0`, `cost_status: "unknown"`) despite Hermes hitting Anthropic API rate limits (so it IS making real paid calls). Relies on upstream fix from NousResearch — design spec at `/data/hermes/hermes-agent/docs/plans/2026-03-16-pricing-accuracy-architecture-design.md`. Until fixed, check actual spend at https://console.anthropic.com/settings/usage — that's authoritative. Not blocking (API billing is happening correctly; Hermes just isn't self-reporting).

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
- **Session 72 (2026-04-20):** Hermes + OpenClaw deployed on g9. g9 brought back from offline state (21h last-seen on Tailscale) via `sudo tailscale up --reset`; LAN IP moved .75 → .50 post-relocation DHCP lease change. Users + dirs created: hermes (1001), openclaw (1002), group agents, /data/{hermes,openclaw,shared}/ tree with setgid shared workspace. Hermes Agent installed from `NousResearch/hermes-agent` via uv venv Python 3.11, brain = Claude Sonnet 4.6, STT = local faster-whisper, TTS = Edge TTS, Telegram bot `@pitmans_heremes_bot`. Voice roundtrip validated. Project manifest (26 KB) absorbed into MEMORY.md + USER.md. OpenClaw installed via npm, system-level systemd unit (not user-level — Node wrapper dropped bus context), 5 plugins ran (acpx, browser, device-pair, phone-control, talk-voice), then stopped+disabled. Phase 1 = Hermes solo for 1–2 weeks; OpenClaw dormant backup. Backup disabled (rclone cron removed, config preserved).

### Key Architectural Decisions Made Along the Way
- **Fixed position sizing** (Session 45): initial_capital only, no compounding — matches prop firm rules
- **Dropped 5m timeframe** (Session 42): zero accepted strategies, ~50% of compute cost
- **Fire-and-forget via GCS** (Session 34): bundle staged to GCS before VM creation, eliminates SCP preemption window
- **Vectorized trades** (Session 61): numpy 2D arrays replace per-bar Python loop, 14-23x faster
- **Block bootstrap MC** (Session 58): preserves crisis clustering vs naive shuffle
- **3-layer correlation** (Session 58): active-day + DD-state + tail co-loss replaces simple Pearson
- **Dukascopy for discovery, The5ers for validation** (Session 63): tick data architecture separates strategy discovery (deep Dukascopy history) from execution validation (The5ers real spreads)
- **Local cluster replaces cloud** (Session 65): `run_local_sweep.py` + `run_cluster_sweep.py` replace GCP SPOT runners. Zero cloud dependencies. ~200 threads available locally (C240: 80, Gen 8: 12→48 post-CPU-upgrade, R630: 88). Note: g9 is NOT in this pool — it's the standalone autonomous business host.

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

- **Session 73 PRIORITY (deferred from 72): ES sanity-check sweep across 4 TFs (daily / 60m / 30m / 15m). ES-only, no 5m.** Rob's scope decision — validate engine params + TF-dependent logic on known-good market before scaling out. Session 70 proved ES daily works (13 accepted, PF 1.52 median). Extends ES to 3 more TFs and confirms clean output. Runs on c240 alone (~30–60 min), no WOL needed. If clean: Session 74 fans out to 23 markets × 4 TFs = 92 sweeps across c240+gen8+r630. If dirty: fix engine before touching other markets.
- **Delete Latitude TDS source** (`C:\Users\Rob\Downloads\Tick Data Suite\`, ~33 GB) — c240 has verified full mirror at `/data/market_data/cfds/ticks_dukascopy_tds/`.
- **Capture C240 CIMC IP** — check router ARP for MAC `00:A3:8E:8E:B3:84`.
- **Clean up stale Tailscale `c240` device** (100.104.66.48) via admin console.
- **Gen 8 CPU install** — 2× E5-2697 v2 arrived, install under house, verify 48 threads.
- **R630 netplan cleanup** — drop stale `192.168.68.75` DHCP lease from eno1.
- **Full 24-market sweep (Session 74)** — `python run_cluster_sweep.py` (all markets × 4 TFs = 92 sweeps, 5m excluded) on c240 orchestrating gen8 + r630. Gated on Session 73 ES validation passing.
- Implement CFD swap/overnight cost modeling in MC simulator (cost profiles in `configs/cfd_markets.yaml`).
- **Challenge vs Funded mode** — implement spec in `docs/CHALLENGE_VS_FUNDED_SPEC.md`.
- Static IP port forwarding setup once new ISP connected.
- **Hermes cluster SSH — DONE Session 72c:** Hermes now has direct SSH to c240/gen8/r630 as rob user (NOPASSWD sudo). Phase 2 trust level elevated ahead of original 1–2-week Phase 1 validation window per Rob's direction. No scoped `hermes-agent-runner` allowlist wrapper — full shell access. Laptops remain isolated.
- **OpenClaw re-enable decision** — defer until specific need emerges (sandboxed untrusted code execution, a plugin Hermes lacks). Unit at `/etc/systemd/system/openclaw-gateway.service`, currently disabled. Fix default model to `anthropic/claude-sonnet-4-6` before restart.
- **External memory provider decision** — FTS5 keyword session search is built-in and working. Supermemory/Honcho/Mem0 only if Phase 1 shows need.
- **Set spend cap on Anthropic API key** at https://console.anthropic.com/settings/limits — belt-and-braces against runaway Hermes cost (currently no hard ceiling). Rob's stated Hermes budget is $30/mo. Set the cap slightly above that to avoid accidental cutoffs during legitimate high-context sessions.
- **Multi-LLM panel-review skill for Hermes.** Already supported by hermes-agent — `hermes_cli/providers.py` uses models.dev catalog (109+ providers) + user overlays. Plan: add OpenAI + Gemini API keys to `~/.hermes/.env`, add provider entries in `~/.hermes/config.yaml`, build `panel-review` skill at `~/.hermes/skills/research/panel-review/` that calls Claude + GPT + Gemini in parallel on a given question and synthesises three perspectives + a reconciliation. Fit: big architectural calls, risky code changes, strategy direction. Cheap (~$0.05/question × 3 providers). Rob already does this manually via ChatGPT and Gemini web — automating via Hermes removes copy-paste. Defer until after Hermes Phase 1 validation settles.
- Strategy templates to reduce search space.

---

## Connection Quick Reference

```
# SSH aliases (from Latitude or X1 Carbon)
ssh c240          # Cisco C240 M4 — LAN 192.168.68.53, Tailscale 100.120.11.35 (device name c240-1)
ssh gen8          # Gen 8 Tailscale (100.76.227.12) — LAN 192.168.68.71
ssh r630          # Dell R630 Tailscale (100.85.102.4) — LAN 192.168.68.78
ssh x1            # X1 Carbon Tailscale (100.86.154.65)
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

# Hermes / OpenClaw management (on g9)
# Hermes status   : sudo -u hermes bash -l -c 'hermes gateway status'
# Hermes logs     : sudo tail -f /home/hermes/.hermes/logs/agent.log
# Hermes restart  : sudo -u hermes env XDG_RUNTIME_DIR=/run/user/1001 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus systemctl --user restart hermes-gateway.service
# Telegram bot    : @pitmans_heremes_bot (voice memo in, audio out)
# Hermes repo     : /data/hermes/psc-handover/ (hermes:agents, git remote=SSH, deploy key Hermes Agent (g9) on GitHub)
# Hermes cluster  : sudo -u hermes ssh c240 / gen8 / r630 (logs in as rob, NOPASSWD sudo)
# Handover sync   : ssh g9-ts "sudo /usr/local/bin/sync-handover"   # called by Latitude after every git push of HANDOVER.md
#                   -> /data/hermes/psc-handover/HANDOVER.md  (canonical, hermes:agents, git-tracked)
#                   -> /home/hermes/.hermes/memories/HANDOVER.md  (symlink, auto-loaded next Hermes session)
#                   -> /data/shared/handover/LAST_CHANGE  (sha+timestamp marker, read by Hermes reconcile cron)
#                   Safety-net cron /etc/cron.d/sync-handover runs every 5 min, logs to /var/log/sync-handover.log
# Hermes cron jobs: /home/hermes/.hermes/cron/jobs.json  (managed by Hermes's `cronjob` tool)
#   Active: 3fbca7f44580 (handover-memory-reconcile, every 60m)
#   Inspect: sudo cat /home/hermes/.hermes/cron/jobs.json | python3 -m json.tool
#   Pause:  ask Hermes "pause cron 3fbca7f44580" via Telegram
# Hermes skills   : /home/hermes/.hermes/skills/productivity/handover-{update,memory-reconcile}/SKILL.md
# OpenClaw start  : sudo systemctl start openclaw-gateway.service && sudo systemctl enable openclaw-gateway.service
# OpenClaw stop   : sudo systemctl stop openclaw-gateway.service && sudo systemctl disable openclaw-gateway.service (current state)
# OpenClaw logs   : sudo tail -f /data/openclaw/logs/gateway.stdout.log

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
