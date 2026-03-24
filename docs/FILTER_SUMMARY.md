# FILTER SUMMARY

> Comprehensive filter reference for the strategy discovery engine.
> Covers filter architecture, per-family usage, timeframe scaling, feature dependencies,
> refinement behavior, and combinatorial search-space size.
>
> Last updated: 2026-03-24 (Session 27 Part A)

---

## Section 1: Filter Architecture Overview

### `BaseFilter` contract

All filters inherit from `BaseFilter` in `modules/filters.py` and implement:

```python
passes(data: pd.DataFrame, i: int) -> bool
```

The interface is intentionally simple:
- `data` is the full price/features DataFrame
- `i` is the current bar index
- the filter returns `True` if the bar passes the condition and `False` otherwise

Each strategy then loops over its filter list and only emits an entry signal when **every**
filter in the combo passes on the same bar.

### How combinations are generated

`modules/filter_combinator.py` exposes:

```python
generate_filter_combinations(filter_classes, min_filters, max_filters)
```

It uses `itertools.combinations()` and builds every `C(n, r)` combination for:
- `r = min_filters`
- `r = min_filters + 1`
- ...
- `r = max_filters`

with one guardrail:
- `max_filters = min(max_filters, len(filter_classes))`

So the engine really does an exhaustive family-by-family sweep over the configured combo sizes.

### How combo names are built

`build_filter_combo_name()` takes filter objects, reads each filter's `name`, strips the
`Filter` suffix, and joins the short names with underscores.

Example:
- `TrendDirectionFilter`
- `PullbackFilter`
- `RecoveryTriggerFilter`

becomes:

`TrendDirection_Pullback_RecoveryTrigger`

That readable name then gets used inside the inline family strategy names.

### End-to-end flow

The actual control flow is:

1. Filter classes are selected by a strategy family.
2. `generate_filter_combinations()` creates class combinations.
3. Family code converts classes into concrete filter objects for the active timeframe.
4. An inline combinable strategy is built with those filters plus default hold/stop settings.
5. `MasterStrategyEngine.run()` evaluates the strategy bar by bar.
6. `engine.results()` produces PF, trades, PnL, IS/OOS metrics, quality flags, and scores.
7. Promoted candidates are refined through `StrategyParameterRefiner`.

---

## Section 2: Trend Family Filters

### Family-level settings

- Strategy type: `TrendStrategyType`
- Available filters: 10
- `min_filters_per_combo = 4`
- `max_filters_per_combo = 6`
- `default_hold_bars = 6`
- `default_stop_distance_points = 1.25`

### Combination count

Trend uses 10 filters and sweeps sizes 4 through 6:

- `C(10,4) = 210`
- `C(10,5) = 252`
- `C(10,6) = 210`

Total trend sweep combinations: **672**

### Promotion gate thresholds

From `get_promotion_thresholds()`:
- `min_profit_factor = 0.75`
- `min_average_trade = 0.0`
- `require_positive_net_pnl = False`
- `min_trades = 60`
- `min_trades_per_year = 3.0`
- `max_promoted_candidates = 20`

### Trade filter thresholds for refinement

From `get_trade_filter_thresholds()`:
- `min_trades = 60`
- `min_trades_per_year = 3.0`

### Refinement grid

On 60m, trend uses:
- `hold_bars = [3, 4, 5, 6, 8, 10, 12, 15]`
- `stop_distance_points = [0.75, 1.0, 1.25, 1.5, 2.0, 2.5]`
- `min_avg_range = [0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4]` if `VolatilityFilter` is in the combo, else `[0.0]`
- `momentum_lookback = [0, 5, 8, 10, 14]` if `MomentumFilter` is in the combo, else `[0]`

Important reality check: the live trend grid is not a flat 256. Its max 60m size is:

- `8 x 6 x 7 x 5 = 1,680`

when both `VolatilityFilter` and `MomentumFilter` are present.

### Timeframe scaling examples

Trend scaling uses `get_timeframe_multiplier()` from `modules/config_loader.py`.

Multiplier examples relative to 60m:
- `daily = 60 / 390 = 0.154`
- `60m = 1.0`
- `15m = 60 / 15 = 4.0`

#### Daily example

Scaled trend values become approximately:
- fast SMA: `50 -> 10`
- slow SMA: `200 -> 31`
- volatility lookback: `20 -> 5`
- default momentum lookback: `8 -> 2`
- slope bars: `5 -> 2`
- hold grid: `[1, 2, 3, 5]`
- momentum grid when active: `[0, 1, 2, 5, 10, 20]`

#### 60m example

This is the base timeframe, so no scaling:
- fast SMA: 50
- slow SMA: 200
- hold grid: `[3, 4, 5, 6, 8, 10, 12, 15]`
- momentum grid when active: `[0, 5, 8, 10, 14]`

#### 15m example

Multiplier is 4.0:
- fast SMA: `50 -> 200`
- slow SMA: `200 -> 800`
- volatility lookback: `20 -> 80`
- default momentum lookback: `8 -> 32`
- slope bars: `5 -> 20`
- hold grid: `[12, 16, 20, 24, 32, 40, 48, 60]`
- momentum grid when active: `[0, 20, 32, 40, 56]`

### Per-filter details

#### `TrendDirectionFilter`

- Purpose: trend regime filter; confirms the fast SMA is above the slow SMA.
- Logic: returns `False` until `i >= max(fast_length, slow_length)`. Then compares `sma_<fast_length>` and `sma_<slow_length>` if precomputed; otherwise recomputes rolling means from `close`.
- Parameters: `fast_length=50`, `slow_length=200`
- Timeframe scaling: yes; both SMA lengths scale.
- Used in refinement: no direct refinement parameter is wired into it.

#### `PullbackFilter`

- Purpose: identifies a pullback inside an existing trend.
- Logic: requires `i >= fast_length`. Reads previous bar fast SMA from `sma_<fast_length>` if present, else rolling `close` mean, then checks `data.iloc[i]["prev_close"] <= prev_fast_sma`.
- Parameters: `fast_length=50`
- Timeframe scaling: yes; `fast_length` scales.
- Used in refinement: no.

#### `RecoveryTriggerFilter`

- Purpose: triggers the entry once price recovers back above the fast SMA.
- Logic: requires `i >= fast_length`, gets current fast SMA, then checks `close > fast_sma`.
- Parameters: `fast_length=50`
- Timeframe scaling: yes; `fast_length` scales.
- Used in refinement: no.

#### `VolatilityFilter`

- Purpose: avoids dead markets by requiring current ATR to be strong enough relative to longer-term true range.
- Logic: requires `i >= lookback * 2`, reads `atr_<lookback>` if available, computes `true_range` mean over the trailing `lookback * 2` window, then checks `current_atr >= long_term_atr * min_atr_mult`.
- Parameters: `lookback=20`, `min_atr_mult=1.0`
- Timeframe scaling: yes; `lookback` scales.
- Used in refinement: yes; `min_avg_range` is wired into `min_atr_mult` during candidate-specific strategy building. If no refinement value is provided, it falls back to `0.95`.

#### `MomentumFilter`

- Purpose: requires directional persistence rather than a one-bar bounce.
- Logic: requires `i >= lookback`, then checks `close[i] > close[i - lookback]`.
- Parameters: `lookback=10`
- Timeframe scaling: yes; default lookback scales.
- Used in refinement: yes; `momentum_lookback` is wired into the filter if the combo contains this class.

#### `UpCloseFilter`

- Purpose: simple bullish confirmation filter.
- Logic: requires `i >= 1`, then checks `close[i] > close[i - 1]`.
- Parameters: none
- Timeframe scaling: no.
- Used in refinement: no.

#### `TwoBarUpFilter`

- Purpose: short-term continuation confirmation.
- Logic: requires `i >= 2`, then checks two consecutive higher closes:
  `close[i] > close[i - 1]` and `close[i - 1] > close[i - 2]`.
- Parameters: none
- Timeframe scaling: no.
- Used in refinement: no.

#### `TrendSlopeFilter`

- Purpose: confirms the fast SMA is actually rising, not merely above the slow SMA.
- Logic: requires `i >= max(fast_length, slope_bars + fast_length)`. Then compares current fast SMA with the fast SMA from `slope_bars` ago.
- Parameters: `fast_length=50`, `slope_bars=5`
- Timeframe scaling: yes; both parameters scale.
- Used in refinement: no direct refinement field, but it inherits scaled defaults from timeframe.

#### `CloseAboveFastSMAFilter`

- Purpose: keeps entries on the strong side of the short-term mean.
- Logic: requires `i >= fast_length`, gets fast SMA, then checks `close > fast_sma`.
- Parameters: `fast_length=50`
- Timeframe scaling: yes; `fast_length` scales.
- Used in refinement: no.

#### `HigherLowFilter`

- Purpose: adds simple structural confirmation of trend continuation.
- Logic: requires `i >= 2`, then checks `low[i] > low[i - 1]`.
- Parameters: none
- Timeframe scaling: no.
- Used in refinement: no.

---

## Section 3: Mean Reversion Family Filters

### Family-level settings

- Strategy type: `MeanReversionStrategyType`
- Available filters: 10
- `min_filters_per_combo = 3`
- `max_filters_per_combo = 6`
- `default_hold_bars = 5`
- `default_stop_distance_points = 0.75`

### Combination count

MR uses 10 filters and sweeps sizes 3 through 6:

- `C(10,3) = 120`
- `C(10,4) = 210`
- `C(10,5) = 252`
- `C(10,6) = 210`

Total MR sweep combinations: **792**

### Promotion gate thresholds

- `min_profit_factor = 0.80`
- `min_average_trade = 0.0`
- `require_positive_net_pnl = False`
- `min_trades = 60`
- `min_trades_per_year = 3.0`
- `max_promoted_candidates = 20`

### Trade filter thresholds for refinement

- `min_trades = 60`
- `min_trades_per_year = 3.0`

### Refinement grid

On 60m, MR uses:
- `hold_bars = [2, 3, 4, 5, 6, 8, 10, 12]`
- `stop_distance_points = [0.4, 0.5, 0.75, 1.0, 1.25, 1.5]`
- `min_avg_range = [0.4, 0.6, 0.8, 1.0, 1.2, 1.4]` if the combo contains `DistanceBelowSMAFilter`, `LowVolatilityRegimeFilter`, or `StretchFromLongTermSMAFilter`; otherwise `[0.0]`
- `momentum_lookback = [0]`

This means:
- MR does **not** use momentum filtering in refinement.
- The `min_avg_range` dimension is conditional rather than universal.

Max 60m MR refinement size:
- `8 x 6 x 6 x 1 = 288`

Minimum 60m MR refinement size when no conditional filter is present:
- `8 x 6 x 1 x 1 = 48`

### Timeframe scaling examples

#### Daily example

With multiplier `0.154`:
- fast SMA: `20 -> 5`
- slow SMA: `200 -> 31`
- volatility lookback: `20 -> 5`
- hold grid: `[1, 2, 3, 5]`

#### 60m example

Base values:
- fast SMA: 20
- slow SMA: 200
- hold grid: `[2, 3, 4, 5, 6, 8, 10, 12]`

#### 15m example

With multiplier `4.0`:
- fast SMA: `20 -> 80`
- slow SMA: `200 -> 800`
- volatility lookback: `20 -> 80`
- hold grid: `[8, 12, 16, 20, 24, 32, 40, 48]`

### Per-filter details

#### `BelowFastSMAFilter`

- Purpose: baseline mean-reversion stretch condition.
- Logic: requires `i >= fast_length`, gets `sma_<fast_length>` if available or computes it from `close`, then checks `close < fast_sma`.
- Parameters: `fast_length=20`
- Timeframe scaling: yes; `fast_length` scales.
- Used in refinement: no direct refinement field.

#### `DistanceBelowSMAFilter`

- Purpose: requires the stretch below the fast SMA to be meaningful, not tiny.
- Logic: requires `i >= fast_length`, gets fast SMA, reads `atr_20` if available, then checks `(fast_sma - close) >= current_atr * min_distance_atr`.
- Parameters: `fast_length=20`, `min_distance_atr=0.3`
- Timeframe scaling: yes; `fast_length` scales. ATR reference stays `atr_20` in the filter code itself.
- Used in refinement: yes; `min_avg_range` is wired into `min_distance_atr`. If absent, it falls back to `0.8`.

#### `DownCloseFilter`

- Purpose: one-bar selling pressure confirmation.
- Logic: requires `i >= 1`, then checks `close[i] < close[i - 1]`.
- Parameters: none
- Timeframe scaling: no.
- Used in refinement: no.

#### `TwoBarDownFilter`

- Purpose: mild exhaustion condition.
- Logic: requires `i >= 2`, then checks two consecutive lower closes.
- Parameters: none
- Timeframe scaling: no.
- Used in refinement: no.

#### `ThreeBarDownFilter`

- Purpose: stronger exhaustion condition.
- Logic: requires `i >= 3`, then checks three consecutive lower closes.
- Parameters: none
- Timeframe scaling: no.
- Used in refinement: no.

#### `ReversalUpBarFilter`

- Purpose: snapback trigger.
- Logic: checks `close > open` on the current bar.
- Parameters: none
- Timeframe scaling: no.
- Used in refinement: no.

#### `LowVolatilityRegimeFilter`

- Purpose: keeps MR focused on calmer market conditions.
- Logic: requires `i >= lookback * 2`, reads `atr_<lookback>`, computes longer-term `true_range` mean, then checks `current_atr <= long_term_atr * max_atr_mult`.
- Parameters: `lookback=20`, `max_atr_mult=1.0`
- Timeframe scaling: yes; `lookback` scales.
- Used in refinement: yes; `min_avg_range` is wired into `max_atr_mult`. If absent, it falls back to `1.10`.

#### `AboveLongTermSMAFilter`

- Purpose: keeps long MR aligned with the larger trend.
- Logic: requires `i >= slow_length`, gets `sma_<slow_length>` or recomputes it, then checks `close > slow_sma`.
- Parameters: `slow_length=200`
- Timeframe scaling: yes; `slow_length` scales.
- Used in refinement: no.

#### `CloseNearLowFilter`

- Purpose: looks for weak closes near the bottom of the bar.
- Logic: computes `bar_range = high - low`, then `close_position = (close - low) / bar_range`, and checks `close_position <= max_close_position`.
- Parameters: `max_close_position=0.35`
- Timeframe scaling: no.
- Used in refinement: no.

#### `StretchFromLongTermSMAFilter`

- Purpose: deeper long-term stretch filter versus the 200 SMA.
- Logic: requires `i >= slow_length`, gets `sma_<slow_length>`, reads `atr_20`, computes `distance = slow_sma - close`, then checks `distance >= current_atr * min_distance_atr`.
- Parameters: `slow_length=200`, `min_distance_atr=0.5`
- Timeframe scaling: yes; `slow_length` scales.
- Used in refinement: yes; `min_avg_range` is wired into `min_distance_atr`. If absent, it falls back to `0.6`.

Special MR notes:
- `DistanceBelowSMAFilter` is the main refinement path for stretch sizing.
- `LowVolatilityRegimeFilter` reuses the same refinement field but interprets it as a volatility ceiling multiplier.
- `StretchFromLongTermSMAFilter` also consumes the same `min_avg_range` slot, despite the variable name being more generic than the actual meaning in this family.

---

## Section 4: Breakout Family Filters

### Family-level settings

- Strategy type: `BreakoutStrategyType`
- Available filters: 10
- `min_filters_per_combo = 3`
- `max_filters_per_combo = 5`
- `default_hold_bars = 4`
- `default_stop_distance_points = 1.25`

### Combination count

Breakout uses 10 filters and sweeps sizes 3 through 5:

- `C(10,3) = 120`
- `C(10,4) = 210`
- `C(10,5) = 252`

Total breakout sweep combinations: **582**

### Promotion gate thresholds

- `min_profit_factor = 0.70`
- `min_average_trade = 0.0`
- `require_positive_net_pnl = False`
- `min_trades = 60`
- `min_trades_per_year = 3.0`
- `max_promoted_candidates = 20`

### Trade filter thresholds for refinement

- `min_trades = 60`
- `min_trades_per_year = 3.0`

### Refinement grid

On 60m, breakout uses:
- `hold_bars = [2, 3, 4, 5, 6, 8, 10]`
- `stop_distance_points = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]`
- `min_avg_range = [0.60, 0.70, 0.80, 0.90, 1.00]` if `CompressionFilter` is in the combo, else `[0.0]`
- `momentum_lookback = [0]`

Max 60m breakout refinement size:
- `7 x 6 x 5 x 1 = 210`

Minimum 60m breakout refinement size when `CompressionFilter` is absent:
- `7 x 6 x 1 x 1 = 42`

### Timeframe scaling examples

#### Daily example

With multiplier `0.154`:
- fast SMA: `50 -> 10`
- slow SMA: `200 -> 31`
- breakout lookback: `20 -> 5`
- rising-base lookback: `5 -> 3`
- hold grid: `[1, 2, 3, 5]`

#### 60m example

Base values:
- breakout lookback: 20
- hold grid: `[2, 3, 4, 5, 6, 8, 10]`

#### 15m example

With multiplier `4.0`:
- fast SMA: `50 -> 200`
- slow SMA: `200 -> 800`
- breakout lookback: `20 -> 80`
- rising-base lookback: `5 -> 20`
- hold grid: `[8, 12, 16, 20, 24, 32, 40]`

### Per-filter details

#### `CompressionFilter`

- Purpose: looks for low-volatility compression before expansion.
- Logic: requires `i >= lookback * 2`, reads `atr_<lookback>`, computes trailing `true_range` mean over `lookback * 2`, then checks `current_atr <= long_term_atr * max_atr_mult`.
- Parameters: `lookback=20`, `max_atr_mult=0.75`
- Timeframe scaling: yes; `lookback` scales.
- Used in refinement: yes; `min_avg_range` is wired into `max_atr_mult`. If absent, it falls back to `0.90`.

#### `RangeBreakoutFilter`

- Purpose: pure price breakout above the recent range high.
- Logic: requires `i >= lookback`, computes `prior_high = max(high[i - lookback : i])`, then checks `close > prior_high`.
- Parameters: `lookback=20`
- Timeframe scaling: yes; `lookback` scales.
- Used in refinement: no.

#### `ExpansionBarFilter`

- Purpose: requires the breakout bar itself to be unusually large.
- Logic: requires `i >= lookback`, reads `true_range` for the current bar and `atr_<lookback>`, then checks `current_tr >= current_atr * expansion_multiplier`.
- Parameters: `lookback=20`, `expansion_multiplier=1.50`
- Timeframe scaling: yes; `lookback` scales.
- Used in refinement: no direct refinement field.

#### `BreakoutRetestFilter`

- Purpose: breakout confirmation above a recent high with optional ATR buffer.
- Logic: requires `i >= lookback`, computes prior high, reads `atr_<lookback>`, then checks `close > prior_high + current_atr * atr_buffer_mult`.
- Parameters: `lookback=20`, `atr_buffer_mult=0.0`
- Timeframe scaling: yes; `lookback` scales.
- Used in refinement: no.

#### `BreakoutTrendFilter`

- Purpose: keeps breakouts aligned with broader trend.
- Logic: requires enough bars for both SMAs, gets fast and slow SMA, then checks `fast_sma > slow_sma`.
- Parameters: `fast_length=50`, `slow_length=200`
- Timeframe scaling: yes; both SMA lengths scale.
- Used in refinement: no.

#### `BreakoutCloseStrengthFilter`

- Purpose: prefers strong closes near the bar high.
- Logic: computes `bar_range = high - low`, then checks `((close - low) / bar_range) >= close_position_threshold`.
- Parameters: `close_position_threshold=0.60`
- Timeframe scaling: no.
- Used in refinement: no.

#### `PriorRangePositionFilter`

- Purpose: ensures the previous close was already positioned strongly within its recent range.
- Logic: requires `i >= lookback` and `i >= 1`, computes prior window high/low, then checks the prior close's fractional position within that range against `min_position_in_range`.
- Parameters: `lookback=20`, `min_position_in_range=0.50`
- Timeframe scaling: yes; `lookback` scales.
- Used in refinement: no.

#### `BreakoutDistanceFilter`

- Purpose: avoids paper-thin breakouts.
- Logic: requires `i >= lookback`, computes prior high, reads `atr_<lookback>`, then checks `(close - prior_high) >= current_atr * min_breakout_atr`.
- Parameters: `lookback=20`, `min_breakout_atr=0.10`
- Timeframe scaling: yes; `lookback` scales.
- Used in refinement: no.

#### `RisingBaseFilter`

- Purpose: detects a constructive base with rising lows.
- Logic: requires `i >= lookback + 1`, splits recent lows into two halves, then checks `second_half.min() >= first_half.min()`.
- Parameters: `lookback=5`
- Timeframe scaling: yes; `lookback` scales.
- Used in refinement: no.

#### `TightRangeFilter`

- Purpose: flags a narrow bar setup before expansion.
- Logic: requires `i >= lookback`, reads `avg_range_<lookback>` if available else computes average bar range, then checks `current_range <= avg_range * max_bar_range_mult`.
- Parameters: `lookback=20`, `max_bar_range_mult=0.85`
- Timeframe scaling: yes; `lookback` scales.
- Used in refinement: no.

Breakout-only note:
- `RangeBreakoutFilter` is unique to breakout and does not appear in trend or MR.

---

## Section 5: Cross-Family Filter Comparison Table

| Filter | Trend | MR | Breakout | Scales with TF? |
|--------|-------|----|----------|-----------------|
| `TrendDirectionFilter` | yes |  |  | SMA lengths |
| `PullbackFilter` | yes |  |  | SMA length |
| `RecoveryTriggerFilter` | yes |  |  | SMA length |
| `VolatilityFilter` | yes |  |  | lookback |
| `MomentumFilter` | yes |  |  | lookback |
| `UpCloseFilter` | yes |  |  | no |
| `TwoBarUpFilter` | yes |  |  | no |
| `TrendSlopeFilter` | yes |  |  | fast SMA + slope bars |
| `CloseAboveFastSMAFilter` | yes |  |  | SMA length |
| `HigherLowFilter` | yes |  |  | no |
| `BelowFastSMAFilter` |  | yes |  | SMA length |
| `DistanceBelowSMAFilter` |  | yes |  | SMA length |
| `DownCloseFilter` |  | yes |  | no |
| `TwoBarDownFilter` |  | yes |  | no |
| `ThreeBarDownFilter` |  | yes |  | no |
| `ReversalUpBarFilter` |  | yes |  | no |
| `LowVolatilityRegimeFilter` |  | yes |  | lookback |
| `AboveLongTermSMAFilter` |  | yes |  | SMA length |
| `CloseNearLowFilter` |  | yes |  | no |
| `StretchFromLongTermSMAFilter` |  | yes |  | SMA length |
| `CompressionFilter` |  |  | yes | lookback |
| `RangeBreakoutFilter` |  |  | yes | lookback |
| `ExpansionBarFilter` |  |  | yes | lookback |
| `BreakoutRetestFilter` |  |  | yes | lookback |
| `BreakoutTrendFilter` |  |  | yes | SMA lengths |
| `BreakoutCloseStrengthFilter` |  |  | yes | no |
| `PriorRangePositionFilter` |  |  | yes | lookback |
| `BreakoutDistanceFilter` |  |  | yes | lookback |
| `RisingBaseFilter` |  |  | yes | lookback |
| `TightRangeFilter` |  |  | yes | lookback |

---

## Section 6: Feature Dependencies

Important implementation nuance:
- Many filters use precomputed feature columns if they exist.
- If a column is missing, several filters fall back to on-the-fly calculations from raw OHLC data.
- `feature_builder.py` still defines the feature vocabulary that the engine precomputes up front.

### Filters that need `sma_X`

- Trend:
  - `TrendDirectionFilter`
  - `PullbackFilter`
  - `RecoveryTriggerFilter`
  - `TrendSlopeFilter`
  - `CloseAboveFastSMAFilter`
- MR:
  - `BelowFastSMAFilter`
  - `DistanceBelowSMAFilter`
  - `AboveLongTermSMAFilter`
  - `StretchFromLongTermSMAFilter`
- Breakout:
  - `BreakoutTrendFilter`

Family lookbacks requested from strategy types:
- Trend: scaled `[50, 200]`
- MR: scaled `[20, 200]`
- Breakout: scaled `[50, 200]`

### Filters that need `atr_X`

- `VolatilityFilter`
- `DistanceBelowSMAFilter` uses `atr_20` directly in the filter code
- `LowVolatilityRegimeFilter`
- `StretchFromLongTermSMAFilter` uses `atr_20` directly
- `CompressionFilter`
- `ExpansionBarFilter`
- `BreakoutRetestFilter`
- `BreakoutDistanceFilter`

Family ATR / avg-range lookbacks requested:
- Trend: scaled `[20]`
- MR: scaled `[20]`
- Breakout: scaled `[20]`

### Filters that need `avg_range_X`

- `TightRangeFilter`

### Filters that need `mom_diff_X`

Currently: **none of the live filters read `mom_diff_X` columns directly**.

`feature_builder.py` precomputes them and trend requests momentum lookbacks, but the current
`MomentumFilter` compares raw `close` values instead of using `mom_diff_X`.

### Filters that need `bar_range`

- `TightRangeFilter`

### Filters that need `prev_close`

- `PullbackFilter`

### Filters that need `true_range`

- `VolatilityFilter`
- `LowVolatilityRegimeFilter`
- `CompressionFilter`
- `ExpansionBarFilter`

### Filters using raw OHLC directly

- `UpCloseFilter`
- `TwoBarUpFilter`
- `HigherLowFilter`
- `DownCloseFilter`
- `TwoBarDownFilter`
- `ThreeBarDownFilter`
- `ReversalUpBarFilter`
- `CloseNearLowFilter`
- `RangeBreakoutFilter`
- `BreakoutCloseStrengthFilter`
- `PriorRangePositionFilter`
- `RisingBaseFilter`

---

## Section 7: Combinatorial Search Space Summary

### Trend

- Filters available: 10
- Combo sizes: 4..6
- Sweep combinations: `C(10,4) + C(10,5) + C(10,6) = 672`
- Max refinement grid per candidate: `8 x 6 x 7 x 5 = 1,680`
- Max promoted candidates: 20
- Theoretical max refinement runs: `20 x 1,680 = 33,600`
- Theoretical max total runs: `672 + 33,600 = 34,272`

### Mean Reversion

- Filters available: 10
- Combo sizes: 3..6
- Sweep combinations: `C(10,3) + C(10,4) + C(10,5) + C(10,6) = 792`
- Max refinement grid per candidate: `8 x 6 x 6 x 1 = 288`
- Min refinement grid per candidate when no conditional filter is present: `8 x 6 x 1 x 1 = 48`
- Max promoted candidates: 20
- Theoretical max refinement runs: `20 x 288 = 5,760`
- Theoretical max total runs: `792 + 5,760 = 6,552`

### Breakout

- Filters available: 10
- Combo sizes: 3..5
- Sweep combinations: `C(10,3) + C(10,4) + C(10,5) = 582`
- Max refinement grid per candidate: `7 x 6 x 5 x 1 = 210`
- Min refinement grid per candidate when `CompressionFilter` is absent: `7 x 6 x 1 x 1 = 42`
- Max promoted candidates: 20
- Theoretical max refinement runs: `20 x 210 = 4,200`
- Theoretical max total runs: `582 + 4,200 = 4,782`

### Combined theoretical max

Across all three families, ignoring dataset multiplication:
- sweep runs: `672 + 792 + 582 = 2,046`
- max refinement runs: `33,600 + 5,760 + 4,200 = 43,560`
- max total runs: **45,606**

That makes two things very clear:
- Trend is the most expensive family under the current refinement design.
- Vectorization and/or smarter refinement will matter a lot before the filter library expands.

---

## Section 8: Known Gaps and Future Filter Ideas

### No volume-based filters

- Missing ideas: `VolumeSpike`, `VolumeDryUp`, `VolumeConfirmation`
- Data required: existing OHLCV is enough because `volume` is already present
- Estimated complexity: simple to moderate
- Best fit:
  - breakout: highest value
  - trend: secondary value
  - MR: occasional value for exhaustion/context

### No time/session filters

- Missing ideas: RTH-only, session window filters, `DayOfWeek`
- Data required: existing timestamp data should be enough if session parsing is normalized cleanly
- Estimated complexity: moderate
- Best fit:
  - MR: very useful
  - breakout: useful
  - trend: lower priority

### No market-structure filters

- Missing ideas: `InsideBar`, `OutsideBar`, `Gap`
- Data required: existing OHLC is enough
- Estimated complexity: simple
- Best fit:
  - breakout: very useful
  - trend: useful
  - MR: some value, especially gap and outside-bar reversal ideas

### No explicit regime filters like ADX or ATR percentile

- Missing ideas: `ADX`, `ATRPercentile`
- Data required: OHLC is enough
- Estimated complexity: moderate
- Best fit:
  - trend: very useful
  - breakout: very useful
  - MR: useful for avoiding bad volatility states

### No short-side filter mirrors

- Missing capability: the entire library is effectively long-side only
- Data required: existing OHLCV is enough
- Estimated complexity: moderate
- Best fit:
  - all families

### Exit logic is not filter-based

- Current state: exits are time-stop plus fixed ATR stop
- Missing ideas: trailing stop, signal exit, profit target
- Data required: existing OHLC is enough
- Estimated complexity: moderate
- Best fit:
  - trend: trailing stop is highest priority
  - breakout: trailing stop also high value
  - MR: profit target and signal exit most useful

### Bottom line

The current filter library is coherent and fully usable, but it is still an OHLC-first,
long-only entry vocabulary. The biggest gaps are:
- no volume context
- no time/session context
- no explicit regime tagging
- no short-side mirrors
- no exit architecture that matches the entry logic

That lines up closely with the current improvement roadmap.
