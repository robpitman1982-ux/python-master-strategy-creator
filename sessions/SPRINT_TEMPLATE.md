# SPRINT_NN — <descriptive sprint name>

> **Pre-registration is mandatory.** Commit this file BEFORE any data is touched.
> Once committed, the parameter grid + verdict criteria are FROZEN for this sprint.
> Mid-sprint changes ("let's also try X") become the next sprint, not an amendment.

**Sprint number:** NN
**Date opened:** YYYY-MM-DD
**Date closed:** ___ (filled in at sprint-end)
**Operator:** Rob
**Author:** Claude Code on Latitude

---

## 1. Sprint goal

One sentence stating the question this sprint answers. Examples:

- "Does the BH-FDR-tightened promotion gate produce a smaller but more robust set of accepted strategies on ES daily-only?"
- "Does the mean-reversion-vol-dip subtype generalise to forex markets (EC, JY, BP, AD)?"
- "Does walk-forward validation reject ≥30% of the strategies that currently pass the static IS/OOS gate?"

## 2. Mechanism plausibility

Before running anything: what is the prior reason to believe this question has a useful answer?

A weak prior is fine, but say so. State the mechanism that you expect would produce the result, and the mechanism by which it could fail.

## 3. Frozen parameter grid

Every parameter that could move the result must be listed here. Anything not listed defaults to `config.yaml`. Mid-sprint changes to anything in this section are FORBIDDEN.

| Parameter | Value | Source |
|-----------|-------|--------|
| Markets | ES | sweep config |
| Timeframes | daily, 60m, 30m, 15m | sweep config |
| Strategy types | all 12 families | engine default |
| `promotion_gate.min_profit_factor` | 1.0 | sweep config |
| `promotion_gate.min_trades` | 50 | sweep config |
| `promotion_gate.bh_fdr_alpha` | 0.05 (or null = disabled) | sweep config |
| `pipeline.oos_split_date` | 2019-01-01 | sweep config |
| Walk-forward gate (post-promotion) | mean_test_t≥1.0, min_test_t≥-0.5 | new |
| DSR threshold (portfolio selector) | DSR > 0.5 | portfolio selector config |
| Random-flip null gate (portfolio selector) | z ≥ 2.0, n_resamples=5000, seed=42 | new |

## 4. Verdict definitions

The sprint produces ONE of these verdicts. Define what evidence supports each before running.

| Verdict | Condition |
|---------|-----------|
| **CANDIDATES** | Some accepted strategies pass all enabled gates and survive walk-forward. Promote to next-stage validation (live paper, capacity sizing). |
| **NO EDGE** | Zero strategies survive after gates. The sprint hypothesis is rejected. Document and close. |
| **SUSPICIOUS** | Many strategies pass — too many. Likely overfit or a gate failure. Halt promotion; investigate the gate. |
| **BLOCKED** | Sprint cannot complete (data missing, infra failure, etc). Document the blocker. |

## 5. Methodology checklist

Items to confirm before declaring the sprint clean:

- [ ] All test suites green pre-launch (`python -m pytest tests/ -x`)
- [ ] Sweep config committed BEFORE data touched
- [ ] Output dir is fresh (no stale results pollute the run)
- [ ] All cluster hosts available and quiet (no betfair contention)
- [ ] Walk-forward + DSR + random-flip null modules validated against this sprint's data shape
- [ ] Pre-registered verdict definitions match what the data reveals

## 6. Anti-convergence consultation (optional)

If consulting external LLMs (ChatGPT, Gemini), capture what they said about this sprint BEFORE the run, not after.

| LLM | Recommendation | Convergence? |
|-----|---------------|--------------|
| ChatGPT-5 | _their take_ | _y/n with the other consult_ |
| Gemini 2.5 Pro | _their take_ | _y/n with the other consult_ |

Heuristic from betfair-trader project (n=8, treat carefully): when LLMs converge, the recommendation tends to be anti-alpha. When they diverge, follow the disagreement to the underlying mechanism question.

## 7. Per-probe Gate-J criteria (if running multiple probes)

For multi-probe sprints, list each probe with its own pass criteria. For monolithic sweep sprints (one big sweep), skip this section.

## 8. Result (filled in at sprint close)

**Verdict:** _CANDIDATES / NO EDGE / SUSPICIOUS / BLOCKED_

### Quantitative summary
- Combos swept: _n_
- Combos passing promotion gate: _n_
- Combos passing BH-FDR: _n_
- Strategies on master leaderboard: _n_
- Strategies passing DSR > 0.5: _n_
- Strategies passing walk-forward gate: _n_
- Strategies passing random-flip null z ≥ 2.0: _n_
- Final accepted set: _list_

### Cross-LLM consultation (if held post-sprint)
What did external LLMs flag in the result that I missed? Did the anti-convergence rule predict anything?

### Lessons learned
What would I change about the sprint structure or gates next time?

### Commits / branches
- Pre-registration commit: _SHA_
- Sprint-close commit: _SHA_
- Output directory: _path_

---

## Append to LOG.md after sprint close

Add a single LOG.md entry summarising the sprint with:
- date, sprint name, verdict
- one-line outcome
- pointer to this sprint file
- next sprint hint
