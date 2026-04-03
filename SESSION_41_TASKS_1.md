# SESSION 41 TASKS — Widen exit grids + validate performance fix

## Date
2026-03-27

## Goal
Two things:
1. **Validate Session 40 perf fix** — check logs and runtime from the run that just completed
2. **Widen trailing stop / profit target grids** — the current ATR values are too tight for ES, choking trend trades on noise

### Why the grid matters
Session 29 exit validation proved trailing stops were tested and lost to time_stop on ES trend. But the trailing_stop_atr grid was [1.0, 1.5, 2.0, 2.5]. On daily ES where ATR is 40–80 points:
- 1.0x ATR = 40–80 pts = $2,000–$4,000 trailing distance
- 2.5x ATR = 100–200 pts = $5,000–$10,000

ES regularly whipsaws 40+ points intraday and resumes the trend. A $2k–$4k trailing stop gets stopped out on noise. Even $10k is borderline tight for a multi-day trend hold. The trailing stop grid needs values like 3.5x, 5.0x, 7.0x ATR to give trend trades room to breathe.

---

## STEP 1 — Validate Session 40 performance fix

### What to check

**A) Download the latest run results:**
```bash
python cloud/download_run.py --latest
```

**B) Check the engine log for caching evidence:**

Look in the run's log output for these lines (they prove the caching engaged):
```
Loading data once for ES_5m
Precomputing superset features for 15 families
   SMA lengths: [...]
   Precomputed XX columns on 1,276,712 rows in XX.Xs
```

If those lines are missing, the caching didn't deploy — investigate why.

**C) Check per-timeframe elapsed times:**

Look in status.json or the family summary CSVs for elapsed times. Compare against the old baseline:
- Old ES_daily: 80s
- Old ES_60m: 766s (12.8 min)
- Old ES_30m: 1715s (28.6 min)
- Old ES_15m: 1271s (21.2 min)
- Old ES_5m: very long, multiple 5-min setup gaps per family

If ES_5m elapsed time dropped significantly (e.g., from 60+ min to under 20 min), caching is working.

**D) Check for concurrent family execution evidence:**

Look for log lines like:
```
Family split: X large (sequential), Y small (concurrent)
Running Y small families with concurrency=3
```

**E) Compare leaderboard:**

Compare the new ultimate_leaderboard_bootcamp.csv against the previous one. Strategy quality should be identical or better (same code, same data, just faster execution). If strategies changed, investigate — the caching may have introduced a subtle data-sharing issue.

### No code changes in this step — just validation.

---

## STEP 2 — Widen trailing stop ATR grid for trend

### Files to modify
- `modules/strategy_types/trend_strategy_type.py`

### What to change

Find `get_exit_parameter_grid_for_combo()` in the trend strategy type. It currently returns:

```python
"trailing_stop_atr": [1.0, 1.5, 2.0, 2.5],
```

Change to:

```python
"trailing_stop_atr": [1.5, 2.5, 3.5, 5.0, 7.0],
```

### Why these values

| ATR mult | Daily ES (40-80pt ATR) | 60m ES (8-20pt ATR) | 30m ES (5-12pt ATR) |
|----------|------------------------|---------------------|---------------------|
| 1.5x | $3k-$6k | $600-$1.5k | $375-$900 |
| 2.5x | $5k-$10k | $1k-$2.5k | $625-$1.5k |
| 3.5x | $7k-$14k | $1.4k-$3.5k | $875-$2.1k |
| 5.0x | $10k-$20k | $2k-$5k | $1.25k-$3k |
| 7.0x | $14k-$28k | $2.8k-$7k | $1.75k-$4.2k |

At 5.0x ATR on daily, the trailing stop is $10k-$20k from the highest high — enough room for a real multi-day trend to develop without getting whipsawed. At $250K capital with 5% max DD ($12,500), a 5.0x ATR stop on a single trade is within risk limits.

7.0x ATR is aggressive but worth testing — some trend strategies need very wide trailing stops to capture the full move.

Dropped 1.0x because it was consistently too tight and wasted compute.

### Test
```bash
python -m pytest tests/ -v
```

### Commit
```bash
git commit -m "perf: widen trend trailing stop ATR grid [1.5, 2.5, 3.5, 5.0, 7.0]

- Old grid [1.0, 1.5, 2.0, 2.5] was too tight for ES daily (1.0x = $2k-$4k)
- Session 29 validation showed trailing stops losing to time_stop with tight grid
- New grid gives trends room to breathe: 5.0x on daily = $10k-$20k trailing distance
- Dropped 1.0x (always too tight), added 3.5x, 5.0x, 7.0x"
```

---

## STEP 3 — Widen trailing stop ATR grid for breakout

### Files to modify
- `modules/strategy_types/breakout_strategy_type.py`

### What to change

Find `get_exit_parameter_grid_for_combo()` in the breakout strategy type. Change:

```python
"trailing_stop_atr": [1.0, 1.5, 2.0, 2.5],
```

To:

```python
"trailing_stop_atr": [1.5, 2.5, 3.5, 5.0],
```

Breakout doesn't need as wide as trend (breakouts resolve faster), but 1.0x was still too tight. Dropped 1.0x and 2.0x, added 3.5x and 5.0x.

### Test
```bash
python -m pytest tests/ -v
```

### Commit
```bash
git commit -m "perf: widen breakout trailing stop ATR grid [1.5, 2.5, 3.5, 5.0]"
```

---

## STEP 4 — Widen profit target ATR grid for mean reversion

### Files to modify
- `modules/strategy_types/mean_reversion_strategy_type.py`

### What to change

Find `get_exit_parameter_grid_for_combo()` in the MR strategy type. Change:

```python
"profit_target_atr": [0.5, 0.75, 1.0, 1.25, 1.5],
```

To:

```python
"profit_target_atr": [0.5, 1.0, 1.5, 2.0, 3.0],
```

MR profit targets can be wider too — a strong mean reversion can snap back 2-3x ATR. The old grid was clustered too tightly around 1.0x and may have been cutting winners short.

### Test
```bash
python -m pytest tests/ -v
```

### Commit
```bash
git commit -m "feat: widen MR profit target ATR grid [0.5, 1.0, 1.5, 2.0, 3.0]"
```

---

## STEP 5 — Verify subtypes and shorts inherit widened grids

### What to check

Subtypes and short families should inherit `get_exit_parameter_grid_for_combo()` from their parent base class. Verify:

1. `trend_subtypes.py` — does NOT override `get_exit_parameter_grid_for_combo()` — inherits from TrendStrategyType
2. `breakout_subtypes.py` — same check
3. `mean_reversion_subtypes.py` — same check
4. `short_strategy_types.py` — same check

If any override exists, update it to match the new grid values.

### No commit needed if inheritance is clean.

---

## STEP 6 — Update docs

### Files to modify
- `CLAUDE.md`
- `CHANGELOG_DEV.md`

### CHANGELOG_DEV.md
Add entry at TOP:

```
## 2026-03-XX — Session 41: Widen exit grids for trend rescue

**What was done**:
- Validated Session 40 performance caching (dataset load + feature precompute per timeframe)
- Widened trailing_stop_atr grid for trend: [1.0, 1.5, 2.0, 2.5] -> [1.5, 2.5, 3.5, 5.0, 7.0]
- Widened trailing_stop_atr grid for breakout: [1.0, 1.5, 2.0, 2.5] -> [1.5, 2.5, 3.5, 5.0]
- Widened profit_target_atr grid for MR: [0.5, 0.75, 1.0, 1.25, 1.5] -> [0.5, 1.0, 1.5, 2.0, 3.0]
- Verified subtypes and shorts inherit widened grids

**Why this matters**:
- Session 29 showed trailing stops losing to time_stop because the grid was too tight
- 1.0x ATR on daily ES = $2k-$4k trailing distance — a single intraday whipsaw
- 5.0x ATR on daily ES = $10k-$20k — enough room for a real trend to develop
- This is the single most likely fix for the trend family's REGIME_DEPENDENT problem

**Test result**: XX/XX pass

**Next priorities**:
1. Run full 5TF ES sweep with widened grids
2. Compare: do trend strategies now use trailing_stop? Do they achieve ROBUST?
3. If trend improves: proceed to CL instrument expansion (Session 42)
4. If trend still fails: investigate whether the trend FILTERS are the problem, not exits
```

### Commit
```bash
git commit -m "docs: update CLAUDE.md and CHANGELOG for session 41"
```

---

## STEP 7 — Push and run

```bash
git push origin main
```

Then launch the full 5TF sweep with widened grids:

```bash
gcloud compute ssh strategy-console --zone us-central1-c --command "
cd /home/robpitman1982/python-master-strategy-creator;
git pull;
python3 run_cloud_sweep.py --config cloud/config_es_all_5tf_ondemand_c.yaml --fire-and-forget
"
```

---

## Summary

| Step | What | Impact |
|------|------|--------|
| 1 | Validate Session 40 perf fix | Confirm caching works |
| 2 | Widen trend trailing_stop_atr | [1.5, 2.5, 3.5, 5.0, 7.0] — rescue trend family |
| 3 | Widen breakout trailing_stop_atr | [1.5, 2.5, 3.5, 5.0] |
| 4 | Widen MR profit_target_atr | [0.5, 1.0, 1.5, 2.0, 3.0] |
| 5 | Verify subtype inheritance | No code change if clean |
| 6 | Docs | Context for next session |
| 7 | Push + run | Full 5TF sweep with widened grids |

## What success looks like
The new leaderboard contains at least one trend strategy with exit_type=trailing_stop and quality flag ROBUST or STABLE. If that happens, the portfolio is no longer 100% mean reversion and we have a real path to The5ers Bootcamp.
