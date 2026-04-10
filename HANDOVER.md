# HANDOVER.md — Session Continuity Document
# Last updated: 2026-04-10 (Session: Infrastructure Hardening)
# Auto-updated by Claude at end of each session, pushed to GitHub

---

## Current State

### Live Trading
- **Portfolio #3 EA** deployed on Contabo VPS (89.117.72.49, Windows Server, US East)
  - Strategies: NQ Daily MR + YM Daily Short Trend + GC Daily MR + NQ 15m MR (all 0.01 lots, magic 557701-557704)
  - First live trade confirmed: YM Daily Short Trend, SELL US30 at 46487.56, ticket 532066267
  - Projected: 99.6% pass rate, 6.9% DD, ~13.4 months to fund
- **Portfolio #1 EA** also live on same VPS
- **The5ers** account 26213568 on FivePercentOnline-Real (MT5), $5K High Stakes

### Home Lab Infrastructure
- **Gen 9 (DL360):** Ubuntu 24.04, IP 192.168.68.69, Tailscale 100.121.107.49, iLO 192.168.68.75
  - SSH enabled at boot, key auth working, WOL persistent via netplan, auto-shutdown 30min idle
  - iLO power restore: Always Power On (confirmed)
  - MAC: ec:eb:b8:97:83:00
- **Gen 8 (DL380p):** Ubuntu 24.04, IP 192.168.68.71, Tailscale 100.76.227.12, iLO 192.168.68.76
  - SSH enabled at boot, key auth working, WOL persistent via netplan, auto-shutdown 30min idle
  - iLO power restore: NEEDS SETTING (iLO web UI has SSL issues, use Firefox or set via ipmitool)
  - iLO was on wrong subnet (192.168.20.233), fixed to 192.168.68.76 via ipmitool
  - MAC: ac:16:2d:6e:74:2c
- **Home Desktop (desktop-k2u9o61):** Windows 10 Pro, Tailscale 100.79.72.125
  - OpenSSH Server installed but key auth not yet working. Needs administrators_authorized_keys setup
- **X1 Carbon (desktop-2kc70vg):** Windows 10 Pro, IP 192.168.68.70, Tailscale 100.86.154.65
  - SSH config at C:\Users\rob_p\.ssh\config with aliases: gen9, gen9-ts, gen8, gen8-ts, homepc, contabo
  - WOL scripts: wake-gen9.bat, wake-gen8.bat, wake-all.bat
- **Dell R630:** Purchased, not yet set up. Will use Ubuntu 24.04, same creds (rob/Ubuntu123.)
- **Network:** TP-Link unmanaged gigabit switch, all servers + X1 Carbon on wired ethernet
- Servers going under the house next week — limited physical access after that

### Cloud Infrastructure
- **GCP (Nikola's account):** project-c6c16a27-e123-459c-b7a, console IP 35.223.104.173
  - n2-highcpu-96, 100 vCPU quota cap (upgrade denied)
  - Zone preference: us-central1-f for SPOT, us-central1-c for on-demand
  - To be decommissioned once local lab stable
- **GCS bucket:** gs://strategy-artifacts-nikolapitman/

### Strategy Engine Status
- **Ultimate leaderboard:** 454 strategies (414 bootcamp-accepted)
- **Vectorized engine:** Confirmed working. All 52 cloud config YAMLs updated with `use_vectorized_trades: true`
- **ES all-timeframe results:** 5 accepted (daily MR PF 1.51 best, daily breakout PF 1.30, daily trend PF 1.18, 60m MR ROBUST PF 1.34, 60m trend PF 1.02). 30m/15m: nothing.
- **9-market sweep (EC, JY, BP, AD, NG, US, TY, W, BTC):** Completed several runs. Standout: JY 60m Breakout (PF 2.27, IS 1.70, OOS 3.60, 89 trades, ROBUST, Bootcamp Score 88.7)
- **CFD swap rates gathered (7 Apr 2026):** CL=$0.70/micro/night (10x Fri!), SI=$4.05, GC=$2.20, indices near-zero, FX $0.10-0.26

---

## Open Issues (Priority Order)

1. **CFD swap costs NOT modeled in MC simulator.** Backtests use futures (no swap) but The5ers executes CFDs. Daily bar strategies most affected. Must implement before trusting funding timelines.
2. **MT5 Netting vs Hedge mode on Contabo VPS.** MT5 connects in Netting mode, making CFD symbols unavailable. Support email sent to The5ers.
3. **Dashboard Live Monitor broken.** Engine log and Promoted Candidates sections don't work during active runs.
4. **Gen 8 iLO power restore policy** not yet set (SSL issues with Chrome, try Firefox or ipmitool).
5. **Home Desktop SSH** — key auth not working, needs administrators_authorized_keys properly configured.
6. **Gen 8 SSH intermittently refuses connections** from Gen 9 (works from X1 Carbon). Transient but worth monitoring.

---

## On The Horizon

- Implement CFD swap/overnight cost modeling in MC simulator
- Re-run portfolio selector for Bootcamp $250K with loosened correlation thresholds
- Vectorize trade simulation loop (next major perf gain after filter vectorization)
- Strategy templates per family to reduce combinatorial search space
- Complete 9-market sweep; download and validate all results
- Home server lab: physical setup under house, cross-server rsync, Google Drive backup for market data
- Make 5m timeframe viable (previous SPOT run preempted after 30 min)
- Consider Hermes Agent on Gen 9 for automated monitoring/alerting (WSL2 required, or native Linux)

---

## Key Principles

- **Drawdown is the binding constraint.** Unlimited time on The5ers = pure DD management. Step 1 ($5k max loss on $100k) is primary failure point.
- **Full fixes only — no patches.** Decisions grounded in actual data.
- **CFDs vs futures distinction matters.** Research = futures. Execution = CFDs. Swap costs are real.
- **Cloud config hygiene.** Feature flags must be in ALL config YAMLs, not just local. Kill stale launcher PIDs.
- **SPOT zone discipline.** us-central1-f for SPOT; us-central1-c for on-demand.
- **Always use Desktop Commander before Windows MCP** for SSH/shell tasks.

---

## Connection Quick Reference

```
# SSH aliases (from X1 Carbon)
ssh gen9          # Gen 9 local
ssh gen9-ts       # Gen 9 Tailscale
ssh gen8          # Gen 8 local  
ssh gen8-ts       # Gen 8 Tailscale
ssh homepc        # Home Desktop Tailscale

# WOL (from X1 Carbon)
C:\Users\rob_p\wake-gen9.bat
C:\Users\rob_p\wake-gen8.bat
C:\Users\rob_p\wake-all.bat

# Server creds: rob / Ubuntu123.
# GCP SSH: ssh -i C:\Users\Rob\.ssh\google_compute_engine pitman_nikola@35.223.104.173
```
