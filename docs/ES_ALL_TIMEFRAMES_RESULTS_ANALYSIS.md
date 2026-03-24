# ES ALL-TIMEFRAMES RESULTS ANALYSIS

> Session 27 Part B results review based on the result files currently present in the repo.
> Important context: this is a partial snapshot, not the full four-timeframe download.
>
> Available now:
> - `Outputs/ES_60m/family_leaderboard_results.csv`
> - `Outputs/ES_60m/family_summary_results.csv`
> - `Outputs/ES_60m/portfolio_review_table.csv`
> - `Outputs/ES_60m/correlation_matrix.csv`
>
> Missing in the current repo snapshot:
> - `Outputs/master_leaderboard.csv`
> - `Outputs/ES_daily/family_leaderboard_results.csv`
> - `Outputs/ES_30m/family_leaderboard_results.csv`
> - `Outputs/ES_15m/family_leaderboard_results.csv`

---

## Overall Summary

From the result files currently available in the repo, there is **1 accepted strategy**:
- timeframe: **ES 60m**
- family: **mean_reversion**
- leader: `RefinedMR_HB12_ATR0.5_DIST1.2_MOM0`
- quality flag: **ROBUST**

Confirmed findings from the available files:
- No daily result file is present yet, so the "did trend work on daily?" question is still unanswered.
- No 30m or 15m leaderboard files are present yet, so there is no multi-timeframe comparison available yet.
- No `master_leaderboard.csv` is present yet, so cross-timeframe ranking cannot be completed.

What we can say with confidence today:
- **Mean reversion succeeded on ES 60m.**
- **Trend and breakout outcomes are not available in the downloaded repo snapshot for the all-timeframe run.**
- The current repo does **not** yet contain the evidence needed to claim success or failure for the broader all-timeframe sweep.

---

## Per-Timeframe Breakdown

### ES daily

Result file status:
- `Outputs/ES_daily/family_leaderboard_results.csv` not present

Assessment:
- No downloaded daily family leaderboard is available yet.
- Trend-on-daily remains the biggest open question.

### ES 60m

Result file status:
- `Outputs/ES_60m/family_leaderboard_results.csv` present

Available family row:

| Family | accepted_final | quality_flag | leader_pf | is_pf | oos_pf | leader_trades | is_trades | oos_trades | leader_net_pnl | Best filter combo |
|--------|----------------|--------------|-----------|-------|--------|---------------|-----------|------------|----------------|------------------|
| mean_reversion | True | ROBUST | 1.71 | 1.67 | 1.80 | 61 | 42 | 19 | 83878.44 | `DistanceBelowSMAFilter,TwoBarDownFilter,ReversalUpBarFilter` |

What the family summary adds:
- sweep combinations tested: 792
- promoted candidates: 9
- accepted refinement rows: 720
- best combo PF / net PnL: `1.51 / 34448.62`
- best refined PF / net PnL: `1.71 / 83878.44`

Important note:
- The current `ES_60m/family_leaderboard_results.csv` contains only the accepted MR row.
- There are no trend or breakout rows in this downloaded snapshot, so their current status cannot be confirmed from the required per-timeframe leaderboard file.

### ES 30m

Result file status:
- `Outputs/ES_30m/family_leaderboard_results.csv` not present

Assessment:
- No downloaded 30m family leaderboard is available yet.

### ES 15m

Result file status:
- `Outputs/ES_15m/family_leaderboard_results.csv` not present

Assessment:
- No downloaded 15m family leaderboard is available yet.

### Trade count comparison across timeframes

Not enough files are present to compare trade counts across daily, 60m, 30m, and 15m.

What is available:
- ES 60m accepted leader trades: 61 total
- ES 60m IS/OOS split: 42 IS, 19 OOS

So the lower-timeframe hypothesis remains untested in the current repo snapshot.

---

## Master Leaderboard Review

`Outputs/master_leaderboard.csv` is not present, so a proper cross-timeframe ranking cannot be performed yet.

Current practical substitute from the available files:
- top confirmed accepted strategy in the repo snapshot is `RefinedMR_HB12_ATR0.5_DIST1.2_MOM0`
- timeframe: ES 60m
- family: mean_reversion
- quality flag: ROBUST
- PF: 1.71
- net PnL: 83878.44

Because only one accepted downloaded strategy is currently available in the expected Session 27 result locations:
- there is no top-5 list yet
- there are no repeated strategies across multiple timeframes to compare yet

---

## Correlation Analysis

`Outputs/ES_60m/correlation_matrix.csv` exists, but it contains only one strategy:
- `20260317_1551_ES_60m_RefinedMR_HB12_ATR0.5_DIST1.2_MOM0`

Matrix result:
- self-correlation = `1.0`

Implication:
- there are no strategy pairs to compare
- no high-correlation warning can be issued yet
- no low-correlation portfolio pair can be identified yet

This reinforces the bigger issue: the current downloaded snapshot is still a **single-strategy** view, not a portfolio candidate set.

---

## Trade Count Assessment

Using the accepted ES 60m family leader:
- total trades: 61
- dataset span: 2008-01-02 to 2026-03-04
- approximate trades/year: **3.4**

Classification:
- `< 5 trades/year` -> **Bootcamp Supplemental**

Interpretation:
- The edge looks real enough to be useful.
- The trade count is still too thin to be a strong standalone Bootcamp core strategy.
- This remains consistent with the roadmap concern that trade frequency is one of the major system weaknesses.

Portfolio-review note:
- `portfolio_review_table.csv` shows 54 reconstructed trades, full PF 1.39, OOS PF 1.24, and Monte Carlo max DD 99th percentile of 79760.17.
- That keeps the strategy interesting, but still not frequent enough to carry the whole Bootcamp effort alone.

---

## Implications for Roadmap

### 1. Exit architecture is still urgent

The only confirmed success in the available snapshot is mean reversion.
That does not prove trend or breakout failed everywhere, but it does mean the repo still lacks
any confirmed evidence that those families are working in the current all-timeframe campaign.

So the roadmap call remains sound:
- trailing stops
- profit targets
- signal exits

are still the highest-value engine changes.

### 2. Trend subfamily split remains likely important

Daily trend was the big test, and that file is not downloaded into the repo yet.
Until we see daily results, trend remains unresolved rather than cleared.

That keeps the trend split idea alive:
- pullback continuation trend
- momentum/breakout trend

### 3. Trade-count problem is still real

The one confirmed accepted strategy is still only around 3.4 trades/year.
That means filter-library expansion and/or lower-timeframe success are still needed if the goal is
to build Bootcamp-core strategies rather than supplemental edges.

### 4. Lower timeframes are still the main open thesis

The repo snapshot does not yet contain 30m or 15m leaderboard files, so the key question remains:
- do lower timeframes finally produce enough trade frequency?

That is still the most important operational result to retrieve and analyse.

### 5. Instrument expansion is still likely necessary

With only one confirmed accepted strategy and no portfolio pair correlations yet, there is still
no evidence that ES alone will provide the diversification target.

That keeps CL and NQ expansion highly relevant once the current result bundle is fully available.

---

## Bottom Line

The current repo snapshot does **not** yet support a full "ES all timeframes" analysis.

What it does support is this narrower conclusion:
- ES 60m mean reversion produced one accepted ROBUST refined strategy
- that strategy is statistically interesting but trade-thin
- there is still no downloaded evidence here for daily trend success, lower-timeframe trade-count expansion, or a true multi-strategy portfolio set

Operationally, the next best move is still:
1. retrieve the missing all-timeframe result files
2. inspect the master leaderboard
3. then move into exit architecture work with the full evidence in hand
