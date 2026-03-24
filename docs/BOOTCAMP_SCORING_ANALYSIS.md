# Bootcamp Scoring Analysis

## 1. Purpose

Session 30 adds a second ranking layer to the strategy engine so research outputs can be viewed through two lenses:

- Classic research ranking: strongest raw research metrics
- Bootcamp ranking: stronger survivability and robustness bias for prop-style evaluation

The goal is not to replace the classic leaderboard. The goal is to surface a more practical ranking for strategies that need:

- acceptable PF
- stronger OOS behavior
- lower drawdown relative to profit
- enough activity to matter
- better stability flags and yearly consistency

## 2. Scoring design

The Bootcamp scorer lives in `modules/bootcamp_scoring.py` and is intentionally simple and deterministic.

Bootcamp score components:

- profitability score
  - rewards PF above 1.0
- OOS score
  - weights `oos_pf` most heavily, with smaller support from `recent_12m_pf` and `is_pf`
- drawdown score
  - rewards lower drawdown relative to net profit
- trade count score
  - rewards both total trades and trades per year
- consistency score
  - uses profitable-year share, losing-year streaks, quality score, and consistency flag
- quality penalty
  - penalizes weak quality flags such as `BROKEN_IN_OOS`, `EDGE_DECAYED_OOS`, `LOW_IS_SAMPLE`, and `NO_TRADES`

Supporting Bootcamp output fields now include:

- `bootcamp_score`
- `bootcamp_profitability_score`
- `bootcamp_drawdown_score`
- `bootcamp_oos_score`
- `bootcamp_consistency_score`
- `bootcamp_trade_count_score`
- `bootcamp_quality_penalty`
- `bootcamp_drawdown_to_profit_ratio`

## 3. Local verification

Local verification was performed with:

```bash
python master_strategy_engine.py --config config_local_quick_test.yaml
python -m modules.bootcamp_report --outputs-dir Outputs_quick_local
```

What was verified successfully:

- classic family leaderboard still generated
- Bootcamp family leaderboard generated alongside it
- leaderboard rows now carry `bootcamp_score` and supporting Bootcamp fields
- `modules.bootcamp_report` printed a Bootcamp-ranked summary without crashing

Observed local result:

- dataset: `ES_60m_quick_smoke`
- family: `mean_reversion`
- leader: `ComboMR_ReversalUpBar_LowVolatilityRegime_CloseNearLow_StretchFromLongTermSMA`
- classic PF: `3.60`
- OOS PF: `0.00`
- Bootcamp score: `53.83`
- quality flag: `BROKEN_IN_OOS`

Interpretation:

- the Bootcamp score did exactly what it should do here
- the strategy still received credit for PF and low drawdown relative to profit
- it was materially penalized for weak OOS behavior and low overall robustness
- this is the intended difference between Bootcamp ranking and raw research ranking

## 4. VM run results

Full VM config created for the overnight validation:

- `cloud/config_bootcamp_vm_run.yaml`

Datasets:

- `ES_daily`
- `ES_60m`
- `ES_30m`

Families:

- `trend`
- `mean_reversion`
- `breakout`

Live run launched:

- run id: `strategy-sweep-20260324T071642Z`
- machine: `n2-highcpu-96`
- provisioning: `SPOT`
- zone: `us-central1-a`

Confirmed VM state during this session:

- instance status: `RUNNING`
- remote run status: `running`
- remote stage: `engine_start`

Important note:

- the full VM engine run was launched successfully during Session 30
- because it is an overnight-scale run, final artifact retrieval and result analysis were still pending at the time this doc was written
- Session 30 also added Windows-safe recovery hardening so `run_cloud_sweep.py` / result recovery is less likely to fail after the expensive remote work completes

## 5. Ranking differences between classic and Bootcamp

Expected ranking differences after the full VM run completes:

- high-PF but low-trade or weak-OOS systems should fall in the Bootcamp view
- moderate-profit but stable OOS / lower-drawdown systems should rise
- strategies with poor quality flags should rank meaningfully lower than they do in the classic research sort

This is especially important for:

- `trend`
  - where we want stable OOS behavior to matter more than headline net PnL
- `breakout`
  - where recent trailing-stop improvements now need a more survival-focused ranking lens
- `mean_reversion`
  - where strong raw PF can still hide fragility if OOS and consistency are weak

## 6. Recommendations

Current recommendation:

- proceed with Bootcamp scoring as the default secondary ranking layer
- keep the classic leaderboard intact for research
- use the completed overnight VM run to judge whether Bootcamp ranking materially changes which strategies deserve attention

Follow-up once the VM run finishes:

1. recover artifacts if needed with `python run_cloud_sweep.py --recover-run strategy-sweep-20260324T071642Z`
2. compare `master_leaderboard.csv` vs `master_leaderboard_bootcamp.csv`
3. inspect the top Bootcamp-ranked strategies with `python -m modules.bootcamp_report --outputs-dir <OutputsDir>`
4. decide in Session 31 whether any family-selection habits should change even if family defaults stay unchanged
