# HANDOVER.md — Session Continuity Document
# Last updated: 2026-04-13 (Session: Infrastructure Hardening + Hardware Shopping)
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
- **Contabo VPS blocker:** MT5 Netting vs Hedge mode — CFD symbols unavailable. Support email sent to The5ers.

### Home Lab Infrastructure

#### Lenovo Latitude (desktop-k2u9o61) — MAIN CONTROL & DEVELOPMENT MACHINE
- Windows 10 Pro, Tailscale 100.79.72.125
- Rob's primary laptop for scripting, development, and project building
- Used at home AND in the field — this is where Rob works day-to-day
- OpenSSH Server installed, key auth working, firewall port 22 open

#### X1 Carbon (desktop-2kc70vg) — ALWAYS-ON NETWORK HUB
- Windows 10 Pro, IP 192.168.68.70, Tailscale 100.86.154.65
- In a drawer, lid down, permanently connected to home LAN
- Always-on Claude.ai + Desktop Commander endpoint
- SSH config at C:\Users\rob_p\.ssh\config with aliases: gen9, gen9-ts, gen8, gen8-ts, homepc, contabo
- WOL scripts: wake-gen9.bat, wake-gen8.bat, wake-all.bat in C:\Users\rob_p\
- Port 22 firewall opened for inbound SSH

#### Gen 9 (DL360, dl360g9) — ALWAYS-ON DATA HUB + COMPUTE
- Ubuntu 24.04, IP 192.168.68.69, Tailscale 100.121.107.49, iLO 192.168.68.75
- MAC: ec:eb:b8:97:83:00
- **ALWAYS ON — do NOT auto-shutdown.** ~$15-20/mo power. Remove auto-shutdown cron.
- SSH enabled at boot ✅, key auth ✅, WOL persistent via netplan ✅
- ARP flush on boot (cron)
- iLO power restore: Always Power On ✅ (set via iLO web UI AND ipmitool)
- ipmitool installed
- Samba share working: \\192.168.68.69\photos (3TB LVM volume)
- SSH config has alias to gen8

#### Gen 8 (DL380p, dl380p) — COMPUTE WORKER (SLEEPS WHEN IDLE)
- Ubuntu 24.04, IP 192.168.68.71, Tailscale 100.76.227.12, iLO 192.168.68.76
- MAC: ac:16:2d:6e:74:2c
- SSH enabled at boot ✅, key auth ✅, WOL persistent via netplan ✅
- Auto-shutdown 30min idle (cron), ARP flush on boot (cron)
- iLO power restore: Always Power On ✅ (set via ipmitool chassis policy always-on)
- iLO was on wrong subnet (192.168.20.233), FIXED to 192.168.68.76
- Duplicate netplan FIXED (removed 50-cloud-init.yaml DHCP conflict)
- **ISSUE: SSH may take 5+ min to come up after reboot (slow BIOS POST). Not a config problem.**
- **ISSUE: SSH failed to auto-start on one reboot test — needs further investigation. May need ssh-recover service fallback.**
- SSH config has alias to gen9

#### Dell R630 — ARRIVING / NOT YET SET UP (COMPUTE WORKER, SLEEPS WHEN IDLE)
- Will use Ubuntu 24.04, same creds (rob/Ubuntu123.)
- Plan: compute worker alongside Gen 9

#### Pending Hardware
- **Dell R730 on eBay** (service tag 3TW3T92, Oakleigh VIC, $500 bid / $1000 BIN) — specs unknown, asked seller for CPU/RAM info. Mfg Jan 2016 (v3 Xeon era). NO HARD DRIVES. Don't bid without knowing specs.
- **RAM needed:** DDR4 ECC RDIMM 32GB sticks, ~$15-25 each on eBay. Check what's in Gen 9/R630 first to match speed/rank.
- **Skip:** Anything DDR3 (R710, R610, R620, R720). Only R630/R730 and above.

### Network
- **New ISP:** Carbon Comms, 500/50 Mbps NBN, **static IP** (being connected)
- **Router:** XE75 Pro at 192.168.68.1
- Static IP enables: direct SSH from field, Hermes webhooks, dashboard access, Contabo push-to-home
- Recommendation: Keep Tailscale as primary remote access. Use static IP for specific services only.

### Cloud Infrastructure
- **GCP (Nikola's account):** project-c6c16a27-e123-459c-b7a, console IP 35.223.104.173
  - n2-highcpu-96, 100 vCPU quota cap (upgrade denied)
  - Bucket: gs://strategy-artifacts-nikolapitman/
- To be decommissioned once local lab stable

### Strategy Engine Status
- **Ultimate leaderboard:** ~454 strategies (414 bootcamp-accepted)
- **Vectorized engine:** Confirmed working. All 52 cloud config YAMLs updated
- **CFD swap rates gathered:** CL=$0.70/micro/night (10x Fri!), SI=$4.05, GC=$2.20, indices near-zero, FX $0.10-0.26

---

## Open Issues (Priority Order)

1. **Gen 8 SSH boot reliability** — failed to auto-start on one reboot test despite `systemctl enable ssh`. May need the ssh-recover.service fallback (25s delayed restart after multi-user.target). Critical before going under house.
2. **Gen 9 reboot test NOT YET DONE** — needs clean reboot verification before going under house.
3. **CFD swap costs NOT modeled in MC simulator.** Must implement before trusting funding timelines.
4. **MT5 Netting vs Hedge mode on Contabo VPS.** Support email sent to The5ers.
5. **Dashboard Live Monitor broken.** Engine log and Promoted Candidates sections don't work during active runs.

---

## Architecture Decision: Compute Cluster

```
Latitude (main control, home + field, SSH via Tailscale)
    │
    ├──► X1 Carbon (always-on, in drawer, Claude + Desktop Commander)
    │        └── SSH relay to all servers
    │
    ├──► Gen 9 (ALWAYS ON — data hub + compute, 80 threads)
    │     ├── holds master/ultimate leaderboards (local SSD)
    │     ├── holds market data (local SSD)
    │     ├── Samba share to X1 Carbon + Latitude
    │     ├── rclone → Google Drive (backup copies only, NOT for compute reads)
    │     ├── receives sweep results from Gen 8 / R630 via rsync
    │     ├── runs leaderboard updater + portfolio selector
    │     └── wakes Gen 8 / R630 via WOL when compute needed
    │
    ├──► Gen 8 (SLEEPS WHEN IDLE — compute worker)
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
- RAM split (96GB DDR4 total): 56GB Gen 9 / 40GB R630 (or 64/32 depending on DIMM sizes)

---

## On The Horizon

- **Remove auto-shutdown cron from Gen 9** (should be always-on)
- Fix Gen 8 SSH boot reliability (ssh-recover.service)
- Complete Gen 9 reboot test
- Set up Google Drive for Desktop on Latitude + X1 Carbon, rclone on Gen 9
- Build sweep results pipeline: Gen 8/R630 → rsync → Gen 9 → leaderboard update → rclone backup
- Implement CFD swap/overnight cost modeling in MC simulator
- Set up Gen 9 as data hub (leaderboards, market data, Samba shares)
- Dell R630 full setup when it arrives
- Hermes Agent on Gen 9 for monitoring/alerting (Linux native, Telegram gateway)
- Vectorize trade simulation loop
- Strategy templates to reduce search space
- Static IP port forwarding setup once new ISP connected

---

## Connection Quick Reference

```
# SSH aliases (from X1 Carbon — Latitude needs same config set up)
ssh gen9          # Gen 9 local (192.168.68.69)
ssh gen9-ts       # Gen 9 Tailscale (100.121.107.49)
ssh gen8          # Gen 8 local (192.168.68.71)
ssh gen8-ts       # Gen 8 Tailscale (100.76.227.12)
ssh homepc        # Latitude Tailscale (100.79.72.125)

# WOL (from X1 Carbon or Latitude)
C:\Users\rob_p\wake-gen9.bat    # MAC ec:eb:b8:97:83:00 (only if Gen 9 is ever manually shut down)
C:\Users\rob_p\wake-gen8.bat    # MAC ac:16:2d:6e:74:2c
C:\Users\rob_p\wake-all.bat    # Both servers

# Server creds: rob / Ubuntu123. (all servers, including future Dell R630)
# GCP SSH: ssh -i C:\Users\Rob\.ssh\google_compute_engine pitman_nikola@35.223.104.173

# iLO access
Gen 9 iLO: https://192.168.68.75 (Administrator / PVPT6M5H)
Gen 8 iLO: https://192.168.68.76 (old SSL - use Firefox, creds unknown)
```

## Key Principles
- Always use Desktop Commander before Windows MCP (Windows MCP hangs)
- Full fixes only — no patches
- Drawdown is the binding constraint on The5ers
- Skip DDR3 servers (R710, R610) — only R630/R730 and above
- SPOT zone: us-central1-f; on-demand fallback: us-central1-c
