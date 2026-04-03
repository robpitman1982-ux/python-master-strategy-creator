# Session 60 Tasks — Vectorized Trade Simulation Loop

## Context
The trade simulation loop in `modules/engine.py` is the #1 remaining bottleneck.
Filters are already vectorized (~50x speedup from Session 44). The trade loop
is still pure Python — a `while i < n_bars` loop with ~200 lines of branching
per bar. For 15m data (230K bars × 45,000 backtests = 10.4 BILLION iterations),
this is what makes 15m/30m runs take forever.

**Current runtimes per market on n2-highcpu-96:**
- daily: ~2 min (2,782 bars)
- 60m: ~8 min (53K bars)  
- 30m: ~18 min (111K bars)
- 15m: ~35 min (231K bars)

**Target after vectorization:**
- ALL timeframes: 2-5 min per market (bar count becomes irrelevant)
- Full 17-market × 4-timeframe sweep: under 60 min total (vs ~8 hours now)

## CRITICAL REQUIREMENT: Exact Parity

**The vectorized engine MUST produce IDENTICAL output to the current engine.**

Not "similar". Not "close enough". IDENTICAL. Same trades, same entry prices,
same exit prices, same PnL, same trade count. The verification approach:

1. Run the CURRENT engine on a real dataset (ES daily, ES 60m, ES 15m)
2. Capture every trade: entry_time, entry_price, exit_time, exit_price, 
   exit_reason, PnL, bars_held
3. Run the VECTORIZED engine on the same dataset with the same strategy
4. Compare trade-by-trade — zero tolerance on trade count, entry/exit prices
   must match within floating point tolerance (1e-10)
5. Run this parity check on ALL exit types: time_stop, protective_stop, 
   profit_target, trailing_stop, signal_exit, early_exit
6. Run on both LONG and SHORT strategies

If ANY trade differs, the vectorized version is WRONG and must be fixed
before proceeding. No exceptions.

## How the Current Engine Works (for reference)

The `engine.py` `run()` method:
```
while i < n_bars:
    if position is not None:
        # Check exits in order:
        # 1. Protective stop (low <= stop for long, high >= stop for short)
        # 2. Profit target (high >= target for long, low <= target for short)
        # 3. Trailing stop (updates running high/low, checks breach)
        # 4. Signal exit (close >= fast_sma for long MR)
        # 5. Early exit (losing after N bars)
        # 6. Time exit (bars_held >= hold_bars)
        # Also: break-even stop modifier, MAE/MFE tracking
    else:
        # Skip to next signal bar (searchsorted)
        # Enter position if signal
    i += 1
```

Key properties that MUST be preserved:
- Trades cannot overlap (one position at a time)
- After a trade exits, the next entry can only happen on a LATER bar
- Stop/target checks use HIGH and LOW of the bar (intrabar fills)
- Time exit uses CLOSE of the bar
- Slippage is applied to entry AND exit prices
- Break-even stop modifies the stop price mid-trade
- Trailing stop ratchets in one direction only (up for long, down for short)
- Position sizing uses current_capital (which changes after each trade)
- Equity curve must be bar-by-bar (not just at trade events)

## Task 1: Parity Test Harness (DO THIS FIRST)

**File**: `tests/test_engine_parity.py`

Before writing ANY vectorized code, build the test harness that will verify it.

```python
def capture_trades(engine) -> list[dict]:
    """Extract normalized trade list from engine results."""
    return [{
        'entry_time': t['entry_time'],
        'entry_price': t['entry_price'],
        'exit_time': t['exit_time'],
        'exit_price': t['exit_price'],
        'exit_reason': t['exit_reason'],
        'pnl': t['pnl'],
        'bars_held': t['bars_held'],
        'direction': t.get('direction', 'long'),
        'contracts': t.get('contracts', 1),
    } for t in engine.trades]

def compare_trades(old_trades, new_trades, tolerance=1e-10):
    """Compare two trade lists. Raise AssertionError on any difference."""
    assert len(old_trades) == len(new_trades), (
        f"Trade count mismatch: old={len(old_trades)}, new={len(new_trades)}"
    )
    for i, (old, new) in enumerate(zip(old_trades, new_trades)):
        assert old['entry_time'] == new['entry_time'], (
            f"Trade {i}: entry_time {old['entry_time']} != {new['entry_time']}"
        )
        assert abs(old['entry_price'] - new['entry_price']) < tolerance, (
            f"Trade {i}: entry_price {old['entry_price']} != {new['entry_price']}"
        )
        assert abs(old['exit_price'] - new['exit_price']) < tolerance, (
            f"Trade {i}: exit_price {old['exit_price']} != {new['exit_price']}"
        )
        assert old['exit_reason'] == new['exit_reason'], (
            f"Trade {i}: exit_reason {old['exit_reason']} != {new['exit_reason']}"
        )
        assert abs(old['pnl'] - new['pnl']) < tolerance, (
            f"Trade {i}: pnl {old['pnl']} != {new['pnl']}"
        )
        assert old['bars_held'] == new['bars_held'], (
            f"Trade {i}: bars_held {old['bars_held']} != {new['bars_held']}"
        )
```

### Test cases to cover:
```python
# Test 1: time_stop exit (most common — ~80% of strategies)
def test_parity_time_stop_long_daily()
def test_parity_time_stop_short_daily()

# Test 2: protective stop hit
def test_parity_stop_hit_long()
def test_parity_stop_hit_short()

# Test 3: profit target hit
def test_parity_profit_target_long()
def test_parity_profit_target_short()

# Test 4: trailing stop
def test_parity_trailing_stop_long()
def test_parity_trailing_stop_short()

# Test 5: signal exit (close >= fast_sma)
def test_parity_signal_exit()

# Test 6: early exit (losing after N bars)
def test_parity_early_exit()

# Test 7: break-even stop modifier
def test_parity_break_even_stop()

# Test 8: mixed — a full strategy with real data
def test_parity_full_strategy_es_daily()
def test_parity_full_strategy_es_60m()
def test_parity_full_strategy_es_15m()  # stress test with 230K bars

# Test 9: position sizing changes (capital changes after each trade)
def test_parity_position_sizing()

# Test 10: short strategies
def test_parity_short_mean_reversion()
def test_parity_short_breakout()
```

Each test:
1. Runs the CURRENT `engine.run()` method
2. Captures trades via `capture_trades()`
3. Runs the NEW vectorized method (Task 2)
4. Captures trades
5. Calls `compare_trades()` — ZERO tolerance


## Task 2: Vectorized Trade Simulator — time_stop only (Phase 1)

**File**: `modules/vectorized_trades.py` (NEW)

Start with time_stop because it's the simplest and covers ~80% of strategies.
Other exit types added in subsequent tasks.

### The Approach — Fixed-Width Trade Windows

For time_stop strategies, every trade has exactly `hold_bars` bars. Given a
signal at bar `s`, the trade occupies bars `s+1` through `s+hold_bars` 
(entry on close of signal bar, exit on close of bar s+hold_bars).

The key insight: since trades can't overlap and each has a fixed width,
we can compute ALL trade outcomes simultaneously using 2D numpy arrays.

```python
def vectorized_backtest_time_stop(
    signal_mask: np.ndarray,       # (n_bars,) boolean — precomputed filter signals
    close: np.ndarray,             # (n_bars,)
    high: np.ndarray,              # (n_bars,)
    low: np.ndarray,               # (n_bars,)
    atr: np.ndarray,               # (n_bars,)
    hold_bars: int,
    stop_distance_atr: float,
    direction: str,                # "long" or "short"
    initial_capital: float,
    risk_per_trade: float,
    commission_per_contract: float,
    slippage_ticks: int,
    tick_value: float,
    dollars_per_point: float,
) -> dict:
    """Vectorized backtest for time_stop exit strategies.
    
    Returns dict matching engine.results() format:
      Total Trades, Net PnL, Profit Factor, Win Rate, Max Drawdown,
      IS trades/PnL, OOS trades/PnL, plus full trade list.
    """
```

### Algorithm:

```python
slippage_pts = slippage_ticks * (tick_value / dollars_per_point)

# Step 1: Identify valid entry bars (signal=True, not inside a previous trade)
signal_bars = np.flatnonzero(signal_mask)

# Remove overlapping entries — after entering at bar s, next entry
# can't be until bar s + hold_bars + 1 at earliest
valid_entries = []
next_allowed = 0
for s in signal_bars:
    if s >= next_allowed:
        valid_entries.append(s)
        next_allowed = s + hold_bars + 1  # +1 because entry bar is consumed
valid_entries = np.array(valid_entries)
# NOTE: This loop is O(n_trades), not O(n_bars) — fast even for 15m data

# Step 2: Compute entry prices for ALL trades at once
if direction == "long":
    entry_prices = close[valid_entries] + slippage_pts  # (n_trades,)
else:
    entry_prices = close[valid_entries] - slippage_pts

# Step 3: Compute stop prices
entry_atrs = atr[valid_entries]  # (n_trades,)
stop_distances = stop_distance_atr * entry_atrs
if direction == "long":
    stop_prices = entry_prices - stop_distances
else:
    stop_prices = entry_prices + stop_distances

# Step 4: Build 2D price windows — (n_trades, hold_bars)
# For each trade, extract the price bars from entry+1 to entry+hold_bars
n_trades = len(valid_entries)
exit_indices = np.minimum(valid_entries + hold_bars, len(close) - 1)

# Build windows — each row is the price bars for one trade
# Use fancy indexing to build all windows at once
window_indices = valid_entries[:, np.newaxis] + np.arange(1, hold_bars + 1)
window_indices = np.minimum(window_indices, len(close) - 1)  # clamp

window_lows = low[window_indices]    # (n_trades, hold_bars)
window_highs = high[window_indices]  # (n_trades, hold_bars)
window_closes = close[exit_indices]  # (n_trades,) — close at time exit bar

# Step 5: Check stop hits — vectorized across ALL trades simultaneously
if direction == "long":
    stop_hit_mask = window_lows <= stop_prices[:, np.newaxis]
else:
    stop_hit_mask = window_highs >= stop_prices[:, np.newaxis]

# First bar where stop is hit (per trade)
any_stop_hit = stop_hit_mask.any(axis=1)  # (n_trades,)
stop_hit_bar = np.argmax(stop_hit_mask, axis=1)  # first True per row

# Step 6: Determine exit price and reason
# If stop hit before hold_bars: exit at stop price
# If no stop hit: exit at close of final bar (time exit)
if direction == "long":
    exit_prices = np.where(any_stop_hit,
        stop_prices - slippage_pts / 2,  # stop fill
        window_closes - slippage_pts / 2)  # time exit
    trade_pnls_per_point = exit_prices - entry_prices
else:
    exit_prices = np.where(any_stop_hit,
        stop_prices + slippage_pts / 2,
        window_closes + slippage_pts / 2)
    trade_pnls_per_point = entry_prices - exit_prices

exit_reasons = np.where(any_stop_hit, "STOP", "TIME")

# Step 7: Position sizing — SEQUENTIAL (must use current_capital)
# This is the one part that CANNOT be fully vectorized because
# each trade's position size depends on capital after previous trades.
# But it's O(n_trades) not O(n_bars) — hundreds vs hundreds of thousands.
capital = initial_capital
contracts_list = []
pnl_list = []
for i in range(n_trades):
    stop_dist = stop_distances[i]
    risk_dollars = capital * risk_per_trade
    contracts = max(1, int(risk_dollars / (stop_dist * dollars_per_point)))
    contracts_list.append(contracts)
    
    pnl = trade_pnls_per_point[i] * dollars_per_point * contracts
    pnl -= 2 * commission_per_contract * contracts  # entry + exit commission
    pnl_list.append(pnl)
    capital += pnl

# This loop runs in microseconds — n_trades is typically 50-500

# Step 8: Build trade list matching engine.trades format
trades = []
for i in range(n_trades):
    actual_bars_held = (hold_bars if not any_stop_hit[i] 
                        else int(stop_hit_bar[i]) + 1)
    exit_bar_idx = valid_entries[i] + actual_bars_held
    trades.append({
        'entry_time': timestamps[valid_entries[i]],
        'entry_price': float(entry_prices[i]),
        'exit_time': timestamps[min(exit_bar_idx, n_bars-1)],
        'exit_price': float(exit_prices[i]),
        'exit_reason': str(exit_reasons[i]),
        'pnl': float(pnl_list[i]),
        'bars_held': actual_bars_held,
        'direction': direction,
        'contracts': contracts_list[i],
    })

return {
    'Total Trades': n_trades,
    'Net PnL': sum(pnl_list),
    'trades': trades,
    # ... other metrics computed from pnl_list
}
```

### Where the speed comes from:

| Step | Current (Python loop) | Vectorized | Why |
|------|----------------------|------------|-----|
| Signal bars | `searchsorted` skip | Same | Already fast |
| Entry prices | Computed per bar | `close[entries] + slip` | One numpy op |
| Stop check | Per bar in while loop | `window_lows <= stops` | One broadcast op |
| Exit prices | Per bar in while loop | `np.where(hit, stop, close)` | One numpy op |
| PnL | Per bar in while loop | `exit - entry` vectorized | One numpy op |
| Position sizing | Per bar | Per trade (O(n_trades)) | 100-1000x fewer iterations |
| Equity curve | Per bar dict append | Pre-allocated numpy array | No Python allocs |

The 10.4 BILLION iterations (15m) reduce to:
- ~300 trades × numpy window construction = ~300 iterations
- Plus ~300 iterations for position sizing
- Plus a handful of numpy broadcast operations on (300, hold_bars) arrays
- Total: maybe 1,000 Python iterations instead of 10,400,000,000

## Task 3: Add Profit Target Exit

Extend `vectorized_trades.py` to handle `ExitType.PROFIT_TARGET`.

Same 2D window approach:
```python
if exit_type == "profit_target":
    target_prices = entry_prices + profit_target_atr * entry_atrs  # long
    target_hit_mask = window_highs >= target_prices[:, np.newaxis]
    any_target_hit = target_hit_mask.any(axis=1)
    target_hit_bar = np.argmax(target_hit_mask, axis=1)
    
    # Resolve: which comes first — stop or target?
    # If both hit on same bar: stop takes priority (conservative)
    stop_first = any_stop_hit & (~any_target_hit | (stop_hit_bar <= target_hit_bar))
    target_first = any_target_hit & (~any_stop_hit | (target_hit_bar < stop_hit_bar))
    time_exit = ~any_stop_hit & ~any_target_hit
```

Run parity tests: `test_parity_profit_target_long`, `test_parity_profit_target_short`


## Task 4: Add Trailing Stop Exit

Trailing stop is harder because the stop price changes bar-by-bar within
the trade window. But it's still vectorizable:

```python
if exit_type == "trailing_stop":
    # For long: trailing stop = running_high - trail_atr * atr
    # Running high: np.maximum.accumulate along axis=1
    running_highs = np.maximum.accumulate(window_highs, axis=1)  # (n_trades, hold_bars)
    
    # ATR at each bar in the window
    window_atrs = atr[window_indices]  # (n_trades, hold_bars)
    
    trailing_stops = running_highs - trailing_stop_atr * window_atrs  # (n_trades, hold_bars)
    
    # Trailing stop can only ratchet UP for longs
    trailing_stops = np.maximum.accumulate(trailing_stops, axis=1)
    
    # Check breach
    trail_hit_mask = window_lows <= trailing_stops
    any_trail_hit = trail_hit_mask.any(axis=1)
    trail_hit_bar = np.argmax(trail_hit_mask, axis=1)
```

Run parity tests: `test_parity_trailing_stop_long`, `test_parity_trailing_stop_short`

## Task 5: Add Signal Exit + Early Exit + Break-Even

**Signal exit** (close >= fast_sma for long MR):
```python
# Pre-compute SMA column as numpy array
sma_arr = data[sma_column].values
window_sma = sma_arr[window_indices]  # (n_trades, hold_bars)
window_close = close[window_indices]
signal_exit_mask = window_close >= window_sma  # long
signal_exit_bar = np.argmax(signal_exit_mask, axis=1)
```

**Early exit** (losing after N bars):
```python
if early_exit_bars is not None:
    # At bar early_exit_bars, check if unrealized PnL is negative
    early_bar_idx = np.minimum(valid_entries + early_exit_bars, n_bars - 1)
    early_close = close[early_bar_idx]
    unrealized = early_close - entry_prices  # long
    early_exit_mask = unrealized < 0  # still losing after N bars
```

**Break-even stop**:
```python
# Check if MFE >= break_even_atr * entry_atr at any point in window
if break_even_atr is not None:
    mfe_threshold = break_even_atr * entry_atrs[:, np.newaxis]
    if direction == "long":
        running_mfe = np.maximum.accumulate(window_highs - entry_prices[:, np.newaxis], axis=1)
    be_triggered = running_mfe >= mfe_threshold
    # Find first bar where BE triggers, update stop from that bar onward
    be_bar = np.argmax(be_triggered, axis=1)
    # New stop = entry + lock_atr * entry_atr (only if triggered)
    be_stop = entry_prices + break_even_lock_atr * entry_atrs
    # Replace stop_prices where be_triggered and be_stop > original stop
```

Run ALL parity tests after each addition.


## Task 6: Integrate into Engine

**File**: `modules/engine.py`

Add a `run_vectorized()` method that calls the vectorized functions.
Keep the original `run()` method unchanged — we need it for parity testing
and as a fallback.

```python
def run_vectorized(self, strategy, hold_bars=None, stop_distance_atr=None,
                   precomputed_signals=None):
    """Vectorized backtest — same interface as run(), same results, 100x+ faster."""
    exit_config = self._resolve_exit_config(strategy, hold_bars, ...)
    
    if exit_config.exit_type == ExitType.TIME_STOP:
        result = vectorized_backtest_time_stop(...)
    elif exit_config.exit_type == ExitType.PROFIT_TARGET:
        result = vectorized_backtest_profit_target(...)
    elif exit_config.exit_type == ExitType.TRAILING_STOP:
        result = vectorized_backtest_trailing_stop(...)
    elif exit_config.exit_type == ExitType.SIGNAL_EXIT:
        result = vectorized_backtest_signal_exit(...)
    
    self.trades = result['trades']
    self.equity_curve = result['equity_curve']
    # ... copy other results
```

Then in `master_strategy_engine.py`, add a config flag:
```yaml
engine:
  use_vectorized_trades: true  # default true, set false to use original loop
```

## Task 7: Full Sweep Parity Test

Run a COMPLETE sweep on ES daily with BOTH engines and compare every single
trade across all 15 promoted strategies. This is the ultimate correctness check.

```python
def test_full_sweep_parity():
    """Run full ES daily sweep with both engines, compare all trades."""
    # Uses the real sweep pipeline with real data
    # Runs each promoted strategy through both engines
    # Compares trade-by-trade across all strategies
    # This test may take 2-3 minutes — that's fine
```


## Task 8: Benchmark

After parity is confirmed, measure the actual speedup:

```python
def test_vectorized_speedup_daily():
    """Vectorized must be at least 20x faster on daily data."""
    
def test_vectorized_speedup_60m():
    """Vectorized must be at least 50x faster on 60m data."""
    
def test_vectorized_speedup_15m():
    """Vectorized must be at least 100x faster on 15m data."""
    # 15m has the most bars, so the speedup should be largest
```

Print timing comparison:
```
Engine comparison on ES 15m (230,626 bars):
  Original:    45.2s per strategy
  Vectorized:   0.3s per strategy
  Speedup:    150x

Full sweep (45,000 backtests):
  Original:    ~35 min
  Vectorized:  ~2 min
```

## Execution Order

1. Task 1 — Build parity test harness (tests BEFORE code)
2. Task 2 — Vectorized time_stop (covers ~80% of strategies)
3. Run parity tests — MUST ALL PASS before continuing
4. Task 3 — Add profit target exit
5. Run parity tests
6. Task 4 — Add trailing stop exit
7. Run parity tests
8. Task 5 — Add signal exit + early exit + break-even
9. Run parity tests
10. Task 6 — Integrate into engine
11. Task 7 — Full sweep parity test
12. Task 8 — Benchmark
13. Commit all, push

## Key Constraints

- **ZERO tolerance on trade parity** — not "similar", IDENTICAL
- **Keep original engine.run() unchanged** — it's the reference implementation
- **Position sizing loop stays sequential** — O(n_trades) is fast enough
- **Test every exit type separately AND in combination**
- **Test BOTH long and short directions**
- **Test on real data (ES daily + ES 60m + ES 15m), not just synthetic**
- **The vectorized code must handle edge cases**:
  - Signal on last bar of data (no room for hold_bars)
  - Stop hit on first bar of trade
  - Two signals closer than hold_bars apart (overlap prevention)
  - Zero ATR (degenerate case)
  - Short data (fewer bars than hold_bars)

## Files Created/Modified

- `modules/vectorized_trades.py` — NEW — vectorized trade simulation
- `tests/test_engine_parity.py` — NEW — parity tests (before code!)
- `modules/engine.py` — MODIFIED — add run_vectorized() method
- `master_strategy_engine.py` — MODIFIED — add config flag
- `config.yaml` — MODIFIED — add engine.use_vectorized_trades flag
