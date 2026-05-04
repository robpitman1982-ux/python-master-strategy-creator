# SPRINT_93 — Engine resume logic for family-level work

> Pre-registration is mandatory. Commit this file BEFORE any code is touched.
> Once committed, the parameter grid + verdict criteria are FROZEN for this sprint.

**Sprint number:** 93
**Date opened:** 2026-05-04
**Date closed:** ___ (filled in at sprint-end)
**Operator:** Rob
**Author:** Claude Code on Latitude
**Branch:** `feat/engine-resume-logic`

---

## 1. Sprint goal

Add per-family resume logic to `master_strategy_engine.py::_run_dataset` so that
when an engine process is killed mid-dataset (e.g. during a RAM crisis), restarting
the same dataset config skips families whose `*_filter_combination_sweep_results.csv`
and `*_promoted_candidates.csv` are already present and well-formed on disk.

**Why now:** today's 5m sweep RAM crisis revealed that any pre-emptive kill loses
EVERY completed family on the dataset (verified via grep — engine has no resume).
On r630 today, killing the ES_5m sweep meant losing mean_reversion + trend +
breakout + short_mr + short_breakout + 2 subtypes = ~6 hours of completed work,
to gain RAM headroom that could have been gained with zero loss if resume existed.

This sprint is the **unblocker for every subsequent RAM/speed experiment**. With
resume, every other fix can be tested as a hotfix-restart without losing prior
work.

## 2. Mechanism plausibility

**Strong prior — it's a pure file-existence check.**

The engine writes per-family CSVs at well-defined boundaries (after sweep finishes,
after promoted candidates are filtered, after refinement, after family leaderboard
update). On restart, before launching a family's sweep, check if the canonical
output CSVs already exist for that family with the expected schema and a
non-trivial row count. If yes, load the existing data into memory and skip the
sweep + refinement compute, going straight to the family leaderboard merge.

**Failure modes considered:**

- **Stale CSVs from a config change.** If the user edits `configs/local_sweeps/<dataset>.yaml`
  between runs (e.g. changes filter pool, hold_bars range, OOS split date), the
  on-disk CSVs reflect the OLD config. Mitigation: write a config fingerprint
  (`.engine_config.fingerprint`) into the dataset output dir on first run; on
  restart, compare current config fingerprint to on-disk; if different, refuse
  to resume that dataset and require explicit `--force-fresh` flag.
- **Truncated CSVs from a hard kill mid-write.** Engine writes via `to_csv` which
  may leave a partial file if killed at exactly the wrong instant. Mitigation:
  validate row count vs expected n_combos for the family; refuse to resume if
  rows < expected.
- **Schema drift across engine versions.** A new column added to the sweep CSV
  in a later commit would make old CSVs incompatible. Mitigation: include
  engine version (git short-sha) in the fingerprint.

## 3. Frozen parameter grid

| Parameter | Value | Source |
|-----------|-------|--------|
| Resume check trigger | At top of each family loop iteration in `_run_dataset` | new |
| Required artifacts for resume | `{family}_filter_combination_sweep_results.csv` AND `{family}_promoted_candidates.csv` | matches existing emission |
| Optional artifacts for resume | `{family}_top_combo_refinement_results_narrow.csv` (refinement skip) | matches existing emission |
| Sweep CSV minimum row count | `>= 0.95 * expected_n_combos` (allows 5% post-dedup) | new |
| Promoted CSV minimum row count | `>= 1` if sweep CSV had any pf >= promotion_gate.min_pf | new |
| Config fingerprint file | `.engine_config.fingerprint` in dataset output dir | new |
| Fingerprint contents | sha256 of: dataset config YAML + git short-sha + engine version | new |
| Behaviour on fingerprint mismatch | Refuse resume, log WARNING, require `--force-fresh` to rerun | new |
| Behaviour on truncated/invalid CSV | Refuse resume of that family, recompute it; other families' valid resumes still apply | new |
| Resume status column in family_leaderboard_results.csv | `resumed_from_disk: bool` | new |
| `--force-fresh` CLI flag | Disables resume entirely for a fresh run | new |
| Default behaviour | Resume enabled (opt-out via flag) | new |

## 4. Verdict definitions

| Verdict | Condition |
|---------|-----------|
| **CANDIDATES** | Smoke test on small dataset with mid-run kill + restart produces identical family_leaderboard_results.csv as the unkilled control run. Resume saves >= 90% of the wall-clock that the killed work represented. |
| **NO EDGE** | n/a — this is plumbing, not a strategy hypothesis. |
| **SUSPICIOUS** | Smoke test produces leaderboard with > 0.5% net_pnl divergence from control, OR resume saves < 50% of expected wall-clock. Indicates implementation drift or incorrect skip predicate. |
| **BLOCKED** | Cannot complete (filesystem semantics issue, schema fingerprint design problem). Document and re-plan. |

## 5. Methodology checklist

Pre-launch (must all be green):
- [ ] All test suites green pre-launch (`python -m pytest tests/ --ignore=tests/test_engine_parity.py -q`)
- [ ] Sprint pre-registration committed BEFORE code changes
- [ ] Branch `feat/engine-resume-logic` cut from `main`

Implementation gates (after each):
- [ ] **Stage 1**: fingerprint write on first family's completion. Verify file appears, contents match expected hash.
- [ ] **Stage 2**: resume detection at top of `_run_dataset` family loop. Verify second run logs "RESUMING: skipping <family> (found valid CSV)" for each completed family.
- [ ] **Stage 3**: family leaderboard merge from disk-resumed families. Verify final `family_leaderboard_results.csv` from resumed run matches control run within zero tolerance on net_pnl, oos_pf, leader_strategy_name.
- [ ] **Stage 4**: fingerprint mismatch detection. Manually edit dataset config, rerun, verify engine refuses to resume and logs the reason.
- [ ] **Stage 5**: `--force-fresh` flag. Verify it disables resume even when fingerprint matches.

Verdict gate:
- [ ] Smoke test: ES_60m on c240 (small dataset, ~6 min total). Run once to completion (control), capture `family_leaderboard_results.csv`. Run again with mid-run kill at family 6 boundary, restart, verify resumed leaderboard matches control.
- [ ] No regression in 108 sprint-suite tests.
- [ ] One pytest case added to `tests/test_engine_resume.py` covering the happy path.

## 6. Implementation map

### 6.1 New module: `modules/engine_resume.py`

```python
def compute_dataset_fingerprint(config_path: Path, engine_version: str) -> str:
    """sha256 of: dataset YAML content + engine_version (git short-sha)."""

def write_fingerprint(output_dir: Path, fingerprint: str) -> None:
    """Write to <output_dir>/.engine_config.fingerprint."""

def read_fingerprint(output_dir: Path) -> str | None:
    """Return on-disk fingerprint or None if missing."""

def is_family_resumable(
    output_dir: Path,
    family_name: str,
    expected_n_combos: int,
) -> tuple[bool, str]:
    """Check if family has valid sweep + promoted CSVs.
    Returns (resumable, reason_if_not).
    """

def load_resumed_family(
    output_dir: Path,
    family_name: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    """Load combo_results, promoted, refinement (if exists) from disk.
    Returns (combo_df, promoted_df, refined_df_or_None).
    """
```

### 6.2 Modification: `master_strategy_engine.py::_run_dataset`

At top of the family loop:
```python
for family in families_to_run:
    if resume_enabled:
        resumable, reason = is_family_resumable(output_dir, family, expected_n)
        if resumable:
            print(f"RESUMING: skipping {family} (found valid CSV)")
            combo_df, promoted_df, refined_df = load_resumed_family(output_dir, family)
            # short-circuit to family leaderboard merge
            family_leader_row = _choose_family_leader(...)
            family_results.append(family_leader_row)
            continue
        else:
            print(f"RESUME REJECTED for {family}: {reason}")
    # existing path: full sweep + refinement + leader selection
    ...
```

At dataset entry, before family loop:
```python
fingerprint = compute_dataset_fingerprint(args.config, engine_version)
on_disk = read_fingerprint(output_dir)
if on_disk is None:
    write_fingerprint(output_dir, fingerprint)
elif on_disk != fingerprint:
    if not args.force_fresh:
        print(f"FINGERPRINT MISMATCH for {output_dir}. Refusing resume.")
        sys.exit(2)
    write_fingerprint(output_dir, fingerprint)
```

### 6.3 Modification: `run_local_sweep.py` and `run_cluster_sweep.py`

Add `--force-fresh` argparse flag → forwarded as `--force-fresh` to `master_strategy_engine.py`.

### 6.4 New test: `tests/test_engine_resume.py`

```python
def test_resume_skips_completed_family(tmp_path):
    # Run engine once on small dataset
    # Verify fingerprint written, sweep CSV written
    # Run engine again with same config
    # Verify second run reads from disk, skips sweep, produces same leaderboard

def test_resume_rejects_fingerprint_mismatch(tmp_path):
    # Run engine once
    # Mutate config (e.g. change OOS split date)
    # Run again, expect refusal with non-zero exit and clear message

def test_force_fresh_overrides_fingerprint(tmp_path):
    # Run engine once
    # Run again with --force-fresh
    # Verify sweep is re-run (timestamp on CSV updated)

def test_resume_rejects_truncated_csv(tmp_path):
    # Run engine once
    # Truncate sweep CSV mid-row
    # Run again, expect that family to be re-swept, others resumed
```

## 7. Anti-convergence consultation

Both LLMs were silent on resume logic specifically — neither raised it as an open
problem (it's been "lurking" in the open issue list at MASTER_HANDOVER, but was
neither flagged as a priority by ChatGPT nor Gemini in the latest round).
Operator's intuition (Sprint #3 in the synthesised list) was that this is
the unblocker for every other RAM/speed experiment. Pre-registering on that
intuition; verdict will judge whether the time savings on the smoke test
justify the implementation cost.

## 8. Expected impact

Post-Sprint-93, every future RAM/speed sprint becomes a tight iteration:
- Kick off 5m sweep (or 60m on smaller hosts)
- Hit RAM brink → kill cleanly
- Apply a fix (maxtasksperchild, float32, shared memory, mask cache, etc.)
- Restart same config → resume from last completed family
- Measure delta

Without this sprint, every "kill + restart with fix" costs 2-6 hours of redo.
With it, the cost drops to ~30 min (the in-flight family) regardless of how
many families had completed. **This is the multiplier on every subsequent
sprint's iteration speed.**
