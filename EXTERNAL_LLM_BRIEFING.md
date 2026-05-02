# EXTERNAL_LLM_BRIEFING.md

> Single-page (now multi-page) project briefing for external LLM consultations (ChatGPT-5, Gemini 2.5 Pro).
> Refresh this file at every checkpoint or session-end ritual.
> Paste the whole file into an external chat, then ask the consultation question at the bottom.
>
> **Last refreshed:** 2026-05-03 (full strat-searching pipeline rewrite + selector deep-dive after architectural review)
> **Maintained by:** Claude Code on Latitude

---

## 30-second elevator pitch

A **futures + CFD strategy discovery engine** that sweeps filter combinations and parameter ranges across multiple markets and timeframes to find statistically robust algorithmic strategies. Output: ranked leaderboards of accepted strategies plus a portfolio selector that builds prop-firm-ready combinations with realistic Monte Carlo pass rates.

It is **research, not a live trading system**. The output feeds Portfolio EAs deployed manually on a Contabo VPS via The5ers MT5 (Hedge mode). Two EAs (Portfolio #1 + #3) are already live at 0.01 lots, on a $5K High Stakes account (26213568).

Operator (Rob, Melbourne, Australia) is time-poor and prefers autonomous Claude sessions that complete end-to-end. Compute lives on a 4-host always-on local cluster (~264 threads, c240 + gen8 + r630 + g9). No cloud.

---

## Current state (2026-05-03)

### Code state
- 12 strategy families: 3 long base (trend, MR, breakout) + 3 short base + 9 subtypes (3 per long-base family). Implemented in `modules/strategy_types/`.
- Vectorized engine (`modules/vectorized_trades.py`): 14-23x speedup vs original per-bar loop, parity-tested at zero tolerance. Active via `engine.use_vectorized_trades: true`.
- Active research leaderboards are now neutral, not Bootcamp-ranked. Futures: `family_leaderboard_results.csv` -> `master_leaderboard.csv` -> `ultimate_leaderboard_FUTURES.csv` (legacy alias `ultimate_leaderboard.csv`). CFDs: `family_leaderboard_results.csv` -> `master_leaderboard_cfd.csv` -> `ultimate_leaderboard_cfd.csv`.
- Post-ultimate gate exists (`modules/post_ultimate_gate.py`) and emits `*_post_gate_audit.csv` plus `*_gated.csv`. Currently passes through most rows because (a) most finalized runs do not preserve `strategy_trades.csv`, so trade-concentration evidence is missing, and (b) the CFD pool is too thin (~88 rows) for neighbour-based fragility evidence.
- Portfolio selector (`modules/portfolio_selector.py`, 2705 lines): 7-stage pipeline (more than the docstring claims). Hard filter, return-matrix + trade-artifact load, multi-layer correlation, correlation dedup, combinatorial sweep with regime gate, portfolio Monte Carlo, sizing optimization with robustness test, CSV report.
- Multi-program runner (`run_portfolio_all_programs.py`) iterates 4 prop-firm programs and writes `Outputs/portfolio_{program}/portfolio_selector_report.csv` plus `Outputs/portfolio_combined_summary.csv`.
- Test coverage: 287/287 non-parity tests green at last clean checkpoint; 25 parity tests pass when explicitly run.

### Live trading
- Portfolio #3 EA on Contabo VPS (89.117.72.49): NQ Daily MR + YM Daily Short Trend + GC Daily MR + NQ 15m MR (0.01 lots).
- Portfolio #1 EA also live on the same VPS.
- The5ers $5K High Stakes account 26213568. First confirmed live trade: YM Daily Short Trend, SELL US30. MT5 Hedge mode, CFD symbols available.

### Infrastructure
- 4 always-on local hosts. HARD RULE: no shutdowns. c240 (80T, data hub), gen8 (48T, post-CPU-upgrade), r630 (88T), g9 (48T, 32 GB RAM). About 264 threads total.
- Latitude (Windows) is the dev machine. Tailscale + SSH mesh between everything.
- Z: drive on Latitude maps to c240 Samba (`\\192.168.68.80\data`). Streamlit dashboard moved off c240 onto X1 Carbon (port 8511) so it survives c240 reboots.
- Google Drive cold backup runs nightly + on-ingest mirror (`run_cluster_results.py mirror-backup`).

### Recent additions (this week, sessions 76-83 + audit)
- **BH-FDR family-aware promotion gate** (Benjamini-Hochberg multiple-testing correction over the sweep family) - opt-in via `promotion_gate.bh_fdr_alpha`. **Currently null in config -> dormant**.
- **Deflated Sharpe Ratio** on master leaderboard (Bailey & Lopez de Prado 2014) - penalises observed SR by trial count from sweep CSV row count. Always-on column.
- **Walk-forward validation module** (`modules/walk_forward.py`) - rolling 3-year-train / 1-year-test windows, mean+min t-stat aggregation. **Module exists but is not called from the engine or selector**.
- **Random-flip null permutation test** (n=5000, robust z >= 2.0 gate) - implemented in `modules/statistics.py`. Gate exists, integration partial.

---

## Full strategy-searching pipeline (end to end)

This is the one place where the entire pipeline is documented. Treat it as authoritative; CLAUDE.md and HANDOVER may be stale.

### Phase 0 - Data pipeline (input layer)

- **Futures**: TradeStation CSV exports under `Data/` (~81 files, ~2.2 GB), 17 markets x 1m/5m/15m/30m/60m/daily. Loaded via `modules/data_loader.py::load_tradestation_csv()`.
- **CFDs**: Dukascopy ticks via Tick Data Suite (TDS) Metatrader exports -> `scripts/convert_tds_to_engine.py` -> TradeStation-format CSVs. 24 markets x 5 TFs = 120 files at `/data/market_data/cfds/ohlc_engine/` on c240, mirrored to gen8/r630/g9.
- **The5ers MT5 ticks** (separate concern): only used for execution-cost validation, never for sweeping. SP500 (3.1 GB) and NAS100 (10.6 GB) exported manually; XAUUSD only 5 days available (need Dukascopy).
- **Per-market specs**: `configs/cfd_markets.yaml` has 24 entries, each with `engine.dollars_per_point/tick_size/tick_value/slippage_ticks` and `cost_profile.spread_pts/swap_per_micro_per_night/weekend_multiplier`. Generic retail estimates, **not The5ers-specific** (open issue).
- **OOS split date**: 2019-01-01 globally (`pipeline.oos_split_date`), except BTC at 2021-01-01 (shorter history).

### Phase 1 - Per-dataset sweep + refinement + family leaderboard

Entrypoint: `master_strategy_engine.py::_run_dataset()` (line 954).

**1a. Load + feature precompute (once per dataset)**
- `load_tradestation_csv()` reads CSV once.
- `add_precomputed_features()` (`modules/feature_builder.py`) precomputes the union of SMA lengths, ATR lookbacks, momentum periods needed across all 12 families - so refinement does not recompute features per combo.

**1b. Filter combination sweep (per family)**
- For each family, generate all C(n, k) filter combinations within `min_filters..max_filters`. Each family carries its own filter pool (currently 7 universal + family-specific filters).
- Each combo runs a backtest at default `hold_bars` and `stop_distance` via `MasterStrategyEngine.run()` (vectorized loop).
- Output per family: `Outputs/{MARKET}_{TF}/{FAMILY}_filter_combination_sweep_results.csv` with columns including `strategy_name, profit_factor, oos_pf, recent_12m_pf, total_trades, net_pnl, quality_flag, quality_score, ...`.
- Family parallelism: large families (>= 200 combos) run sequentially in a shared ProcessPoolExecutor; small families (subtypes) batched 3-concurrent in a ThreadPoolExecutor.

**1c. Promotion gate (`apply_promotion_gate`, master_strategy_engine.py:235-311)**
- Hard filters: `min_pf` (1.00), `min_trades` (50), `min_trades_per_year` (3.0).
- Optional **BH-FDR**: if `promotion_gate.bh_fdr_alpha` is set, p-values from `pf_to_pvalue()` get FDR-adjusted across the family; only `bh_fdr_passes==True` rows survive. Currently null -> dormant.
- Lightweight dedup (`deduplicate_promoted_candidates`) on (total_trades, net_pnl within 1%).
- If > `max_promoted_candidates` (20), rank by composite: 0.40 * quality_score + 0.30 * oos_pf + 0.30 * trades_per_year (normalised).
- Output: `{FAMILY}_promoted_candidates.csv`.

**Quality flag assignment (`engine.py:790-815`)**
- Inputs: `is_pf, oos_pf, is_trades, oos_trades` and a 0.04 boundary buffer.
- Buckets: NO_TRADES, LOW_IS_SAMPLE / OOS_HEAVY, EDGE_DECAYED_OOS, REGIME_DEPENDENT, BROKEN_IN_OOS, ROBUST (is/oos PF >= 1.15), STABLE (>= 1.0), MARGINAL. Strategies near boundaries flagged as `*_BORDERLINE`.

**1d. Refinement (top N candidates)**
- Top `max_candidates_to_refine` (default 3) per family enter parameter refinement.
- Brute-force grid (256 points typical) over: `hold_bars` (timeframe-scaled), `stop_distance_atr/points`, `min_avg_range`, `momentum_lookback`, plus exit-config variants (`trailing_stop_atr`, `profit_target_atr`, `signal_exit`).
- `as_completed()` consumption + task-level dedup keeps CPU at 80%+. Output: `{FAMILY}_top_combo_refinement_results_narrow.csv`.

**1e. Family leaderboard + final acceptance gate**
- `_choose_family_leader` selects refined-combo winner only if `net_pnl` improves (or ties with PF >=).
- `_passes_final_leaderboard_gate` enforces `leader_net_pnl > 0`, `leader_pf >= 1.00`, `oos_pf >= 1.00`, `leader_trades >= 60` -> sets `accepted_final` boolean.
- Adds derived columns: `calmar_ratio`, `oos_is_pf_ratio`, `recent_12m_pf`, `pct_profitable_years`, `max_consecutive_losing_years`, `consistency_flag`.
- Sorted via `sort_family_leaderboard()`: accepted_final, quality_flag priority, oos_pf, recent_12m_pf, calmar, leader_pf, max_dd asc, net_pnl, trades_per_year, avg_trade.
- Output: `family_leaderboard_results.csv`.

### Phase 2 - Cross-dataset aggregation (master + ultimate leaderboards)

**2a. Master leaderboard (`modules/master_leaderboard.py`)**
- Scans all `Outputs/{MARKET}_{TF}/family_leaderboard_results.csv`.
- Filters to `accepted_final == True`.
- Adds `deflated_sharpe_ratio` via `annotate_dataframe_with_dsr()` (Bailey/LdP 2014; trial count from sweep CSV row count).
- Universe-aware emit: writes `master_leaderboard.csv` (futures) plus `master_leaderboard_cfd.csv` if any dataset is CFD.
- Sort: `sort_aggregate_leaderboard()` favours accepted, quality, oos_pf, recent_12m_pf, calmar, DSR, leader_pf, max_dd asc, net_pnl, trades_per_year.

**2b. Cross-dataset / cross-timeframe portfolio review (`modules/cross_dataset_evaluator.py`)**
- Per-dataset `strategy_returns.csv` outputs combined to compute cross-TF correlation matrix and a portfolio review snapshot.
- Outputs: `cross_timeframe_correlation_matrix.csv`, `cross_timeframe_portfolio_review.csv`, `cross_timeframe_yearly_stats.csv`.

**2c. Ultimate leaderboard (`modules/ultimate_leaderboard.py`)**
- Aggregates **across runs** (not just within one master). Walks `CONSOLE_STORAGE_ROOT/runs/{run_id}/artifacts/Outputs/` for ingested master leaderboards.
- Dedupes on strategy signature (`strategy_type, dataset, leader_strategy_name, best_combo_filter_class_names`); keeps highest `leader_pf`.
- Outputs: `ultimate_leaderboard_FUTURES.csv` (legacy alias `ultimate_leaderboard.csv`), `ultimate_leaderboard_cfd.csv`.

**2d. Post-ultimate gate (`modules/post_ultimate_gate.py`)**
- Gate A - **trade concentration**: profit Gini (max 0.60), top-5% profit contribution (max 0.40), equity flat-time pct (max 0.40). Requires per-trade PnL from `strategy_trades.csv`.
- Gate B - **parameter fragility (neighbour-based)**: finds neighbours sharing dataset/strategy_type/exit/filters but with parameters within +/-1 bar / +/-0.25 ATR / +/-1 lookback. Requires `neighbor_count >= 3`, `neighbor_median_oos_pf / current_oos_pf >= 0.70`, `weak_frac (oos_pf<1.0) <= 0.20`.
- Outputs: `*_post_gate_audit.csv` (all rows + gate columns) and `*_gated.csv` (only `post_gate_pass == True`).
- Reality check: most finalised runs lack `strategy_trades.csv`, so Gate A is vacuously true; the CFD pool of ~88 rows is too sparse for Gate B neighbour evidence. So the gate currently passes most rows through unchanged.

### Phase 3 - Returns/trades artifact rebuild (`generate_returns.py`)

- Reads ultimate leaderboard.
- Rebuilds each accepted strategy from leaderboard metadata via `_rebuild_strategy_from_leaderboard_row()` (`modules/portfolio_evaluator.py`). Falls back to `best_combo_filter_class_names` if the original combo is missing from `promoted_candidates`.
- Parallelised via `ProcessPoolExecutor` with per-dataset cache (`_load_cached`).
- **strategy_returns.csv**: daily resampled PnL per strategy (date-indexed, columns are strategy labels).
- **strategy_trades.csv**: per-trade rows with `entry_time, exit_time, direction, entry_price, exit_price, net_pnl, bars_held, exit_reason, mae_points, mfe_points`.
- These two files are the input contract for the portfolio selector and the post-ultimate gate.

### Phase 4 - Cluster orchestration (how Phase 1-3 actually run on the cluster)

- **Single market sweep**: `run_local_sweep.py --config configs/local_sweeps/{MARKET}_{TF}.yaml --data-dir /data/market_data/cfds/ohlc_engine/`. Wraps `master_strategy_engine.py` as a subprocess with the merged config.
- **Multi-job batch on one host**: `run_cluster_sweep.py --jobs ES:60m NQ:daily ... --workers 72`. Sequential per-job; sweep manifest tracks completion for resume.
- **Distributed planner**: `run_cluster_sweep.py --distributed-plan --hosts c240:72 gen8:44 r630:80 g9:28 --remote-root /tmp/psc_<runid>` produces a JSON plan with per-host commands plus a watcher block. Today this is a planner/command-generator, not yet an autonomous SSH dispatcher.
- **Auto-ingest watcher** (`scripts/auto_ingest_distributed_run.py`): polls hosts via SSH, ingests completed datasets via `run_cluster_results.py ingest-host`, then `finalize-run`, then `mirror-backup` to Google Drive. Currently runs on x1 Carbon as a scheduled task.
- **Storage layout** on c240: `/data/sweep_results/runs/{run_id}/` for per-run artifacts; `/data/sweep_results/exports/` for canonical aggregated leaderboards; `strategy_console_storage/` is the alternative storage root used during dev.

### Phase 5 - Portfolio selector (`modules/portfolio_selector.py::run_portfolio_selection`)

The selector is a 7-stage pipeline (the docstring still says 6). Configured via `pipeline.portfolio_selector` in config.yaml. The full set of knobs is in the snapshot at the bottom of this section.

**5.1 Hard-filter candidates** (`hard_filter_candidates`)
- Default input: `ultimate_leaderboard_cfd.csv` (set `prefer_gated_leaderboard: true` to switch to `*_gated.csv` instead - currently false).
- Filters in order: quality_flag whitelist (default `["ROBUST", "ROBUST_BORDERLINE", "STABLE"]`), `oos_pf > oos_pf_threshold` (default 1.0), trade count >= 60 (hard-coded - not exposed to config), per-program `excluded_markets` (The5ers configs carry `[W, NG, US, TY, RTY, HG]`), dedup by (strategy_name, market) keeping highest neutral priority, cap to `candidate_cap` (default 60).
- Neutral priority tuple: (quality_rank, oos_pf, leader_pf, recent_pf, net_pnl, trades).

**5.2 Build return matrix + load trade artifacts**
- `build_return_matrix(candidates, runs_base_path)` returns daily PnL DataFrame (date-indexed, columns are strategy labels). Resamples per `exit_time` if loading from `strategy_trades.csv`.
- `_load_trade_artifacts` + `_load_raw_trade_lists`: prefers `strategy_trades.csv`; falls back to `strategy_returns.csv`. Returns a `dict[label] -> list[dict]` of per-trade rows (`net_pnl, entry_time, exit_time, bars_held` minimum).
- **Behavior diagnostics computed here** (lines 275-317): `overnight_hold_share`, `weekend_hold_share`, `avg_swap_units_per_trade`, plus per-market `spread_cost_per_micro` and `swap_per_micro_per_night` from `cfd_markets.yaml`. Merged back onto candidate dicts.

**5.3 Three-layer correlation matrix** (`compute_multi_layer_correlation`, gated on `use_multi_layer_correlation: true`)
- Layer A - active-day Pearson on days where both strategies have nonzero PnL (min overlap 30 days, else 0).
- Layer B - drawdown-state Pearson on each strategy's fractional drawdown series.
- Layer C - tail co-loss: P(B losing | A in worst-10%-DD), max-symmetrised. **Currently disabled** by setting `tail_coloss_threshold: 1.01` because the calc was rejecting almost everything (config comment: "DISABLED - tail co-loss calc is broken").
- Outputs: `portfolio_selector_active_corr.csv`, `portfolio_selector_dd_corr.csv`, `portfolio_selector_tail_coloss.csv`.

**5.4 Pre-sweep correlation dedup** (`correlation_dedup`, threshold 0.6 - hardcoded, not configurable)
- Builds adjacency graph of pairs with |Pearson| > 0.6, BFS over connected components, keeps highest-priority strategy per cluster. Reduces n before the C(n, k) explosion.

**5.5 Combinatorial sweep with regime gate** (`sweep_combinations`, ProcessPoolExecutor)
- Sweep over `n_min..n_max` (default 3..8) portfolio sizes.
- Hard ceiling: any pair active_corr > 0.85 -> reject.
- Mean-based gates: `mean active_corr > 0.60` reject (was 0.50, **loosened**), `mean dd_corr > 0.80` reject (was 0.40, **loosened heavily**).
- Market concentration: `max_strategies_per_market: 3` (was 2, **loosened**), `max_equity_index_strategies: 5` (was 3, **loosened**).
- ECD pair-wise gate: `use_ecd: false` by default (was rejecting everything).
- Composite scoring: 0.25*avg_oos_pf + 0.20*calmar_proxy + 0.15*recent_pf + 0.10*market_div + 0.10*direction_mix + 0.10*logic_div - 0.25*dd_overlap_penalty.
- **Regime survival gate** (`regime_survival_gate`, prop_firm_simulator.py): runs the candidate portfolio through 2022 (inflation), 2023 (recovery), 2024-2025 (AI/metals) windows; rejects if any window's PF < `min_regime_pf` (0.8). Hard-coded windows. Active by default.

**5.6 Portfolio Monte Carlo** (`run_bootcamp_mc`)
- Two MC engines:
  - **block_bootstrap** (default): sample consecutive-day blocks (sizes [5, 10, 20]) with replacement until reaching n_days, preserving auto-correlation and crisis clustering. Independent per-strategy; no cross-strategy interleaving.
  - **shuffle_interleave** with cost-aware variant: per-trade shuffle and interleave; deducts spread + swap costs per trade using `cfd_markets.yaml`. Spread cost = `spread_pts * dollars_per_point * (weight*10)`. Swap cost = `swap_per_micro_per_night * (weight*10) * swap_units` (Friday-to-Monday counts as 3 units via `weekend_multiplier`).
- **Cost-aware MC activation**: only when `_supports_cost_modeling(trade_artifacts)` is true (needs at least one trade with `entry_time/exit_time` or `bars_held`). Auto-switches to `shuffle_interleave` in that case. If finalised run lacks `strategy_trades.csv`, falls back to cost-blind `block_bootstrap`.
- Per-portfolio outputs: `step1_pass_rate, step2_pass_rate, ... final_pass_rate, p95_worst_dd, p99_worst_dd, median_trades_to_pass, p75_trades_to_pass`.

**5.7 Sizing optimization + robustness test**
- Objective: minimise `median_trades_to_pass` subject to `pass_rate >= min_pass_rate` (0.40) AND `p95_dd <= dd_p95_limit_pct * program_dd_limit` (0.90 - **was 0.70, loosened**) AND `p99_dd <= dd_p99_limit_pct * program_dd_limit` (0.95 - was 0.90).
- Weight grid hard-coded: `[0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0, 5.0]`. For 3 strategies: 1000 combos brute force; for 8: sampled to 500 + inverse-DD seed.
- Final MC at 10k sims with chosen weights for accurate step rates.
- Robustness test: weight perturbation (+/-0.1 each strategy) and remove-one analysis. `robustness_score = 0.5 * (1 - max_weight_delta) + 0.5 * (1 - max_remove_delta)`.

**5.8 Report generation**
- `{output_dir}/portfolio_selector_report.csv` per program: strategy_names, n_strategies, all step pass rates, final_pass_rate, p95_worst_dd_pct, avg_oos_pf, avg_correlation, diversity_score, composite_score, micro_contracts, median_trades_to_fund, p75_trades_to_fund, est_months_median/p75, **max_overnight_hold_share, max_weekend_hold_share, max_swap_per_micro_per_night**, robustness_score, verdict (RECOMMENDED / VIABLE / MARGINAL).
- Verdict thresholds: RECOMMENDED if final_rate > 60% AND p95_dd < 90% of limit AND >= 3 markets; VIABLE if final_rate > 30% AND >= 2 markets; else MARGINAL.

**5.9 Multi-program orchestration (`run_portfolio_all_programs.py`)**
- Iterates `bootcamp_250k`, `high_stakes_100k`, `hyper_growth_5k`, `pro_growth_5k`. Each gets a fresh `run_portfolio_selection()` call with that program's config and its own `Outputs/portfolio_{program}/` directory.
- Combined summary at `Outputs/portfolio_combined_summary.csv`.

### PropFirmConfig field comparison

| Field | Bootcamp 250K | High Stakes 100K | Hyper Growth 5K | Pro Growth 5K |
|---|---|---|---|---|
| n_steps | 3 | 2 | 1 | 1 |
| step_balances | [100K, 150K, 200K] | [100K, 100K] | [5K] | [5K] |
| profit_target_pct | 6% | 8% step1 / 5% step2 (per-step) | 10% | 10% |
| max_drawdown_pct | 5% | 10% | 6% | 6% |
| max_daily_dd_pct | None | 5% (recalculates daily) | 3% (pause) | 3% (pause) |
| daily_dd_is_pause | False (terminate) | False | True | True |
| min_profitable_days | None | 3 | None | 3 |
| leverage | 30x | 100x | 30x | 30x |
| mandatory_stop_loss | False | True | False | False |
| excluded_markets | [W, NG, US, TY, RTY, HG] | [W, NG, US, TY, RTY, HG] | [W, NG, US, TY, RTY, HG] | [W, NG, US, TY, RTY, HG] |

### Active config snapshot (`config.yaml`, abridged)

```yaml
engine:
  initial_capital: 250000.0
  risk_per_trade: 0.01
  use_vectorized_trades: true

pipeline:
  max_workers_sweep: 2          # local default; overridden per cluster host
  max_workers_refinement: 2
  max_candidates_to_refine: 3
  oos_split_date: "2019-01-01"
  skip_portfolio_evaluation: false
  skip_portfolio_selector: true   # selector run separately via run_portfolio_all_programs.py
  portfolio_selector:
    prop_firm_program: high_stakes
    prop_firm_target: 100000
    min_pass_rate: 0.40
    candidate_cap: 60
    oos_pf_threshold: 1.0
    n_sims_mc: 10000
    n_sims_sizing: 1000
    n_min: 3
    n_max: 8
    quality_flags: [ROBUST, ROBUST_BORDERLINE, STABLE]
    active_corr_threshold: 0.60   # was 0.50 - loosened
    dd_corr_threshold: 0.80       # was 0.40 - loosened heavily
    tail_coloss_threshold: 1.01   # DISABLED - calc broken
    use_ecd: false                # DISABLED - was rejecting everything
    use_multi_layer_correlation: true
    use_regime_gate: true
    dd_p95_limit_pct: 0.90        # was 0.70 - loosened
    dd_p99_limit_pct: 0.95        # was 0.90 - loosened
    max_strategies_per_market: 3  # was 2 - loosened
    max_equity_index_strategies: 5 # was 3 - loosened

promotion_gate:
  min_profit_factor: 1.00
  min_trades: 50
  min_trades_per_year: 3.0
  max_promoted_candidates: 20
  bh_fdr_alpha: null              # dormant

leaderboard:
  min_pf: 1.00
  min_oos_pf: 1.00
  min_total_trades: 60
```

---

## Honest gap inventory (what is wired vs what is dormant)

### Wired and working
- Vectorized engine, 14-23x speedup, parity-tested.
- Sweep -> promotion gate -> refinement -> family leaderboard -> master leaderboard -> ultimate leaderboard chain on both futures and CFD universes.
- Cluster ingest + finalize + Drive mirror via `run_cluster_results.py`.
- 7-stage portfolio selector orchestration including block-bootstrap MC, sizing optimisation, robustness test, multi-program runner.
- Per-program `excluded_markets` enforcement.
- Layer A (active-day) and Layer B (drawdown-state) correlation, used in mean-based gates.
- Regime survival gate at sweep stage.

### Wired but loosened to avoid empty results
- `active_corr_threshold` and `dd_corr_threshold` raised because tighter values rejected every combo.
- `dd_p95_limit_pct` and `dd_p99_limit_pct` raised because tight DD ceilings forced the sizing optimiser to minimum weights everywhere.
- `max_strategies_per_market` and `max_equity_index_strategies` increased to allow larger portfolios.
- These loosenings suggest the gate calibration was brittle relative to the available pool; the gates are still meaningful but the binding constraint moves around with pool composition.

### Implemented but currently disabled / dormant
- **Tail co-loss gate** (Layer C): metric is computed but threshold set to 1.01 because the calculation is acknowledged broken in config.
- **Expected Conditional Drawdown gate**: code exists in `sweep_combinations`, `use_ecd: false`. Threshold tuning open.
- **BH-FDR multiple-testing correction**: implemented in `modules/statistics.py`, dormant (`bh_fdr_alpha: null`).
- **Walk-forward validation**: `modules/walk_forward.py` (273 lines) is feature-complete, but no call sites in the engine, refinement, or selector. Output not consumed anywhere.
- **Random-flip null permutation test**: implemented in `modules/statistics.py`. Integration with promotion gate is partial.
- **Bootcamp-score-based ranking**: deliberately retired from the active path; lives in `modules/bootcamp_scoring.py`. Selector now does program-specific ranking instead.

### Documented but not implemented
- **Challenge-vs-funded selector mode**: spec at `docs/CHALLENGE_VS_FUNDED_SPEC.md`. The selector simulates challenge steps but does not simulate funded-stage behaviour (scaled balance, profit split, scaling rules) - and there is no `selection_mode` knob to score against either.
- **Per-strategy attribution in selector report**: only portfolio-level diagnostics are emitted; individual strategy contributions to portfolio pass rate are not.
- **Cross-program optimality view**: combined summary has one row per program but no diff/overlap analysis to surface strategies that appear strong in multiple programs.
- **Walk-forward gate at portfolio selection time**: walk_forward outputs are not consumed by `run_portfolio_selection()`.

### Hard-coded values that should be config
- Trade count minimum 60 in selector hard filter (line 376).
- Correlation dedup threshold 0.6 (line 872).
- Block bootstrap block sizes [5, 10, 20].
- Sizing weight grid [0.1 ... 5.0].
- Regime survival windows (2022, 2023, 2024-2025).
- Stress percentile 0.10 in ECD and tail co-loss.

### Data quality / artifact reliability
- `strategy_trades.csv` (per-trade) is required by both the post-ultimate gate's concentration check and the cost-aware MC. Most finalised CFD runs do not preserve it. This is the single biggest blocker right now: without rich trade artifacts, the most expensive parts of the pipeline (cost realism, fragility evidence) can't do real work.
- Time-to-fund estimates use trade frequency from leaderboard metadata. If metadata is stale or wrong (e.g. a refined strategy that re-trades at different cadence), funding timelines silently mislead.
- Generic spread/swap costs in `cfd_markets.yaml` are retail estimates, not The5ers MT5-specific. Real swap is asymmetric long/short and weekend rollover day differs by asset class. Open issue.

---

## In-flight cluster state (snapshot)

- 2026-05-01 10-market CFD batch (`ES NQ YM RTY DAX N225 FTSE STOXX CAC GC` x `daily/60m/30m/15m`, no 5m). 33/40 jobs ingested. 7 jobs distributed across all 4 hosts. Auto-ingest watcher is running on x1 Carbon.
- ETA baseline from r630 ES 5m breakout sweep: 20% at `21:42:30Z`, 40% at `22:24:13Z` -> ~42 min per 20% on r630 with 80 workers. Family ETA dropping from 133.7 min -> 112.7 min as expected for that family alone.
- CFD ultimate row count cumulative: 494 in latest post-gate-audit (much larger than the 88 referenced earlier; new audit file is 2026-05-03).
- Validated CFD run `2026-04-30_es_nq_validation` is finalised and mirrored to Drive.
- The historical futures corpus `Outputs/ultimate_leaderboard.csv` (649 rows) is preserved as `ultimate_leaderboard_LEGACY_FUTURES_649rows_2026-04-04.csv` in Drive.

### Empirical state of `ultimate_leaderboard_cfd_post_gate_audit.csv` (2026-05-03)

This is the latest post-ultimate gate audit, used to drive the operator's "too many strategies are making it through" intuition. Numbers below come from direct row-level inspection.

- **Total rows**: 494
- **post_gate_pass = True**: 476 (96.4% pass rate). The gate is doing almost no work.
- **gate_loaded_trade_count == 0** for **every single row**. Concentration check is mathematically vacuous.
- **gate_concentration_pass = True** for all 494 (because trade-level data was never loaded).
- **gate_fragility_status**: 476 rows = INSUFFICIENT_NEIGHBORS (passed by default), 18 rows = EVIDENCED (and 0 of those 18 passed - so when the gate has actual evidence it does cull, but the universe is too sparse for evidence).
- **Quality flag distribution** (passed rows): STABLE_BORDERLINE 164, ROBUST_BORDERLINE 149, ROBUST 114, STABLE 26, REGIME_DEPENDENT 10, MARGINAL_BORDERLINE 9, LOW_IS_SAMPLE 3, BROKEN_IN_OOS 1.
- **Selector quality whitelist [ROBUST, ROBUST_BORDERLINE, STABLE]** -> 289 candidates before excluded_markets.
- **Strict whitelist [ROBUST, STABLE]** -> 140 candidates.
- **Timeframe distribution at the leaderboard level** (passed rows): 60m=129, 30m=121, daily=111, 15m=101, 5m=14. Daily is ~23% of the universe.
- **Timeframe distribution at the top-of-leaderboard**: top 10 = 10/10 daily, top 20 = 20/20 daily, top 50 = 50/50 daily, top 100 = 86/100 daily.
- **Selector top-60 candidate cap**: when the current sort applies, the candidate cap of 60 selects **60 daily strategies, zero intraday**. The selector never sees an intraday candidate under current ranking.
- **Operator inference**: the leaderboard universe is reasonably balanced across timeframes, but the **ranking** is daily-dominated, and the candidate cap mechanically locks intraday strategies out before MC ever runs.

---

## Open issues / blockers (priority order)

1. **`strategy_trades.csv` is not reliably preserved across canonical run storage.** Without it, post-ultimate gate concentration check is vacuous and selector MC silently falls back to cost-blind. Need to make `generate_returns.py` part of the canonical finalize flow, not a separate optional pass.
2. **Selector still defaults to raw `ultimate_leaderboard_cfd.csv` rather than the gated version.** Intentional today because the gate is evidence-thin, but should flip once gating has teeth.
3. **Disabled Layer C (tail co-loss) and ECD gates.** Calculations need fixing or replacement; without them the selector relies almost entirely on Pearson + DD-state mean.
4. **Walk-forward not wired into selector orchestration.** Module is ready but not consumed.
5. **Challenge vs funded mode is unimplemented.** Selector treats challenge passing as the entire objective; funded-stage longevity is not modelled.
6. **The5ers-specific cost data is missing.** Spreads, swaps (long/short asymmetric), weekend rollover day, commission-by-asset-class. Need a proper `configs/the5ers_mt5_specs.yaml` populated from MT5 Symbol Specification dialog.
7. **Calibration brittleness.** Multiple selector gates were loosened to avoid rejecting everything. Suggests either the strategy pool is too thin (88 CFD rows) or the gates need a different formulation.
8. **`run_cluster_sweep.py` is still a single-host sequential runner with optional planner mode.** Distributed dispatch is operator-driven, not autonomous.
9. **Dashboard Live Monitor**: engine log + promoted candidates panels broken during active runs.
10. **Hard-coded thresholds** scattered through the selector that operationally should be in config.

---

## Things that should NOT be touched (working as intended, hard-won)

- **Vectorized engine** - 14-23x speedup, parity-tested. Refactor only with parity preservation.
- **3-layer correlation architecture** in portfolio selector - multi-LLM-validated (Session 58). Layers A and B should remain even if Layer C gets reworked.
- **Block bootstrap MC** - preserves crisis clustering vs naive shuffle.
- **Position sizing fixed at initial_capital** - Session 45 critical fix; do NOT re-introduce compounding.
- **Vectorized filter masks** - pandas Series.rolling + numpy broadcast.
- **Quality flag thresholds and BORDERLINE buffer** - tuned over many sessions; do not loosen.

---

## Architectural decisions (load-bearing)

| Decision | Session | Why |
|---|---|---|
| Local cluster, not cloud | 65-69 | Cheaper, no SPOT preemption, no SCP timeouts, no quotas |
| Dukascopy ticks for discovery, The5ers ticks for execution | 65 | Dukascopy: deep history. The5ers: real spreads at execution |
| Always-on hard rule for cluster | 73 | Power savings cost too much ops time |
| MASTER_HANDOVER.md not HANDOVER.md | 75 | Project-scoped naming prevents collision with sister project |
| Selector reads neutral pool, ranks per-program internally | 80 | One discovery universe, multiple firm-specific selections |
| Drop 5m timeframe | 42 | Zero accepted strategies, ~50% of compute cost |
| Vectorized trades | 61 | 14-23x faster, zero-tolerance parity |

---

## Project rules (operator's standing instructions to Claude)

- Never `git add -A`. Stage by path.
- Never push without being asked.
- Never amend a published commit.
- ASCII-only output (Windows PowerShell breaks on emoji).
- MASTER_HANDOVER.md updated in place per session.
- LOG.md is append-only audit.
- Risk discipline: per-action confirmation for destructive/external-visibility actions.
- One project, one Claude, one CLAUDE.md. Cross-project reads only via this briefing file.

---

## Layered context (read deeper as needed)

- `MASTER_HANDOVER.md` - current state, open issues, infrastructure
- `LOG.md` - append-only audit trail
- `CLAUDE.md` - project bible, family inventory, filter inventory, contract specs
- `CHANGELOG_DEV.md` - session-by-session development history
- `docs/PROJECT_REVIEW_2026-04-26.md` - 9-phase project review with lessons learned
- `docs/CFD_SWEEP_SETUP.md` - CFD pipeline (Dukascopy to engine format)
- `docs/CHALLENGE_VS_FUNDED_SPEC.md` - two-mode portfolio selection spec (not yet implemented)
- `docs/the5ers_program_rules.md` - canonical prop-firm rules (verified 2026-04-30)
- `sessions/SPRINT_TEMPLATE.md` - sprint pre-registration template

---

## How to use this file for a consultation round

1. Refresh this file (Claude does it at session-end).
2. Open ChatGPT-5 (paid) or Gemini 2.5 Pro (paid) in a fresh chat.
3. Paste the whole file as the first message.
4. Ask the consultation questions below.
5. Capture the response back into the next session's spec.

**Anti-convergence rule** (from sister project, validated 8x): when ChatGPT and Gemini converge on the same recommendation, that recommendation drops priority - convergence is anti-alpha in their hit-rate data. Divergence is where the real edges hide. (8 samples is small; treat as heuristic.)

---

## Current consultation questions

We are restarting active work on the portfolio selector. The architecture review above is the ground truth - the docstring and HANDOVER are slightly behind reality. Please answer the questions below in order. Concrete recommendations beat abstract critiques. If you think the framing is wrong, say so and reframe.

### Question 1 - Calibration brittleness vs gate redesign

The selector has six gates that were progressively loosened to avoid rejecting every combination: `active_corr_threshold` 0.50 -> 0.60, `dd_corr_threshold` 0.40 -> 0.80, `dd_p95_limit_pct` 0.70 -> 0.90, `dd_p99_limit_pct` 0.90 -> 0.95, `max_strategies_per_market` 2 -> 3, `max_equity_index_strategies` 3 -> 5. Two more gates (Layer C tail co-loss and ECD) are disabled outright.

Is this a calibration problem (thresholds wrong, but gates correct in shape) or a gate-design problem (the gates themselves are the wrong tool when the candidate pool is around 80-150 strategies and dominated by long-equity-index combos)? What is your honest call, and what specific replacement gates would you propose if you think the shape is wrong?

### Question 2 - Trade-artifact reliability is the bottleneck

`strategy_trades.csv` (per-trade rows: entry_time, exit_time, direction, entry_price, exit_price, net_pnl, bars_held) is required by both the post-ultimate fragility/concentration gate and the cost-aware MC in the selector. Most finalised CFD runs don't preserve it because `generate_returns.py` is run as a separate pass and is fragile (rebuild bugs were the Session 49 fix). The "right" fix is to bake `generate_returns` into the canonical finalize flow.

What's the minimum-risk way to make this guaranteed-on-every-run? Options I'm considering: (a) call generate_returns from `finalize_cluster_run`; (b) emit per-trade artifacts directly from the engine sweep stage so they're a first-class output, not a rebuild; (c) keep rebuild as an option but make the post-ultimate gate refuse to gate strategies whose trades are missing (fail closed instead of pass through). Which would you pick, and why?

### Question 3 - Walk-forward integration

`modules/walk_forward.py` does rolling 3-year-train / 1-year-test windows and aggregates mean+min t-stats per strategy. It is feature-complete and unused. Where in the pipeline should this output be consumed: (a) at the family-leaderboard stage as an extra column influencing `accepted_final`, (b) at the master/ultimate stage as a cross-cut filter, (c) at the post-ultimate gate as a third leg alongside concentration and fragility, or (d) at the portfolio selector hard-filter? Each costs more compute the earlier we put it. Pick one and defend it.

### Question 4 - Challenge vs funded modes

The selector currently optimises challenge passing as the sole objective. After the trader is funded, the constraint shape changes: profit split kicks in, scaling rules kick in, and longevity matters more than time-to-fund. What is the cleanest way to extend the selector to a two-mode system without duplicating the orchestration?

Concretely, would you (a) add a `selection_mode: ["challenge", "funded", "both"]` field that toggles different scoring inside the same pipeline, (b) keep two separate entrypoints `run_portfolio_selection_challenge` and `run_portfolio_selection_funded` and have the multi-program runner call both, or (c) reframe entirely so the prop-firm config carries `mode_specific_objective` blocks and the selector is mode-agnostic by construction? What failure modes does each path have?

### Question 5 - Layer C (tail co-loss) - fix or replace?

Layer C of the multi-layer correlation is `P(B losing | A in worst-10%-DD)`, max-symmetrised across pair direction. It was disabled because the metric "always exceeds the threshold". I'd like a pointed second opinion: is the metric definitionally wrong (e.g. drawdown vs return mixing, percentile threshold instability with thin samples), or is the threshold wrong (1.01 makes no sense as a tail-coloss bound), or is this the wrong measure entirely?

If you'd replace it, what would you replace it with? Candidate ideas: (i) lower partial moment co-movement, (ii) crash-conditional Spearman, (iii) skewness-weighted DCC, (iv) just drop Layer C and lean harder on Layers A and B.

### Question 6 - The5ers cost realism

`configs/cfd_markets.yaml` has generic retail estimates: `spread_pts`, `swap_per_micro_per_night` (single value, not asymmetric long/short), `weekend_multiplier: 3`. The5ers MT5 has the real values (SwapLong, SwapShort, SwapType, SwapRollover3Days). What's the lowest-effort way to incorporate The5ers-specific values without losing the universality of the discovery pipeline? Options: (a) per-firm cost overlay file `configs/the5ers_mt5_specs.yaml` consulted by selector only, (b) per-firm cost block inside each PropFirmConfig, (c) a separate cost-realism MC pass that runs after the universal one and reports cost-haircut deltas. Pick one.

### Question 7 - The big-picture architecture call

Universal discovery -> universal pool -> firm-specific portfolio. The current implementation is mostly this, but firm-specific behaviour leaks back into the discovery layer in two places: `excluded_markets` is a per-program field that is consulted at selector hard-filter time (fine), but the regime gate at sweep time uses fixed windows (2022/2023/2024-2025) baked into the selector, not into a firm config or a market-conditions config. Should regime windows be: (a) firm-agnostic (universal market-condition checkpoints, per-asset class), (b) firm-specific (each firm's evaluation window), or (c) candidate-data-driven (pick worst-N realised drawdown windows from the candidate's own history)?

### Question 8 - Anti-convergence

If you have read this far and your answer to multiple questions agrees with what you think a more conservative model would say, please flag it. We have a calibrated 8x prior (small sample, treat as heuristic) that ChatGPT/Gemini convergence is anti-alpha for us. Where do you think you are giving us the safe answer instead of the right one?

---

## Round 2 - Gemini consultation (after ChatGPT-5 round)

ChatGPT-5 has already answered the Q1-Q8 round above. Below is a faithful summary of its positions so you can disagree where you genuinely disagree. Anti-convergence rule: where you simply restate ChatGPT, the answer drops priority. We want your divergent take.

### ChatGPT-5's positions (summary)

- **Q1**: Mostly gate-design problem, not calibration. Replace blunt thresholds with **portfolio risk budgets** (max cluster weight, max market weight, max equity-index weight, max same-direction weight, max daily weight). Keep Pearson and DD-corr but stop relying on them as the main protection. Add **cluster exposure**, **drawdown-overlap during stress windows**, **contribution concentration**, **trade-frequency / time-to-target**, and **stress-cost survival** as additional gates.
- **Q2**: Pick (a) first, then (c). Call `generate_returns.py` from `finalize_cluster_run`, validate artifacts, fail-closed when missing. Don't yet emit per-trade rows from the engine sweep stage (don't disturb the parity-tested vectorized engine).
- **Q3**: Walk-forward at the **post-ultimate gate**, third leg alongside concentration and fragility.
- **Q4**: Mode-agnostic selector with config-driven **objective blocks** per mode (challenge / funded / both). Same pipeline, different objective function and constraints.
- **Q5**: **Replace** Layer C. Use a **stress-window co-loss** metric (find each strategy's worst rolling 20/60/120-day windows, measure the other strategy's PnL during those windows, average-symmetrise). Use as score penalty rather than hard gate unless multiple high pairs. Threshold guidance: > 0.70 bad, 0.50-0.70 penalty, < 0.50 acceptable.
- **Q6**: Per-firm cost overlay file `configs/the5ers_mt5_specs.yaml`. Selector reads firm overlay first, falls back to `cfd_markets.yaml`. Asymmetric long/short swap is the key reason.
- **Q7**: **Candidate-data-driven worst windows** as the binding regime gate. Keep 2022/2023/2024-25 macro windows as diagnostic-only.
- **Q8**: ChatGPT flagged its safe answers as: "fix artifacts before bigger sweeps", "fail closed", "walk-forward at post-ultimate", "cost overlay", "don't rewrite the engine". Its self-flagged divergent answers: "change gate shape not threshold", "use risk budgets not rejection thresholds", "marginal-portfolio-contribution metric", "penalise/quota daily not ban", "let mediocre standalone strategies in if they raise MC pass rate", "stress-window co-loss not co-LPM2".

ChatGPT also did a CSV-level inspection of `ultimate_leaderboard_cfd_post_gate_audit.csv` and produced the empirical findings now embedded in the "In-flight cluster state" section above (494 rows, 96.4% pass rate, 0 trade loads, 50/50 daily in top 50, candidate top-60 = all daily).

ChatGPT proposed two specific operational changes the operator should be aware of:
1. **Bucketed candidate pool** instead of a single `candidate_cap: 60` global. Per-timeframe caps (e.g. daily 35, 60m 30, 30m 30, 15m 25, 5m 10) so intraday strategies actually reach the MC stage.
2. **Marginal portfolio contribution** as a candidate metric: a strategy's value is `portfolio_pass_rate_with - portfolio_pass_rate_without`. Mediocre standalone strategies can be portfolio-valuable.

### Divergence-seeking questions for Gemini

For each question below, take the bolder/divergent position when you have one. If you agree with ChatGPT, say so explicitly and explain why - but only after attempting to find a meaningfully different answer first.

**Q9 - Risk budgets vs greedy frontier vs both.** ChatGPT proposes portfolio risk budgets (max cluster weight, max market weight, etc.) as the replacement for the loosened threshold gates. An alternative is **greedy frontier construction**: at each portfolio-size step, add the strategy that maximises marginal contribution to (expected_return / combined_drawdown), no thresholds at all. Which approach is fundamentally sounder for an 80-150-strategy daily-dominated pool? If both, what's the right composition - greedy as the primary mechanism with budgets as a sanity overlay, or budgets as the primary with greedy as a tiebreaker? Pick a side.

**Q10 - Stress-window co-loss vs co-LPM2 vs both.** ChatGPT recommends stress-window co-loss as the Layer C replacement (find A's worst rolling-window losses, measure B's PnL there, average-symmetrise). An alternative is **co-LPM2 (lower-partial-moment-2 co-variance)**: `E[max(0, -ra) * max(0, -rb)]` over the return matrix, no windowing needed, calibrate threshold from empirical pair distribution. Which has fewer pathologies in thin-sample / serially-correlated data? Take a position.

**Q11 - Per-trade artifact emission strategy.** ChatGPT recommends Phase 1 = call `generate_returns.py` from finalize, then Phase 2 = consider direct emission from the engine. The alternative is to skip the rebuild path entirely and emit per-trade rows for accepted strategies directly from the engine's vectorized output, since the data already exists in numpy arrays during the sweep. The argument for direct emission: one fewer rebuild step, no parity risk between sweep and rebuild, no Session-49-style bugs. The argument against: touches the parity-tested hot path. Which is the right call given the operator's compute-rich, time-poor profile?

**Q12 - Candidate pool design.** ChatGPT proposes per-timeframe bucketed caps (e.g. daily 35, 60m 30, 30m 30, 15m 25). An alternative is **per-cluster bucketed caps** based on the strategy's correlation cluster (computed once, cached): force the candidate pool to span clusters rather than timeframes. A more aggressive alternative: drop the cap entirely and let MC sift the entire 289-strategy quality pool. Which gives the highest probability of finding the actually-best portfolio for a thin pool that grows over time?

**Q13 - Marginal portfolio contribution as a metric.** ChatGPT proposes scoring each strategy by `portfolio_pass_rate_with - portfolio_pass_rate_without`. This is conceptually clean but expensive (requires running portfolio MC for each candidate addition/removal). For a 289-candidate pool with portfolio sizes 3-8, the naive cost is huge. What's the cheapest principled approximation? Options: (i) Shapley-value-like sampling over portfolio compositions, (ii) leave-one-out from a single best portfolio, (iii) leverage Layers A+B correlation matrix to predict marginal contribution analytically without MC. Take a position on whether the metric is worth the compute and how to make it tractable.

**Q14 - Daily quotas: hard cap vs scoring penalty.** ChatGPT proposes both: a hard `max_daily_strategies_pct: 0.50` AND a scoring penalty for overnight/weekend exposure. Are both needed, or does one make the other redundant? The operator's empirical observation: top 50 ranked rows are 100% daily right now. After cost-aware MC with The5ers swap data, how many of those daily-dominated portfolios survive at all? If the answer is "very few", the quota is unnecessary because the MC cull does the work. If the answer is "most", the quota is vital because the MC isn't punishing daily exposure correctly. Which is your prior?

**Q15 - The single highest-leverage thing the operator could do this week.** Compute is plentiful. The operator wants the best portfolios per program with minimum hand-holding. Setting aside ChatGPT's sequence (which is sensible but conservative), what is the **one** change that, if made well, would most increase the probability of finding genuinely robust portfolios in the next two weeks? You only get one. Defend it.

**Q16 - Where ChatGPT is most likely wrong.** Read ChatGPT's positions carefully. Pick the one position you have the lowest confidence in (whether you agree or not), and explain what would make it wrong. This is the opposite of anti-convergence: even where Gemini agrees, there's value in stress-testing the consensus.

---

## Cross-project notes (betfair-trader)

This project has a sibling: `betfair-trader` (pre-match Betfair Exchange trading bot). The two share:
- Local compute cluster (c240, gen8, r630, g9)
- Operator (Rob, Latitude + X1 Carbon)
- Claude Code as primary dev interface
- MASTER_HANDOVER + LOG + memory persistence pattern

They diverge on:
- Domain (futures/CFDs vs Betfair markets)
- Sprint architecture (this project: monolithic sweeps; betfair: 4-15 probes per sprint with frozen pre-registration)
- Live execution (this: Contabo VPS + MT5; betfair: Lightsail Dublin)
- Risk gate severity (this: 6-element promotion gate + post-ultimate gate; betfair: stricter Gate-J + DSR + walk-forward + random-flip + per-segment positivity)

When consulting externally, mention which project the question pertains to.
