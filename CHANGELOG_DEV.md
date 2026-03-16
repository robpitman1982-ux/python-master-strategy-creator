# CHANGELOG_DEV.md — Session-by-session development log

> Each session adds an entry at the TOP of this file.
> Format: date, what was done, what's next.

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
