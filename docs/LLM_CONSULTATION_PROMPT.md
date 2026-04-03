# LLM Consultation Prompt — Strategy Discovery Engine
## Next 3 Sessions After Dashboard Fix + Shorts

---

## Your Role

You are being asked to design the next three development sessions for an automated
algorithmic strategy discovery engine. The owner is building toward a portfolio of
~6 uncorrelated futures strategies for a prop firm challenge ($25K account, The5ers
$250K Bootcamp: 6% profit target, 5% max drawdown).

Read the full context below carefully before proposing sessions.

---

## What Has Already Been Built (Do Not Redesign These)

The engine already has:

1. **Three strategy families**: Mean Reversion, Trend, Breakout — each with 10 filters
2. **Vectorised filter evaluation** (~50x speedup via numpy mask() methods)
3. **Full pipeline**: sanity check → filter combo sweep → promotion gate → parameter
   refinement grid → quality scoring → leaderboard → portfolio evaluation
4. **Quality flags**: ROBUST, STABLE_BORDERLINE, REGIME_DEPENDENT, MARGINAL, BROKEN_IN_OOS
5. **Bootcamp scoring** (0-100, prop-firm aligned: weights OOS PF, drawdown, consistency)
6. **IS/OOS split**: pre-2019 = In-Sample, post-2019 = Out-of-Sample on 18 years of data
7. **Cloud infrastructure**: GCP n2-highcpu-96, 38 minutes for full 5-TF ES sweep, ~$2
8. **Ultimate leaderboard**: cumulative cross-run CSV, auto-regenerated on download
9. **Streamlit dashboard**: live monitoring + results explorer

**Sessions being done right now (before your 3):**
- Session A: Fix and modernise the Streamlit dashboard
- Session B: Add short-side strategies (mirror logic of long entries — trend shorts,
  MR shorts on overbought bars, breakout shorts on downside breaks)

**Your job: design the 3 sessions that come AFTER those two.**

---

## Current Results (What the Engine Has Found So Far)

On ES futures across 5 timeframes:
- 9 accepted strategies, 2 ROBUST (30m MR and 60m MR)
- Best filter combos: DistanceBelowSMA + TwoBarDown + ReversalUpBar (30m/60m MR)
- Daily MR: DownClose + LowVolatilityRegime + StretchFromLongTermSMA (high PnL)
- Trade counts are thin on some strategies (60m MR: only 61 trades / 18 years)
- 5m timeframe produced zero results (too noisy)

Current search space:
- MR: C(10,3..6) = 792 filter combinations per timeframe
- Trend: C(10,4..6) = 672 combinations
- Breakout: C(10,3..5) = 582 combinations
- Total per full run: ~2,046 sweep combos + ~43,560 refinement variants

**Known gaps / weaknesses to address:**
- Thin trade counts on ROBUST strategies (60m MR = 3.4 trades/year)
- Only long-side tested so far
- Only ES tested so far (CL, NQ, GC planned)
- Portfolio reconstruction gap: only 2 of 9 accepted strategies make it into
  the portfolio evaluator's correlation/MC analysis
- Breakout strategies have decade-long drawdown periods
- Regime dependency concentration (4 of 9 strategies are REGIME_DEPENDENT)

---

## Architecture Context for Your Proposals

### Filter system
Each filter is a Python class with:
- `passes(data, i)` → bool (bar-by-bar evaluation)
- `mask(data)` → numpy bool array (vectorised, fast)

All 30 existing filters already have vectorised masks. New filters need both methods.

### Adding new filters
New filters slot directly into the existing families by being added to a family's
`get_filter_classes()` list. The combinatorial sweep automatically includes them.
Each new filter added to a 10-filter pool of size N increases combos from C(N,k) to
C(N+1,k) — manageable growth.

### Strategy subtypes (being added in Session A/B)
Instead of one flat pool per family, we are splitting each family into 3 named subtypes
with 6-8 semantically coherent filters each. This:
- Reduces search space ~4x while being more targeted
- Makes it safe to add more filters (they slot into specific subtypes)
- Example MR subtypes: VolatilityDip, MomentumExhaustion, TrendPullback

### Refinement grid
After the sweep promotes candidates, a parameter grid is tested:
- hold_bars, stop_distance (ATR), min_avg_range, momentum_lookback
- Current grid: brute force (up to 288 variants per MR candidate)
- All parameters auto-scale with timeframe

### Exit architecture
Currently implemented exits: time_stop, trailing_stop, profit_target, signal_exit
Each family declares its preferred exit types. Trend/Breakout prefer trailing stops,
MR prefers profit_target or signal_exit.

---

## Constraints to Respect

1. **Single VM limit**: 100 vCPU global quota cap — one n2-highcpu-96 at a time
2. **Cost target**: keep full runs under ~$5 (currently $2 on-demand, $0.45 SPOT)
3. **Runtime target**: keep full ES 5-TF runs under 60 minutes
4. **No live trading yet**: research pipeline only
5. **Data**: TradeStation CSV exports. CL, NQ, GC not yet exported but ready to add
6. **Language**: Python 3.11+, ProcessPoolExecutor for parallelism
7. **No ML models yet**: pure rule-based filters only (this may change but keep simple)
8. **Test suite**: 100+ tests must stay passing after every session

---

## What We Want From You

**Design 3 concrete, executable development sessions** covering the most valuable
next steps after dashboard modernisation and shorts are done.

For each session provide:

1. **Session title and theme** (one sentence)
2. **Motivation** — why this session, why in this order
3. **Specific deliverables** — what files change, what new modules are created,
   what new outputs the engine produces
4. **Technical approach** — enough detail that a developer could implement it
   (not pseudocode, but concrete architectural decisions)
5. **Acceptance criteria** — how do we know the session succeeded?
6. **Estimated complexity** — simple / medium / complex
7. **Risk or gotchas** — what could go wrong

---

## Prioritisation Guidance

The owner's highest priorities in rough order:
1. Finding more robust strategies (currently only 2 ROBUST out of 9)
2. Increasing trade counts on ROBUST strategies (too thin for live deployment)
3. Portfolio construction (selecting the best 3-6 uncorrelated strategies for Bootcamp)
4. Expanding to new instruments (CL, NQ) for decorrelation
5. Making the search smarter (reduce time on unproductive areas)

The owner is NOT focused on:
- UI polish beyond functional dashboard
- Live trading infrastructure
- Walk-forward validation (noted as future but not urgent)
- Machine learning or neural networks

---

## Format of Your Answer

Please provide exactly 3 sessions in this format:

---
SESSION [N]: [TITLE]
Theme: [one sentence]
Why now: [2-3 sentences]
Deliverables: [bullet list]
Technical approach: [paragraph or bullet list with real technical detail]
Acceptance criteria: [bullet list of testable outcomes]
Complexity: [Simple / Medium / Complex]
Risks: [bullet list]
---

Be specific and practical. Avoid vague suggestions like "improve the scoring system."
Instead say exactly which file changes, what the new column is called, what the
threshold values should be, and what test confirms it works.

If you think the priority order above is wrong, say so and explain why before
giving your sessions.

Good luck.
