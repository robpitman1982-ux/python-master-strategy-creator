# SESSION HANDOVER — For Next Claude Chat in This Project

## Date: 2026-04-01
## From: Sessions 47-53 (portfolio selector build, prop firm configs, all 8 markets)
## To: Session 54+ (selector fixes, filter review, SPOT runner)

---

## WHAT THIS PROJECT IS

Rob is building an automated strategy discovery engine (`python-master-strategy-creator`) that sweeps filter combinations across 8 futures markets (ES, CL, NQ, SI, HG, RTY, YM, GC), runs strategies through a quality pipeline, and selects optimal portfolios for The5ers prop firm challenges. The engine runs on GCP n2-highcpu-96 VMs.

**Repo**: `C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator\`
**GitHub**: `robpitman1982-ux/python-master-strategy-creator`

---

## CURRENT STATE — WHAT'S WORKING

### All 8 Markets Complete — 315 Strategies
Every market has been swept across 4 timeframes (daily, 60m, 30m, 15m):
- NQ: 56, GC: 53, RTY: 39, CL: 38, SI: 37, ES: 36, YM: 30, HG: 26
- Results in `Outputs/runs/` (8 run directories)
- Master leaderboard: `Outputs/ultimate_leaderboard_bootcamp.csv`

### Portfolio Selector (pipeline working)
6-stage pipeline in `modules/portfolio_selector.py`:
1. Hard filter → 2. Return matrix → 3. Correlation → 4. Combinatorial sweep → 5. Portfolio MC → 6. Sizing optimizer

### Prop Firm Configs (Session 52)
`modules/prop_firm_simulator.py` has factories for:
- `The5ersBootcampConfig()` — 3 steps, 5% DD, 6% target
- `The5ersHighStakesConfig()` — 2 steps, 10% DD, 8%+5% targets
- `The5ersHyperGrowthConfig()` — 1 step, 6% DD, 10% target
- `The5ersProGrowthConfig()` — 1 step, 6% DD, 10% target
- Configurable via `config.yaml` → `pipeline.portfolio_selector.prop_firm_program`

### Returns Data Generated
`generate_returns.py` has produced `strategy_returns.csv` and `strategy_trades.csv` for all 32 market/timeframe groups (315 strategies total).

---

## BOOTCAMP RESULTS (working correctly)

Top 3 portfolios (Bootcamp $250K, 3 steps, 5% DD):
1. NQ daily MR + SI daily BO + NQ 60m MR + NQ 15m MR — **46.5% pass, 13.4 months, DD 8.8%**
2. NQ daily MR + YM daily Trend + NQ 60m MR + NQ 15m MR — **39.8% pass, 5.8 months, DD 8.9%**
3. SI daily BO + NQ 60m MR + NQ 15m MR + YM daily MR — **41.4% pass, 14.5 months, DD 9.1%**

All 10 portfolios rated VIABLE. Mixed micro sizing working (NQ 60m = 7 micros, NQ daily = 1 micro).

---

## HIGH STAKES RESULTS — HAS BUGS, NEEDS FIXING

Top 3 portfolios (High Stakes $100K, 2 steps, 10% DD):
1. NQ daily MR + SI daily BO + NQ 60m MR + NQ 15m MR — **44.6% pass, 4.7 months, DD 14.4%**
2. NQ daily MR + YM daily Trend + NQ 60m MR + NQ 15m MR — **42.8% pass, 2.3 months, DD 14.2%**
3. YM Trend + NQ 60m MR + NQ 15m MR + YM MR — **42.9% pass, 2.7 months, DD 14.6%**

All 10 rated MARGINAL because DD exceeds 10% limit. Pass rates are good (42-44%), time-to-fund is great (2-5 months), but the sizing optimizer is oversizing.

### Bug 1: Sizing optimizer oversizes for High Stakes
The optimizer cranks all micros to max (7-10) to hit the 8% profit target fast, pushing DD to 12-14%. This exceeds the 10% DD limit. The optimizer's DD constraint isn't binding tightly enough.

**Root cause**: The optimizer minimizes trades-to-pass subject to `pass_rate >= 40%`. It does NOT have a hard constraint on DD. The DD column in the report is the P95 worst-case DD, which exceeds 10% for High Stakes because the micros are too high.

**Fix needed**: Add DD constraint to the optimizer:
```python
# In optimise_sizing(), add:
if dd > config.max_drawdown_pct:
    continue  # Skip this weight combo, exceeds DD limit
```
This will force the optimizer to only consider weight combos where P95 DD stays under 10%.

### Bug 2: step3_pass_rate hardcoding (PARTIALLY FIXED)
The report and console output used `step3_pass_rate` which is always 0 for 2-step programs. This was partially fixed in this session by adding `final_pass_rate` field. However, there may be more places in the code that reference step3 specifically. Do a thorough search for `step3` across the codebase.

The fix already applied:
- `portfolio_monte_carlo()` now returns `final_pass_rate` = last step's rate
- Report writer uses `final_pass_rate` for display
- Console output uses `final_rate` 
- Sizing optimizer already correctly uses `f"step{config.n_steps}_pass_rate"`

### Bug 3: source_capital scaling
Backtests were run with implied $250K capital (TradeStation full contracts). When simulating High Stakes ($100K) or Pro Growth ($5K/$20K), the `_scale_trade_pnl()` function divides by source_capital ($250K) then multiplies by step_balance. This is mathematically correct but means:
- High Stakes $100K: trades are 0.4x original → need more micros to hit targets → pushes DD
- Pro Growth $5K: trades are 0.02x original → virtually impossible to hit targets with current micro grid

**The source_capital is currently hardcoded at $250K in portfolio_monte_carlo()**. This needs to be dynamic based on the backtest data, or the micro grid needs to be wider for smaller accounts.

---

## CRITICAL FILES

| File | Purpose |
|------|---------|
| `modules/portfolio_selector.py` | Main 6-stage pipeline (~1167 lines) |
| `modules/prop_firm_simulator.py` | PropFirmConfig, simulate_challenge, factory functions |
| `generate_returns.py` | Rebuilds trades → strategy_returns.csv + strategy_trades.csv |
| `config.yaml` | All config including portfolio_selector params |
| `Outputs/ultimate_leaderboard_bootcamp.csv` | 315 strategies, master source |
| `Outputs/portfolio_selector_report.csv` | Latest selector output |
| `CLAUDE.md` | Engine orientation for Claude Code |
| `CHANGELOG_DEV.md` | Session-by-session dev log |

---

## PENDING TASKS (PRIORITY ORDER)

### IMMEDIATE — Selector fixes (before Session 54 filter work)

1. **Fix sizing optimizer DD constraint** — Add hard DD limit so optimizer never picks weights that exceed `config.max_drawdown_pct`. Currently it minimizes trades-to-pass without bounding DD.

2. **Fix source_capital for different account sizes** — The source capital ($250K) is from the Bootcamp backtest. For High Stakes ($100K) and Pro Growth ($5K-$20K), the scaling math is correct but the micro grid [0.1-1.0] doesn't go small enough for tiny accounts. Either:
   - Make source_capital configurable per program, OR
   - Widen micro grid for smaller accounts (e.g., [0.01, 0.02, 0.05, 0.1] for $5K)

3. **Verify daily DD simulation** — Session 52 added daily DD checks in `simulate_single_step()`. The MC approximates "days" using `trades_per_year / 252`. Verify this doesn't over-reject by running a comparison with and without daily DD.

4. **Re-run High Stakes** after fixes to get proper results with DD under 10%.

5. **Run Pro Growth ($20K, $270 fee)** — need to verify scaling works for smaller accounts. Config: `prop_firm_program: "pro_growth"`, `prop_firm_target: 20000`.

### Session 53 — Parallelise generate_returns.py (may already be done)
Check if Claude Code completed Session 53. If so, future generate_returns.py runs will be 4-5x faster locally.

### Session 54 — Filter & Parameter Review
Task file: `SESSION_54_TASKS.md`
Review all filters and parameters with multi-LLM input. Goal: discover new strategy patterns.

### Session 55 — Bulletproof SPOT Runner
Task file: `SESSION_55_TASKS.md`
Build `run_spot_resilient.py` for cheap multi-region auto-retry sweeps.

---

## CONFIG STATE

Current `config.yaml` portfolio_selector section:
```yaml
pipeline:
  portfolio_selector:
    prop_firm_program: "high_stakes"  # ← Currently set to high_stakes
    prop_firm_target: 100000
    min_pass_rate: 0.40
    candidate_cap: 50
    oos_pf_threshold: 1.0
    bootcamp_score_min: 40
    n_sims_mc: 10000
    n_sims_sizing: 1000
```

To switch programs, change `prop_firm_program` and `prop_firm_target`:
- Bootcamp: `"bootcamp"`, `250000`
- High Stakes: `"high_stakes"`, `100000`
- Pro Growth: `"pro_growth"`, `20000`
- Hyper Growth: `"hyper_growth"`, `5000`

---

## CLOUD INFRASTRUCTURE

- **Compute**: GCP n2-highcpu-96 SPOT VMs (100 vCPU quota, 200 denied twice)
- **Default zone**: `us-central1-f` (all 18 cloud configs updated)
- **Strategy console**: e2-micro in `us-central1-c` (IP: 35.232.131.181)
- **Dashboard**: `http://35.232.131.181:8501` (Live Monitor sections broken)
- **GCS bucket**: `strategy-artifacts-robpitman`
- **SSH**: Use `robpitman1982` user. Desktop Commander SSH unreliable — use terminal.

## The5ers Programs (from Rob's screenshots)

| Program | Steps | DD | Daily DD | Target | Fee | Split |
|---------|-------|----|----------|--------|-----|-------|
| Bootcamp $250K | 3 | 5% | None | 6%×3 | $225 | 50%→100% |
| Bootcamp $20K | 3 | 5% | None | 6%×3 | $22 | 50%→100% |
| High Stakes $100K | 2 | 10% | 5% | 8%+5% | $545 | 80%→100% |
| Pro Growth $20K | 1 | 6% | 3% | 10% | $270 | up to 100% |
| Pro Growth $5K | 1 | 6% | 3% | 10% | $74 | up to 100% |
| Hyper Growth $5K | 1 | 6% | 3% | 10% | $260 | up to 100% |

All scale to $4M. Fees refunded on first payout. Minimum 3 profitable days for High Stakes.
Pro Growth and Hyper Growth have identical rules — only fee differs.

## WORKFLOW PATTERN

- **Planning**: Claude.ai (this chat) for architecture and session design
- **Execution**: Claude Code (`claude --dangerously-skip-permissions`) for unattended work
- **Session files**: `SESSION_XX_TASKS.md` committed to repo, read by Claude Code
- **Handover**: `SESSION_HANDOVER_XX.md` for context transfer between chats
- **Orientation**: Claude Code reads `CLAUDE.md` and `CHANGELOG_DEV.md` before executing

## KEY PRINCIPLES

- No patches — full fixes only
- One commit per task step
- Upfront review before Claude Code sessions prevents costly mistakes
- Decisions grounded in actual data — Rob catches analytical errors quickly
- `ultimate_leaderboard_bootcamp.csv` is the authoritative source for portfolio construction
- Rob trades MICRO contracts on The5ers. Weight 0.1 = 1 micro (1/10th full contract)
