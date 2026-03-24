# Exit Validation Analysis

Date: 2026-03-24

## Scope

This session validated the Session 28 exit architecture on focused ES local runs.

Tracked validation config:
- `config_exit_validation_es.yaml`
- Target datasets: `ES_60m`, `ES_30m`
- Families: `trend`, `mean_reversion`, `breakout`

Local execution note:
- The full validation config was too slow on this Windows laptop because `ProcessPoolExecutor` falls back to sequential execution.
- To complete the session locally, a reduced local validation harness was used:
  - recent ES 60m / 30m samples
  - representative family filter sets
  - trimmed refinement grids
  - full Session 28 exit dimensions preserved (`time_stop`, `trailing_stop`, `profit_target`, `signal_exit`)

Outputs used for analysis:
- `Outputs_exit_validation_local/exit_validation_summary.csv`
- Per-dataset refinement CSVs under `Outputs_exit_validation_local/ES_60m/` and `Outputs_exit_validation_local/ES_30m/`

## Exit Comparison By Family

### Trend

Tested exits:
- `time_stop`
- `trailing_stop`

Result:
- `time_stop` won on both local datasets.
- `ES_60m`: best `time_stop` PF `1.84` vs best `trailing_stop` PF `1.82`
- `ES_30m`: best `time_stop` PF `0.77` vs best `trailing_stop` PF `0.70`

Interpretation:
- Trailing stop did not materially improve trend in this local validation.
- On 60m it came close, which suggests the architecture works, but not strongly enough to justify changing the default.

### Breakout

Tested exits:
- `time_stop`
- `trailing_stop`

Result:
- Mixed, but with the clearest positive signal of the session.
- `ES_30m`: `trailing_stop` won materially.
  - best `trailing_stop` PF `1.23`, net PnL `829.50`
  - best `time_stop` PF `0.85`, net PnL `-820.50`
- `ES_60m`: `time_stop` remained better.
  - best `time_stop` PF `1.15`, net PnL `1892.38`
  - best `trailing_stop` PF `0.71`, net PnL `-1269.37`

Interpretation:
- Breakout appears to benefit from trailing exits on 30m.
- That is a real validation win for the new exit architecture.
- Breakout defaults should still stay unchanged for now because the improvement was not universal across both local datasets.

### Mean Reversion

Tested exits:
- `time_stop`
- `profit_target`
- `signal_exit`

Result:
- Local validation was inconclusive.
- `ES_60m`: all tested MR variants produced `NO_TRADES`.
- `ES_30m`: MR produced only single-trade outcomes in the reduced local run.
  - `signal_exit` tied `time_stop` on the best row
  - `profit_target` was weaker than both

Interpretation:
- The architecture supports MR exits correctly.
- This local run did not provide enough trade count to claim that `profit_target` or `signal_exit` materially improves MR quality.
- MR needs a broader validation run before any default exit recommendation changes.

## Best Examples

### Best clear improvement

- Dataset: `ES_30m`
- Family: `breakout`
- Exit type: `trailing_stop`
- Best strategy: `RefinedBreakout_HB6_ATR1.5_COMP0.8_MOM0`
- Improvement:
  - PF improved from `0.85` (`time_stop`) to `1.23`
  - Net PnL improved from `-820.50` to `829.50`
- Why it matters:
  - This is the strongest direct evidence that the new exit architecture can uncover a better exit style than the legacy time stop.

### Near miss, but not enough to flip default

- Dataset: `ES_60m`
- Family: `trend`
- Exit type: `time_stop` remained best
- Best `time_stop`: PF `1.84`
- Best `trailing_stop`: PF `1.82`
- Why it matters:
  - Trailing stop was competitive, so trend exit tuning is still worth revisiting later.
  - But the local evidence is not strong enough to say trailing stop materially improved trend yet.

### Underpowered MR result

- Dataset: `ES_30m`
- Family: `mean_reversion`
- Exit type: `signal_exit` matched the best `time_stop` row
- Trade count: `1`
- Why it matters:
  - This is not robust evidence.
  - MR exit validation should be considered unresolved rather than failed.

## Implications

- Exit architecture is partially validated.
- The engine can now compare exit styles and surface different winners by family/timeframe.
- The strongest local positive result was breakout on 30m with `trailing_stop`.
- Trend did not show enough improvement to justify changing defaults.
- Mean reversion remains unresolved because the reduced local run was too thin.

Default-exit conclusion for now:
- Trend: keep `time_stop`
- Breakout: keep `time_stop` for default, but consider `trailing_stop` a strong candidate for broader validation
- Mean Reversion: keep `time_stop` until a larger validation run proves `profit_target` or `signal_exit`

## Recommendation

Recommendation: proceed to Session 30, but do not change family defaults yet.

Why:
- Session 28 architecture is working and analyzable.
- Session 29 found at least one meaningful exit win (`breakout` on `ES_30m` with `trailing_stop`).
- The remaining weak spots are about validation breadth, not architecture correctness.

Follow-up after Session 30:
- Re-run exit validation on a larger cloud sample or full-history focused run
- Re-test mean reversion exits on a dataset/window that produces enough trades
- Revisit whether trend trailing stops deserve a family-default change after broader evidence
