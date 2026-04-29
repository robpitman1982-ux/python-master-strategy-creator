# The5ers Program Rules — Canonical Source of Truth

**Verified:** 2026-04-30 (from operator-supplied screenshots of The5ers website)
**Maintained by:** Claude Code on Latitude
**Refresh policy:** verify on every major version change of the website; re-screenshot when visiting account dashboard

This file is the canonical reference for what's encoded in
`modules/prop_firm_simulator.py`. When the simulator behaviour disagrees with
this file, treat the website as truth and patch the simulator.

---

## Bootcamp

Three tracks: $20K, $100K, $250K.

### Step balances by track (NOTE: differs by track)

| Track | Step 1 | Step 2 | Step 3 | Funded | Pattern |
|-------|--------|--------|--------|--------|---------|
| $20K | $5,000 | $10,000 | $15,000 | $20,000 | 25 / 50 / 75 / 100 |
| $100K | $25,000 | $50,000 | $75,000 | $100,000 | 25 / 50 / 75 / 100 |
| $250K | $100,000 | $150,000 | $200,000 | $250,000 | **40 / 60 / 80 / 100** |

### Per-step rules

| Setting | Step 1 | Step 2 | Step 3 | Funded |
|---------|--------|--------|--------|--------|
| Profit target | 6% | 6% | 6% | 5% |
| Max loss | 5% | 5% | 5% | 4% |
| Daily pause | none | none | none | **3%** (only on funded) |
| Leverage | 1:30 | 1:30 | 1:30 | 1:30 |
| Time limit | unlimited | unlimited | unlimited | unlimited |
| Profit share | — | — | — | up to 100% |

### Costs

| Track | Step 1 entry | Step 1 reward | Funded fee |
|-------|--------------|---------------|------------|
| $20K | $22 | $2 Hub Credit | $50 |
| $100K | $95 | $5 Hub Credit | $205 |
| $250K | $225 | $10 Hub Credit | $350 |

### Other rules

- Inactivity > 30 consecutive days expires account.
- Holding open trades overnight and over weekends allowed; indices weekend holds carry high swap.
- News trading allowed.
- Mandatory stop loss: yes.
- Account combination cap: 1×$250K + 1×$100K + 2×$20K = 4 max, **each must use a different trading method**.
- First payout 14 days after funded, every 2 weeks; cycle resets on scaling.

---

## High Stakes — Classic

Six tracks: $2.5K, $5K, $10K, $25K, $50K, $100K.

There is also a "New" version (toggle on website); rules below are for **Classic**.

### Step balances (same balance both eval steps)

| Track | Step 1 / Step 2 / Funded balance |
|-------|----------------------------------|
| All | Same as track size (e.g., $100K → $100K / $100K / $100K) |

### Per-step rules

| Setting | Step 1 | Step 2 | Funded |
|---------|--------|--------|--------|
| Profit target | 8% | 5% | 10% (for scaling) |
| Max loss | 10% | 10% | 10% |
| Max daily loss | **5%** | **5%** | 5% |
| Min profitable days | 3 | 3 | 3 (for scaling) |
| Max trading period | unlimited | unlimited | unlimited |

### Costs

| Track | Step 1 cost | Step 1 reward | Step 2 | Funded |
|-------|-------------|---------------|--------|--------|
| $2.5K | $22 | $2 reward | refund | refund + 80-100% split |
| $5K | $39 | $5 reward | refund | refund + 80-100% split |
| $10K | $78 | $10 reward | refund | refund + 80-100% split |
| $25K | $195 | $15 reward | refund | refund + 80-100% split |
| $50K | $309 | $25 reward | refund | refund + 80-100% split |
| $100K | $545 | $40 reward | refund | refund + 80-100% split |

### Daily DD recalculation (CRITICAL)

> "Daily loss is 5% of the **starting equity of the day** OR the **starting balance of the day** (the highest between them) at MT5 Server Time."

Both terms are day-level. Our simulator uses `daily_dd_recalculates=True` and at each day boundary recomputes:

```
daily_dd_limit = day_start_balance × 0.05
```

In our model we don't simulate overnight open positions, so equity = balance at every day boundary — `max(balance, equity) = balance`.

### News trading restriction (NOT modeled)

> "Holding open trades over news is allowed. Executing orders 2 minutes before until 2 minutes after high-impact news is not allowed."

The simulator does NOT model news exclusion windows. Strategies that fire entries within ±2 minutes of high-impact news will look fine in MC but get rejected on the live account. **MC pass rates for high-frequency strategies should be treated as upper bounds for High Stakes.**

### Other rules

- Leverage 1:100 (much higher than other programs).
- Inactivity > 30 consecutive days from registration day expires account.
- Holding overnight and weekend allowed; indices weekend = high swap.
- Profitable day definition: closed-position profit ≥ 0.5% of initial balance, where "profit" = `Min(midnight_balance, midnight_equity) - previous_day_balance`.
- Step 1 completion: HUB credits option (operator perk).
- Step 2 completion: withdrawable refund of entry fee (excluding discounts).
- Funded payouts: anytime, regardless of 10% scaling target.
- First payout 14 days after funded, every 2 weeks; cycle resets on scaling.
- Account combination caps:
  - **Classic:** 1×$2.5K + 1×$5K + 1×($10K or $25K) + 1×($50K or $100K), plus 3 Bootcamp + 4 Instant Funding accounts.
  - **New:** 3×$2.5K + 3×$5K + 3×$10K + 1×$25K + 1×($50K or $100K), plus 3 Bootcamp + 4 Instant Funding.
- Scaling up to $500,000.

---

## Pro Growth

Three tracks: $5K, $10K, $20K. (Hyper Growth is a sibling program with same rules but higher fees.)

### Per-step rules (1 step + Funded)

| Setting | Step 1 | Funded |
|---------|--------|--------|
| Evaluation target | 10% | 10% |
| Stop-out level | 6% | 6% |
| Daily loss | **3% (PAUSE, not terminate)** | 3% (pause) |
| Min profitable days | 3 | — |
| Leverage | 1:30 | 1:30 |
| Time limit | unlimited | unlimited |
| Profit split | — | up to 100% |

### Costs

| Track | Cost | Funded |
|-------|------|--------|
| $5K | $74 | refund (bonus from $15) |
| $10K | $140 | refund (bonus from $25) |
| $20K | $270 | refund (bonus from $50) |

### Daily DD pause behaviour

> "The daily pause does not terminate an account. It only disables the account for the current day. Traders can continue trading the very next day at 00:00 MT5 Server Time."

Our simulator uses `daily_dd_is_pause=True`. When daily DD is breached, remaining trades for that day are skipped; trading resumes next day with a fresh daily limit. **Step does NOT terminate on daily DD breach.**

### Other rules

- Mandatory stop loss: not required (`mandatory_stop_loss=False`).
- Inactivity > 30 days expires account.
- News trading allowed.
- Weekend holds allowed; indices weekend = high swap.
- Assets: FX, Metals, Indices, Crypto.
- Platform: MT5 Hedge.
- Funded: same target/max loss/daily pause as Step 1.
- No min trades or min days for completing Step 1 — only the 3 profitable days requirement.
- **Max combined eval capital per trader: $40,000.** (E.g., 1×$20K + 1×$10K + 2×$5K, or 2×$20K.)
- Scaling up to $4M.
- First payout 14 days after funded, every 2 weeks; cycle resets on scaling.

---

## Things NOT modeled in the simulator (review before live deployment)

| Rule | Affects | Risk in our MC |
|------|---------|----------------|
| News trading 2-min exclusion | High Stakes only | MC overstates pass rate for high-frequency strategies |
| Account combination caps | Portfolio construction | Doesn't affect strategy selection; affects how operator sizes the funded portfolio |
| Trading-method-distinct rule (Bootcamp) | Operator can't run same strategy on multiple Bootcamp accounts | Operator-level constraint; not in selector |
| Funded scaling progression | Long-term P&L projections | Selector currently treats funded as single-state |
| Mandatory stop loss enforcement (Bootcamp + High Stakes) | Strategies without protective stops | Engine has stop_distance_atr in all strategies — likely OK but worth verifying |
| HUB credits / bonus rewards | Operator-side P&L | Not relevant to strategy selection |
| Profitable day exact definition (Min(balance, equity) - prev balance) | High Stakes specifically | We use closed-trade PnL ≥ 0.5% — equivalent in our no-open-positions model |

---

## Verification cadence

- **On any The5ers website redesign or program update:** re-screenshot all three pages and re-verify against this file.
- **On every major handover:** check this file's `Verified` date — if older than 60 days, prompt operator for fresh screenshots.
- **On any code change to `modules/prop_firm_simulator.py` factories:** the change must be verifiable against this file or this file must be updated first.

---

## Operator notes

- Currently funded on: $5K High Stakes (account 26213568, FivePercentOnline-Real)
- Current live trading: Portfolio #3 EA on Contabo VPS — challenging High Stakes
- Programs of interest for portfolio construction (per operator's stated focus):
  1. Bootcamp $250K — highest payout potential, no daily DD on eval
  2. High Stakes $100K — fastest path with strict daily DD
  3. Pro Growth $5K — cheapest entry, smallest capital
