# SESSION 5 TASKS — Smoke Tests, Master Leaderboard, Timeframe-Aware Grids
# Date: 2026-03-18

---

## Context

Sessions 0-4 built and hardened the engine, added config/consistency, deployed to cloud, and added structured logging. Two DigitalOcean droplets are running ES 60m sweeps now.

**This session's theme**: Make the engine testable and ready for multi-timeframe expansion.

Three deliverables:
1. Smoke test suite (catch broken imports/interfaces before cloud runs)
2. Master leaderboard aggregator (consolidate results across datasets)
3. Timeframe-aware refinement grids (so hold_bars scales with bar duration)

Work through each step in order. Commit after each step. Push to GitHub when all done.

---

## Step 1: Create smoke test suite

**File**: `tests/test_smoke.py`

Also create `tests/__init__.py` (empty).

These are fast, minimal tests that verify the pipeline doesn't crash. They should NOT require the full ES 60m CSV — generate synthetic OHLCV data inline (500-1000 bars of random walk data with realistic ES-like prices around 4000-5000, proper high > open/close > low relationships).

### Tests to include:

1. **test_config_loader** — `load_config()` returns a dict; `get_nested()` handles missing keys with defaults.

2. **test_feature_builder** — `add_precomputed_features()` on synthetic data adds expected columns (`sma_20`, `sma_50`, `avg_range_20`, `atr_14`, `mom_diff_10`, `bar_range`, `true_range`). Verify no NaN in the tail rows (after warmup period).

3. **test_engine_config** — `EngineConfig` can be instantiated with all fields; verify defaults are sensible.

4. **test_engine_run_minimal** — Create a tiny strategy (always signal=1 or simple moving average cross) and run `MasterStrategyEngine` on synthetic data. Verify `engine.results()` returns a dict with expected keys: `strategy_name`, `total_trades`, `net_pnl`, `profit_factor`, `quality_flag`, `is_trades`, `oos_trades`, `quality_score`, `consistency_flag`.

5. **test_consistency_module** — `analyse_yearly_consistency()` on a mock trade list. Verify it returns `pct_profitable_years`, `max_consecutive_losing_years`, `consistency_flag`. Test at least two cases: one CONSISTENT (>60% profitable years), one INCONSISTENT.

6. **test_filter_combination_generation** — `generate_filter_combinations()` with a known set of 4 filter classes, min=2, max=3. Verify the count matches expected C(4,2) + C(4,3) = 6 + 4 = 10.

7. **test_strategy_type_factory** — `get_strategy_type("trend")`, `get_strategy_type("mean_reversion")`, `get_strategy_type("breakout")` all return valid instances. `list_strategy_types()` returns a list of length >= 3.

8. **test_quality_score_range** — Run the engine on synthetic data, verify `quality_score` is between 0.0 and 1.0 inclusive.

9. **test_progress_tracker** — `ProgressTracker` can be instantiated, `start_family()` / `end_family()` / `log_done()` don't crash. Verify `status.json` is written to the specified output directory (use a temp dir).

### Implementation notes:
- Use `pytest` (already available or installable)
- Use `tempfile.mkdtemp()` for any file output tests
- Each test should run in < 2 seconds
- Add `pytest` to `requirements.txt` if not already there
- The synthetic data helper function should be reusable: `def make_synthetic_ohlcv(n_bars=500, start_price=4500.0, seed=42) -> pd.DataFrame`
- Make sure the synthetic data has a DatetimeIndex spanning at least 2015-01-01 to 2025-12-31 so the IS/OOS split (2019-01-01) works correctly

### Verify:
```bash
cd /path/to/repo
python -m pytest tests/test_smoke.py -v
```

All 9 tests should pass. Fix any issues before moving on.

**Commit**: `feat: add smoke test suite (9 tests covering config, engine, filters, consistency, progress)`

---

## Step 2: Create master leaderboard aggregator

**File**: `modules/master_leaderboard.py`

This module scans all output directories and consolidates every accepted strategy leader into one ranked table.

### Function signature:

```python
def aggregate_master_leaderboard(
    outputs_root: str | Path = "Outputs",
    min_pf: float = 1.0,
    min_oos_pf: float = 1.0,
) -> pd.DataFrame:
```

### Behaviour:

1. Walk all subdirectories of `outputs_root` (e.g. `Outputs/ES_60m/`, `Outputs/ES_5m/`, `Outputs/CL_60m/`).
2. In each subdirectory, look for `family_leaderboard_results.csv`.
3. Load each CSV, filter to rows where `accepted_final == True`.
4. Add columns extracted from the directory name:
   - `market` (e.g. "ES")
   - `timeframe` (e.g. "60m")
5. Concatenate all rows into one DataFrame.
6. Apply optional filters: `min_pf`, `min_oos_pf`.
7. Add a `rank` column sorted by: `leader_net_pnl` descending, then `leader_pf` descending.
8. Return the consolidated DataFrame.

### Output columns (at minimum):
`rank`, `market`, `timeframe`, `strategy_type`, `leader_strategy_name`, `quality_flag`, `leader_pf`, `leader_avg_trade`, `leader_net_pnl`, `leader_trades`, `is_pf`, `oos_pf`, `recent_12m_pf`, `leader_hold_bars`, `leader_stop_distance_points`, `best_combo_filters`

### Also add a CLI entry point:

```python
if __name__ == "__main__":
    df = aggregate_master_leaderboard()
    if df.empty:
        print("No accepted strategies found across any dataset.")
    else:
        print(f"\n{'='*72}")
        print(f"MASTER LEADERBOARD — {len(df)} accepted strategies")
        print(f"{'='*72}")
        print(df.to_string(index=False))
        df.to_csv("Outputs/master_leaderboard.csv", index=False)
        print(f"\nSaved to Outputs/master_leaderboard.csv")
```

So it can be run standalone: `python -m modules.master_leaderboard`

### Add a smoke test:

Add `test_master_leaderboard` to `tests/test_smoke.py`:
- Create a temp directory structure mimicking `Outputs/ES_60m/` with a minimal `family_leaderboard_results.csv` (1-2 rows).
- Call `aggregate_master_leaderboard()` on it.
- Verify it returns a DataFrame with the expected columns and correct row count.

**Commit**: `feat: add master leaderboard aggregator module with CLI and smoke test`

---

## Step 3: Timeframe-aware refinement grids

The current refinement grids in each strategy type have hardcoded values (e.g. MR: `hold_bars=[2,3,4,5,6,8,10,12]`, trend: `hold_bars=[3,5,8,12,15,20]`). These values are calibrated for 60m bars. On a 5m chart, hold_bars=12 means just 1 hour — very different from 12 hours on 60m.

### Changes needed:

**A) Add `timeframe` field to `EngineConfig`** dataclass (default: `"60m"`). This field is already available from `config.yaml` datasets but isn't passed into the engine config today.

**B) Add timeframe multiplier mapping** in a new utility or in `config_loader.py`:

```python
TIMEFRAME_BAR_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "60m": 60,
    "daily": 390,  # ~6.5 hours trading day
}

def get_timeframe_multiplier(timeframe: str, base_timeframe: str = "60m") -> float:
    """Return multiplier to scale parameters from base_timeframe to target timeframe.
    
    Example: 5m relative to 60m = 12.0 (need 12x more bars to cover same time)
    Example: daily relative to 60m = 0.154 (need fewer bars)
    """
    base_minutes = TIMEFRAME_BAR_MINUTES.get(base_timeframe, 60)
    target_minutes = TIMEFRAME_BAR_MINUTES.get(timeframe, 60)
    return base_minutes / target_minutes
```

**C) Update `get_active_refinement_grid_for_combo()` in all 3 strategy types** to accept an optional `timeframe` parameter and scale `hold_bars` values accordingly:

- The base grids remain as-is (calibrated for 60m).
- When `timeframe` is provided and differs from 60m, multiply each hold_bars value by the multiplier, round to int, deduplicate, and sort.
- Example: MR base hold_bars=[2,3,4,5,6,8,10,12] on 5m chart → multiply by 12 → [24,36,48,60,72,96,120,144].
- Example: MR base hold_bars on daily → multiply by 0.154 → [1,1,1,1,1,1,2,2] → deduplicate → [1,2]. In this case, also add a sensible minimum set like [1,2,3,5] so there's enough grid diversity.
- Apply same logic to `stop_distance_points` — scale by the multiplier but cap at reasonable bounds. OR, if stop is already in ATR multiples (as it appears for MR), leave it unscaled since ATR already adapts to timeframe.
- `min_avg_range` and `momentum_lookback` — scale momentum_lookback the same way as hold_bars. Leave min_avg_range unscaled if it's absolute points (the ATR/range values will naturally differ per timeframe in the data).

**D) Thread `timeframe` through the pipeline**:
- In `_run_dataset()` in `master_strategy_engine.py`, pass `ds_timeframe` into `EngineConfig`.
- In `run_single_family()`, pass `cfg.timeframe` to the strategy type's refinement grid method.
- Update the strategy type `run_top_combo_refinement()` methods to pass timeframe to `get_active_refinement_grid_for_combo()`.

**E) Print the scaled grid** in the compute budget output so it's visible in logs:
```
📊 COMPUTE BUDGET — Refinement (5m timeframe, multiplier=12.0x)
   hold_bars: [24, 36, 48, 60, 72, 96, 120, 144]
   stop_distance_points: [0.4, 0.5, 0.75, 1.0, 1.25, 1.5]  (ATR-based, unscaled)
   ...
```

### Add a smoke test:

Add `test_timeframe_multiplier` to `tests/test_smoke.py`:
- Verify `get_timeframe_multiplier("5m")` returns 12.0
- Verify `get_timeframe_multiplier("60m")` returns 1.0
- Verify `get_timeframe_multiplier("daily")` returns approximately 0.154

**Commit**: `feat: add timeframe-aware refinement grid scaling for multi-timeframe support`

---

## Step 4: Update CLAUDE.md and CHANGELOG_DEV.md

### CLAUDE.md updates:
- Mark completed items in the issues list:
  - [x] Smoke test suite added
  - [x] Master leaderboard aggregator
  - [x] Timeframe-aware refinement grids
- Add `tests/test_smoke.py` and `modules/master_leaderboard.py` to the repository structure section
- Add `pytest` to coding standards if not there
- Update "Last updated" line

### CHANGELOG_DEV.md:
Add new entry at the TOP:

```
## 2026-03-18 — Session 5: Smoke tests, master leaderboard, timeframe grids

**What was done**:
- Created tests/test_smoke.py — 10+ smoke tests covering config, engine, filters, consistency, progress, master leaderboard, timeframe multiplier
- Created modules/master_leaderboard.py — scans all Outputs/*/family_leaderboard_results.csv, consolidates into ranked master table with market/timeframe columns
- Added timeframe field to EngineConfig, get_timeframe_multiplier() utility, scaled refinement grids in all 3 strategy types
- Threaded timeframe through pipeline: _run_dataset → EngineConfig → strategy type refinement grids

**Output changes vs Session 4**:
- `python -m pytest tests/test_smoke.py -v` runs full smoke suite
- `python -m modules.master_leaderboard` produces Outputs/master_leaderboard.csv
- Refinement grids now auto-scale hold_bars and momentum_lookback based on dataset timeframe
- Compute budget output shows scaled grid values and timeframe multiplier

**Verified**:
- All smoke tests pass
- Master leaderboard aggregator tested with mock data
- Timeframe multiplier tested for 1m, 5m, 15m, 30m, 60m, daily

**Next session priorities**:
1. Download and analyze results from DigitalOcean droplets (destroy droplets after)
2. Export ES 5m/15m/30m/daily data from TradeStation
3. Run multi-timeframe sweep on cloud
4. Walk-forward validation (alternative to fixed IS/OOS split)
5. Bayesian/Optuna optimization for refinement grid
```

**Commit**: `docs: update CLAUDE.md and CHANGELOG_DEV.md for Session 5`

---

## Final: Push to GitHub

```bash
git push origin main
```

---

## Summary of deliverables

| # | File | What |
|---|------|------|
| 1 | `tests/__init__.py` | Empty init for test package |
| 2 | `tests/test_smoke.py` | 10+ smoke tests (config, engine, filters, consistency, progress, leaderboard, timeframe) |
| 3 | `modules/master_leaderboard.py` | Aggregates all dataset leaderboards into one ranked master table |
| 4 | `modules/config_loader.py` | Add `get_timeframe_multiplier()` and `TIMEFRAME_BAR_MINUTES` |
| 5 | `modules/engine.py` | Add `timeframe` field to `EngineConfig` |
| 6 | `modules/strategy_types/trend_strategy_type.py` | Timeframe-scaled refinement grid |
| 7 | `modules/strategy_types/mean_reversion_strategy_type.py` | Timeframe-scaled refinement grid |
| 8 | `modules/strategy_types/breakout_strategy_type.py` | Timeframe-scaled refinement grid |
| 9 | `master_strategy_engine.py` | Thread `timeframe` into EngineConfig in `_run_dataset()` |
| 10 | `requirements.txt` | Add `pytest` if not present |
| 11 | `CLAUDE.md` | Updated issues list + structure |
| 12 | `CHANGELOG_DEV.md` | Session 5 entry at top |
