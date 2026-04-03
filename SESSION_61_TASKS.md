# Session 61 Tasks — Prop Firm Config Fixes (All Programs)

## Context
Verified all prop firm configs against The5ers website screenshots (April 2026).
Found several discrepancies and missing features that affect MC simulation accuracy.
These must be fixed before running the portfolio selector for real.

## Programs Verified
1. **Bootcamp $250K** — CORRECT (no changes needed)
2. **High Stakes $100K** — 3 issues found
3. **Pro Growth $5K** — 2 issues found  
4. **Hyper Growth $5K** — 1 issue (shared with Pro Growth)

## Cross-Program Issues (affect simulation accuracy)

### Issue A: Daily DD is "pause" not "termination" (Pro Growth + Hyper Growth)
**Current**: `simulate_single_step()` treats daily DD breach as account failure
**Actual rules**: "The daily pause does not terminate an account. It only disables 
the account for the current day. Traders can continue trading the very next day."

**Impact**: Our MC simulation is MORE pessimistic than reality. Strategies that hit
the daily DD limit get counted as failures when they should just skip a day and continue.

**Fix**: Add `daily_dd_is_pause: bool` field to `PropFirmConfig`. When True, daily DD
breach skips remaining trades for that "day" but does NOT fail the step. The simulation
continues from the next day boundary.

```python
# In PropFirmConfig dataclass, add:
daily_dd_is_pause: bool = False  # True = pause (skip day), False = terminate

# In simulate_single_step(), change daily DD handling:
if daily_pnl_accumulator <= -daily_dd_limit:
    if config.daily_dd_is_pause:
        # Skip to next day boundary, continue trading
        remaining_in_day = trades_per_day_group - ((i + 1) % trades_per_day_group)
        i += remaining_in_day  # skip rest of day
        daily_pnl_accumulator = 0.0
        continue
    else:
        # Terminate (current behavior — for High Stakes)
        return StepResult(..., passed=False, daily_dd_breach=True)
```

**Set in configs:**
- Bootcamp: `daily_dd_is_pause=False` (no daily DD during eval anyway)
- High Stakes: `daily_dd_is_pause=False` (daily DD = TERMINATION per rules)
- Pro Growth: `daily_dd_is_pause=True` (pause only, continue next day)
- Hyper Growth: `daily_dd_is_pause=True` (pause only, continue next day)

### Issue B: Daily DD should recalculate per day (High Stakes)
**Current**: `daily_dd_limit = step_balance * config.max_daily_drawdown_pct` — fixed at step start
**Actual rules** (High Stakes): "Daily loss is 5% of the starting equity of the day 
OR the starting balance of the day (the highest between them)"

**Impact**: As account grows, real daily DD limit grows too. Our fixed calculation
is more conservative (pessimistic).

**Fix**: Track day-start equity and recalculate daily DD limit at each day boundary:
```python
# At day boundary reset:
if (i + 1) % trades_per_day_group == 0:
    daily_pnl_accumulator = 0.0
    # Recalculate daily DD limit based on max(balance, day_start_balance)
    day_start_balance = balance  # update for next day
    daily_dd_limit = max(balance, step_balance) * config.max_daily_drawdown_pct
```

Add `daily_dd_recalculates: bool = False` to PropFirmConfig. Only High Stakes uses this.

### Issue C: Min profitable days not enforced in MC
**Current**: `min_profitable_days` field exists in PropFirmConfig but `simulate_single_step()`
and `simulate_challenge()` never check it.

**Impact**: High Stakes requires 3 min profitable days per step. Pro Growth requires 3 
for evaluation. Our MC ignores this, potentially counting passes that wouldn't qualify.

**Fix**: After a step "passes" (profit target hit), check if the number of profitable days
meets the minimum. If not, the step still passes but needs more trades/days.

```python
# In simulate_single_step, after profit target hit:
if config.min_profitable_days is not None:
    # Count profitable days from equity curve
    n_profitable_days = _count_profitable_days(equity_curve, trades_per_day_group)
    if n_profitable_days < config.min_profitable_days:
        # Don't exit yet — need more profitable days
        # Continue trading until min days met or DD breach
        continue
```


## Per-Program Fixes

### High Stakes $100K — 3 fixes

**Fix 1: Leverage 1:100 (not 1:30)**
```python
# Change in The5ersHighStakesConfig:
leverage=100.0,  # was 30.0
```

**Fix 2: Daily DD recalculates per day** (Issue B above)
```python
daily_dd_recalculates=True,
```

**Fix 3: Min profitable days = 3**
```python
min_profitable_days=3,  # already set, but needs enforcement in simulation
```

### Pro Growth $5K — 2 fixes

**Fix 1: Daily DD is pause, not termination** (Issue A above)
```python
daily_dd_is_pause=True,
```

**Fix 2: Min profitable days = 3 for evaluation**
```python
min_profitable_days=3,  # was None
```

### Hyper Growth $5K — 1 fix

**Fix 1: Daily DD is pause, not termination** (Issue A above)
```python
daily_dd_is_pause=True,
```

### Bootcamp $250K — NO CHANGES (verified correct)


## Task Summary

### Task 1: Add new PropFirmConfig fields
**File**: `modules/prop_firm_simulator.py`

Add to PropFirmConfig dataclass:
```python
daily_dd_is_pause: bool = False      # True = skip day, False = terminate
daily_dd_recalculates: bool = False  # True = recalc daily limit per day start
```

### Task 2: Fix simulate_single_step() daily DD handling
**File**: `modules/prop_firm_simulator.py`

- When `daily_dd_is_pause=True`: skip remaining trades in the day, reset accumulator,
  continue from next day. Do NOT return StepResult with passed=False.
- When `daily_dd_recalculates=True`: at each day boundary, recalculate 
  `daily_dd_limit = max(balance, step_balance) * config.max_daily_drawdown_pct`

### Task 3: Enforce min_profitable_days
**File**: `modules/prop_firm_simulator.py`

After profit target is hit, count profitable days. If fewer than 
`config.min_profitable_days`, continue trading until requirement met
or DD breach occurs.

A "profitable day" for The5ers = day where closed positions made positive 
profit of at least 0.5% of initial balance. Implement `_count_profitable_days()`.

### Task 4: Update factory configs
**File**: `modules/prop_firm_simulator.py`

High Stakes:
- `leverage=100.0` (was 30.0)
- `daily_dd_recalculates=True`
- `min_profitable_days=3` (already set)

Pro Growth:
- `daily_dd_is_pause=True`
- `min_profitable_days=3` (was None)

Hyper Growth:
- `daily_dd_is_pause=True`

Bootcamp: NO CHANGES

### Task 5: Fix simulate_challenge_batch() (vectorized version from Session 59)
**File**: `modules/prop_firm_simulator.py`

The vectorized batch simulator also needs the same daily DD fixes:
- Pause vs terminate logic
- Recalculating daily DD limit
- Min profitable days enforcement

Must maintain parity with the sequential simulator.

### Task 6: Tests
**File**: `tests/test_prop_firm_configs.py` (NEW or extend existing)

```python
def test_high_stakes_config_correct():
    cfg = The5ersHighStakesConfig(100_000)
    assert cfg.n_steps == 2
    assert cfg.step_profit_targets == [0.08, 0.05]
    assert cfg.max_drawdown_pct == 0.10
    assert cfg.max_daily_drawdown_pct == 0.05
    assert cfg.leverage == 100.0  # FIXED
    assert cfg.daily_dd_recalculates == True  # NEW
    assert cfg.daily_dd_is_pause == False  # terminates
    assert cfg.min_profitable_days == 3

def test_pro_growth_config_correct():
    cfg = The5ersProGrowthConfig(5_000)
    assert cfg.n_steps == 1
    assert cfg.profit_target_pct == 0.10
    assert cfg.max_drawdown_pct == 0.06
    assert cfg.max_daily_drawdown_pct == 0.03
    assert cfg.daily_dd_is_pause == True  # FIXED — pause not terminate
    assert cfg.min_profitable_days == 3  # FIXED
    assert cfg.leverage == 30.0
    assert cfg.entry_fee == 74.0

def test_daily_dd_pause_continues_trading():
    """Daily DD pause should skip rest of day, not fail the step."""
    cfg = The5ersProGrowthConfig(5_000)
    # Create trades where one day has big loss but overall profitable
    trades = [100, -200, 50, 75, 100, -50, 80, 60]  # day 1 loss, days 2-3 profit
    result = simulate_challenge(trades, cfg, source_capital=250_000, trades_per_day=2)
    # Should NOT fail on day 1's daily DD breach
    # Should continue trading days 2-3

def test_daily_dd_terminate_fails_step():
    """High Stakes daily DD should terminate the step."""
    cfg = The5ersHighStakesConfig(100_000)
    trades = [-6000]  # immediate 6% loss on $100K = breach 5% daily
    result = simulate_challenge(trades, cfg, source_capital=250_000, trades_per_day=1)
    assert not result.passed_all_steps
    assert result.steps[0].daily_dd_breach == True

def test_daily_dd_recalculates_with_profit():
    """High Stakes daily DD limit should increase as account grows."""
    cfg = The5ersHighStakesConfig(100_000)
    # Day 1: profit $5K. Day 2: daily DD limit should be 5% of $105K = $5,250
    # not 5% of $100K = $5,000
    
def test_min_profitable_days_enforced():
    """Step should not pass until min profitable days met."""
    cfg = The5ersHighStakesConfig(100_000)
    # Hit 8% profit target in 1 trade but only 1 profitable day
    # Should need 2 more profitable days before step passes

def test_bootcamp_unchanged():
    """Bootcamp config should be identical to before."""
    cfg = The5ersBootcampConfig(250_000)
    assert cfg.max_daily_drawdown_pct is None
    assert cfg.n_steps == 3
    assert cfg.profit_target_pct == 0.06
    assert cfg.max_drawdown_pct == 0.05
    assert cfg.leverage == 30.0
```

## Execution Order

1. Task 1 — Add PropFirmConfig fields (daily_dd_is_pause, daily_dd_recalculates)
2. Task 4 — Update factory configs (leverage, min_profitable_days, pause flags)
3. Task 6 — Config verification tests (run first to confirm configs are correct)
4. Task 2 — Fix simulate_single_step() daily DD handling
5. Task 3 — Enforce min_profitable_days
6. Task 5 — Fix simulate_challenge_batch() (vectorized version)
7. Run ALL tests: `python -m pytest tests/ -v`
8. Commit all, push

## Key Constraints

- **Bootcamp MUST NOT change** — it's verified correct, don't touch it
- **Existing tests must still pass** — these fixes add behavior, they don't change 
  the Bootcamp path
- **Vectorized batch simulator must match sequential** — any fix to simulate_single_step
  must also be applied to simulate_challenge_batch
- **Conservative is OK** — if a fix is hard to implement perfectly (e.g. min profitable
  days counting), a conservative approximation is better than ignoring the rule entirely
- **Daily DD pause vs terminate is the highest-impact fix** — it makes Pro Growth and
  Hyper Growth MC pass rates more realistic (higher, since we were over-penalizing)

## Config Summary Table

| Program | Steps | Target | Max DD | Daily DD | DD Type | Pause? | Recalc? | Min Days | Leverage | Fee |
|---------|-------|--------|--------|----------|---------|--------|---------|----------|----------|-----|
| Bootcamp $250K | 3 | 6%/6%/6% | 5% | None (eval) / 3% (funded) | static | N/A | No | None | 1:30 | $225+$350 |
| High Stakes $100K | 2 | 8%/5% | 10% | 5% | static | No (terminate) | Yes | 3 | **1:100** | $545 |
| Pro Growth $5K | 1 | 10% | 6% | 3% | static | **Yes (pause)** | No | **3** | 1:30 | $74 |
| Hyper Growth $5K | 1 | 10% | 6% | 3% | static | **Yes (pause)** | No | None | 1:30 | $260 |

Bold = changes from current code.
