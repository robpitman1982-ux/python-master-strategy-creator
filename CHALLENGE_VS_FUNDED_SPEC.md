# Portfolio Selector: Challenge Mode vs Funded Mode

## Date: 2026-04-17
## Status: SPEC — Ready for implementation

---

## Architecture Summary

One strategy pool, two selection modes. The sweep engine discovers edge on clean midprice data. The portfolio selector applies mode-specific scoring, weighting, and cost configs to assemble portfolios optimised for different objectives.

No changes to the sweep engine. All changes are in `modules/portfolio_selector.py` and config YAML files.

---

## Phase 1: Challenge Mode — "Pass Fast"

### Objective
Maximise probability of passing prop firm evaluation within 2-3 months. Accept higher volatility in exchange for speed. Risk is capped at the entry fee ($150-$545), not funded capital.

### Config: `challenge_mode.yaml`

```yaml
pipeline:
  portfolio_selector:
    selection_mode: "challenge"

    # --- Prop firm target ---
    prop_firm_program: "high_stakes"
    prop_firm_target: 5000

    # --- Recency weighting ---
    recency:
      enabled: true
      recent_window_years: 3          # Score strategies on last 3 years of OOS
      regime_window_years: [2020]     # Also include COVID crash year as stress test
      recent_weight: 0.60             # 60% weight on recent OOS performance
      regime_weight: 0.20             # 20% weight on crisis regime performance
      full_history_weight: 0.20       # 20% weight on full OOS history
      metric: "oos_pf"               # Metric to split-window evaluate

    # --- Hard filters (slightly relaxed vs funded) ---
    quality_flags: ["ROBUST", "ROBUST_BORDERLINE", "STABLE"]
    oos_pf_threshold: 1.0
    bootcamp_score_min: 35            # Lower bar — recency scoring handles quality
    candidate_cap: 80
    min_trades_total: 100             # Lower trade count OK for shorter eval window

    # --- Portfolio construction ---
    n_min: 3
    n_max: 5                          # Concentrated — fewer strategies, bigger edge
    min_market_count: 2               # At least 2 markets for basic diversification

    # --- MC parameters ---
    min_pass_rate: 0.90               # Accept 90% (not 99.6%)
    optimise_for: "time_to_pass"      # Minimise median trades to pass
    n_sims_mc: 10000
    n_sims_sizing: 1000
    n_sims_final: 10000

    # --- DD constraints (slightly looser) ---
    dd_p95_limit_pct: 0.75            # Allow P95 DD up to 75% of program limit
    dd_p99_limit_pct: 0.92            # Allow P99 DD up to 92% of program limit

    # --- Cost layer ---
    cost_profile: "the5ers"           # References cost_profiles.yaml

    # --- Scoring weights (rebalanced for speed) ---
    scoring:
      recency_adjusted_pf: 35         # Heavily weight recent performance
      time_to_pass_score: 25          # Speed matters
      diversity: 20                   # Still need diversification
      inverse_correlation: 15         # Uncorrelated strategies
      regime_survival: 5              # Light weight on crisis survival

    # --- Regime gate (relaxed) ---
    regime_gate:
      enabled: true
      windows:
        - name: "2024-2025"
          min_pf: 1.05                # Must be profitable in recent window
        - name: "2020"
          min_pf: 0.90                # Can lose slightly in COVID (transient shock)
      # No 2022-2023 gate — rate hike regime less relevant to current oil shock
```

### How Recency Scoring Works

For each candidate strategy, the selector splits the OOS equity curve:

```
Full OOS:     |----2016----|----2017----|...|----2023----|----2024----|----2025----|----2026----|
                                             ^                                                ^
                                             recent_start                                     now

Recent window (last 3 years):               |============ 60% weight =========================|
Regime window (2020 COVID):  |== 20% ==|
Full history:                |================================ 20% weight =====================|
```

Composite score per strategy:
```
challenge_score = (recent_pf × 0.60) + (regime_pf × 0.20) + (full_pf × 0.20)
```

This replaces the current flat `bootcamp_score` as the primary ranking metric in challenge mode.

### Market Preferences for Challenge Mode (April-October 2026)

Given current macro (Iran war, oil shock, stagflation risk):

| Priority | Markets | Rationale |
|----------|---------|-----------|
| High | EURUSD, USDJPY, GBPUSD, AUDUSD | Near-zero swap, high liquidity, strong trends on USD strength |
| Medium | XAUUSD | Secular bull, high vol, $4,000 floor — good for MR and trend |
| Medium | NAS100, SP500, US30 | Range-bound/choppy — favour MR strategies only |
| Low | XTIUSD (CL) | Massive edge but $0.70/night swap + 10x Friday kills holds |
| Low | XAGUSD (SI) | $4.05/night swap — prohibitive at scale |

---

## Phase 2: Funded Mode — "Never Blow It"

### Objective
Survive indefinitely on funded account. Minimise drawdown. Maximise long-term compounding. Profit split income is the goal — never risk losing the funded account.

### Config: `funded_mode.yaml`

```yaml
pipeline:
  portfolio_selector:
    selection_mode: "funded"

    # --- Prop firm target ---
    prop_firm_program: "high_stakes"
    prop_firm_target: 100000          # Funded account size

    # --- Recency weighting ---
    recency:
      enabled: false                  # Equal weight across all history
      # When disabled, full OOS PF used as-is (current behaviour)

    # --- Hard filters (strict) ---
    quality_flags: ["ROBUST"]         # ROBUST only — no borderline, no stable
    oos_pf_threshold: 1.15            # Higher bar — need proven edge
    bootcamp_score_min: 55
    candidate_cap: 60
    min_trades_total: 200             # Need statistical significance

    # --- Portfolio construction ---
    n_min: 5
    n_max: 12                         # Diversified — many strategies, small size each
    min_market_count: 4               # At least 4 markets

    # --- MC parameters ---
    min_pass_rate: 0.995              # Near-certainty of survival
    optimise_for: "min_drawdown"      # Minimise P95 max drawdown
    n_sims_mc: 20000                  # More sims for tighter confidence
    n_sims_sizing: 2000
    n_sims_final: 20000

    # --- DD constraints (very tight) ---
    dd_p95_limit_pct: 0.55            # P95 DD must stay under 55% of program limit
    dd_p99_limit_pct: 0.75            # P99 DD must stay under 75% of program limit

    # --- Cost layer ---
    cost_profile: "the5ers"

    # --- Scoring weights (rebalanced for safety) ---
    scoring:
      full_history_pf: 25             # Long-term proven edge
      diversity: 25                   # Maximum diversification
      inverse_correlation: 20         # Uncorrelated strategies critical
      min_drawdown: 20                # Low DD is primary objective
      regime_survival: 10             # Must survive all regimes

    # --- Regime gate (strict) ---
    regime_gate:
      enabled: true
      windows:
        - name: "2022-2023"
          min_pf: 1.05                # Must survive rate hike regime
        - name: "2020"
          min_pf: 1.0                 # Must survive COVID
        - name: "2024-2025"
          min_pf: 1.0                 # Must survive recent market
```

---

## Cost Profiles

Separate YAML file defining prop-firm-specific costs. Referenced by `cost_profile` field.

### `cost_profiles.yaml`

```yaml
the5ers:
  spreads:
    # Typical spread in points (from Dukascopy tick data analysis + firm markup)
    SP500: 0.50
    NAS100: 1.50
    US30: 2.00
    XAUUSD: 0.30
    XAGUSD: 0.03
    XTIUSD: 0.04
    EURUSD: 0.00012
    USDJPY: 0.015
    GBPUSD: 0.00015
    AUDUSD: 0.00012
    # TODO: validate these against live The5ers spreads via MT5 exports

  swap_per_micro_per_night:
    SP500: 0.10
    NAS100: 0.10
    US30: 0.10
    XAUUSD: 2.20
    XAGUSD: 4.05
    XTIUSD: 0.70
    EURUSD: 0.10
    USDJPY: 0.26
    GBPUSD: 0.15
    AUDUSD: 0.12

  weekend_multiplier:
    # Friday swap = N × daily swap (triple swap on some brokers)
    default: 3
    XTIUSD: 10            # CL has 10x Friday multiplier on The5ers

  # How costs are applied in MC simulation:
  # Per trade: spread_cost = spread_pts × dollars_per_point × n_micros
  # Per overnight hold: swap_cost = swap_per_micro × n_micros × hold_nights
  # Friday holds: swap_cost × weekend_multiplier

ftmo:
  # TODO: populate when FTMO account active
  spreads: {}
  swap_per_micro_per_night: {}
  weekend_multiplier:
    default: 3

darwinex_zero:
  # TODO: populate when Darwinex account active
  spreads: {}
  swap_per_micro_per_night: {}
  weekend_multiplier:
    default: 3
```

---

## Implementation Plan

### What needs to change in `portfolio_selector.py`

1. **New parameter: `selection_mode`** — reads from config, switches scoring logic

2. **New function: `recency_weighted_score()`**
   - Takes strategy OOS equity curve (from `strategy_trades.csv`)
   - Splits into windows based on config
   - Computes PF per window
   - Returns weighted composite score
   - Replaces `bootcamp_score` as primary ranking when recency enabled

3. **New function: `apply_cost_profile()`**
   - Takes raw trade list + cost profile config
   - Deducts spread cost per trade (entry + exit)
   - Deducts swap cost per overnight hold
   - Returns cost-adjusted trade list for MC simulation
   - Called BEFORE MC simulation, AFTER portfolio combination

4. **Modified: `hard_filter_candidates()`**
   - Accept `min_trades_total` override (currently hardcoded 60)
   - Accept `selection_mode` to adjust quality_flags defaults

5. **Modified: `optimise_sizing()`**
   - New objective: `optimise_for: "time_to_pass"` vs `"min_drawdown"`
   - time_to_pass: current behaviour (minimise median_trades_to_pass)
   - min_drawdown: minimise P95 DD subject to pass_rate >= min_pass_rate

6. **Modified: `_score_portfolio()`**
   - Accept scoring weight dict from config
   - Currently hardcoded: OOS PF × 20 + diversity × 30 + (1-corr) × 20
   - Challenge: recency_pf × 35 + speed × 25 + diversity × 20 + corr × 15 + regime × 5
   - Funded: full_pf × 25 + diversity × 25 + corr × 20 + min_dd × 20 + regime × 10

7. **New: `split_oos_windows()`**
   - Takes trade list with timestamps
   - Returns dict of {window_name: [trades]} for recency scoring
   - Windows defined by config (recent N years, specific regime years, full)

### What needs to change in `prop_firm_simulator.py`

1. **New: cost deduction in `simulate_single_step()`**
   - Accept optional `cost_profile` dict
   - After each trade, deduct spread cost
   - For each calendar day a position is held, deduct swap cost
   - Friday positions get weekend_multiplier applied

### New files

1. `configs/challenge_mode.yaml` — challenge mode selector config
2. `configs/funded_mode.yaml` — funded mode selector config
3. `configs/cost_profiles.yaml` — prop firm cost profiles

### Runner scripts

1. `run_challenge.py` — runs selector with challenge_mode.yaml
2. `run_funded.py` — runs selector with funded_mode.yaml

---

## The Pivot Workflow

```
1. Start The5ers $5K High Stakes with Challenge portfolio
   - Recency-biased, 3-5 concentrated strategies
   - Target: pass within 2-3 months
   - Risk: $150 entry fee per attempt

2. While challenge is running:
   - Funded portfolio running in paper on same VPS (separate MT5 demo)
   - Validates funded portfolio performance in real-time
   - Builds confidence before deploying real capital

3. On challenge pass:
   - Swap EA on VPS from Challenge to Funded portfolio
   - Funded portfolio takes over on the funded account
   - 5-12 diversified strategies, ultra-conservative sizing
   - Optimised for minimum DD, maximum longevity

4. Ongoing:
   - Re-run challenge mode monthly as new strategies get discovered
   - Queue additional challenges on FTMO / Darwinex Zero in parallel
   - Each firm gets its own cost_profile in cost_profiles.yaml
```

---

## Estimated Implementation Effort

| Component | Effort | Priority |
|-----------|--------|----------|
| `recency_weighted_score()` | 2-3 hours | P1 — core of challenge mode |
| `apply_cost_profile()` | 2-3 hours | P1 — required for accurate MC |
| Config YAML files | 30 min | P1 — drives everything |
| `split_oos_windows()` | 1 hour | P1 — supports recency scoring |
| Modified `_score_portfolio()` | 1 hour | P1 — configurable weights |
| Modified `optimise_sizing()` | 1 hour | P2 — min_drawdown objective |
| Cost deduction in simulator | 2 hours | P2 — swap/spread in MC |
| Runner scripts | 30 min | P2 — convenience |
| Tests | 2-3 hours | P2 — verify parity + new logic |
| **Total** | **~12-15 hours** | |

---

## Dependencies

Before this can run:

1. **Dukascopy tick data downloaded via TDS** — SP500 done, need NQ/YM/GC/SI/CL/FX
2. **Tick-to-bar converter built** — converts TDS .bfc → engine-compatible OHLC CSVs
3. **CFD sweeps completed on local cluster** — Gen 9 + Gen 8 + R630
4. **Leaderboard populated with CFD strategies** — from Dukascopy data sweeps
5. **Cost profiles validated** — cross-check TDS spread stats vs The5ers live spreads

Items 1-3 are the current pipeline blockers. This spec can be implemented in parallel once item 4 is in progress.
