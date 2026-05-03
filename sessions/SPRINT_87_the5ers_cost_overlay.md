# SPRINT_87 - The5ers MT5 cost overlay wiring

**Sprint number:** 87
**Date opened:** 2026-05-03
**Date closed:** 2026-05-03
**Operator:** Rob
**Author:** Claude Code on Latitude
**Branch:** `main` (shipped direct)
**Depends on:** Sprint 84 (trade artifacts), Sprint 85A (CFD config plumbing)

---

## 1. Sprint goal

Wire `configs/the5ers_mt5_specs.yaml` into the portfolio selector's cost-aware
Monte Carlo so cost simulation uses **firm-specific** per-symbol values
(asymmetric long/short swaps, custom triple-day rules, round-trip commission)
instead of generic `cfd_markets.yaml` defaults.

Default off (`use_the5ers_overlay: false`) so existing runs are unchanged
and the new path can be A/B-compared.

## 2. What changed

### `modules/portfolio_selector.py`

- Added `_load_the5ers_specs()` cache loader for `configs/the5ers_mt5_specs.yaml`.
- Added `_the5ers_excluded_markets()` accessor.
- Added module-level toggle `_USE_THE5ERS_OVERLAY` plus
  `_set_the5ers_overlay_enabled(bool)`.
- Rewrote `_get_market_cost_context(market)` to prefer overlay when toggle
  is on, fall back to `configs/cfd_markets.yaml` otherwise. Returns extended
  dict with `swap_long_per_micro_per_night`,
  `swap_short_per_micro_per_night`, `commission_pct`, `triple_day`,
  `cfd_dollars_per_point`, `source` ("the5ers_overlay" or "cfd_markets").
- Extended `_estimate_swap_charge_units()` with `triple_day` parameter.
  - `triple_day="friday"` (default): existing weekday charging with Fri triple.
  - `triple_day="monday"|"tuesday"|...`: same logic but on that weekday.
  - `triple_day="none"`: charge every calendar day at single rate (BTC).
- Extended `_compute_trade_cost_adjustment()`:
  - Picks long vs short swap rate from `trade["direction"]` (falls back to
    max-of-both for safety when direction is missing).
  - Adds round-trip commission = `2 * commission_pct/100 * notional * micros`
    when `entry_price` is present.
- Threaded `use_the5ers_overlay` flag through `run_bootcamp_mc` →
  `_mc_worker_init` initargs so ProcessPool workers honour the toggle.
- `run_portfolio_selection()` reads
  `pipeline.portfolio_selector.use_the5ers_overlay` and:
  - Sets module-level flag.
  - Merges overlay's `excluded_markets` (W, NG, US, TY, RTY, HG) with any
    operator-supplied list.
  - Logs which markets are loaded.

### `config.yaml`
- Added `use_the5ers_overlay: false` under `pipeline.portfolio_selector` with
  inline comment explaining the flag.

### `tests/test_the5ers_overlay.py` (NEW)
- 17 tests covering loader, cache, fallback, asymmetric swap selection by
  direction, BTC daily-no-triple, CL Friday 10x, commission applied on
  symbols with non-zero pct, no commission on zero-pct symbols, overlay-off
  preserves prior behaviour.

## 3. Verification

- `pytest tests/test_the5ers_overlay.py -v` → 17/17 pass.
- `pytest tests/test_smoke.py tests/test_subtypes.py
  tests/test_trade_emission.py tests/test_post_ultimate_gate.py -v` →
  58/58 pass (no regressions in existing suite).

## 4. Operational notes

- **Default off.** Setting `use_the5ers_overlay: true` in `config.yaml` flips
  the cost-aware MC to read the overlay. Re-run `portfolio_all_programs` to
  observe the diff in `portfolio_selector_report.csv`'s pass rates and time-
  to-fund estimates.
- **Verified data sources** referenced in the overlay file:
  - Swap rates: account 26213568 (FivePercentOnline-Real), 7-Apr-2026.
  - Contract specs: `modules/cfd_mapping.py` cross-checked 1-Apr-2026.
  - Excluded markets: MT5 Symbol Watch (W, NG, US, TY, RTY, HG not present).
- **Asymmetric swap impact**: most material on CL (long -0.70 vs short -0.40)
  and BTC (long -1.25 vs short -0.90). Long-biased portfolios on those
  symbols will see higher carry cost than they previously did.
- **CL Friday 10x**: holding a CL position over Friday into Mon now costs 10x
  the normal nightly rate (vs the cfd_markets default of 3x). Selector's
  time-to-fund estimates should now correctly penalise weekend-holders on CL.
- **BTC daily-no-triple**: BTC is now charged 7 nights/week at a single rate
  (no Fri 3x), matching MT5 reality.

## 5. Verdict

**CANDIDATES** — overlay shipped, tests green, off by default. Next selector
re-run with `use_the5ers_overlay: true` will surface real cost impact on
each program's portfolio.

## 6. Follow-ups (out of scope)

- **Sprint 88**: enforce per-program account_balance + min_lot constraints
  during sweep + sizing optimisation.
- A/B compare: run `portfolio_all_programs` once with overlay off, once with
  overlay on, on the same gated leaderboard. Diff `final_pass_rate` and
  `est_months_median` per program. Record the result here.
