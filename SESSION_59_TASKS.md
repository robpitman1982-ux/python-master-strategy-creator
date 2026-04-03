# Session 59 Tasks — Vectorized Cloud Portfolio Selector (Multi-Program)

## Context
Portfolio selector currently runs single-threaded with Python loops.
With 649 strategies (526 accepted) across 16 markets, and needing to evaluate
multiple prop firm programs (Bootcamp $250K, High Stakes $100K, Hyper Growth $5K,
Pro Growth, home futures $25K), this needs to run on the 96-vCPU GCP VM with
vectorized numpy MC + ProcessPoolExecutor parallelism.

**Estimated speedup**: 5,000-10,000x (vectorization ~200x × parallelism ~50x)
**Target runtime**: All 5 programs in under 10 minutes on n2-highcpu-96

## Architecture Overview

The key insight: vectorize the CORE MC simulation so it processes all N sims
as a single numpy 2D array operation, then parallelize ACROSS combinations
with ProcessPoolExecutor. This makes every program run fast, not just one.

### Layers (they stack):
1. **Vectorize simulate_challenge** → numpy batch of N sims simultaneously
2. **Vectorize block bootstrap** → pre-generate all N return series as 2D array  
3. **Vectorize risk metrics** → rolling DD, streaks, recovery as array ops
4. **ProcessPoolExecutor** → spread 50 combinations across 96 cores
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
generates a combined report. This is the main entry point for cloud runs.

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
    # "home_futures_25k": {"prop_firm_program": "home_futures", "prop_firm_target": 25_000},
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


## Task 5: Cloud Infrastructure
**Files**: `cloud/config_portfolio.yaml` (NEW), `cloud/startup_portfolio.sh` (NEW)

### config_portfolio.yaml:
```yaml
cloud:
  instance_name: portfolio-selector
  machine_type: n2-highcpu-96
  zone: us-central1-c
  provisioning_model: STANDARD  # Never SPOT for portfolio — too short to preempt
  boot_disk_size_gb: 50
  project: project-c6c16a27-e123-459c-b7a
  bucket: strategy-artifacts-nikolapitman
  
run:
  type: portfolio_selector
  script: cloud/startup_portfolio.sh
  
  # Bundle these directories to the VM
  bundle_dirs:
    - Outputs/runs          # strategy_returns.csv files needed for MC
    - Outputs/ultimate_leaderboard_bootcamp.csv
    - modules/
    - cloud/
    - generate_returns.py
    - run_portfolio_all_programs.py
    - config.yaml
```

### startup_portfolio.sh:
```bash
#!/usr/bin/env bash
set -euo pipefail

cd ~/python-master-strategy-creator

# Install deps
pip install numpy pandas --break-system-packages

# Step 1: Generate returns (parallel rebuild)
echo "=== STEP 1: Generating strategy returns ==="
python3 generate_returns.py

# Step 2: Run portfolio selector across all programs
echo "=== STEP 2: Running portfolio selector (all programs) ==="
python3 run_portfolio_all_programs.py --programs all

# Step 3: Package results
echo "=== STEP 3: Packaging results ==="
tar czf /tmp/portfolio_results.tar.gz \
    Outputs/portfolio_*/portfolio_selector_report.csv \
    Outputs/portfolio_combined_summary.csv

# Step 4: Upload to GCS
gsutil cp /tmp/portfolio_results.tar.gz \
    gs://strategy-artifacts-nikolapitman/runs/portfolio-$(date -u +%Y%m%dT%H%M%SZ)/

echo "=== DONE ==="
```

### Launch mechanism:
Option A: Adapt `launch_gcp_run.py` to support `run.type: portfolio_selector`
Option B: Simpler — create `run_cloud_portfolio.py` that does SSH to console,
          launches VM, runs script, downloads results. Similar pattern to 
          `run_cloud_sweep.py` but with portfolio-specific bundling.

PREFER Option A — less code duplication, reuses existing VM lifecycle management.
Add a check in `launch_gcp_run.py` for `run.type` and branch the startup command.


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

With 96 cores, rebuilding 526 strategies should take ~30 seconds vs ~15 minutes locally.

## Execution Order

1. Task 8 — Smart combo search + config wiring (FIRST — unlocks 6-10 strategy portfolios)
2. Task 1 — `simulate_challenge_batch()` in prop_firm_simulator.py
3. Task 6 — Tests (verify parity before changing anything else)
4. Task 2 — Vectorized block bootstrap MC  
5. Task 3 — ProcessPoolExecutor wrappers
6. Task 7 — Fix generate_returns.py
7. Task 4 — Multi-program runner
8. Task 5 — Cloud config + startup script
9. Commit all, push, pull on console, test launch

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
- [ ] Portfolio selector runs locally in < 5 minutes (down from hours)
- [ ] `run_portfolio_all_programs.py` produces reports for all 4+ programs
- [ ] Cloud config launches and runs successfully on n2-highcpu-96
- [ ] Results uploaded to GCS bucket automatically


## Task 8: Smart Combination Search (CRITICAL — unlocks 6-10 strategy portfolios)

### The problem
Current `sweep_combinations()` uses `itertools.combinations(n, k)` brute force:
- n=50 candidates, k=4: 230K combos ✓ (under 500K guard)
- n=50 candidates, k=6: 15.9M combos ✗ (auto-reduced by guard)
- n=50 candidates, k=8: 537M combos ✗✗✗
- n=30 (after dedup), k=6: 594K combos ✗ (just over guard)

Result: **portfolio selector has NEVER actually tested portfolios > 4-5 strategies**
because the combinatorial guard auto-reduces n_max.

### Current constraints in code:
```python
# sweep_combinations() defaults:
n_min: int = 4        # hardcoded default
n_max: int = 8        # hardcoded default, but auto-reduced
candidate_cap: int = 50   # hard_filter_candidates default

# Combinatorial guard:
while total > 500_000 and n_max > n_min:
    n_max -= 1

# run_portfolio_selection() does NOT pass n_min/n_max from config
```

### What's also NOT configurable from config.yaml:
- n_min (portfolio minimum size)
- n_max (portfolio maximum size)
- candidate_cap needs raising for 16 markets
- quality filter only allows ROBUST/STABLE — misses ROBUST_BORDERLINE

### The fix — multi-layer approach:

**Step 1: Make n_min, n_max, candidate_cap all configurable from config.yaml**

Add to config.yaml under pipeline.portfolio_selector:
```yaml
pipeline:
  portfolio_selector:
    n_min: 4
    n_max: 10           # allow up to 10 strategies
    candidate_cap: 80   # more candidates for 16 markets
    quality_flags: ["ROBUST", "ROBUST_BORDERLINE", "STABLE"]  # include borderline
```

Wire into run_portfolio_selection():
```python
combinations = sweep_combinations(
    candidates, corr_matrix, return_matrix,
    n_min=int(ps_cfg.get("n_min", 4)),
    n_max=int(ps_cfg.get("n_max", 10)),
    ...
)
```

**Step 2: Replace brute-force with greedy + random sampling hybrid**

For small k (4-5) where C(n,k) < 500K: keep brute force — exhaustive is best.

For large k (6-10) where brute force is infeasible:
```python
def _sample_large_k_combinations(
    strategy_names, k, n_samples, cand_by_name, corr_matrix,
    multi_layer_corr, thresholds, return_matrix, seed=42
):
    """Generate valid large-k combinations via greedy + random sampling.
    
    Strategy:
    1. Start from top brute-force k=4 or k=5 survivors as seeds
    2. Greedily extend each seed by adding the least-correlated candidate
    3. Also do N random samples with correlation rejection
    4. Score all, keep top 50 for MC
    """
    rng = random.Random(seed)
    results = []
    
    # Method A: Greedy extension from small-k survivors
    # Take top 50 k=4 combos, try extending each to k strategies
    for base_combo in small_k_survivors[:50]:
        combo = list(base_combo["strategy_names"])
        remaining = [s for s in strategy_names if s not in combo]
        
        while len(combo) < k and remaining:
            # Pick candidate with lowest max correlation to existing combo
            best_add = min(remaining, key=lambda s: max(
                abs(corr_matrix.loc[s, c]) for c in combo if s in corr_matrix and c in corr_matrix
            ))
            # Check all correlation gates pass
            if _passes_correlation_gates(combo + [best_add], ...):
                combo.append(best_add)
                remaining.remove(best_add)
            else:
                remaining.remove(best_add)
        
        if len(combo) == k:
            results.append(combo)
    
    # Method B: Random sampling with correlation rejection
    for _ in range(n_samples):
        combo = rng.sample(strategy_names, k)
        if _passes_all_gates(combo, ...):
            results.append(combo)
    
    return results
```

**Step 3: Raise the combinatorial guard for cloud runs**

On a 96-core VM with vectorized MC, we can handle more combos.
Add a configurable guard:
```yaml
pipeline:
  portfolio_selector:
    max_combinations: 2_000_000  # raise from 500K for cloud runs
```

On cloud with vectorized MC, each combo takes milliseconds, so 2M combos
× ~1ms each = ~33 minutes — feasible on 96 cores (parallel → ~30 seconds).

### Summary of config.yaml additions:
```yaml
pipeline:
  portfolio_selector:
    # Existing
    oos_pf_threshold: 1.0
    bootcamp_score_min: 40
    candidate_cap: 80
    n_sims_mc: 10000
    n_sims_sizing: 1000
    
    # NEW — portfolio size range
    n_min: 4
    n_max: 10
    
    # NEW — quality filter expansion
    quality_flags: ["ROBUST", "ROBUST_BORDERLINE", "STABLE"]
    
    # NEW — combinatorial guard (raise for cloud)
    max_combinations: 2000000
    
    # NEW — greedy extension samples for large k
    greedy_extension_seeds: 50
    random_samples_per_k: 10000
```

