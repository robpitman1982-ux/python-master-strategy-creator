# Sessions 38–41: Road Forward
## Updated Roadmap | March 2026

---

## Guiding Principles for This Phase

1. **Collect strategies aggressively** — the ultimate leaderboard has no cap. Every run
   adds unique accepted strategies. More is better at this stage. Do NOT filter or
   constrain the search in ways that reduce the candidate pool.

2. **Correlation and portfolio selection come later** — once the ultimate leaderboard
   has 30-100+ strategies across ES, CL, NQ, we will do a dedicated portfolio session
   where we review the full leaderboard, check correlations, and select 3-6 for Bootcamp.

3. **Important note for portfolio selection time**: The ultimate leaderboard dedup keeps
   the highest PF version of each unique strategy signature. If an older run had a
   higher PF through luck and a newer run's lower PF is more realistic, we'd be keeping
   the wrong one. At portfolio selection time, cross-check the `run_id` column and verify
   recent runs confirm the older PF numbers before relying on them.

4. **Session order reflects actual dependencies** — dashboard must work before we can
   see results clearly; shorts must work before we know the full strategy universe;
   engine improvements before we scale to new instruments.

---

## What Is Happening RIGHT NOW (Before Session 38)

**Session 37 (in progress via Claude Code):**
- Fix and modernise the Streamlit dashboard
- Add short-side strategies (MR shorts on overbought, trend shorts, breakout shorts)
- Add strategy subtypes (3 per family = 9 named subtypes)
- Enrich leaderboard with calmar_ratio, is_oos_pf_ratio, win_rate, max_drawdown
- Add ultimate_leaderboard_bootcamp.csv

---

## SESSION 38: Portfolio Reconstruction Completeness Fix
**Theme:** Make the portfolio evaluator see all accepted strategies, not just 2 of 9

### Why first
Right now only 2 of 9 accepted strategies (daily MR + daily breakout) make it into
the portfolio evaluator. The other 7 have never had MC drawdowns, stress tests, or
correlations computed. This is a bug in how the master engine calls the portfolio
evaluator — it runs per-dataset but the cross-dataset aggregation step doesn't feed
all accepted strategies correctly.

This is a prerequisite for Session 41 (portfolio selection) to be meaningful at all.
Fix it now so every future run automatically evaluates all strategies.

### Deliverables
- `modules/portfolio_evaluator.py` — fix reconstruction to handle all accepted rows
  from all datasets, not just the dataset it was called with
- `modules/cross_dataset_evaluator.py` — new module that runs after all per-dataset
  evaluations complete, produces a unified cross-timeframe view:
  - `Outputs/cross_timeframe_portfolio_review.csv` — all accepted strategies with
    MC max DD, stress tests
  - `Outputs/cross_timeframe_correlation_matrix.csv` — full N×N matrix
- `master_strategy_engine.py` — call `cross_dataset_evaluator` at end of full run
- Dashboard updated to display the full cross-timeframe correlation heatmap

### Technical approach
Normalise all strategy trade series to daily PnL (sum intraday trades per calendar day)
before computing correlations. This solves the alignment problem between timeframes —
a 30m strategy and a daily strategy both collapse to a daily PnL series.

Graceful skip if a strategy fails reconstruction (log warning, continue) — never crash
the full evaluation because one strategy has a missing filter column.

### Acceptance criteria
- All accepted strategies appear in `cross_timeframe_portfolio_review.csv`
- Cross-timeframe correlation matrix has shape N×N where N = all accepted strategies
- 30m MR vs 60m MR correlation is now known (currently missing — critical unknown)
- Dashboard shows the full heatmap
- All tests pass + 2 new tests

### Complexity: Medium
### Risks
- Some strategies may fail reconstruction due to filter name mismatches — need
  graceful skip with clear logging

---

## SESSION 39: Trade Density Expansion via Threshold Softening
**Theme:** Extract more trades from ROBUST edges via filter threshold parameter sweep

### Why second
60m MR ROBUST has 3.4 trades/year. It genuinely can't be deployed at that frequency.
But the filter combo is verified ROBUST (IS PF 1.67, OOS PF 1.80). The question is
whether a slightly looser distance/volatility threshold fires more often at modest
PF cost — this is answerable systematically within the existing refinement framework.

Note: this is about finding more trade opportunities within proven edges, NOT about
collecting fewer strategies. The looser-threshold variants that pass quality gates
become additional entries in the ultimate leaderboard.

### Deliverables
- `modules/filters.py` — add `threshold_multiplier` kwarg to 3 key MR filters:
  `DistanceBelowSMAFilter`, `LowVolatilityRegimeFilter`, `StretchFromLongTermSMAFilter`
  Both `passes()` and `mask()` respect it. Default = 1.0 (no change to existing behaviour)
- `modules/strategy_types/mean_reversion_strategy_type.py` — add `threshold_multiplier`
  to refinement grid: `[0.6, 0.8, 1.0]` (only in Stage 2, NOT in Stage 1 sweep)
- New refinement result column: `threshold_multiplier`
- New leaderboard column: `leader_threshold_multiplier`
- Bootcamp score: add `trade_density_bonus = min(5.0, trades_per_year / 4.0)` (5pt max)

### Technical approach
```python
# In DistanceBelowSMAFilter.mask():
threshold = self.min_distance_atr * self.threshold_multiplier
return data[f'dist_below_sma_{self.lookback}'] >= threshold
```
The threshold_multiplier is passed as a refinement task parameter alongside hold_bars,
stop_distance etc. No change to Stage 1 sweep — only Stage 2 refinement.

Cap: minimum multiplier 0.6 (never loosen by more than 40% from default).

### Acceptance criteria
- At least one MR strategy increases from <5 to >12 trades/year while OOS PF > 1.3
- `threshold_multiplier` column visible in all refinement CSVs and leaderboard
- Stage 1 sweep runtime unchanged (threshold not swept there)
- All tests pass + 2 new tests

### Complexity: Medium
### Risks
- Loosening thresholds in OOS period may not hold. The IS/OOS quality flag catches this.
  Cap at 0.6× minimum to avoid destroying the setup's core logic.

---

## SESSION 40: Regime Veto Layer
**Theme:** Block entries in structurally hostile market conditions using pre-computed regime states

### Why third
4 of 9 current strategies are REGIME_DEPENDENT. The breakout family lost money almost
every year 2010–2018 — not because the filters are wrong, but because it was entering
during persistent low-ADX chop where breakouts don't follow through. A macro-level
regime veto, computed once per bar before any backtesting, addresses this at the root.

This improves quality flags on existing strategies AND generates new regime-aware
strategy variants that go into the ultimate leaderboard as additional rows.

### Deliverables
- `modules/regime_calculator.py` — new module, fully vectorised:
  - `compute_regime_states(data, timeframe)` → adds boolean columns:
    - `is_chop`: ADX(14) < 20 for 5+ consecutive bars
    - `is_trending`: ADX(14) > 25
    - `is_high_vol`: ATR > 1.5× 200-bar ATR
    - `is_low_vol`: ATR < 0.7× 200-bar ATR
  - ADX lookback scales with timeframe multiplier
- `modules/feature_builder.py` — call `compute_regime_states()` in
  `add_precomputed_features()` so regime columns are always available
- `modules/strategy_types/base_strategy_type.py` — add `hostile_regimes: list[str]`
  class attribute (default empty = no veto)
- Strategy type files — assign hostile regimes:
  - Breakout subtypes: `hostile_regimes = ['is_chop']`
  - Trend subtypes: `hostile_regimes = ['is_chop']`
  - MR subtypes: `hostile_regimes = ['is_trending', 'is_high_vol']`
- `modules/vectorized_signals.py` — apply veto in `compute_combined_signal_mask()`:
  ```python
  for regime_col in strategy_type.hostile_regimes:
      if regime_col in data.columns:
          signal_mask &= ~data[regime_col].values
  ```
  This is one numpy bitwise AND per regime column — zero meaningful cost.
- New column in sweep/refinement results: `regime_filtered_pct`

### Acceptance criteria
- Breakout family average max_drawdown reduces by >20% across timeframes on next run
- At least 1 currently REGIME_DEPENDENT strategy improves its quality flag
- `regime_filtered_pct` appears in all result CSVs
- ADX vectorisation confirmed fast: < 0.5s on 215K bars (30m dataset)
- All tests pass + 3 new tests in `test_regime_calculator.py`

### Complexity: Medium
### Risks
- ADX lookback scaling needs careful validation across timeframes
- Over-vetoing: if `regime_filtered_pct` > 40% for any family, review thresholds

---

## SESSION 41: Instrument Expansion — CL and NQ
**Theme:** Run the full sweep engine on crude oil and Nasdaq to grow the strategy pool

### Why fourth
The engine is now mature enough (shorts + subtypes + regime filtering) to expand.
CL and NQ have different volatility regimes and correlation properties vs ES — they
are the fastest path to a genuinely uncorrelated strategy pool for Bootcamp.

This is pure discovery. Every accepted CL/NQ strategy goes straight into the ultimate
leaderboard. No portfolio selection yet — just collection.

### Deliverables
- Export CL (crude oil) and NQ (Nasdaq) data from TradeStation
  - Same format as ES: daily, 60m, 30m, 15m — from 2008 to present
  - See `docs/TRADESTATION_EXPORT_GUIDE.md` for exact steps
- `cloud/config_cl_all_5tf_ondemand_c.yaml` — CL config (same structure as ES)
- `cloud/config_nq_all_5tf_ondemand_c.yaml` — NQ config
- Upload data files to strategy-console
- Run CL sweep, download results, run NQ sweep, download results
- Verify both runs regenerate `ultimate_leaderboard.csv` with new strategies added

### Technical approach
The engine already supports multi-instrument via the `market` field in config datasets.
The only changes needed:
- Set `dollars_per_point` and `tick_value` correctly per instrument:
  - CL: `dollars_per_point: 1000.0`, `tick_value: 10.0` (per 0.01 move)
  - NQ: `dollars_per_point: 20.0`, `tick_value: 5.0` (per 0.25 move)
- Confirm `commission_per_contract` is appropriate per instrument
- IS/OOS split date stays 2019-01-01

### Acceptance criteria
- CL sweep completes, at least 1 accepted strategy in master_leaderboard.csv
- NQ sweep completes, at least 1 accepted strategy in master_leaderboard.csv
- Ultimate leaderboard grows beyond current 9 ES strategies
- Both runs complete in < 60 minutes each
- All existing ES tests still pass (no regressions from instrument changes)

### Complexity: Low-Medium (mostly data preparation, engine already supports it)
### Risks
- CL data export from TradeStation needs to be tested — format must match ES
- Contract specs (tick value, dollar per point) must be double-checked before any
  PnL comparisons. Wrong values give misleading net PnL numbers.
- 5m data for CL/NQ may be large — store on strategy-console only, not in git

---

## Summary Table

| Session | Theme | Key Output | Complexity |
|---------|-------|-----------|------------|
| 37 | Dashboard + shorts + subtypes | Working dashboard, short strategies, 9 subtypes | (in progress) |
| 38 | Portfolio reconstruction fix | Full N×N correlation matrix, MC on all strategies | Medium |
| 39 | Trade density via thresholds | More trades from ROBUST edges, threshold_multiplier | Medium |
| 40 | Regime veto layer | Cleaner drawdowns, regime-aware strategies | Medium |
| 41 | CL + NQ expansion | Grow ultimate leaderboard with new instruments | Low-Medium |

---

## AFTER SESSION 41: Portfolio Selection Session

Once the ultimate leaderboard has CL, NQ, and ES strategies with regime filtering and
shorts included, bring the full ultimate_leaderboard.csv here (Claude.ai) for a
dedicated portfolio selection discussion covering:

- Full correlation matrix review
- Selecting 3-6 uncorrelated strategies for The5ers Bootcamp attempt
- Position sizing per strategy ($25K account, 1 MES/MCL/MNQ per strategy)
- Monte Carlo Bootcamp pass rate simulation
- EasyLanguage conversion checklist for TradeStation live trading

**Dedup note for that session**: The ultimate leaderboard keeps the highest PF version
of each unique strategy signature. Before trusting any number, cross-check the `run_id`
column and verify recent runs confirm the older PF values — don't pick a strategy
purely because an old lucky run showed inflated PF.

---

## Ideas Parked for Even Later

**Apriori sweep pruning** (Gemini's Session 3): Excellent for when we have 4+ instruments
and the combinatorial space starts to matter again. Blacklist threshold: pairs producing
< 30 total trades across 18 years (not < 5 as Gemini suggested — too aggressive).

**Portfolio selector module** (ChatGPT's Session 2): Automate the greedy selection
algorithm once we have enough strategies. Not needed until we have 30+ candidates.

**Walk-forward validation**: Multiple IS/OOS windows instead of a single 2019 split.
High value but expensive compute. Add after instrument expansion proves the engine scales.
