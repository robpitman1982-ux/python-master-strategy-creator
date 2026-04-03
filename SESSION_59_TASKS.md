# Session 59 Tasks — Vectorized Local Portfolio Selector (Multi-Program)

## Context
Portfolio selector currently runs single-threaded with Python loops.
With 649 strategies (526 accepted) across 16 markets, and needing to evaluate
multiple prop firm programs (Bootcamp $250K, High Stakes $100K, Hyper Growth $5K,
Pro Growth), this needs vectorized numpy MC + ProcessPoolExecutor parallelism
to run locally on Rob's 8-core/16-thread Windows machine.

**Target**: k=3..8 portfolio sizes, candidate_cap=60, all programs
**Target runtime**: Under 6 minutes per program locally (8 cores)
**Estimated total**: ~25 minutes for all 4 programs

## Architecture Overview

The key insight: vectorize the CORE MC simulation so it processes all N sims
as a single numpy 2D array operation, then parallelize ACROSS combinations
with ProcessPoolExecutor(max_workers=8). This makes every program run fast.

### Layers (they stack):
1. **Vectorize simulate_challenge** → numpy batch of N sims simultaneously
2. **Vectorize block bootstrap** → pre-generate all N return series as 2D array  
3. **Vectorize risk metrics** → rolling DD, streaks, recovery as array ops
4. **ProcessPoolExecutor** → spread 50 combinations across 8 cores
5. **Multi-program loop** → run all prop firm programs sequentially (each is fast now)


## Task 1: Vectorized Challenge Simulator
**File**: `modules/prop_firm_simulator.py`
**Add**: `simulate_challenge_batch()` function

This is the core vectorization. Instead of calling `simulate_single_step()` once
per simulation in a Python loop, process ALL N simulations simultaneously.

### What to build:

```python
def simulate_challenge_batch(
    trade_matrix: np.ndarray,  # (n_sims, n_trades) — pre-generated
    config: PropFirmConfig,
    source_capital: float = 250_000.0,
) -> dict:
    """Vectorized multi-step prop firm challenge for N simulations at once.
    
    Returns dict with:
      - pass_rate, step pass rates
      - DD percentiles (median, p95, p99)
      - trades_to_pass stats (median, p75)
      - risk metrics (rolling 20 DD, max losing streak, max recovery)
    """
```

### Vectorization strategy for each step:

```python
# trade_matrix shape: (n_sims, n_trades)
# Scale trades: raw_pnl / source_capital * step_balance
scaled = trade_matrix * (step_balance / source_capital)

# Cumulative equity for all sims: (n_sims, n_trades)
equity = step_balance + np.cumsum(scaled, axis=1)

# Running peak: (n_sims, n_trades)
peaks = np.maximum.accumulate(equity, axis=1)

# Static DD breach: equity <= floor
if config.drawdown_type == "static":
    floor = step_balance * (1 - config.max_drawdown_pct)
    dd_breach = equity <= floor
elif config.drawdown_type == "trailing":
    floors = peaks * (1 - config.max_drawdown_pct)
    dd_breach = equity <= floors

# Profit target hit: equity >= target
target = step_balance * (1 + effective_target_pct)
target_hit = equity >= target

# For each sim, find FIRST breach and FIRST target hit
# Use argmax on boolean arrays — returns first True index
# But argmax returns 0 if no True exists, so need to check .any()
breach_idx = np.argmax(dd_breach, axis=1)  # (n_sims,)
breach_exists = dd_breach.any(axis=1)       # (n_sims,)
target_idx = np.argmax(target_hit, axis=1)  # (n_sims,)
target_exists = target_hit.any(axis=1)      # (n_sims,)

# Step passes if target hit comes BEFORE breach (or breach doesn't exist)
passed = target_exists & (~breach_exists | (target_idx < breach_idx))
trades_used = np.where(passed, target_idx + 1, 
                       np.where(breach_exists, breach_idx + 1, n_trades))
```

### Multi-step handling:
For multi-step challenges (Bootcamp = 3 steps, High Stakes = 2 steps):
- Run step 1 vectorized → get `passed_step1` mask and `trades_used_step1`
- For sims that passed step 1, extract remaining trades, run step 2
- Continue for step 3 if applicable
- Track per-step pass counts

### Daily DD (High Stakes / Hyper Growth):
When `config.max_daily_drawdown_pct` is set:
- Reshape trades into (n_sims, n_days, trades_per_day) 
- Sum within each day: daily_pnl = reshaped.sum(axis=2)
- Check daily_pnl <= -daily_dd_limit per day
- First daily breach terminates that sim

### Risk metrics (vectorized):
```python
# Rolling 20-trade DD: use stride_tricks or convolve along axis=1
kernel = np.ones(20)
# For each sim, convolve with ones kernel
rolling_20 = np.apply_along_axis(lambda x: np.convolve(x, kernel, 'valid'), 1, scaled)
rolling_20_worst = rolling_20.min(axis=1)  # (n_sims,)

# Max losing streak: vectorized
signs = (scaled < 0).astype(int)  # (n_sims, n_trades)
# For each sim, find longest consecutive run of 1s
# Use diff trick: transitions from 0→1 start a streak
# This is trickier to vectorize fully — use a compiled helper or per-row
# Fallback: numba @njit for the streak loop (still 100x faster than Python)

# Max recovery trades: 
# equity_from_peak = equity - peaks (always <= 0 during DD)
# Recovery = consecutive trades where equity < peak
# Similar streak detection as above
```

### Tests:
- Compare output of `simulate_challenge_batch()` against N sequential calls to
  `simulate_challenge()` with same random seed. Results must match within float tolerance.
- Test with Bootcamp (3 steps), High Stakes (2 steps), Hyper Growth (daily DD)


## Task 2: Vectorized Block Bootstrap MC
**File**: `modules/portfolio_selector.py`  
**Replace**: `portfolio_monte_carlo_block_bootstrap()` internals

### What to change:

The current function has a `for _ in range(n_sims)` loop that:
1. Samples blocks one sim at a time
2. Calls `simulate_challenge()` per sim
3. Computes risk metrics per sim in Python loops

Replace with:

```python
def portfolio_monte_carlo_block_bootstrap(
    return_matrix, strategy_names, config, source_capital=250_000,
    n_sims=10_000, seed=42, contract_weights=None, block_sizes=None,
) -> dict:
    # ... setup unchanged ...
    
    # VECTORIZED: Pre-generate ALL n_sims block-sampled return series
    rng = np.random.RandomState(seed)
    
    # Pre-compute weighted daily returns (unchanged)
    daily_returns = weighted_returns.values.copy()
    n_days = len(daily_returns)
    
    # Generate block starts and sizes for all sims at once
    # Each sim needs ~n_days/avg_block_size blocks
    avg_block = np.mean(block_sizes)
    n_blocks_per_sim = int(np.ceil(n_days / avg_block)) + 2  # padding
    total_blocks = n_sims * n_blocks_per_sim
    
    all_block_sizes = rng.choice(block_sizes, size=total_blocks)
    all_block_starts = rng.randint(0, n_days, size=total_blocks)
    
    # Build (n_sims, n_days) matrix by extracting blocks
    sim_matrix = _build_block_bootstrap_matrix(
        daily_returns, all_block_starts, all_block_sizes,
        n_sims, n_days, n_blocks_per_sim
    )  # returns np.ndarray (n_sims, n_days)
    
    # Extract non-zero returns as trade matrix
    # For block bootstrap, we pass the full daily matrix to simulate_challenge_batch
    # since the challenge sim handles the equity curve
    
    # VECTORIZED: Run all sims through challenge at once
    mc_result = simulate_challenge_batch(sim_matrix, config, source_capital)
    
    return mc_result
```

### Helper for matrix construction:
```python
def _build_block_bootstrap_matrix(
    daily_returns, block_starts, block_sizes, n_sims, n_days, n_blocks_per_sim
) -> np.ndarray:
    """Build (n_sims, n_days) matrix from pre-generated block params."""
    result = np.zeros((n_sims, n_days))
    for sim in range(n_sims):
        offset = sim * n_blocks_per_sim
        pos = 0
        for b in range(n_blocks_per_sim):
            if pos >= n_days:
                break
            bs = block_sizes[offset + b]
            start = block_starts[offset + b]
            end = min(start + bs, len(daily_returns))
            chunk = daily_returns[start:end]
            take = min(len(chunk), n_days - pos)
            result[sim, pos:pos+take] = chunk[:take]
            pos += take
    return result
```
NOTE: This helper still has a Python loop for matrix construction, but it's 
doing simple array copies (fast) and runs once. The expensive part — the MC 
simulation — is fully vectorized. If needed, this can be @numba.njit'd later.

### Also vectorize `portfolio_monte_carlo()` (shuffle-interleave method):
Same pattern — pre-generate all N shuffled+interleaved trade sequences as a 
2D matrix, then call `simulate_challenge_batch()`.


## Task 3: Parallelize Across Combinations
**File**: `modules/portfolio_selector.py`  
**Modify**: `run_bootcamp_mc()` and `optimise_sizing()`

### run_bootcamp_mc — ProcessPoolExecutor:

```python
from concurrent.futures import ProcessPoolExecutor

def _mc_worker(args):
    """Worker for parallel MC across combinations."""
    combo, return_matrix, n_sims, mc_method, config, raw_trade_lists = args
    names = combo["strategy_names"]
    
    if mc_method == "block_bootstrap":
        mc = portfolio_monte_carlo_block_bootstrap(
            return_matrix, names, config, n_sims=n_sims,
        )
    else:
        # shuffle_interleave path
        trade_lists = {}
        for name in names:
            if raw_trade_lists and name in raw_trade_lists:
                trade_lists[name] = raw_trade_lists[name]
            elif name in return_matrix.columns:
                vals = return_matrix[name].values
                trades = [float(v) for v in vals if v != 0.0]
                if trades:
                    trade_lists[name] = trades
        if not trade_lists:
            return None
        mc = portfolio_monte_carlo(trade_lists, config, n_sims=n_sims)
    
    return {**combo, **mc}

def run_bootcamp_mc(combinations, return_matrix, n_sims=10_000, 
                    raw_trade_lists=None, prop_config=None, mc_method="block_bootstrap"):
    config = prop_config or The5ersBootcampConfig()
    
    # Detect available CPUs
    n_workers = min(len(combinations), os.cpu_count() or 4)
    
    args_list = [
        (combo, return_matrix, n_sims, mc_method, config, raw_trade_lists)
        for combo in combinations
    ]
    
    results = []
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = executor.map(_mc_worker, args_list)
        for i, result in enumerate(futures):
            if result is not None:
                results.append(result)
            logger.info(f"Portfolio MC {i+1}/{len(combinations)} complete")
    
    # Sort by final step pass rate
    n_steps = config.n_steps
    results.sort(key=lambda r: r.get(f"step{n_steps}_pass_rate", 0), reverse=True)
    return results
```

### optimise_sizing — parallelize weight grid search:

The inner loop over weight combos is independent per weight combo.
Use ProcessPoolExecutor to spread weight_combo_iter across cores.

```python
def _sizing_worker(args):
    """Worker for parallel sizing grid search."""
    weight_tuple, strat_names, trade_lists, n_sims, config, source_capital = args
    weights = {s: w for s, w in zip(strat_names, weight_tuple)}
    
    # Run MC with these weights
    mc = portfolio_monte_carlo_block_bootstrap(
        return_matrix_global, strat_names, config,
        n_sims=n_sims, contract_weights=weights,
    )
    return weight_tuple, mc
```

NOTE: ProcessPoolExecutor needs picklable args. The return_matrix DataFrame
is large — use module-level initializer pattern (same as the strategy engine):
```python
_sizing_shared_data = {}

def _sizing_initializer(return_matrix_bytes, columns, index):
    """Called once per worker process."""
    _sizing_shared_data['return_matrix'] = pd.DataFrame(
        np.frombuffer(return_matrix_bytes).reshape(-1, len(columns)),
        columns=columns, index=index
    )
```


## Task 4: Multi-Program Runner
**File**: `run_portfolio_all_programs.py` (NEW)

Script that runs the portfolio selector for ALL prop firm programs and
generates a combined report. This is the main entry point for local runs.

```python
#!/usr/bin/env python3
"""Run portfolio selection across all prop firm programs.

Usage:
    python run_portfolio_all_programs.py
    python run_portfolio_all_programs.py --programs bootcamp high_stakes
    python run_portfolio_all_programs.py --programs all
"""
import argparse, logging, os, time
from pathlib import Path
from modules.portfolio_selector import run_portfolio_selection
from modules.config_loader import load_config

PROGRAMS = {
    "bootcamp_250k": {"prop_firm_program": "bootcamp", "prop_firm_target": 250_000},
    "high_stakes_100k": {"prop_firm_program": "high_stakes", "prop_firm_target": 100_000},
    "hyper_growth_5k": {"prop_firm_program": "hyper_growth", "prop_firm_target": 5_000},
    "pro_growth_5k": {"prop_firm_program": "pro_growth", "prop_firm_target": 5_000},
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--programs", nargs="+", default=["all"])
    args = parser.parse_args()
    
    programs = list(PROGRAMS.keys()) if "all" in args.programs else args.programs
    config = load_config()
    results = {}
    
    for prog_name in programs:
        prog_cfg = PROGRAMS[prog_name]
        print(f"\n{'='*60}")
        print(f"RUNNING: {prog_name}")
        print(f"{'='*60}")
        
        # Override config with program-specific settings
        ps_cfg = config.setdefault("pipeline", {}).setdefault("portfolio_selector", {})
        ps_cfg["prop_firm_program"] = prog_cfg["prop_firm_program"]
        ps_cfg["prop_firm_target"] = prog_cfg["prop_firm_target"]
        
        output_dir = f"Outputs/portfolio_{prog_name}"
        os.makedirs(output_dir, exist_ok=True)
        
        t0 = time.time()
        result = run_portfolio_selection(
            output_dir=output_dir, config=config,
        )
        elapsed = time.time() - t0
        
        results[prog_name] = {**result, "elapsed_seconds": elapsed}
        print(f"  Completed in {elapsed:.1f}s — status: {result.get('status')}")
    
    # Write combined summary
    _write_combined_summary(results)

def _write_combined_summary(results):
    """Write a single CSV comparing top portfolio across all programs."""
    # ... compare best portfolio per program, time-to-fund, DD, pass rates ...
    pass

if __name__ == "__main__":
    main()
```

### Output structure:
```
Outputs/
  portfolio_bootcamp_250k/
    portfolio_selector_report.csv
    portfolio_selector_matrix.csv
  portfolio_high_stakes_100k/
    portfolio_selector_report.csv
    ...
  portfolio_hyper_growth_5k/
    ...
  portfolio_combined_summary.csv  ← comparison across all programs
```


## Task 5: SKIP — Cloud infrastructure deferred
Cloud config (n2-highcpu-96 VM) is not needed for this session.
The vectorized + parallel code runs locally on 8 cores in under 6 minutes per program.
Cloud config can be added later if needed for larger sweeps (k=10, n=80+).


## Task 6: Tests
**File**: `tests/test_vectorized_mc.py` (NEW)

### Critical test — vectorized vs sequential parity:
```python
def test_vectorized_matches_sequential():
    """Ensure vectorized MC produces same results as sequential."""
    # Use a small, deterministic test case
    trades = [100, -50, 200, -150, 75, -30, 180, -90, 60, -40]
    config = The5ersBootcampConfig(250_000)  # 3-step Bootcamp
    n_sims = 1000
    seed = 42
    
    # Sequential (current code)
    seq_results = []
    rng = random.Random(seed)
    for _ in range(n_sims):
        shuffled = trades.copy()
        rng.shuffle(shuffled)
        result = simulate_challenge(shuffled, config, 250_000)
        seq_results.append(result)
    seq_pass_rate = sum(1 for r in seq_results if r.passed_all_steps) / n_sims
    
    # Vectorized (new code)  
    trade_matrix = _build_shuffled_matrix(trades, n_sims, seed)
    vec_result = simulate_challenge_batch(trade_matrix, config, 250_000)
    
    assert abs(vec_result["pass_rate"] - seq_pass_rate) < 0.01
    # Step pass rates should also match
    # DD percentiles should match within tolerance
```

### Test multi-step:
```python
def test_vectorized_high_stakes_2_step():
    """High Stakes has 2 steps + daily DD — verify vectorized handles it."""
    config = The5ersHighStakesConfig(100_000)
    assert config.n_steps == 2
    assert config.max_daily_drawdown_pct == 0.05
    # ... run batch, verify step rates, daily DD breaches detected ...
```

### Test performance:
```python
def test_vectorized_speedup():
    """Vectorized should be at least 50x faster than sequential."""
    # Time 10,000 sims vectorized vs 1,000 sims sequential, extrapolate
    ...
```


## Task 7: Fix generate_returns.py for ProcessPoolExecutor
**File**: `generate_returns.py`

The current `ThreadPoolExecutor` hits the GIL because `_rebuild_strategy_from_leaderboard_row()`
is CPU-bound (runs backtests). Switch to `ProcessPoolExecutor` with initializer pattern:

```python
_worker_data_cache = {}

def _worker_init(data_bytes_map):
    """Initialize per-worker data cache."""
    for key, (arr, cols, idx) in data_bytes_map.items():
        _worker_data_cache[key] = pd.DataFrame(arr, columns=cols, index=idx)

def _process_strategy(args):
    """Worker function for ProcessPoolExecutor."""
    row_dict, data_csv_key, run_id = args
    data = _worker_data_cache[data_csv_key]
    # ... rebuild strategy, generate returns ...
    return result
```

With 8 cores, rebuilding 526 strategies should take ~2 minutes vs ~15 minutes single-threaded.

## Execution Order

1. Task 8 — Config wiring + parallel sweep (FIRST — unlocks 3-8 strategy portfolios)
2. Task 1 — `simulate_challenge_batch()` in prop_firm_simulator.py
3. Task 6 — Tests (verify parity before changing anything else)
4. Task 2 — Vectorized block bootstrap MC  
5. Task 3 — ProcessPoolExecutor wrappers for MC + sizing
6. Task 7 — Fix generate_returns.py (ThreadPool → ProcessPool)
7. Task 4 — Multi-program runner (`run_portfolio_all_programs.py`)
8. Task 5 — SKIP (cloud deferred)
9. Run locally: `python run_portfolio_all_programs.py --programs all`
10. Commit all, push to GitHub

## Key Constraints

- **DO NOT break existing tests** — run `python -m pytest tests/ -v` after each task
- **Vectorized results must match sequential** — use seed-controlled RNG for reproducibility
- **ProcessPoolExecutor needs picklable args** — use initializer pattern for DataFrames
- **source_capital bug still exists** — hardcoded at $250K. For now, accept this. 
  The multi-program runner will handle different step balances via PropFirmConfig,
  but the source_capital used for trade scaling is still wrong for small accounts.
  Fix in a separate session.
- **All prop firm configs already exist** in `modules/prop_firm_simulator.py`:
  The5ersBootcampConfig, The5ersHighStakesConfig, The5ersHyperGrowthConfig, 
  The5ersProGrowthConfig. Home futures config needs to be added if required.
- **Sizing optimizer DD constraint bug** — still outstanding. The vectorized MC
  will make this MORE visible (faster iteration). Flag it in the output but
  don't try to fix it in this session.

## Success Criteria

- [ ] `python -m pytest tests/ -v` all pass (including new vectorized tests)
- [ ] Portfolio selector runs locally in < 6 minutes per program (8 cores, k=3..8, n=60)
- [ ] `run_portfolio_all_programs.py` produces reports for all 4 programs
- [ ] Selector can pick 3-strategy portfolio if it beats larger ones (n_min=3)
- [ ] Selector exhaustively tests k=3 through k=8 (no artificial cap)


## Task 8: Brute-Force All Portfolio Sizes (CRITICAL — unlocks 4-10 strategy portfolios)

### The problem
Current `sweep_combinations()` uses `itertools.combinations(n, k)` brute force
with a 500K guard that auto-reduces `n_max`. Result: portfolio selector has 
NEVER actually tested portfolios > 4-5 strategies.

### Why brute force NOW works
With vectorized MC + parallel sweep, the bottleneck is the SWEEP (correlation checking),
NOT the MC (which only runs on ~50 survivors). The sweep is ~1us per combo.

**Sweep timing on 8 cores (local):**
| Candidates | k=6 | k=8 |
|-----------|------|------|
| n=30 | 0.1s | 1.1s |
| n=40 | 0.6s | 12.5s |
| n=50 | 2.3s | 81.9s |
| n=60 | 5.8s | 375s (6.3min) |

**n=60 candidates, k=3..8 on 8 cores = ~6 minutes total. Fully exhaustive.**

No greedy heuristics needed. Pure exhaustive search on local machine.

### What to do:

**Step 1: Make everything configurable from config.yaml**

```yaml
pipeline:
  portfolio_selector:
    # Portfolio size range — let data decide best size
    n_min: 3              # allow lean 3-strategy portfolios if they're best
    n_max: 8              # up to 8 strategies
    
    # Candidate pool — 60 for 16 markets
    candidate_cap: 60
    
    # Quality filter — include borderline
    quality_flags: ["ROBUST", "ROBUST_BORDERLINE", "STABLE"]
    
    # Combinatorial guard — raised for vectorized+parallel
    max_combinations: 10_000_000_000  # 10 billion — brute force everything
```

Wire ALL of these into `run_portfolio_selection()`:
```python
combinations = sweep_combinations(
    candidates, corr_matrix, return_matrix,
    n_min=int(ps_cfg.get("n_min", 4)),
    n_max=int(ps_cfg.get("n_max", 10)),
    ...
)
```

Wire quality_flags into `hard_filter_candidates()`:
```python
valid_flags_str = ps_cfg.get("quality_flags", ["ROBUST", "STABLE"])
valid_flags = set(f.upper().strip() for f in valid_flags_str)
```

**Step 2: Parallelize the sweep loop with ProcessPoolExecutor**

The sweep is embarrassingly parallel — each C(n,k) combo's pairwise checks
are independent. Split the iteration across 8 cores:

```python
def sweep_combinations_parallel(candidates, corr_matrix, return_matrix, 
                                n_min=3, n_max=8, n_workers=None, **kwargs):
    """Parallel brute-force sweep across all C(n,k) combinations."""
    n_workers = n_workers or min(os.cpu_count() or 4, 8)
    
    # Pre-compute correlation matrices as numpy arrays for fast worker access
    abs_corr_arr = corr_matrix.abs().values
    col_index = {c: i for i, c in enumerate(corr_matrix.columns)}
    
    # For each k, chunk the combinations across workers
    all_results = []
    for k in range(n_min, n_max + 1):
        combos = list(itertools.combinations(strategy_names, k))
        chunk_size = max(1, len(combos) // n_workers)
        chunks = [combos[i:i+chunk_size] for i in range(0, len(combos), chunk_size)]
        
        with ProcessPoolExecutor(max_workers=n_workers, 
                                 initializer=_sweep_init,
                                 initargs=(abs_corr_arr, col_index, ...)) as executor:
            futures = [executor.submit(_sweep_chunk, chunk, k, ...) for chunk in chunks]
            for f in futures:
                all_results.extend(f.result())
    
    # Sort by score, keep top 50
    all_results.sort(key=lambda r: r["score"], reverse=True)
    return all_results[:50]
```

The worker function does the same pairwise checks as now, but on numpy arrays
instead of DataFrames (much faster — no label lookup overhead).

**Step 3: Adaptive n_max based on candidate count**

Rather than a fixed guard, auto-calculate the feasible n_max:
```python
# Target: sweep should complete in < 60 seconds on available cores
target_sweep_seconds = 300
us_per_combo = 1.0  # microseconds
n_cores = min(os.cpu_count() or 4, 8)  # local machine

for test_max in range(n_max, n_min - 1, -1):
    total = sum(comb(n, k) for k in range(n_min, test_max + 1))
    wall_secs = total * us_per_combo / 1_000_000 / n_cores
    if wall_secs <= target_sweep_seconds:
        actual_n_max = test_max
        break
    logger.info(f"n_max={test_max} would take {wall_secs:.0f}s, reducing...")
```

With 60 candidates on 8 cores, k=3..8 is ~6 min — within budget.

### Summary of changes:
1. Add `n_min`, `n_max`, `quality_flags`, `max_combinations` to config.yaml
2. Wire all into `run_portfolio_selection()`
3. Parallelize `sweep_combinations()` with ProcessPoolExecutor + numpy arrays
4. Auto-adapt n_max based on available cores and candidate count
5. Remove the old 500K hardcoded guard

