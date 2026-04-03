SESSION_28_TASKS.md
# SESSION 28 TASKS
## Date: 2026-03-24
## Focus: Exit Architecture — First-Class Exit Types for Better Strategy Quality

> Codex / Claude Code: Read `CLAUDE.md` and `CHANGELOG_DEV.md` first.
> Then work through all steps below in order.
> Commit after each step using the exact commit message provided.
> Run the requested tests after each step.
> Do not change unrelated infrastructure or dashboard code in this session.
> This session is about engine quality, not UI polish.

---

## Goal

Upgrade the strategy engine so **exit logic becomes a first-class search dimension** instead of being limited to:

- time stop (`hold_bars`)
- fixed ATR stop (`stop_distance_points`)

We want to add multiple exit styles that the engine can refine and compare, because the recent ES all-timeframe run showed:

- **Mean reversion is strongest**
- **Trend works on daily / 30m but is regime-dependent**
- **Breakout works but is weaker**
- The most likely next major edge improvement is **smarter exits**, especially:
  - trailing stop for trend / breakout
  - profit target and signal exit for mean reversion

This session should build the **foundation** cleanly.

---

## Non-goals

Do **not**:
- change dashboard tabs/layout
- change cloud launcher flow
- add new filters
- add short-side strategies
- add Bootcamp-native ranking yet
- do vectorization yet

Keep this session focused on **exit architecture only**.

---

## Design target

We want strategy definitions and the engine to support these exit types:

- `time_stop`
- `trailing_stop`
- `profit_target`
- `signal_exit`

With these principles:

1. `time_stop` remains available and still uses `hold_bars`
2. ATR stop remains available as the protective stop floor
3. Different strategy families can declare which exit types they support
4. Exit type becomes part of refinement / candidate-specific strategy building
5. Exit behavior must be explicit, inspectable, and testable

---

## STEP 1 — Add exit configuration primitives to strategy layer

### Files to inspect first
- `modules/strategies.py`
- `modules/engine.py`
- `modules/strategy_types/base_strategy_type.py`
- `modules/strategy_types/trend_strategy_type.py`
- `modules/strategy_types/mean_reversion_strategy_type.py`
- `modules/strategy_types/breakout_strategy_type.py`

### Task

Introduce clean, typed exit configuration primitives in the strategy layer.

### Requirements

Add to `modules/strategies.py`:

1. An `ExitType` enum or equivalent constants for:
   - `TIME_STOP`
   - `TRAILING_STOP`
   - `PROFIT_TARGET`
   - `SIGNAL_EXIT`

2. A small exit config container, preferably a dataclass, something like:
   - `exit_type`
   - `hold_bars`
   - `stop_distance_points`
   - `profit_target_atr`
   - `trailing_stop_atr`
   - `signal_exit_reference`

Keep naming practical and consistent with the current code style.

3. Update the relevant base strategy / refined strategy classes so strategies can carry this exit config without breaking existing behavior.

### Backward compatibility

If no explicit exit config is provided:
- current behavior should remain equivalent to:
  - `exit_type = TIME_STOP`
  - use `hold_bars`
  - use `stop_distance_points`

### Notes

- `signal_exit_reference` can start as a simple string, e.g. `"fast_sma"`, even if only one reference is supported initially.
- The goal of Step 1 is **structure**, not fully working execution logic yet.

### Test
Run:

```bash
python -m pytest tests/test_smoke.py tests/test_cloud_launcher.py tests/test_dashboard_utils.py -v
Commit
git commit -m "feat: add exit type primitives and exit config to strategy layer"
STEP 2 — Teach strategy families which exit types they support
Files to modify
modules/strategy_types/base_strategy_type.py
modules/strategy_types/trend_strategy_type.py
modules/strategy_types/mean_reversion_strategy_type.py
modules/strategy_types/breakout_strategy_type.py
Task

Each strategy family should explicitly declare:

supported exit types
sensible default exit type
candidate-specific exit wiring
Requirements
A) Base strategy type API

Add methods to the base class, something like:

get_supported_exit_types()
get_default_exit_type()
optionally get_exit_parameter_grid_for_combo(...)
B) Family defaults

Use these defaults:

Trend

Supported:

time_stop
trailing_stop

Default:

time_stop for backward compatibility
Mean Reversion

Supported:

time_stop
profit_target
signal_exit

Default:

time_stop for backward compatibility
Breakout

Supported:

time_stop
trailing_stop

Default:

time_stop for backward compatibility
C) Candidate-specific strategy building

Update each family’s build_candidate_specific_strategy() so it can accept:

exit_type
any required exit params

and attach them to the strategy’s exit config.

Do not fully expand the refinement grids yet if that makes the session too large; but the strategy-building path must support it.

Notes

This step is about family-level exit intent, not full engine execution yet.

Test

Run:

python -m pytest tests/test_smoke.py tests/test_cloud_launcher.py tests/test_dashboard_utils.py -v
Commit
git commit -m "feat: add family-level supported exit types and default exit behavior"
STEP 3 — Implement engine support for new exit types
Files to modify
modules/engine.py
possibly modules/strategies.py
Task

Update the backtest engine so trades can actually exit using the new exit types.

Required behavior
A) time_stop

Keep current behavior:

exit when held bars >= hold_bars
B) trailing_stop

Implement:

once in a long trade, track the highest high since entry
trailing stop level = highest_high_since_entry - trailing_stop_atr * current_atr
trade exits if current low / price breaches trailing stop

Use existing ATR feature columns where practical.
Keep implementation simple and deterministic.

C) profit_target

Implement:

profit target level = entry_price + profit_target_atr * entry_atr
exit when price reaches or exceeds target
D) signal_exit

For this session, support one initial reference:

"fast_sma"

Behavior:

exit long when close crosses back above / to / through the chosen mean-reversion exit reference in the intended way

Be explicit in code comments about the exact rule used.
For example, for long MR:

exit when close >= fast_sma

That is good enough for Session 28 foundation.

Protective stop

Keep the existing ATR protective stop behavior working for all exit types unless your current implementation requires a small refactor.

Priority rule

Document and implement a clear precedence if more than one exit condition fires on the same bar.

Recommended order:

protective stop
profit target / trailing stop / signal exit
time stop

If your current engine structure naturally uses a different order, document it clearly and keep it consistent.

Notes

Keep the implementation readable. Add comments describing:

what ATR snapshot is used
how trailing stop updates
how signal exit is interpreted
Tests

Add or update tests so the following are covered locally:

time stop still works
trailing stop exits a synthetic rising-then-falling trade
profit target exits a synthetic winning trade
signal exit exits when price returns to / above the fast SMA

Run:

python -m pytest tests/ -v
Commit
git commit -m "feat: engine supports trailing stop profit target and signal exit types"
STEP 4 — Add refinement support for exit types and exit parameters
Files to modify
modules/refiner.py
modules/strategy_types/trend_strategy_type.py
modules/strategy_types/mean_reversion_strategy_type.py
modules/strategy_types/breakout_strategy_type.py
any small helper module if genuinely needed
Task

Wire exit type into refinement so the engine can compare different exit styles.

Requirements
A) Trend refinement

Add exit refinement dimension:

exit_type: time_stop, trailing_stop

If trailing_stop is active:

include trailing_stop_atr grid, e.g.
[1.0, 1.5, 2.0, 2.5]

If time_stop is active:

keep current hold_bars logic
B) Mean reversion refinement

Add exit refinement dimension:

exit_type: time_stop, profit_target, signal_exit

If profit_target is active:

include profit_target_atr grid, e.g.
[0.5, 0.75, 1.0, 1.25, 1.5]

If signal_exit is active:

use reference "fast_sma" for now
keep hold_bars as a backstop, but do not treat it as the primary exit
C) Breakout refinement

Add exit refinement dimension:

exit_type: time_stop, trailing_stop

Use a similar trailing ATR grid to trend.

D) Result visibility

Ensure refinement results include enough information to tell which exit was used.
Add result fields such as:

exit_type
trailing_stop_atr
profit_target_atr
signal_exit_reference

where applicable.

Keep scope manageable

Do not explode the refinement grid unnecessarily.
A practical first implementation is fine.
The purpose is to let the engine compare exit families, not to perfectly optimize every exit parameter yet.

Test

Run:

python -m pytest tests/ -v
Commit
git commit -m "feat: add exit type and exit parameter support to refinement flow"
STEP 5 — Add smoke tests for exit architecture
Files to modify
tests/test_smoke.py
optionally create a small dedicated file like tests/test_exit_architecture.py
Add tests for at least:
Strategy family supported exit types
trend returns trailing support
MR returns profit_target and signal_exit support
breakout returns trailing support
Candidate-specific strategy build accepts exit_type
Engine can process the new exit config without crashing
Refinement result rows include exit metadata
Backward compatibility:
existing strategy creation without explicit exit type still behaves as time_stop

Run:

python -m pytest tests/ -v
Commit
git commit -m "test: add smoke coverage for exit architecture and backward compatibility"
STEP 6 — Update docs
Files to modify
CLAUDE.md
CHANGELOG_DEV.md
CLAUDE.md updates

Add to known issues / priorities:

mark exit architecture foundation as in progress or completed, depending on final implementation
note supported exit types now include:
time_stop
trailing_stop
profit_target
signal_exit

In the improvement roadmap summary section, update the wording so Session 28 is reflected as underway/completed.

CHANGELOG_DEV.md

Add a new entry at the top:

## 2026-03-24 — Session 28: Exit architecture foundation

**What was done**:
- Added first-class exit architecture to the strategy layer
- Added supported exit type declarations per family:
  - Trend: time_stop, trailing_stop
  - Mean Reversion: time_stop, profit_target, signal_exit
  - Breakout: time_stop, trailing_stop
- Updated engine execution to support trailing stop, profit target, and signal exit handling
- Added refinement support for exit type comparison and exit-specific parameters
- Added tests covering exit architecture and backward compatibility

**Why this matters**:
- Trend and breakout were likely being handicapped by blunt time-based exits
- Mean reversion can now express more natural exit logic
- Exit quality is now a searchable part of the engine, not a fixed assumption

**Next session priorities**:
1. Run validation sweep(s) to compare exit styles on ES
2. Begin Bootcamp-native scoring / dual leaderboard
3. Evaluate whether trend quality improves materially with trailing exits
Test

Run:

python -m pytest tests/ -v
Commit
git commit -m "docs: session 28 exit architecture updates"
Final verification

Run all of the following:

python -m py_compile master_strategy_engine.py modules/engine.py modules/strategies.py modules/refiner.py
python -m pytest tests/ -v
git log --oneline -6

If all good, push:

git push origin main
Acceptance criteria

This session is successful if:

Strategies can explicitly carry exit type information
Trend / MR / Breakout each declare supported exit types
Engine supports:
time stop
trailing stop
profit target
signal exit
Refinement can compare exit styles
Results expose which exit type was used
Existing strategies still work without explicit exit config
Tests cover the new architecture

---

## Post-session follow-up completed on 2026-03-24

- Verified the exit refinement grid is genuinely wired into `modules/refiner.py` and strategy-family refinement calls, not just added as result metadata.
- Fixed Windows console output issues by removing remaining non-ASCII status characters that could crash local runs.
- Added config-path fallback so `python master_strategy_engine.py --config config_quick_test.yaml` can resolve `cloud/config_quick_test.yaml` from repo root.
- Added dataset-path fallback so bare dataset filenames can resolve via `Data/`.
- Added safe sequential fallback when `ProcessPoolExecutor` is blocked on Windows during sweep/refinement.
- Added `config_local_quick_test.yaml` as a truly small local completion test config.
- Verified `python master_strategy_engine.py --config config_local_quick_test.yaml` completes successfully without crashing.
