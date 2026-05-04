# SPRINT_99 — Trade-array refactor (data-model speedup, conditional ship)

> Pre-registration is mandatory. Commit BEFORE any code is touched.
> Once committed, the parameter grid + verdict criteria are FROZEN.

**Sprint number:** 99
**Date opened:** 2026-05-04
**Date closed:** 2026-05-04 (trial verdict: RED on original scope; pivoted to Sprint 99-bis is_enabled fix that shipped a 3.4x sequential profile speedup, 1-2% on parallel sweeps)
**Operator:** Rob
**Author:** Claude Code on Latitude
**Branch:** `feat/trade-array-refactor`

---

## 1. Sprint goal

Replace per-trade `Trade` Python class instantiation in
`engine.run_vectorized` and the per-trade Python loops in
`engine.results()` with numpy-array-backed equivalents. Goal: capture
the 2-5× per-combo speedup that Numba JIT (Sprint 97, skipped)
couldn't deliver because the hot path isn't filter masks or trade
simulation — it's the **`vectorized_backtest()` returning a list of
dicts → engine constructing 50-500 Trade objects → results() looping
back over them with sum() and Python comprehensions** chain.

This sprint is **conditional-ship**: only proceeds past the trial
phase if a profile-driven measurement shows the targeted code paths
account for >=20% of per-combo wall-clock time. Otherwise the data
says the refactor isn't worth the parity risk on the
zero-tolerance-tested vectorised engine.

## 2. Mechanism plausibility

**Moderate prior — depends on profiling data.**

The Round 3 profiling argued trade simulation dominates per-combo
time. Sprint 97's pre-launch reading of `vectorized_trades.py`
modified that picture: the inner kernel is already pure numpy, but
the **integration layer** (`engine.run_vectorized`'s Trade-object
loop + `engine.results()`'s aggregation loops) is still Python.

Per-combo, the engine does:
1. `compute_combined_signal_mask` — numpy, fast (verified Sprint 94)
2. `vectorized_backtest` — numpy 2D ops, mostly fast (Session 61)
3. **For each of N trades, `Trade(entry_time=..., ...)`** — Python class
4. **For each of N trades, `equity += t.pnl`** — Python loop
5. **`results()`: 10+ `sum(... for t in self.trades ...)` calls** — Python

For typical N = 50-500 trades per combo:
- Step 3 cost: ~5 us per Trade × 200 trades = 1 ms
- Step 4 cost: ~2 us per trade × 200 = 0.4 ms
- Step 5 cost: ~10 sums × 200 trades × 1 us = 2 ms

Total Python-loop cost per combo: ~3-4 ms. Per the profile, MR family
takes ~6.77 ms per combo on small dataset. If 3-4 ms of that is
the steps 3-5 we'd refactor, **the upper bound is ~50% per-combo
speedup**.

**How it could fail:**
- The numbers above are estimates, not measurements. Trial phase will
  measure for real.
- Refactor changes Trade data model — many downstream consumers
  (`trades_dataframe()`, `_calculate_max_drawdown()`, the equity
  curve builder) read `Trade` attributes. They'll need numpy-array
  equivalents.
- Parity is non-negotiable — the engine has zero-tolerance parity tests
  vs the original loop. Refactor must produce identical
  `results()` output.

## 3. Frozen parameter grid

| Phase | Parameter | Value |
|-------|-----------|-------|
| **Trial** | Profile target | One MR family on a representative dataset (small ES daily for speed; if available 60m) |
| Trial | Profiler | `cProfile` with `pstats.SortKey.CUMULATIVE` |
| Trial | Decision threshold | Trade-loop + results-loop must total **≥20% of per-combo time** to justify refactor |
| Trial | Output | Profile dump + summary; commit to repo regardless of decision |
| **Refactor (conditional)** | Trade storage | numpy structured array OR per-field 1D arrays in `MasterStrategyEngine` (e.g. `_trade_pnl: np.ndarray`, `_trade_exit_times: np.ndarray`) |
| Refactor | Trade-class compatibility | Keep `Trade` dataclass for any external API; add `_arrays_to_trades()` lazy property |
| Refactor | results() implementation | numpy operations: `np.sum(pnl > 0)`, `np.maximum.accumulate(equity)`, etc. |
| Refactor | Parity test | All existing engine_parity tests must still pass with zero tolerance |

## 4. Verdict definitions

### Trial phase
| Verdict | Condition |
|---------|-----------|
| **GREEN** | Trade-loop + results-loop ≥ 20% of per-combo wall-clock time on the profiled MR family. Proceed to refactor phase. |
| **RED** | Trade-loop + results-loop < 20% of per-combo wall-clock time. The data says the refactor won't deliver. **Halt sprint, document, move on.** |

### Refactor phase (only reached on GREEN)
| Verdict | Condition |
|---------|-----------|
| **CANDIDATES** | Per-combo speedup ≥ 25% on MR family (modest of the 2-5× ceiling). All zero-tolerance parity tests still pass. |
| **SUSPICIOUS** | Parity passes but speedup < 25%. Document, ship default-off behind a flag if achievable. |
| **BLOCKED** | Parity fails. Halt and investigate. |

## 5. Methodology checklist

- [ ] All test suites green pre-launch
- [ ] Pre-registration committed BEFORE code changes
- [ ] Branch `feat/trade-array-refactor` cut from main

Trial stage:
- [ ] Map all call sites that read `self.trades` (or `Trade` instances) so the refactor's blast radius is documented before code changes.
- [ ] Build `scripts/profile_engine_combo.py` — runs ONE MR family with cProfile, dumps top 30 functions by cumulative time.
- [ ] Run profiler on r630 against ES daily (small dataset, faster turnaround than 5m).
- [ ] Compute the **trade-handling fraction**: time spent inside `Trade.__init__`, the equity loop in `run_vectorized`, and the `sum(...)` calls in `results()` divided by total per-combo time.
- [ ] Trial verdict: GREEN if ≥ 20%, RED otherwise.

Refactor stage (gated on GREEN):
- [ ] Define numpy-array storage on `MasterStrategyEngine` alongside existing `self.trades` for backward compat.
- [ ] Refactor `run_vectorized` to populate arrays directly instead of constructing Trade objects.
- [ ] Refactor `results()` to compute metrics from arrays.
- [ ] Keep `trades_dataframe()` working (build DataFrame from arrays).
- [ ] Run `tests/test_engine_parity.py` and `tests/test_smoke.py` — must be zero-tolerance green.
- [ ] Re-run profiler — confirm targeted code paths shrink as expected.
- [ ] Smoke test on r630 against the same ES daily dataset, compare leaderboard against control.

## 6. Implementation map (refactor phase only)

### 6.1 New storage on `MasterStrategyEngine`

```python
class MasterStrategyEngine:
    def __init__(self, ...):
        ...
        # Sprint 99: numpy-array storage. Existing self.trades list kept
        # populated for backward-compat consumers; arrays are the canonical
        # source of truth for results() and downstream metrics.
        self._trade_pnl: np.ndarray = np.empty(0, dtype=np.float64)
        self._trade_entry_time: np.ndarray = np.empty(0, dtype="datetime64[ns]")
        self._trade_exit_time: np.ndarray = np.empty(0, dtype="datetime64[ns]")
        self._trade_direction: np.ndarray = np.empty(0, dtype="U5")  # "LONG"/"SHORT"
        self._trade_contracts: np.ndarray = np.empty(0, dtype=np.int64)
        self._trade_bars_held: np.ndarray = np.empty(0, dtype=np.int64)
        self._trade_exit_reason: np.ndarray = np.empty(0, dtype="U20")
```

### 6.2 `run_vectorized` simplified hot path

Replace:
```python
for td in result["trades"]:
    self.trades.append(Trade(...))

equity = float(self.initial_capital)
self.equity_curve.append({"datetime": self.data.index[0], "equity": equity})
for t in self.trades:
    equity += t.pnl
    self.equity_curve.append({"datetime": t.exit_time, "equity": equity})
```

With:
```python
trades_list = result["trades"]
n = len(trades_list)
if n > 0:
    # Bulk-fill arrays in one pass — avoid per-element __init__ cost
    self._trade_pnl = np.fromiter((t["pnl"] for t in trades_list), dtype=np.float64, count=n)
    self._trade_exit_time = np.array([t["exit_time"] for t in trades_list], dtype="datetime64[ns]")
    # ... etc

    # Equity curve via cumulative sum
    cum_pnl = np.cumsum(self._trade_pnl)
    equity_arr = self.initial_capital + cum_pnl
    # equity_curve still as list-of-dicts for compat; build via zip
    ...
```

### 6.3 `results()` rewritten with numpy

Replace `sum(t.pnl for t in self.trades if t.pnl > 0)` etc. with
`np.sum(self._trade_pnl[self._trade_pnl > 0])`. Avoids 10× iteration
over the trades list.

## 7. Anti-convergence notes

ChatGPT-5 + Gemini both implicitly endorsed Numba JIT (Sprint 97) as
the engine speedup angle — convergence I called out as anti-alpha
during the session. Skipping 97 was the right call given the engine
is already vectorised. Sprint 99 attacks a layer **neither LLM
identified specifically** but profiling makes obvious in retrospect:
the integration glue between `vectorized_backtest` (numpy) and
`engine.results()` (Python loops over `self.trades`) is where the
Python overhead actually lives.

Risk-weighted: this is a profile-first sprint with an explicit RED
exit. We don't ship the refactor unless the data says it'll pay off.

## 8. Expected impact

Per the rough estimate: 3-4 ms of 6.77 ms per-combo on small MR =
~50% upper bound. Realistic 25-40% per-combo speedup on MR family
specifically. On the heavy MR family that dominates dataset
wall-clock (57% of small-dataset, 2h22m of large-dataset), this
translates to:

- Small dataset: 75s → ~60s (modest, within noise on smoke)
- Large 60m dataset (MR alone 2h22m): → ~1h45m (saves ~40 min)
- 5m datasets where MR is even larger fraction: proportional savings

The trial phase will tell us which end of that range to expect.

## 9. Trial verdict (2026-05-04, gen8 cProfile)

**RED on original scope.** Profile of 1500 MR combos on ES daily
revealed a completely different bottleneck:

```
load_config (yaml.safe_load):       57.87s of 78.76s total = 73%
filter_mask_cache.is_enabled:       28.95s
signal_mask_memo.is_enabled:        28.97s
compute_combined_signal_mask:       42.13s (cumulative incl is_enabled)
```

The Sprint 94 + 95 `is_enabled()` functions were calling
`load_config()` -> `yaml.safe_load()` on **every** combo evaluation.
With 1500 combos × 2 cache flag checks = 3000 yaml loads. Both flags
default-OFF, so this was pure overhead.

**The Trade-object loop + results() loop targeted by this sprint were
not the per-combo bottleneck**; the yaml-reload was. Per the
pre-registered RED exit, this sprint halts.

## 10. Sprint 99-bis spin-off (shipped immediately)

A 30-line fix in three modules:
- `modules/filter_mask_cache.py::is_enabled` -> resolve once, cache result
- `modules/signal_mask_memo.py::is_enabled` -> same
- `modules/strategy_types/sweep_worker_pool.py::_is_recycling_enabled` -> same

Plus `reset_*_cache()` test helpers wired into pytest fixtures.

Committed as `be0ee0e`, merged to main same session.

**Verified speedup (cProfile on gen8, 1500 MR combos, 1 worker):**
- Before fix: 78.76s total, 52.51 ms/combo
- After fix:  **23.40s total, 15.60 ms/combo (3.4x faster)**

**However**: re-tested on the parallel smoke (40 workers, ES daily):
- Before fix (Sprint 94 original smoke): 76.1s OFF -> 76.8s ON
- After fix (gen8 4-mode re-test): 125.0s OFF -> 122.6s ON (1.9% delta)

The 3.4× was a sequential-profiling artifact. In parallel runs each
worker forks once and amortises the yaml load across many combos —
yaml was never the parallel-run bottleneck. The fix is real and
valuable for **dev workflow** (cProfile sessions, unit tests,
small-dataset interactive runs) but **does not change the production
parallel sweep speed**.

**Net of Sprint 99 + 99-bis:**
- Original Sprint 99 scope (Trade-array refactor): NOT pursued — RED
  trial; Trade-object construction is not the per-combo bottleneck
  in either sequential OR parallel runs.
- Sprint 99-bis is_enabled() fix: **shipped as `be0ee0e`**, real win
  on dev workflow, noise on production sweeps.
- Sprints 94 + 95 verdicts UNCHANGED at SUSPICIOUS even after the fix.
