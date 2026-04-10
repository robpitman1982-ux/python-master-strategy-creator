# HANDOVER.md — Master System Handover Document
# Last updated: 2026-04-10 (Session: Gen 8 Full Setup + SSH Reboot Fix)
# Auto-updated by Claude at end of each session, pushed to GitHub
# This is the SINGLE SOURCE OF TRUTH for project state across sessions.

---

# TABLE OF CONTENTS

1. [Project Overview](#1-project-overview)
2. [Live Trading Status](#2-live-trading-status)
3. [Prop Firm Targets](#3-prop-firm-targets)
4. [Strategy Engine](#4-strategy-engine)
5. [Infrastructure — Home Lab](#5-infrastructure--home-lab)
6. [Infrastructure — Cloud (GCP)](#6-infrastructure--cloud-gcp)
7. [Infrastructure — VPS (Contabo)](#7-infrastructure--vps-contabo)
8. [Network & Connectivity](#8-network--connectivity)
9. [Market Data](#9-market-data)
10. [Sweep Results & Leaderboard](#10-sweep-results--leaderboard)
11. [Portfolio Selector](#11-portfolio-selector)
12. [CFD Swap Cost Discovery](#12-cfd-swap-cost-discovery)
13. [Open Issues (Priority Order)](#13-open-issues-priority-order)
14. [Roadmap](#14-roadmap)
15. [Key Principles & Lessons Learned](#15-key-principles--lessons-learned)
16. [Session Log](#16-session-log)
17. [Quick Reference](#17-quick-reference)

---

# 1. PROJECT OVERVIEW

**What:** Automated strategy discovery and portfolio selection engine for futures/CFD trading. Sweeps filter combinations, evaluates against prop firm rules, selects portfolios via Monte Carlo simulation.

**Who:** Rob, Melbourne, Australia. Algorithmic futures trader targeting prop firm funding.

**Repo:** `robpitman1982-ux/python-master-strategy-creator`
**Local (Home Desktop):** `C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator\`
**On servers:** `~/python-master-strategy-creator/`

**Key files:** `CLAUDE.md` (Claude Code bible), `HANDOVER.md` (this file), `config.yaml`, `master_strategy_engine.py`, `run_portfolio_all_programs.py`, `run_spot_resilient.py`

**Working style:** Direct and concise. Full fixes only. Cross-validates with ChatGPT/Gemini. Claude.ai for planning, Claude Code for unattended execution.

---

# 2. LIVE TRADING STATUS

**Account:** The5ers account 26213568, FivePercentOnline-Real (MT5), $5K High Stakes

**Portfolio #3 EA** — LIVE on Contabo VPS (89.117.72.49)
- Strategies: NQ Daily MR + YM Daily Short Trend + GC Daily MR + NQ 15m MR (0.01 lots, magic 557701-557704)
- First live trade: YM Daily Short Trend, SELL US30 at 46487.56, ticket 532066267
- Projected: 99.6% pass rate, 6.9% DD, ~13.4 months to fund

**Portfolio #1 EA** — also LIVE on same VPS

---

# 3. PROP FIRM TARGETS

**Priority:** 1. The5ers (PRIMARY), 2. FTMO, 3. Darwinex Zero, 4. FundedNext CFD
**Excluded:** Topstep, Apex, FundedNext Futures (no overnight holds)
**Key constraint:** Drawdown is binding. Unlimited time on The5ers = pure DD management. Step 1 ($5k max loss) is primary failure point.

---

# 4. STRATEGY ENGINE

**Families:** Mean Reversion (31,008 combos), Trend (9,373), Breakout (16,473). 12 strategy types total.
**Vectorized engine:** 14-23x faster. All 52 cloud YAMLs updated with `use_vectorized_trades: true`.
**Tests:** 30 smoke + 4 subtype + 25 parity + 7 generate_returns tests.

---

# 5. INFRASTRUCTURE — HOME LAB

## Gen 9 — HP DL360 Gen9 (PRIMARY)
- **OS:** Ubuntu 24.04.4 LTS, hostname dl360g9
- **CPU:** E5-2603 v4 (6c) — UPGRADE PENDING: 2x E5-2673 V4 ordered (40c/80t)
- **RAM:** 1x 32GB DDR4-2400 RDIMM. Target 128GB (need DDR4-2400 ECC RDIMM PC4-19200R)
- **Storage:** 7.3TB (100GB OS, 3TB /mnt/photos)
- **IPs:** LAN 192.168.68.69, Tailscale 100.121.107.49, iLO 192.168.68.75
- **iLO creds:** Administrator / PVPT6M5H
- **MAC:** ec:eb:b8:97:83:00
- **SSH:** Key auth, passwordless sudo, ssh.socket DISABLED, ssh-recover.service + cron @reboot
- **Python:** 3.12.3, venv with all deps. Repo cloned via deploy key `dl360g9`.

## Gen 8 — HP DL380p Gen8 (SECONDARY)
- **OS:** Ubuntu 24.04.4 LTS, hostname dl380p
- **CPU:** 1x E5-2640 v1 (6c/12t). Planned: 2x E5-2697 V2 (24c/48t)
- **RAM:** 80GB DDR3 ECC. Target 128GB (need DDR3-1333 ECC RDIMM PC3-10600R)
- **Storage:** 97.87GB (P420i RAID, degraded)
- **IPs:** LAN 192.168.68.71, Tailscale 100.76.227.12, iLO 192.168.68.76
- **MAC:** ac:16:2d:6e:74:2c
- **SSH:** Key auth, passwordless sudo, ssh.socket DISABLED, ssh-recover.service + cron @reboot
- **Python:** 3.12.3, venv with all deps. Repo cloned via deploy key `dl380p-deploy`.
- **iLO:** Password unknown (factory reset). Old TLS blocks browsers. Use ipmitool.

## Dell R630 (NOT YET SET UP)
- Purchased, freight pending. Expected: 2x E5-2699 V4 (44c/88t). Ubuntu 24.04.

## Post-upgrade total: Gen9 40c/80t + Gen8 24c/48t + R630 44c/88t = **108c/216t**

## Control Machines
- **X1 Carbon (desktop-2kc70vg):** Win10 Pro, IP .70, TS 100.86.154.65, user rob_p. SSH config + WOL scripts.
- **Home Desktop (desktop-k2u9o61):** Win10 Pro, TS 100.79.72.125, user Rob. SSH config with aliases.
- **Contabo VPS (89.117.72.49):** Windows Server, US East, $17.66/mo. MT5 for The5ers live trading.

---

# 6. INFRASTRUCTURE — CLOUD (GCP)

**Status:** TO BE DECOMMISSIONED once home lab stable.
- Nikola's account, project `project-c6c16a27-e123-459c-b7a`, console 35.223.104.173
- n2-highcpu-96, 100 vCPU cap. SPOT zone: us-central1-f. On-demand: us-central1-c.
- Bucket: `gs://strategy-artifacts-nikolapitman/`

---

# 8. NETWORK & CONNECTIVITY

```
NBN -> Deco XE75 Pro (192.168.68.1)
       Port 1 -> TP-Link LS108G (under house)
                  Gen 9 (.69) + iLO (.75)
                  Gen 8 (.71) + iLO (.76)
                  R630 (TBD)
                  X1 Carbon (.70)
```

Cross-SSH verified: X1->Gen9, X1->Gen8, Gen9->Gen8, Gen8->Gen9, HomePC->both via Tailscale.

---

# 9. MARKET DATA

**On servers (344MB):** AD, BP, BTC, EC, JY, NG, TY, US, W (9 markets x 4 timeframes)
**MISSING from servers:** ES, NQ, YM, GC, CL, SI (core 6 — on Home Desktop and GCP)
**The5ers tradeable:** SP500, NAS100, US30, XAUUSD, XAGUSD, XTIUSD. NOT available: RTY, HG, W, NG, US, TY.

---

# 10. SWEEP RESULTS & LEADERBOARD

**Ultimate leaderboard:** 454 strategies (414 bootcamp-accepted)
**ES best:** Daily MR PF 1.51 (590 trades)
**Standout:** JY 60m Breakout PF 2.27, ROBUST, Score 88.7 — prime diversification candidate

---

# 11. PORTFOLIO SELECTOR

Recent fixes: Pre-screen MC, 50/50 composite score, 2-step/3-step logic, per-step time estimates, regime gate off, correlation thresholds loosened, candidate cap 100.

---

# 12. CFD SWAP COST DISCOVERY

**Critical:** Swap costs NOT modeled in MC simulator. CL=$0.70/micro/night (10x Fri = $350/weekend at 50 micros). SI=$4.05. GC=$2.20. Indices near-zero. FX $0.10-0.26. Must implement before trusting funding timelines.

---

# 13. OPEN ISSUES (PRIORITY ORDER)

1. CFD swap costs NOT modeled in MC simulator
2. Core market data (ES/NQ/YM/GC/CL/SI) missing from home lab servers
3. MT5 Netting vs Hedge mode on Contabo VPS
4. Dashboard Live Monitor broken
5. Gen 8 iLO password unknown (try ipmitool or Firefox TLS min=1)
6. Code refactor needed — strip GCS references for local workflow
7. W/NG/US/TY not on The5ers — add to excluded_markets

---

# 14. ROADMAP

## Phase 1: Infrastructure (MOSTLY DONE)
- [x] Both servers: Ubuntu, deps, repo, venv, SSH, Tailscale, static IP, WOL
- [x] SSH after reboot fix (ssh.socket disabled, recovery service + cron)
- [x] Cross-SSH between all machines
- [ ] Transfer core market data to servers
- [ ] Dell R630 setup
- [ ] Move servers under house
- [ ] Google Drive backup via rclone

## Phase 2: Code Refactor
- [ ] Strip GCS references, localize everything
- [ ] Implement CFD swap cost modeling in MC simulator
- [ ] Build distributed sweep launcher (cross-server)

## Phase 3: Dual Engine (Futures + CFD)
## Phase 4: Expansion (FX 15m/30m sweeps, 5m timeframe, strategy templates)

---

# 15. KEY PRINCIPLES & LESSONS LEARNED

- Drawdown is the binding constraint. Full fixes only — no patches.
- CFDs vs futures matters operationally. Swap costs are real and unmodeled.
- Cloud config hygiene — feature flags in ALL 52 YAMLs. Kill stale PIDs.
- On HP ProLiants: DISABLE ssh.socket, use plain ssh.service + recovery service + cron @reboot. DO NOT use network-online.target — it hangs.
- RAM must be ECC Registered (RDIMM). Gen9=DDR4-2400. Gen8=DDR3-1333.
- WOL from home desktop needs subnet broadcast (192.168.68.255), not plain broadcast.
- Always use Desktop Commander before Windows MCP for SSH tasks.

---

# 16. SESSION LOG

| Date | Session | Key Accomplishments |
|------|---------|-------------------|
| Mar 2026 | 1-58 | Engine built, GCP sweep flow, 8 markets (315 strategies) |
| 2026-04-01 | 59 | SPOT resilient runner, 9 new markets |
| 2026-04-02 | 60 | Vectorized trade engine (14-23x speedup) |
| 2026-04-03 | 61-62 | Cloud config fix, 9-market sweeps, leaderboard aggregation fix |
| 2026-04-05 | - | Dell R630 purchased |
| 2026-04-06 | Portfolio V2 | 5 critical selector fixes |
| 2026-04-07 | Swap discovery | CFD swap rates, candidate cap 100 |
| 2026-04-08 | Home lab | Gen 9 Ubuntu+Tailscale, Gen 8 Ubuntu, handover doc |
| 2026-04-09 | Hardening | SSH at boot, WOL, auto-shutdown, iLO fix, HANDOVER.md pushed |
| 2026-04-10 | Full setup | Both servers: apt, sudo, TZ, Tailscale, static IP, deploy keys, repo, venv, deps, cross-SSH. SSH reboot fix (ChatGPT: disable ssh.socket + recovery service + cron). Reboot + WOL tests PASSED on both. |

---

# 17. QUICK REFERENCE

## SSH (from Home Desktop)
```
ssh gen9    # Tailscale 100.121.107.49
ssh gen8    # Tailscale 100.76.227.12
ssh gcp     # 35.223.104.173
```

## SSH (from X1 Carbon)
```
ssh -i C:\Users\rob_p\.ssh\id_ed25519 rob@192.168.68.69   # Gen 9
ssh -i C:\Users\rob_p\.ssh\id_ed25519 rob@192.168.68.71   # Gen 8
```

## WOL (from Home Desktop — PowerShell)
```powershell
# Gen 8: MAC ac:16:2d:6e:74:2c
# Gen 9: MAC ec:eb:b8:97:83:00
# Use subnet broadcast 192.168.68.255 port 9
```

## Server creds: rob / Ubuntu123
## iLO Gen 9: Administrator / PVPT6M5H
## Venv: cd ~/python-master-strategy-creator && source venv/bin/activate
