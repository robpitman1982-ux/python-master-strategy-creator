# SPRINT_84 - Canonical per-trade artifact emission

> **Pre-registration is mandatory.** Commit this file BEFORE any code is touched.
> Once committed, the parameter grid + verdict criteria are FROZEN for this sprint.

**Sprint number:** 84
**Date opened:** 2026-05-03
**Date closed:** ___ (filled in at sprint-end)
**Operator:** Rob
**Author:** Claude Code on Latitude
**Branch:** `feat/canonical-trade-emission`

---

## 1. Sprint goal

Make `strategy_trades.csv` (per-trade rows) and `strategy_returns.csv` (daily resampled) **mandatory artifacts of every accepted strategy on every sweep run**, regardless of `skip_portfolio_evaluation` setting. Add a parity check between rebuilt trades and family leaderboard summary stats so divergence is detected and surfaced rather than silently ignored.

This is Sprint A from the cross-LLM consultation roadmap (post ChatGPT-5 + Gemini 2.5 Pro round). Both LLMs converged on this being the binding bottleneck.

## 2. Mechanism plausibility

**Strong prior.** Empirical evidence from `ultimate_leaderboard_cfd_post_gate_audit.csv` (2026-05-03):
- 494 rows total
- `gate_loaded_trade_count == 0` for every single row
- `gate_concentration_pass = True` for all 494 (vacuous - no trade data was loaded)
- Post-gate pass rate 96.4% (gate is doing almost no work)

Root cause: every cluster sweep config sets `skip_portfolio_evaluation: true`, which is why `strategy_returns.csv` and `strategy_trades.csv` are not produced inline. The post-hoc `generate_returns.py` rebuild was meant to fill the gap but is fragile and often skipped (Session 49 fixed a critical rebuild bug; the pattern recurs).

**Mechanism by which the fix produces the result:** add a lightweight post-leaderboard rebuild step that runs unconditionally on accepted strategies, writes both artifacts, and validates parity against `leader_net_pnl`. Post-ultimate gate then reads real trade data and the concentration check stops being vacuous.

**Mechanism by which it could fail:** rebuild divergence (Session 49 class). If `_rebuild_strategy_from_leaderboard_row()` doesn't faithfully reconstruct the original strategy from leaderboard metadata, the rebuilt trades won't match the accepted strategy. Mitigation: the new parity check (rebuilt sum within 1% of `leader_net_pnl`) catches and surfaces divergence rather than silently propagating ghost data.

## 3. Frozen parameter grid

| Parameter | Value | Source |
|-----------|-------|--------|
| Trade emission triggers on | `accepted_final == True` rows in `family_leaderboard_results.csv` | new |
| Emission output filenames | `strategy_trades.csv`, `strategy_returns.csv` (next to family leaderboard) | matches existing schema |
| `strategy_trades.csv` schema | `exit_time, strategy, net_pnl, entry_time, direction, entry_price, exit_price, bars_held` | matches `generate_returns.py` output |
| `strategy_returns.csv` schema | date-indexed, columns are `{strategy_type}_{leader_strategy_name}` keys | matches existing |
| Parity tolerance | rebuilt `net_pnl.sum()` within 1% of `leader_net_pnl`, or absolute < $100 if leader_net_pnl is small | new |
| Parity status column | `trade_artifact_status` added to family_leaderboard_results.csv: `OK / PARITY_FAILED / REBUILD_FAILED / SKIPPED` | new |
| `skip_portfolio_evaluation: true` behaviour | Trade emission still runs (lightweight, no MC, no stress) | changed |
| `skip_portfolio_evaluation: false` behaviour | `evaluate_portfolio` runs full review AND emits both artifacts (existing path enriched) | changed |
| Post-ultimate gate behaviour for missing trades | Fail-closed: `gate_concentration_pass = False`, `post_gate_pass = False`, `gate_status = MISSING_TRADE_ARTIFACTS` | changed |
| Post-ultimate gate behaviour for parity-failed trades | Fail-closed: `gate_concentration_pass = False`, `post_gate_pass = False`, `gate_status = PARITY_FAILED` | changed |

## 4. Verdict definitions

| Verdict | Condition |
|---------|-----------|
| **CANDIDATES** | Trade emission runs successfully on a smoke-test sweep; >= 90% of accepted strategies pass parity; post-ultimate gate now emits non-vacuous concentration column. Promote to Sprint 85 (cost overlay integration into MC). |
| **NO EDGE** | n/a - this is plumbing, not a strategy hypothesis. |
| **SUSPICIOUS** | < 90% parity pass rate. Investigate rebuild divergence. Halt promotion. |
| **BLOCKED** | Cannot complete (test failure, rebuild infra error). Document and re-plan. |

## 5. Methodology checklist

- [ ] All test suites green pre-launch (`python -m pytest tests/ --ignore=tests/test_engine_parity.py -q`)
- [ ] Sprint pre-registration committed BEFORE code changes
- [ ] Branch `feat/canonical-trade-emission` cut from `main`
- [ ] Smoke test: run `master_strategy_engine.py` on ES 60m with `skip_portfolio_evaluation: true` and verify `strategy_trades.csv` exists
- [ ] Smoke test: run with `skip_portfolio_evaluation: false` and verify same artifact present
- [ ] Parity test: known-good ES 60m strategy from existing leaderboard, rebuilt sum within 1% of `leader_net_pnl`
- [ ] Post-ultimate gate test: missing `strategy_trades.csv` produces `gate_status = MISSING_TRADE_ARTIFACTS` and `post_gate_pass = False`
- [ ] No regression in 287 non-parity tests

## 6. Anti-convergence consultation (held pre-sprint)

| LLM | Recommendation | Convergence? |
|-----|---------------|--------------|
| ChatGPT-5 | Phase 1 = call `generate_returns.py` from `finalize_cluster_run`; Phase 2 = consider direct engine emission | both LLMs agree this is the binding bottleneck |
| Gemini 2.5 Pro | Direct emission from vectorized engine, fail-closed on missing | y on bottleneck, n on implementation strategy |
| Claude (synthesis) | Hybrid: lightweight rebuild always-on (low risk, ships today), parity check catches divergence, fail-closed at post-ultimate gate. Defer direct engine emission to Sprint 85+ if parity issues emerge. | both convergent on bottleneck identification; divergent on path; this sprint takes the lower-risk middle path |

The convergence on "trade artifacts are the binding bottleneck" is by your 8x calibration potentially anti-alpha. But this is plumbing, not a strategy hypothesis - the convergence here reflects shared correct identification of an evidence-quality problem, not a model-bias artifact. Risk-weighted, the plumbing is required infra.

## 7. Implementation map

### 7.1 New module: `modules/trade_emission.py`
- `emit_trade_artifacts(leaderboard_csv, data_csv, output_dir, market, timeframe, oos_split_date) -> dict` 
  - Reads accepted rows
  - Rebuilds via `_rebuild_strategy_from_leaderboard_row` (parity-verified Session 49)
  - Writes `strategy_trades.csv` (per-trade rows) and `strategy_returns.csv` (daily resampled)
  - Returns `{strategy_name: {status, rebuilt_net_pnl, leader_net_pnl, parity_ratio, n_trades}}`
- `apply_parity_status(leaderboard_csv, status_dict) -> None`
  - Adds `trade_artifact_status` column to family_leaderboard_results.csv
  - `OK` if parity passes
  - `PARITY_FAILED` if rebuilt sum diverges > 1% (and abs > $100)
  - `REBUILD_FAILED` if rebuild raised
  - `SKIPPED` if not accepted_final

### 7.2 Modification: `master_strategy_engine.py::_run_dataset`
- After `family_leaderboard_results.csv` is written
- Branch on `skip_portfolio_evaluation`:
  - True: call `emit_trade_artifacts(...)` only (no portfolio review)
  - False: call `evaluate_portfolio(...)` (existing) AND `emit_trade_artifacts(...)` AND merge parity status
- In both branches, write `trade_artifact_status` column update to family_leaderboard_results.csv

### 7.3 Modification: `modules/post_ultimate_gate.py`
- Add new gate failure modes:
  - `MISSING_TRADE_ARTIFACTS`: when `strategy_trades.csv` is not found for the (run_id, market, timeframe) tuple
  - `PARITY_FAILED`: when leaderboard `trade_artifact_status` is `PARITY_FAILED` or `REBUILD_FAILED`
- Both modes: `gate_concentration_pass = False`, `post_gate_pass = False`, `gate_status` populated
- Existing concentration math runs only when `gate_loaded_trade_count > 0` AND `trade_artifact_status == OK`

### 7.4 New tests: `tests/test_trade_emission.py`
- `test_emit_trade_artifacts_writes_both_files`
- `test_parity_pass_marks_OK`
- `test_parity_fail_marks_PARITY_FAILED`
- `test_rebuild_exception_marks_REBUILD_FAILED`
- `test_skip_portfolio_evaluation_true_still_emits`
- `test_post_ultimate_gate_fails_closed_on_missing_trades`

## 8. Result (filled in at sprint close)

**Verdict:** _CANDIDATES / NO EDGE / SUSPICIOUS / BLOCKED_

### Quantitative summary
- Smoke-test sweep: ES 60m, n accepted strategies: ___
- Strategies with `trade_artifact_status == OK`: ___ / ___
- Strategies with `PARITY_FAILED`: ___
- Strategies with `REBUILD_FAILED`: ___
- New test count: ___ added, ___ green

### Cross-LLM consultation (post-sprint)
n/a - plumbing sprint, no strategy hypothesis to consult on.

### Lessons learned
TBD

### Commits / branches
- Pre-registration commit: ___
- Implementation commits: ___
- Merge commit: ___
- Branch: `feat/canonical-trade-emission`

---

## Append to LOG.md after sprint close

Single LOG.md entry: date, sprint name, verdict, one-line outcome, pointer to this file, next sprint hint (Sprint 85 = wire `configs/the5ers_mt5_specs.yaml` into selector cost-aware MC).
