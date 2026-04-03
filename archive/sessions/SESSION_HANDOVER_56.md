# SESSION HANDOVER — For Next Claude Chat
## Date: 2026-04-02
## From: Session 55/56 (S54 sweep analysis, portfolio selection, prop firm research, GCP migration)
## To: Session 57+ (EA build for Portfolio #3 on The5ers $5K High Stakes)

---

## WHAT THIS PROJECT IS

Rob is building an automated strategy discovery engine (`python-master-strategy-creator`) that sweeps filter combinations across futures markets, runs strategies through a quality pipeline, and selects optimal portfolios for prop firm challenges. The engine runs on GCP n2-highcpu-96 VMs.

**Repo**: `C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator\`
**GitHub**: `robpitman1982-ux/python-master-strategy-creator`

---

## CRITICAL CONTEXT: THE5ERS IS CFD, NOT FUTURES

The5ers main programs trade **CFDs on MT5**, not futures. Backtested edge transfers directly — CFDs track the same underlying instruments. Only position sizing (lots vs contracts) differs.

### Rob's Live The5ers Account
- **Program**: $5K High Stakes (2-step, 10% DD, 5% daily DD, 8%+5% targets)
- **Account**: 26213568 on FivePercentOnline-Real (MT5)
- **Status**: Active, Evaluation phase, 0 trades
- **Platform**: MetaTrader 5 (installed, connected, live data flowing)

### CFD Symbol Mapping (verified from MT5)
| Futures | CFD Symbol | Contract Size | $/Point/Lot |
|---------|-----------|--------------|-------------|
| ES | SP500 | 1 | $1/pt |
| NQ | NAS100 | 1 | $1/pt |
| YM | US30 | 1 | $1/pt |
| GC | XAUUSD | 100 | $100/pt |

**File**: `modules/cfd_mapping.py` — verified mapping with conversion functions.


---

## WHAT WAS ACCOMPLISHED THIS SESSION

### 1. S54 Sweep Analysis — All 6 CFD Markets Complete
Re-swept ES, NQ, GC, SI, CL, YM with Session 54's new filters (daily + 60m).
- **379 total strategies** in ultimate leaderboard
- **314 CFD-eligible** across 6 markets
- **99 ROBUST+STABLE** quality strategies
- **67 new strategies** added by S54 re-sweeps
- Key DD improvements: NQ daily MR (-43%), CL daily MR (-60%), SI daily MR (-53%)

### 2. Portfolio Selection — High Stakes $5K
**Portfolio #3 chosen for $5K test (RECOMMENDED):**
- NQ daily MR `RefinedMR_HB5_ATR0.4_DIST0.4_MOM0` — 1 micro
- YM daily Trend `RefinedTrend_HB1_ATR0.75_VOL0.0_MOM0` — 1 micro  
- GC daily MR `RefinedMR_HB5_ATR0.4_DIST0.4_MOM0` — 1 micro
- NQ 15m MR `RefinedMR_HB16_ATR0.4_DIST1.0_MOM0` — 1 micro
- **99.6% pass rate, 6.9% P95 DD, est 13.4 months to fund**
- CFD symbols needed: NAS100, US30, XAUUSD

### 3. Portfolio Selection — High Stakes $100K
Ran but sizing optimizer kept micros at 1-3 even on $100K account.
**Known bug**: DD constraint in sizing optimizer is too conservative for larger accounts.
Needs fixing before $100K account is worth pursuing — `source_capital` scaling issue.

### 4. Portfolio Selection — Bootcamp $250K
Was still running at end of session. Check `Outputs/portfolio_selector_report.csv` for results.

### 5. Prop Firm Research
**Ranking for Rob's algo strategies:**
1. **The5ers** — primary, active $5K High Stakes account
2. **FTMO** — second CFD firm, static DD, Swing account for overnight holds
3. **Darwinex Zero** — long-game parallel play, €38/month, build DARWIN track record
4. **FundedNext CFD** — third prop firm for diversification
- Skip: Topstep, Apex, FundedNext Futures — none allow overnight holds


### 6. New GCP Account Setup (Wife's Account)
- **Project ID**: `project-c6c16a27-e123-459c-b7a`
- **GCS Bucket**: `gs://strategy-artifacts-nikolapitman/`
- **Strategy Console VM**: `35.223.104.173` (e2-micro, us-central1-c)
- **Credit**: $435.26, expires July 2, 2026
- **CPU Quota**: Was 12 regional default, increase to 100 requested (pending)
- **Firewall**: Port 8501 open for Streamlit
- `robpitman1982` user created, Python3/pip/git installed

### 7. Session 56 Claude Code Tasks — Running
Session 56 task file (`SESSION_56_TASKS.md`) was written and Claude Code is executing it.
Tasks: migrate bucket/IP defaults in launcher code, set up GitHub access on new console,
install Streamlit dashboard, update CLAUDE.md, dry-run launcher test.

### 8. Portfolio Selector Fix — Returns File Fallback
Two fixes applied to `modules/portfolio_selector.py`:
- `_find_returns_file()`: Added fallback to scan ALL runs when primary run doesn't have `strategy_returns.csv`
- `_match_column()`: Added approx matching by strategy_type prefix when exact refined name doesn't match
These fixes allow S54 strategies to participate in portfolio selection using returns data from older runs.

---

## IMMEDIATE PRIORITY: SESSION 57 — MT5 EA BUILD

### What Needs Building
An MQL5 Expert Advisor that implements Portfolio #3 on The5ers MT5:

**Strategies to implement:**

| Strategy | Market | CFD Symbol | Timeframe | Hold Bars | Stop ATR | Type |
|----------|--------|-----------|-----------|-----------|----------|------|
| NQ daily MR | NQ | NAS100 | Daily | 5 | 0.4 | Mean Reversion |
| YM daily Trend | YM | US30 | Daily | 1 | 0.75 | Trend |
| GC daily MR | GC | XAUUSD | Daily | 5 | 0.4 | Mean Reversion |
| NQ 15m MR | NQ | NAS100 | 15min | 16 | 0.4 | Mean Reversion |

**Each strategy needs:**
- Entry filters (from `best_combo_filter_class_names` in leaderboard)
- Position sizing: 1 micro lot each (0.01 lots on The5ers CFDs)
- Stop loss: ATR-based, placed with entry order (The5ers requires visible SL)
- Exit: time-stop (hold_bars), then close
- No overnight restriction on The5ers — holds are fine


### Entry Filter Details (from leaderboard)
Look up each strategy in `Outputs/ultimate_leaderboard_bootcamp.csv` for:
- `best_combo_filter_class_names` — the filter combination that produced the winning strategy
- `leader_strategy_name` — the refined parameter set
- `leader_hold_bars`, `leader_stop_distance_atr` — exit parameters

The filter implementations are in `modules/filters.py`. Each filter checks conditions on
price bars (SMA relationships, close position, bar patterns, etc.) and returns True/False
for whether to take the trade.

### EA Architecture
- Single EA managing all 4 strategies
- Each strategy runs independently on its symbol/timeframe
- On each new bar, check all filters for that strategy's timeframe
- If all filters pass, enter trade with SL
- Track open positions per strategy (max 1 per strategy at a time)
- Close position after hold_bars bars elapse (time stop)
- The5ers rules: visible SL required, no HFT, no latency arb

### Deployment Path
1. Build EA in MQL5 (Session 57)
2. Test in MT5 Strategy Tester with historical data
3. Run live on local MT5 for a few days while monitoring
4. Deploy to Windows VPS for 24/5 unattended operation
5. Monitor via The5ers dashboard + MT5 mobile app

---

## KEY FILES

| File | Purpose |
|------|---------|
| `modules/filters.py` | All 25+ filters including S54 additions |
| `modules/engine.py` | Backtest engine with entry/exit logic |
| `modules/portfolio_selector.py` | 6-stage pipeline (MODIFIED this session) |
| `modules/cfd_mapping.py` | CFD instrument mapping |
| `modules/prop_firm_simulator.py` | PropFirmConfig for all programs |
| `Outputs/ultimate_leaderboard_bootcamp.csv` | 379 strategies ranked |
| `Outputs/portfolio_selector_report.csv` | Portfolio selection results |
| `SESSION_56_TASKS.md` | GCP migration tasks (running) |
| `CLAUDE.md` | Engine orientation |
| `CHANGELOG_DEV.md` | Session-by-session dev log |


---

## INFRASTRUCTURE

### Old GCP Account (Rob's — EXHAUSTED)
- Project: `project-813d2513-0ba3-4c51-8a1`
- Console: `35.232.131.181` (may still be running, no credit)
- Bucket: `gs://strategy-artifacts-robpitman/`

### New GCP Account (Nikola's — ACTIVE)
- Project: `project-c6c16a27-e123-459c-b7a`
- Console: `35.223.104.173` (e2-micro, us-central1-c)
- Bucket: `gs://strategy-artifacts-nikolapitman/`
- Credit: $435, expires July 2, 2026
- CPU quota: 100 requested (pending), currently 12

### Local Dev
- Windows/PowerShell, VS Code, Desktop Commander
- Repo: `C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator\`
- MT5: installed, connected to The5ers account 26213568

---

## KNOWN BUGS / DEFERRED ITEMS

1. **Sizing optimizer too conservative for large accounts** — keeps micros at 1-3 even on $100K. `source_capital` scaling issue. Needs fix before $100K/$250K accounts.
2. **S54 strategies missing `strategy_returns.csv`** — approx matching workaround applied but proper fix needs re-running engine locally for those specific strategies.
3. **Dashboard Live Monitor** — engine log and promoted candidates sections don't work.
4. **SPOT resilience** — Sonnet designed multi-region failover architecture (saved as separate doc). Deferred to after EA is live.
5. **Bootcamp portfolio** — may still be running. Check results in `Outputs/portfolio_selector_report.csv`.

---

## SESSION ROADMAP

- **Session 56** — Migrate to wife's GCP account (RUNNING via Claude Code)
- **Session 57** — MT5 EA build for Portfolio #3 ($5K High Stakes)
- **Session 58** — Generate proper `strategy_returns.csv` for S54 strategies
- **Session 59** — SPOT resilience implementation (Sonnet's architecture)
- **Session 60** — Fix sizing optimizer for $100K/$250K accounts

## WORKFLOW PATTERN
- **Planning**: Claude.ai for architecture and analysis
- **Execution**: Claude Code (`claude --dangerously-skip-permissions`) reading SESSION_XX_TASKS.md
- **One commit per task step**
- **Handover**: SESSION_HANDOVER_XX.md for context transfer
