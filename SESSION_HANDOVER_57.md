# SESSION HANDOVER — For Next Claude Chat
## Date: 2026-04-03
## From: Session 57 (EA build, GCP migration, Contabo VPS, portfolio selector upgrades)
## To: Session 58+ (VPS MT5 fix, portfolio re-evaluation, live trading)

---

## WHAT THIS PROJECT IS

Rob is building an automated strategy discovery engine (`python-master-strategy-creator`) that sweeps filter combinations across futures markets, runs strategies through a quality pipeline, and selects optimal portfolios for prop firm challenges. The engine runs on GCP n2-highcpu-96 VMs.

**Repo**: `C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator\`
**GitHub**: `robpitman1982-ux/python-master-strategy-creator`

---

## CRITICAL: THE5ERS IS CFD, NOT FUTURES

The5ers main programs trade **CFDs on MT5**, not futures. Backtested edge transfers directly.

### Rob's Live The5ers Account
- **Program**: $5K High Stakes (2-step, 10% DD, 5% daily DD, 8%+5% targets)
- **Account**: 26213568 on FivePercentOnline-Real (MT5)
- **Status**: Active, Evaluation phase, 0 trades
- **Platform**: MetaTrader 5 (installed, connected on laptop, EA attached)

### CFD Symbol Mapping (verified from MT5)
| Futures | CFD Symbol | Contract Size | $/Point/Lot |
|---------|-----------|--------------|-------------|
| ES | SP500 | 1 | $1/pt |
| NQ | NAS100 | 1 | $1/pt |
| YM | US30 | 1 | $1/pt |
| GC | XAUUSD | 100 | $100/pt |


---

## WHAT WAS ACCOMPLISHED THIS SESSION

### 1. MT5 EA Built — Portfolio #3 (LIVE)
Built complete MQL5 Expert Advisor for The5ers $5K High Stakes evaluation.
- **File**: `EA/Portfolio3_The5ers.mq5`
- **Compiled**: 0 errors, 0 warnings (build 5723)
- **Status**: Was running on laptop MT5, currently stopped pending VPS setup
- **4 strategies implemented**:

| # | Strategy | Symbol | TF | Direction | Filters | Hold | Stop | Trail |
|---|----------|--------|----|-----------|---------|------|------|-------|
| 1 | NQ Daily MR | NAS100 | D1 | LONG | BelowFastSMA(5) + DistanceBelowSMA(5,0.4) + DistanceFromExtreme(5,20,1.5) | 5 bars | 0.4×ATR | — |
| 2 | YM Short Trend | US30 | D1 | SHORT | LowerHigh + DownCloseShort + LowerLow | 1 bar | 0.75×ATR | 1.5×ATR |
| 3 | GC Daily MR | XAUUSD | D1 | LONG | BelowFastSMA(5) + DistanceBelowSMA(5,0.4) + TwoBarDown | 5 bars | 0.4×ATR | — |
| 4 | NQ 15m MR | NAS100 | M15 | LONG | ThreeBarDown + ReversalUpBar + StretchFromLongTermSMA(800,1.0) | 16 bars | 0.4×ATR | — |

- **Position sizing**: 0.01 lots each (1 micro equivalent)
- **Magic numbers**: 557701-557704
- **Entry logic**: Checks filters on completed bar (shift=1), enters at market on new bar open
- **The5ers compliance**: Visible SL on every entry, no HFT, no latency arb

### 2. GCP Account Migrated (Wife's Account)
- **Project ID**: `project-c6c16a27-e123-459c-b7a`
- **GCS Bucket**: `gs://strategy-artifacts-nikolapitman/`
- **Strategy Console VM**: `35.223.104.173` (e2-micro, us-central1-c)
- **Credit**: $435.26, expires July 2, 2026
- **CPU Quota**: 100 on-demand + 100 preemptible across us-central1, us-west1, us-east1
- **Repo cloned**, Streamlit dashboard running on port 8501
- **Session 56 Claude Code**: All 9 tasks completed, all committed


### 3. Contabo Windows VPS Ordered
- **Order ID**: 14812002
- **IP**: 89.117.72.49
- **Location**: Carlstadt, US East (New York) — near The5ers' NY server
- **Specs**: Cloud VPS 10, 4 vCPU AMD EPYC, 8GB RAM, 75GB NVMe, Windows Server
- **Cost**: $17.66/month incl GST
- **RDP access**: Working (username `Administrator`)
- **MT5 installed**: Yes, Five Percent Online branded installer
- **BLOCKER**: MT5 connects as **Netting** instead of **Hedge** mode. CFD symbols (NAS100, US30, XAUUSD) not available. Only stocks/indices appear.

### 4. VPS MT5 Issue — WAITING ON THE5ERS
- **Problem**: Every new MT5 installation (both generic and branded) connects to FivePercentOnline-Real in Netting mode. Rob's laptop installation (from March 31) works in Hedge mode with all CFD symbols.
- **Email sent** to help.desk@the5ers.com requesting fix
- **Subject**: "Account 26213568 - MT5 connecting as Netting instead of Hedge on new installation"
- **Things tried that didn't work**:
  - Generic MT5 installer from metatrader5.com
  - Five Percent Online branded installer from laptop Downloads
  - Server names: FivePercentOnline-Real, mt5.the5ers.com
  - Disconnecting laptop MT5 first
  - Reinstalling multiple times
- **Things NOT yet tried**:
  - Disabling Windows Firewall on VPS (PowerShell as Admin ON THE VPS: `Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False`)
  - Copying entire MT5 data folder from laptop to VPS via RDP drive sharing
  - Contabo network firewall at new.contabo.com → Network Services → Firewall
- **Once The5ers responds**: Should be a quick fix, then 5 minutes to get EA running on VPS


### 5. Portfolio Selector Upgrades — Sessions 57-58 (COMPLETED)
Both sessions executed by Claude Code unattended. **13 commits, 261 tests passing.**

**Session 57 (6 tasks — sizing + scoring):**
1. Hard DD constraint in sizing optimizer (p95 ≤ 70% of limit, p99 ≤ 90%)
2. Inverse-DD sizing initialization (risk-parity seeded weights)
3. Calmar-based pre-MC scoring (7 weighted components replacing crude composite)
4. Portfolio plateau robustness test (weight perturbation + remove-one analysis)
5. Rolling 20-trade DD, max losing streak, recovery time metrics
6. Tests for all above (249/249 passing)

**Session 58 (7 tasks — correlation + MC realism):**
1. 3-layer correlation (active-day, DD-state, tail co-loss) — replaces Pearson
2. Expected Conditional Drawdown (ECD) — replaces binary DD overlap
3. Block bootstrap MC (5/10/20-day blocks) — preserves crisis clustering
4. Daily DD breach tracking in simulation results
5. Regime survival gate (2022/2023/2024-2025 regime windows)
6. 12 new tests (261/261 passing)
7. CHANGELOG + CLAUDE.md updated

**Config flags** (all default to new behavior):
- `use_multi_layer_correlation`: True/False
- `use_ecd`: True/False
- `use_regime_gate`: True/False
- `mc_method`: "block_bootstrap" / "shuffle_interleave"

**Old functions preserved** alongside new ones for backward compatibility.

### 6. New Portfolio Selector Results (Block Bootstrap)
Ran High Stakes with block bootstrap MC + DD-constrained sizing + Calmar scoring.
3-layer correlation and ECD were DISABLED (too strict, rejected all combos — needs threshold tuning).

**Top results:**
| Rank | Portfolio | Pass Rate | DD | Time | Robustness | Verdict |
|------|-----------|-----------|-----|------|------------|---------|
| 1 | NQ daily MR + YM daily Trend + GC daily MR + ES 30m MR | **99.9%** | 6.1% | 11.2mo | 0.99 | RECOMMENDED |
| 4 | NQ+YM+GC daily + GC 30m BO + YM daily BO (5 strats) | 95.7% | 10.2% | **9.3mo** | 0.96 | VIABLE |
| 5 | NQ daily MR + YM daily Trend + GC 30m BO + SI 15m MR | **98.6%** | 8.7% | 15.4mo | 0.96 | RECOMMENDED |

Pass rates did NOT drop as ChatGPT predicted — block bootstrap confirmed the strategies are genuinely robust.


### 7. LLM Review of Portfolio Selector
Shared `docs/PORTFOLIO_SELECTOR_BRIEF.md` with ChatGPT and Gemini for independent review.
Both LLMs provided feedback. Key ideas implemented in Sessions 57-58 above.
File: `docs/PORTFOLIO_SELECTOR_BRIEF.md` — full technical brief with 10 questions for LLM review.

### 8. Bootcamp Portfolio Results (from earlier run)
**Bootcamp $250K top 3:**
1. NQ daily MR + SI daily BO + NQ 60m MR + ES 30m MR — 84.8% pass, DD 7.1%
2. NQ daily MR + YM daily Trend + GC 30m BO + NQ 15m MR — **91.8% pass**, DD 6.1%
3. NQ daily MR + SI daily BO + GC 30m BO + NQ 60m MR — 81.6% pass, DD 7.1%

**3 of 4 strategies in Bootcamp #2 are shared with High Stakes Portfolio #3.**
Only difference: GC 30m Breakout (Bootcamp) vs GC daily MR (High Stakes).

---

## IMMEDIATE PRIORITIES (for next session)

### Priority 1: Fix VPS MT5 (waiting on The5ers)
- Check email for The5ers support response
- Try remaining fixes: disable VPS firewall, copy laptop MT5 data folder, check Contabo network firewall
- Once fixed: compile EA, attach, enable Algo Trading, confirm init messages in Experts tab
- Then stop EA on laptop, VPS takes over 24/7

### Priority 2: Tune 3-layer correlation thresholds
- The new multi-layer correlation + ECD gates rejected ALL portfolio combinations
- Need to loosen thresholds or tune per the current strategy pool
- Suggested: Run with `use_multi_layer_correlation=True` but increase thresholds:
  - active_corr_max: 0.50 → 0.70
  - dd_corr_max: 0.40 → 0.60
  - tail_coloss_max: 0.30 → 0.50
- Then progressively tighten to find the sweet spot

### Priority 3: Re-run Bootcamp with new selector
- Run Bootcamp $250K through the upgraded pipeline (block bootstrap + DD constraints)
- Compare against old Bootcamp results (91.8% pass)
- Decide if worth running a parallel Bootcamp eval


### Priority 4: Consider updating live EA
- Current live Portfolio #3: NQ daily MR + YM daily Trend + GC daily MR + NQ 15m MR
- New Portfolio #1 (block bootstrap): NQ daily MR + YM daily Trend + GC daily MR + ES 30m MR
- Only difference: NQ 15m MR → ES 30m MR in 4th slot
- The core 3 strategies (NQ MR + YM Trend + GC MR) appear in EVERY top portfolio
- Decision: keep current EA or update to new #1? Need to weigh pros/cons

---

## INFRASTRUCTURE

### Old GCP Account (Rob's — EXHAUSTED)
- Console: `35.232.131.181` (may still be running, no credit)
- Bucket: `gs://strategy-artifacts-robpitman/`

### New GCP Account (Nikola's — ACTIVE)
- Project: `project-c6c16a27-e123-459c-b7a`
- Console: `35.223.104.173` (e2-micro, us-central1-c)
- Bucket: `gs://strategy-artifacts-nikolapitman/`
- Credit: $435, expires July 2, 2026
- CPU quota: 100 on-demand + 100 preemptible (us-central1, us-west1, us-east1)

### Contabo Windows VPS
- **IP**: 89.117.72.49
- **Order**: 14812002
- **RDP**: Administrator + password set during checkout
- **Purpose**: Run MT5 24/7 with Portfolio #3 EA on The5ers
- **Capacity**: 8GB RAM = can run 4-6 MT5 instances (4 The5ers evals simultaneously)

### Local Dev
- Windows/PowerShell, VS Code, Desktop Commander
- MT5 installed (Five Percent Online branded), EA compiled

---

## KEY FILES

| File | Purpose |
|------|---------|
| `EA/Portfolio3_The5ers.mq5` | **NEW** — MQL5 EA for The5ers live trading |
| `modules/portfolio_selector.py` | 6-stage pipeline (UPGRADED with 13 new features) |
| `modules/prop_firm_simulator.py` | PropFirmConfig + simulate_challenge (now with daily DD) |

| `modules/filters.py` | All 25+ filters including S54 additions |
| `modules/cfd_mapping.py` | CFD instrument mapping |
| `Outputs/ultimate_leaderboard_bootcamp.csv` | 379 strategies ranked |
| `Outputs/portfolio_selector_report.csv` | Latest selector output (block bootstrap results) |
| `docs/PORTFOLIO_SELECTOR_BRIEF.md` | Technical brief shared with ChatGPT/Gemini |
| `SESSION_57_TASKS.md` | Sizing + scoring upgrade tasks (COMPLETED) |
| `SESSION_58_TASKS.md` | Correlation + MC upgrade tasks (COMPLETED) |
| `SESSION_57_58_PRE_REVIEW.md` | Safety rails for Claude Code |
| `CLAUDE.md` | Engine orientation |
| `CHANGELOG_DEV.md` | Session-by-session dev log |

---

## KNOWN BUGS / DEFERRED ITEMS

1. **VPS MT5 Netting vs Hedge** — waiting on The5ers support (email sent)
2. **3-layer correlation too strict** — thresholds need tuning for current strategy pool
3. **source_capital hardcoded at $250K** — breaks Pro Growth and smaller accounts
4. **Some S54 strategies missing strategy_returns.csv** — approx matching workaround applied
5. **Dashboard Live Monitor** — engine log and promoted candidates sections don't work
6. **SPOT resilience** — multi-region failover architecture designed but not implemented

---

## WORKFLOW PATTERN

- **Planning**: Claude.ai for architecture and analysis
- **Execution**: Claude Code (`claude --dangerously-skip-permissions`) reading SESSION_XX_TASKS.md
- **One commit per task step**
- **Handover**: SESSION_HANDOVER_XX.md for context transfer between chats
- **Multi-LLM**: Claude for architecture, ChatGPT+Gemini for cross-validation

---

## PROP FIRM PRIORITY RANKING

1. **The5ers** — primary, active $5K High Stakes account, EA built
2. **FTMO** — second CFD firm, static DD, Swing account for overnight holds
3. **Darwinex Zero** — long-game parallel play, €38/month
4. **FundedNext CFD** — third prop firm for diversification
