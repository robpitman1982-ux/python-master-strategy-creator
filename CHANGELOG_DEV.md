# CHANGELOG_DEV.md — Session-by-session development log

> Each session adds an entry at the TOP of this file.
> Format: date, what was done, what's next.

---

## 2026-03-16 — Session 1: Foundation hardening

**What was done**:
- Added `quality_score` (0.0–1.0 continuous metric) to `engine.py` results; weighted on avg PF strength, IS/OOS balance, trade count confidence, recent PF, OOS trade presence
- Added `BORDERLINE` suffix detection: any ROBUST/STABLE/MARGINAL flag within 0.05 of a threshold boundary gets `_BORDERLINE` appended
- Propagated `quality_score` through sweep results (all 3 strategy types) and `RefinementResult` dataclass in `refiner.py`
- Capped promotion gate at max 20 candidates using composite ranking (quality_score × 0.4 + oos_pf × 0.3 + trades/yr × 0.3)
- Added `estimate_compute_budget()` — prints eval count and estimated minutes before sweep and refinement
- Added `deduplicate_promoted_candidates()` — removes near-duplicates by matching total_trades + PnL within 1%

**Output changes vs baseline**:
- Trend family: was 93 promoted → now capped at 20
- BORDERLINE flags will appear on strategies near PF thresholds
- Compute budget printed before each sweep and refinement stage
- Dedup report printed after promotion gate

**Next session priorities**:
1. Walk-forward validation as alternative to fixed IS/OOS split
2. Make dataset path configurable (prep for multi-timeframe)
3. Add yearly consistency check (flag strategies that lose money >60% of years)
4. Consider Bayesian optimization (Optuna) for refinement grid

---

## 2026-03-16 — Session 0: Project review and workflow setup

**What happened**:
- Full pipeline review with Claude (claude.ai project chat)
- Analyzed first run outputs: trend (REGIME_DEPENDENT), MR (STABLE), breakout (BROKEN_IN_OOS)
- Identified key issues: quality flag boundary logic, loose promotion gate, brute-force refinement grid
- Created CLAUDE.md for session continuity
- Created this CHANGELOG_DEV.md
- Established GitHub commit workflow

**Key findings from first run**:
- ES 60m data: 107,149 bars, 2008-01-02 to 2026-03-04
- Trend: 672 combos → 93 promoted → best refined PF 1.13, IS PF 0.83 (below 1.0), OOS PF 1.71
- MR: 792 combos → 27 promoted → best refined PF 1.42, IS PF 1.09, OOS PF 1.86
- Breakout: 582 combos → 37 promoted → best refined PF 0.82, BROKEN_IN_OOS
- Correlation between trend & MR: -0.0005 (excellent)

**Next session priorities**:
1. Fix quality flag boundary logic (make continuous/scored)
2. Tighten promotion gate or add secondary screening
3. Add compute budget estimator
4. Add filter-combo deduplication before refinement
