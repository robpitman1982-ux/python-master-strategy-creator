# SPRINT_88 - Account-aware sizing constraints

**Sprint number:** 88
**Date opened:** 2026-05-03
**Date closed:** ___
**Operator:** Rob
**Author:** Claude Code on Latitude
**Branch:** `feat/account-aware-sizing` (TBD)
**Depends on:** Sprint 84 (trade artifacts), Sprint 85A (CFD config plumbing), Sprint 87 (cost overlay wiring)

---

## 1. Sprint goal

Make the portfolio selector's Monte Carlo and sizing optimizer aware of the **actual account balance** and **per-symbol min_lot** + **per-program leverage cap**, so portfolios it recommends are deployable as-is on every account size from $5K (Hyper/Pro Growth) up to $250K (Bootcamp).

Today the selector simulates against a hardcoded $250K notional and produces `micro_multiplier` ratios that translate proportionally to smaller accounts. This is correct in ratio but doesn't catch portfolios that **literally cannot deploy** at $5K because the smallest weight falls below `min_lot = 0.01` for that symbol on The5ers MT5.

## 2. Mechanism plausibility

Strong prior. Empirical evidence:
- The5ers MT5 enforces `min_lot = 0.01` per symbol (per `configs/the5ers_mt5_specs.yaml`)
- A portfolio with 7 strategies at average weight 0.15 on a $5K Pro Growth account translates to ~0.003 CFD lots per strategy on indices — below min_lot, can't trade
- `modules/cfd_mapping.futures_pnl_to_cfd_lots()` already clamps to min_lot at execution time, but this **distorts** the optimizer's intended ratios silently
- Leverage caps are also unenforced: 30x on Bootcamp/Hyper/Pro Growth, 100x on High Stakes. DD constraints usually bind first but not guaranteed.

The fix produces deployable portfolios at every account size; without it, $5K-account recommendations may need manual edits to be tradeable.

## 3. Proposed changes

### 3.1 Add `account_balance` to PropFirmConfig (or pass-through field)
- Field: `account_balance: float` per program
- Default: same as `target_balance` (i.e. account starts at the target balance to be reached)
- Bootcamp 250K = $100K start, $150K step2, $200K step3 (already in step_balances)
- High Stakes 100K = $100K start (already)
- Hyper Growth 5K = $5K start (already in target_balance)
- Pro Growth 5K = $5K start (already)

### 3.2 Add `min_viable_weight` calculation per (strategy, account_size)
For each strategy in the candidate pool:
```python
min_viable_weight = (min_lot * cfd_dollars_per_point) / (futures_dollars_per_point / 10)
# i.e. fraction of "1 micro" that maps to 1 cfd_lot at min_lot
```

For example: SP500 has min_lot=0.01 → 0.01 CFD lots = $1/point. ES futures = $50/point. So one micro = $5/point. min_viable_weight = $1 / $5 = 0.2.

A portfolio with weight 0.1 on ES at $5K is ABOVE the leverage relevant scaling but BELOW min_lot at execution. Reject it.

### 3.3 Reject combos with sub-min-lot weights
In `sweep_combinations()`:
- For each combo, compute the optimizer's smallest-weight solution
- If any strategy's weight × (account_balance / 250K) × (per-strategy notional ratio) yields CFD lots < min_lot, mark combo as `INFEASIBLE_AT_ACCOUNT_SIZE`
- Drop from MC consideration

### 3.4 Enforce leverage cap during sizing optimization
In `optimise_sizing()`:
- Compute total notional = sum(weight_i * notional_per_micro_i) across portfolio
- Reject weight combinations where `total_notional / account_balance > program_leverage`
- Bootcamp/Hyper/Pro Growth: 30x cap
- High Stakes: 100x cap

### 3.5 Surface deployment readiness in selector report
Add columns to `portfolio_selector_report.csv`:
- `min_lot_check_passed` (bool): all weights deployable at account size
- `effective_leverage` (float): total notional / account balance
- `smallest_strategy_lots` (float): smallest CFD lot size in the portfolio
- `deployment_warnings` (string): comma-separated warnings (e.g. "ES at min_lot, SI rounded up 4%")

### 3.6 Update verdict logic
RECOMMENDED → must be deployable: `min_lot_check_passed AND effective_leverage <= program_leverage`
VIABLE → can deploy with weight rounding: minor min_lot violations on at most 1 strategy
MARGINAL → fundamentally undeployable at this account size

## 4. Frozen parameter grid

| Parameter | Value | Source |
|---|---|---|
| account_balance per program | from PropFirmConfig | new |
| min_lot lookup | from `configs/the5ers_mt5_specs.yaml` per symbol | Sprint 84 |
| program_leverage | 30x default, 100x for High Stakes | new field on PropFirmConfig |
| min_viable_weight rejection threshold | strict (any strategy below = reject) | new |
| deployment warning tolerance | 1 strategy with <5% rounding allowed for VIABLE verdict | new |

## 5. Verdict definitions

| Verdict | Condition |
|---|---|
| **CANDIDATES** | Selector produces RECOMMENDED portfolios at all 4 program account sizes. Live deployment instructions match selector output without manual edits. |
| **PARTIAL** | Works for 3 of 4 programs but fails at one specific account size (typically $5K). Document the gap. |
| **NO EDGE** | n/a - this is plumbing |
| **BLOCKED** | Cannot integrate without breaking parity-tested MC code paths |

## 6. Why this matters

Operator runs 4 prop firm programs with capital ranging $5K-$250K. Without account-aware sizing:
- A $250K-optimal portfolio might be undeployable at $5K
- Manual workaround: drop strategies until smallest weight is feasible (distorts the recommendation)
- Risk: operator deploys a "RECOMMENDED" portfolio that the selector blessed but that breaks at execution

After this sprint:
- Each program's portfolio is guaranteed deployable
- The selector's RECOMMENDED tier means "ready to deploy as-is"
- Operator stops doing manual weight-juggling per account

## 7. Implementation order

1. Add `account_balance` and `program_leverage` fields to PropFirmConfig (1 hour)
2. Implement `min_viable_weight` helper (1 hour)
3. Add infeasibility check to sweep_combinations (2 hours)
4. Add leverage check to optimise_sizing (2 hours)
5. Add new report columns and verdict logic (1 hour)
6. Tests for each gate (3 hours)
7. Smoke test on a 4-program full run (verify all programs produce deployable portfolios)

Total estimated: 1-2 days code + verification.

## 8. Result (filled in at sprint close)

TBD
