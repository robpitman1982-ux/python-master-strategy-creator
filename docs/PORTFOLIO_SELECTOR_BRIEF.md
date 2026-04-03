# Portfolio Selector Pipeline — Full Technical Brief for LLM Review

## Purpose

This document describes the portfolio selection pipeline used in `python-master-strategy-creator`. The goal is to assemble a portfolio of 4-6 uncorrelated futures/CFD strategies that reliably passes prop firm evaluation challenges (specifically The5ers). I'm sharing this with other LLMs (ChatGPT, Gemini, etc.) to get independent ideas on how to improve portfolio construction, identify blind spots, and potentially find better portfolios.

## Context

- **What we're trading**: CFDs on MT5 via The5ers prop firm (NAS100, US30, XAUUSD, SP500, XAGUSD, XTIUSD)
- **Strategy discovery engine**: Sweeps filter combinations × parameter grids across 8 futures markets, 4 timeframes (daily, 60m, 30m, 15m), and 15 strategy families (MR, Trend, Breakout + short variants + sub-families)
- **Current strategy pool**: 379 strategies in `ultimate_leaderboard_bootcamp.csv`, of which ~99 are ROBUST or STABLE quality
- **Target programs**:
  - **High Stakes $5K**: 2 steps, 10% max DD, 5% daily DD, 8%+5% profit targets, no time limit
  - **Bootcamp $250K**: 3 steps, 5% max DD, no daily DD, 6% profit target per step, no time limit
- **Position sizing**: Micro contracts (0.01 lots on CFDs). Weight 0.1 = 1 micro contract.
- **Key constraint**: Unlimited time means drawdown is the ONLY failure mode. PF > 1.0 will eventually hit any profit target given enough time. The portfolio must simply never breach the max DD limit.


## The 6-Stage Pipeline

### Stage 1: Hard Filter Candidates

**Input**: `ultimate_leaderboard_bootcamp.csv` (379 rows, one per strategy)

**Filters applied (in order)**:
1. `quality_flag` must be ROBUST or STABLE (rejects MARGINAL, REGIME_DEPENDENT, BROKEN_IN_OOS)
2. `oos_pf > 1.0` — strategy must be profitable out-of-sample (IS/OOS split at 2019)
3. `bootcamp_score > 55` — composite score combining PF, consistency, trade count, DD
4. `leader_trades >= 60` — minimum statistical significance (~3.5 trades/year over 18 years)
5. **Dedup**: same refined strategy name + market → keep highest bootcamp_score (prevents duplicates from different strategy families finding the same parameter set)
6. **Cap**: top 30 by bootcamp_score (prevents combinatorial explosion downstream)

**Output**: ~24-30 candidate strategies as list of dicts

**Potential improvement areas**:
- The bootcamp_score_min=55 and candidate_cap=30 are somewhat arbitrary
- No filtering by recent performance (last 12 months PF) at this stage
- No filtering by max drawdown at this stage — DD only enters at Stage 5 (MC simulation)

---

### Stage 2: Build Return Matrix

**Input**: Candidate list from Stage 1 + `strategy_returns.csv` files from each market's run output

**Process**:
- For each candidate, finds the corresponding `strategy_returns.csv` file in `Outputs/runs/`
- Matches the strategy's column in the returns file (by leader_strategy_name or approximate match)
- Builds a combined DataFrame indexed by exit_time, one column per strategy
- Each cell = dollar PnL of that strategy's trade on that date (0.0 on non-trade days)
- Time range: 2008-2026 (~6,600 trading days)

**Output**: `pd.DataFrame` with shape (6600 × N_candidates), daily PnL per strategy

**Important note**: The returns data is from futures backtests ($250K notional). Dollar PnL values are pre-conversion — they get scaled to account size during Monte Carlo via `_scale_trade_pnl()` which divides by source_capital ($250K) then multiplies by step_balance.

**Known issue**: Some S54 strategies don't have matching `strategy_returns.csv` files. An approximate matching fallback was added but isn't perfect.

---

### Stage 3: Correlation Matrix

**Input**: Return matrix from Stage 2

**Process**:
- Computes pairwise Pearson correlation on daily PnL columns
- Uses `pd.DataFrame.corr()` on the full return matrix

**Output**: N×N correlation matrix

**Stage 3b: Pre-sweep Correlation Dedup**
- If two strategies have correlation > 0.70, keeps only the one with higher bootcamp_score
- Prevents highly correlated strategies from both entering the combinatorial sweep

---

### Stage 4: Sweep Combinations

**Input**: Surviving candidates + correlation matrix + return matrix

**Process**:
- Generates all C(n, k) combinations where k ranges from n_min=4 to n_max (auto-capped to keep total combos < 500,000)
- For each combination, applies rejection gates:

**Rejection gates (any fails = combo rejected)**:
1. **Max correlation**: No pair in the combo can have Pearson correlation > 0.40
2. **Max per market**: No more than 2 strategies from the same market (e.g., max 2 NQ strategies)
3. **Equity index cap**: Max 3 strategies from {ES, NQ, RTY, YM} combined
4. **Metals cap**: Max 2 strategies from {GC, SI, HG} combined
5. **Drawdown overlap**: For each pair, computes the fraction of days both strategies are simultaneously in >2% drawdown. Rejects combo if max pairwise overlap > 0.30 (30%)

**Scoring**: Surviving combos are scored by:
- `diversity_score = market_diversity × 0.4 + direction_mix × 0.3 + logic_diversity × 0.3`
  - market_diversity = unique markets / n_strategies
  - direction_mix = 1.0 if combo has both long and short strategies, else 0.0
  - logic_diversity = unique strategy types / n_strategies
- `avg_oos_pf` = mean OOS PF across combo strategies
- `composite_score = diversity_score × 100 + avg_oos_pf × 10`

**Output**: Top 50 combos ranked by composite_score, passed to Monte Carlo

**Potential improvement areas**:
- Composite score heavily weights diversity over pure profitability
- No Sharpe ratio or Calmar ratio in scoring
- DD overlap uses a fixed 2% threshold — could be dynamic based on program DD limit
- The correlation gate uses Pearson on daily PnL which can be misleading for strategies that trade rarely

---

### Stage 5: Portfolio Monte Carlo

**Input**: Top 50 combos + individual strategy trade lists + PropFirmConfig

**Process (per combo, 5000 simulations)**:
1. For each simulation run:
   a. Independently shuffle each strategy's historical trade list (preserves trade-level PnL distribution)
   b. Interleave all shuffled trades via round-robin across strategies (simulates concurrent execution)
   c. Apply contract weight scaling to each trade's PnL
   d. Scale trade PnL from backtest capital ($250K) to program step balance
   e. Run combined trade sequence through `simulate_challenge()`:
      - Walk through trades sequentially
      - Track running equity, max equity, drawdown
      - Check if profit target hit before max DD breached
      - For multi-step programs (Bootcamp 3 steps), cascade through steps
2. Collect pass/fail rates per step, worst drawdown distribution, trades-to-fund

**Key parameters**:
- `n_sims = 5000` (initial MC)
- `source_capital = 250000` (backtest capital base for PnL scaling)
- Trades are dollar PnL values, not percentage returns
- The shuffle-and-interleave approach preserves each strategy's edge characteristics while randomizing sequencing

**Output per combo**: pass_rate, step1/2/3 pass rates, P95 worst DD, median trades to fund, P75 trades to fund

**Potential improvement areas**:
- Round-robin interleaving doesn't model calendar time — in reality, strategies trade at different frequencies and the timing of concurrent drawdowns matters
- The PnL scaling from $250K to smaller accounts ($5K, $20K) may undersize micro contracts
- No daily DD tracking in the MC (The5ers High Stakes has 5% daily DD limit)
- The shuffle assumes trades are i.i.d. — doesn't capture regime clustering or serial correlation

---

### Stage 6: Optimise Sizing (Contract Weights)

**Input**: Top 10 portfolios from MC + return matrix + trade lists

**Process**:
- Grid search over contract weight options: [0.1, 0.2, 0.3, 0.5, 0.7, 1.0] per strategy
- Each weight maps to micro contracts (0.1 = 1 micro, 0.2 = 2 micros, etc.)
- For each weight combination:
  - Run MC with 1000 sims (speed) using those weights
  - Track pass_rate and median_trades_to_fund
- Objective: **minimize median_trades_to_fund** subject to pass_rate >= 0.40
- After finding best weights, run final 10,000-sim MC for accurate rates

**Output per portfolio**: optimised micro contracts per strategy, final pass rates, DD stats, time-to-fund estimates

**Known bug**: The optimizer currently has no hard DD constraint — it can pick weights that push DD beyond the program limit if doing so reduces trades-to-fund. This causes oversized positions on larger accounts ($100K+).

---

## Current Best Portfolios

### High Stakes $5K (Portfolio #3 — chosen for live trading)
| Strategy | Market | Timeframe | Type | Micros |
|----------|--------|-----------|------|--------|
| RefinedMR_HB5_ATR0.4_DIST0.4_MOM0 | NQ | Daily | Mean Reversion (LONG) | 1 |
| RefinedTrend_HB1_ATR0.75_VOL0.0_MOM0 | YM | Daily | Short Trend (SHORT) | 1 |
| RefinedMR_HB5_ATR0.4_DIST0.4_MOM0 | GC | Daily | Mean Reversion (LONG) | 1 |
| RefinedMR_HB16_ATR0.4_DIST1.0_MOM0 | NQ | 15m | Mean Reversion (LONG) | 1 |

- **Pass rate**: 87-99% (varies by selector run)
- **P95 DD**: 6.5-6.9% (vs 10% limit)
- **Median time to fund**: ~13-19 months
- **Correlation**: near-zero pairwise

### Bootcamp $250K (Portfolio #2)
| Strategy | Market | Timeframe | Type | Micros |
|----------|--------|-----------|------|--------|

| RefinedMR_HB5_ATR0.4_DIST0.4_MOM0 | NQ | Daily | Mean Reversion (LONG) | 1 |
| RefinedTrend_HB1_ATR0.75_VOL0.0_MOM0 | YM | Daily | Short Trend (SHORT) | 1 |
| RefinedBreakout_HB20_ATR0.5_COMP0.6_MOM0 | GC | 30m | Breakout (LONG) | 1 |
| RefinedMR_HB16_ATR0.4_DIST1.0_MOM0 | NQ | 15m | Mean Reversion (LONG) | 1 |

- **Pass rate**: 91.8% (all 3 steps)
- **Step pass rates**: 97.5% → 94.4% → 91.8%
- **P95 DD**: 6.1% (vs 5% limit — tight)
- **Median time to fund**: ~24 months
- **3 of 4 strategies are shared with High Stakes portfolio**

---

## Data Files

| File | Description |
|------|-------------|
| `Outputs/ultimate_leaderboard_bootcamp.csv` | 379 strategies with quality flags, PF, IS/OOS splits, bootcamp scores |
| `Outputs/runs/*/strategy_returns.csv` | Per-trade daily PnL for each strategy in each market sweep |
| `Outputs/runs/*/strategy_trades.csv` | Individual trade records with entry/exit prices, bars held |
| `Outputs/portfolio_selector_report.csv` | Final output: ranked portfolios with pass rates, DD, time-to-fund |
| `modules/portfolio_selector.py` | The 6-stage pipeline (~1300 lines) |
| `modules/prop_firm_simulator.py` | PropFirmConfig classes and simulate_challenge() |
| `modules/cfd_mapping.py` | Futures-to-CFD symbol mapping |

---

## What I Want From You (Other LLMs)

1. **Pipeline critique**: Are there flaws in the 6-stage approach? Missing stages? Wrong ordering?

2. **Scoring improvements**: The composite score (diversity × 100 + avg_oos_pf × 10) is crude. What's a better way to score and rank portfolios before MC? Should we include Sharpe, Calmar, or tail-risk metrics?

3. **Correlation alternatives**: Pearson on daily PnL is problematic for strategies that trade rarely (mostly zeros). Should we use rank correlation (Spearman/Kendall)? Return-on-trade correlation? Rolling correlation? Copula methods?

4. **DD overlap methodology**: We compute binary "in drawdown > 2%" overlap. Is there a better way to measure concurrent drawdown risk? Should the threshold scale with program DD limits?

5. **Monte Carlo realism**: The shuffle-and-interleave approach doesn't model calendar time. Trades from different strategies that historically occurred in the same week get randomly separated. Is there a better simulation approach that preserves temporal clustering?

6. **Sizing optimizer**: Currently minimizes trades-to-fund with a pass_rate floor. Should it instead minimize P95 DD? Maximize Calmar ratio? Use Kelly criterion? The grid search over [0.1, 0.2, 0.3, 0.5, 0.7, 1.0] is coarse — worth refining?

7. **Missing risk metrics**: We don't compute max consecutive losing days, max losing streak, or daily DD (The5ers High Stakes has a 5% daily DD limit that we approximate but don't simulate properly). What risk metrics should we add?

8. **Portfolio construction alternatives**: Instead of enumerate-and-score, should we use:
   - Mean-variance optimization (Markowitz)?
   - Risk parity?
   - Hierarchical risk parity (HRP)?
   - Sequential addition (greedy algorithm)?
   - Multi-objective optimization (Pareto frontier)?

9. **Out-of-sample validation**: Our IS/OOS split is fixed at 2019. Should we use walk-forward? K-fold? Anchored walk-forward? The strategies were already selected using the same OOS period, which creates potential look-ahead bias in portfolio construction.

10. **Any other ideas**: What am I missing? What would you do differently if you were building this from scratch?

---

## Constraints to Keep in Mind

- Strategies trade MICRO contracts only (0.01 lots on CFDs)
- Max 1 position per strategy at a time
- The5ers has no time limit — only DD matters
- Overnight holds are allowed
- No HFT, no latency arbitrage, visible stop losses required
- We cannot change the strategies themselves — only select and size them
- The strategy pool is fixed at 379 — we pick from what we have
- All backtests use the same IS/OOS split (pre/post 2019)
- Dollar PnL values are from $250K notional futures backtests, scaled to account size
