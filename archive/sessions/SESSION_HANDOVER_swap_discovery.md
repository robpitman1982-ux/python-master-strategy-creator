# Session Handover — Portfolio Selector V2 + Swap Cost Discovery
**Date:** 7 April 2026, ~12:00 AM AEST
**Repo:** robpitman1982-ux/python-master-strategy-creator
**Local:** C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator\

---

## COMPLETED THIS SESSION

### 1. Per-step time-to-fund estimates (DONE)
**Files changed:** `modules/prop_firm_simulator.py`, `modules/portfolio_selector.py`, `run_portfolio_all_programs.py`

- `simulate_challenge_batch()` now tracks trades used per step per sim via `step_passed_mask` and `step_trades_per_sim` arrays
- Populates `step{N}_median_trades` and `step{N}_p75_trades` (was empty `[]`)
- Report CSV includes `step1_est_months`, `step2_est_months`, `step3_est_months`, `total_est_months`
- Terminal output: `0mo -> 11mo -> 7mo = 18mo funded`
- Combined summary CSV includes per-step months

### 2. Composite score fix — 50/50 pass rate + speed (DONE)
**Old:** `pass_rate * (target_months / est_months) ^ 0.5` — speed dominated, 84% pass beat 100% pass
**New:** `0.5 * pass_rate + 0.5 * min(1.0, target_months / est_months)` — true equal weight

### 3. Max DD added to terminal summary (DONE)
Output now shows: `bootcamp_250k  success  3 strats  86.7% pass  DD 5.1%  0mo -> 11mo -> 7mo = 18mo funded`

### 4. Arrow character fix (DONE)
Replaced Unicode `→` with ASCII `->` — was crashing on Windows cp1252 encoding for multi-step programs.

### 5. Candidate cap raised to 100 (DONE)
`config.yaml`: `candidate_cap: 100` — was 60. Lets JY (3→8 candidates), EC (4→8), and other new markets through the hard filter.

### 6. Portfolio selector run completed with all fixes (DONE)
Full run with candidate_cap=100, 89 candidates, 115 combinations tested per program.

---

## CURRENT RESULTS (candidate_cap=100 run)

```
ALL PROGRAMS COMPLETE
  bootcamp_250k      success  3 strats  86.7% pass  DD 5.1%  0mo -> 11mo -> 7mo = 18mo funded
  high_stakes_100k   success  3 strats  100%  pass  DD 3.5%  0mo -> 12mo = 12mo funded
  hyper_growth_5k    success  4 strats  100%  pass  DD 3.3%  8mo funded
  pro_growth_5k      success  4 strats  100%  pass  DD 3.3%  8mo funded
```

**Top portfolio (Pro Growth #1):** CL 15m MR (50 micros) + ES daily Trend (1) + SI 15m MR (1) + W daily Breakout (1)
- 100% pass, 3.3% DD, 7.7mo funded, robustness 1.0

**Key finding: Still all k=3 and k=4.** No k=5 portfolios. No JY/EC/BP/AD in any top 10.
CL 15m MR appears in 36/40 portfolios. SI 15m MR in 34/40.

**Root cause:** New markets (JY, EC, BP, AD, NG, US, TY, W) only swept on daily+60m.
Daily/60m strategies have too few trades/year to compete with 15m strategies on speed.
Need 15m/30m sweeps for these markets.

---

## CRITICAL DISCOVERY: SWAP COSTS

### The5ers CFD Swap Rates (from MT5 specifications, 7 April 2026)

| Symbol | Market | Swap Type | Long | Short | Triple Day | $/micro/night (long) |
|--------|--------|-----------|------|-------|------------|---------------------|
| XTIUSD | CL | Points | -70 | -40 | Fri 10x | $0.70 |
| XAGUSD | SI | Points | -81 | -78.9 | Fri 3x | $4.05 |
| XAUUSD | GC | Points | -220 | -220 | Fri 3x | $2.20 |
| NAS100 | NQ | Points | -480 | -466 | Fri 3x | $0.048 |
| SP500 | ES | Points | -144 | -144 | Fri 3x | $0.014 |
| US30 | YM | Points | -720 | -720 | Fri 3x | $0.072 |
| BTCUSD | BTC | USD | -125 | -90 | Daily 1x | $1.25 |
| USDJPY | JY | Points | -41.4 | -40.3 | Fri 3x | $0.26 |
| EURUSD | EC | Points | -21 | -19.5 | Fri 3x | $0.21 |
| GBPUSD | BP | Points | -22.8 | -21.6 | Fri 3x | $0.23 |
| AUDUSD | AD | Points | -9.8 | -8.2 | Fri 3x | $0.10 |

### Swap cost per micro per night formula
- **Points type:** swap_points × contract_size × 10^(-digits) / 100
- **USD type:** swap_value / 100 (direct dollar amount per lot, divide by 100 for micro)

### Impact on current Portfolio #1 (50 micros CL, 1 micro each ES/SI/W)

| Strategy | Micros | Normal night | Friday (3x/10x) |
|----------|--------|-------------|-----------------|
| CL 15m MR | 50 | $35.00 | **$350.00** (10x) |
| SI 15m MR | 1 | $4.05 | $12.15 |
| ES daily Trend | 1 | $0.01 | $0.04 |
| W daily Bkout | 1 | N/A | N/A (not on The5ers) |
| **Total** | | **$39.06** | **$362.19** |

**Pro Growth target = $500 profit. One Friday hold = 72% of target wiped.**

### Swap-friendliness tiers

**LOW (safe for daily holds):** SP500, NAS100, US30, AUDUSD, EURUSD, GBPUSD, USDJPY
**MEDIUM (avoid weekends):** XAUUSD, BTCUSD
**HIGH (intraday only at scale):** XAGUSD, XTIUSD (10x Friday!)

### Additional discovery: Wheat (W) NOT on The5ers
W daily Breakout appears in most top portfolios but cannot actually be traded.
Must add "W" to `excluded_markets` in config.

### Markets NOT available on The5ers (confirmed from Market Watch)
- W (Wheat) — no symbol
- NG (Natural Gas) — no symbol
- US (US Bonds) — no symbol
- TY (Treasury Notes) — no symbol

### Available on The5ers (confirmed)
SP500, NAS100, US30, XAUUSD, XAGUSD, XTIUSD, BTCUSD,
USDJPY, EURUSD, GBPUSD, AUDUSD (+ other FX pairs)

---

## WHAT NEEDS TO CHANGE IN THE PORTFOLIO SELECTOR

### 1. Swap cost modeling in MC simulator (HIGH PRIORITY)
Add per-trade swap cost deduction in `simulate_challenge_batch()`:
- For each trade, estimate nights held from hold_bars and timeframe
- Deduct: `swap_per_micro × n_micros × n_nights × (10 if crosses_friday else 1)`
- Config: swap rates per symbol in `config.yaml` or dedicated `swap_rates.yaml`
- This changes pass rates AND time-to-fund estimates — everything downstream shifts

### 2. Update excluded_markets (QUICK FIX)
```yaml
excluded_markets: ["BTC", "RTY", "HG", "W", "NG", "US", "TY"]
```
W, NG, US, TY are not tradeable on The5ers. BTC excluded for sizing reasons.
RTY and HG already excluded.

### 3. Sizing optimizer must respect swap constraints
The sizing optimizer gave CL 50 micros — the worst possible outcome for swap costs.
Options:
- Hard cap max_micros_per_strategy in config (e.g., max 10 micros CL)
- Integrate swap cost into the sizing objective function
- Add swap-adjusted pass rate as the optimization target instead of raw pass rate

### 4. 15m/30m sweeps for new markets (HIGH PRIORITY — unlocks diversification)
Currently swept: daily + 60m only for JY, EC, BP, AD
Need: 15m + 30m sweeps for:
- **USDJPY (JY)** — $0.26/micro swap, excellent for overnight holds
- **EURUSD (EC)** — $0.21/micro swap
- **GBPUSD (BP)** — $0.23/micro swap
- **AUDUSD (AD)** — $0.10/micro swap (lowest swap of all)

These FX 15m strategies would be:
- Uncorrelated with CL/SI (breaks the duopoly)
- Swap-friendly (can hold overnight cheaply)
- High trade count (15m = more trades/year = faster funding)
- Genuine k=5 portfolio enablers

Data files already exist locally: JY_15m, JY_30m, EC_15m, etc.
8 markets × 2 timeframes = 16 sweep configs for Nikola's GCP.

### 5. Composite score weighting per program type
For multi-step programs (Bootcamp 3-step), pass rate should be weighted higher than speed.
Failing at step 3 after 18 months is catastrophic. Consider:
- 1-step programs: 50/50 pass/speed (current)
- 2-step programs: 60/40 pass/speed
- 3-step programs: 70/30 pass/speed

---

## NEXT SESSION PRIORITIES (ordered)

1. **Update excluded_markets** — Add W, NG, US, TY (quick config fix, re-run selector)
2. **Implement swap cost modeling** — Per-trade deduction in `simulate_challenge_batch()`
   - Swap rates table in config
   - Estimate nights held per trade from timeframe + hold_bars
   - Apply to sizing optimizer objective
3. **15m/30m cloud sweeps** — JY, EC, BP, AD on Nikola's GCP (16 configs)
4. **Sizing cap** — Max micros per strategy to prevent CL 50-micro catastrophe
5. **Program-specific composite weights** — Higher pass rate weight for multi-step
6. **Re-run portfolio selector** — With swap costs, excluded markets, new strategies
7. **Push all changes to GitHub** — Nothing committed this session

---

## FILES CHANGED THIS SESSION (not committed)

| File | Changes |
|------|---------|
| `modules/prop_firm_simulator.py` | Per-step trade tracking in `simulate_challenge_batch()` |
| `modules/portfolio_selector.py` | Per-step est_months in report, 50/50 composite score, arrow fix |
| `run_portfolio_all_programs.py` | Max DD in summary, per-step months display, arrow fix |
| `config.yaml` | `candidate_cap: 100` |

---

## SWAP RATES REFERENCE (for implementation)

```yaml
# The5ers CFD swap rates (from MT5 specs, 7 April 2026)
# Rates change periodically — verify on platform before major decisions
swap_rates:
  XTIUSD:  # CL — DANGER: 10x Friday
    swap_long_per_micro: -0.70
    swap_short_per_micro: -0.40
    triple_day: friday
    triple_multiplier: 10
  XAGUSD:  # SI
    swap_long_per_micro: -4.05
    swap_short_per_micro: -3.95
    triple_day: friday
    triple_multiplier: 3
  XAUUSD:  # GC
    swap_long_per_micro: -2.20
    swap_short_per_micro: -2.20
    triple_day: friday
    triple_multiplier: 3
  NAS100:  # NQ
    swap_long_per_micro: -0.048
    swap_short_per_micro: -0.047
    triple_day: friday
    triple_multiplier: 3
  SP500:  # ES
    swap_long_per_micro: -0.014
    swap_short_per_micro: -0.014
    triple_day: friday
    triple_multiplier: 3
  US30:  # YM
    swap_long_per_micro: -0.072
    swap_short_per_micro: -0.072
    triple_day: friday
    triple_multiplier: 3
  BTCUSD:  # BTC
    swap_long_per_micro: -1.25
    swap_short_per_micro: -0.90
    triple_day: none  # charged daily, every day = 1x
    triple_multiplier: 1
  USDJPY:  # JY
    swap_long_per_micro: -0.26
    swap_short_per_micro: -0.25
    triple_day: friday
    triple_multiplier: 3
  EURUSD:  # EC
    swap_long_per_micro: -0.21
    swap_short_per_micro: -0.20
    triple_day: friday
    triple_multiplier: 3
  GBPUSD:  # BP
    swap_long_per_micro: -0.23
    swap_short_per_micro: -0.22
    triple_day: friday
    triple_multiplier: 3
  AUDUSD:  # AD
    swap_long_per_micro: -0.10
    swap_short_per_micro: -0.08
    triple_day: friday
    triple_multiplier: 3
```
