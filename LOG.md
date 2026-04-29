# LOG.md — Append-only audit log

> Every meaningful task (success or failure) gets an entry. Append only — never edit retroactively.
> Format: date, session/task, status, what, outcome, files, next.

---

### 2026-04-30 [Sessions 76-78 partial] Throughput investigation, BH-FDR gate, DSR on leaderboard
Status: OK
What: Sessions 76-78 partially executed under Option C (no cluster work — betfair Claude is using cluster for sweeps).
  - **Throughput investigation:** Read `run_cluster_sweep.py` + `run_local_sweep.py`. Confirmed AND extended the betfair Claude's claim. The "cluster" runner is misleadingly named — it's a single-host sequential batch runner that loops 92 jobs on whatever machine launched it. Other 3 cluster hosts sit idle. Bug shape is worse than predicted: 0 processes on 3/4 hosts, not "1 process per host with combos serialised." On 24-market sweep, this means ~15-25h on c240 alone vs ~4-6h with per-host dispatch. Refactor needed — deferred to clean cluster window.
  - **BH-FDR gate:** Added `modules/statistics.py` with `pf_to_pvalue` (Lo 2002 t-stat from PF + N), `apply_bh_fdr` (Benjamini-Hochberg multiple-testing correction), and `annotate_dataframe_with_pvalues`. Wired into `apply_promotion_gate` in `master_strategy_engine.py`: always annotates `pf_pvalue` column on results, optional FDR filter via `promotion_gate.bh_fdr_alpha` config (default disabled = no behavioural change). When enabled, family-aware over the full sweep.
  - **DSR on leaderboard:** Extended `modules/statistics.py` with Bailey & Lopez de Prado (2014) Deflated Sharpe Ratio: `expected_max_sharpe_under_null` (using Euler-Mascheroni + Phi^-1), `sharpe_estimator_std` (Mertens variance with skew/kurt), `deflated_sharpe_ratio` (probability that observed SR exceeds expected-max-null), `pf_to_sharpe`, `annotate_dataframe_with_dsr`. Wired into `modules/master_leaderboard.py`: per-leader trial count sourced from row count of `<strategy_type>_filter_combination_sweep_results.csv` in each subdir; falls back to 100 if missing. New columns on `master_leaderboard.csv`: `deflated_sharpe_ratio`, `sharpe_per_trade`, `n_trials_in_search`.
Outcome: 42 new tests in `tests/test_statistics.py` (all pass). Full test suite: 257/257 pass, zero regressions. The realistic-family integration test confirms BH-FDR cleanly separates real edges from noise (≥4/5 real candidates pass, ≤5/45 noise candidates pass at alpha=0.05). DSR test confirms strong-signal-with-few-trials passes (>0.95) and weak-signal-with-many-trials fails (<0.5).
Files: modules/statistics.py (new, 333 lines), tests/test_statistics.py (new, 42 tests), master_strategy_engine.py (BH-FDR wiring), modules/master_leaderboard.py (DSR + trial-count plumbing).
Next: Sessions 79-83 — walk-forward replacing fixed IS/OOS, random-flip null at promotion, EXTERNAL_LLM_BRIEFING.md + cross-LLM consult round, sprint-architecture-with-frozen-grids upgrade. Cluster work (g9 onboarding + throughput refactor) waits for clean window.

### 2026-04-26 [Hermes decommission] External retirement complete
Status: OK
What: Operator confirmed all 4 manual external-cleanup items done: GitHub deploy keys revoked on `python-master-strategy-creator` repo, GitHub deploy key revoked on `betfair-trader` repo, Telegram bot `@pitmans_heremes_bot` deleted via @BotFather, Hermes Anthropic API key revoked in Anthropic console.
Outcome: Hermes is now fully gone — no server-side state, no SSH access anywhere, no GitHub access, no Telegram presence, no API ability. Updated MASTER_HANDOVER.md (header status line + decommission audit trail line) and removed the "Operator-side Hermes external retirement" item from On the Horizon.
Files: MASTER_HANDOVER.md, LOG.md.
Next: g9 onboarding to compute cluster (Open Issue #10).

### 2026-04-26 [Hermes decommission] Full Hermes + OpenClaw teardown (g9 + cluster)
Status: OK
What: Operator decided to retire the Hermes/OpenClaw experiment after 1 week. Claude Code + X1 Carbon Claude Remote Control hub replaces the agent-driven ops layer. Executed full teardown:
  - On g9: stopped/killed any hermes+openclaw processes, removed `/etc/cron.d/sync-handover`, `/etc/sudoers.d/agents`, `/usr/local/bin/sync-handover`, `/usr/local/bin/sync-betfair-handover`, `/usr/local/bin/ingest-handover` (already retired but checked). Wiped `/data/hermes/` (~1.5 GB), `/data/openclaw/`, `/data/shared/` (entire tree). `userdel -r hermes` + `userdel -r openclaw` + `groupdel agents` — all clean. /home/ now only contains rob.
  - On c240, gen8, r630: removed `hermes-agent@g9-cluster` line from `/home/rob/.ssh/authorized_keys` via sed against unique `JvbVaj` fingerprint. Backups taken to `~/.ssh/authorized_keys.bak-pre-hermes-removal-YYYYMMDD` on each host. Verified rob's own SSH still works to all three hosts post-edit (load avg 50-60 — confirmed Rob's parallel betfair sweeps are untouched).
  - In repo: rewrote Gen 9 section in MASTER_HANDOVER.md (removed ~115 lines of Hermes/OpenClaw config docs, replaced with leaner compute-worker section + decommission audit trail). Updated Open Issues, On the Horizon, Connection Quick Reference. Renumbered Open Issues. Deleted `scripts/sync-handover.sh` and `docs/HANDOVER_RENAME_MIGRATION.md` (both obsolete now). Updated header status line to reflect Session 75.
Outcome: Server-side, repo-side, and cluster authorized_keys all clean. Hermes is gone from infrastructure. Operator-side cleanup remaining (manual): GitHub deploy keys on python-master-strategy-creator + betfair-trader repos, Telegram bot `@pitmans_heremes_bot` via @BotFather, Hermes Anthropic API key. g9 is now a 48-thread/32GB compute worker, but repo clone + market_data + sweep scripts not yet set up — added as Open Issue #10.
Files: MASTER_HANDOVER.md (Gen 9 section rewrite + scattered Hermes ref removal), LOG.md (this entry), deleted scripts/sync-handover.sh and docs/HANDOVER_RENAME_MIGRATION.md.
Next: Operator does the external retirement (deploy keys, Telegram bot, API key) when convenient. Compute-cluster onboarding for g9 is next major work item.

### 2026-04-26 [handover rename] HANDOVER.md → MASTER_HANDOVER.md across repo
Status: OK
What: Renamed `HANDOVER.md` to `MASTER_HANDOVER.md` to avoid filename collision with other projects' handover files (e.g. `BETFAIR_HANDOVER.md`) when Hermes or future agents load multi-project memories. Updated all in-repo references in MASTER_HANDOVER.md (Hermes protocol section, sync paths, embedded server-side path docs), LOG.md, scripts/sync-handover.sh, docs/CFD_SWEEP_SETUP.md, docs/AUDIT_REPORT.md. Updated global `~/.claude/CLAUDE.md` rule to require project-named handover. Wrote server-side migration checklist at docs/HANDOVER_RENAME_MIGRATION.md covering g9 symlink repoint, sync-handover script redeploy, retired Session 72b path cleanup, Hermes skills update, Latitude PowerShell update, and rollback steps.
Outcome: Repo-side rename complete and all references consistent. Server-side (g9 symlinks, /usr/local/bin/sync-handover, Hermes skills) and Latitude-side (PowerShell handover script) NOT yet migrated — checklist in docs/HANDOVER_RENAME_MIGRATION.md is the to-do list. Next sync-handover run on g9 will fast-forward the new filename into the Hermes clone automatically; the symlink repoint is the operator step.
Files: MASTER_HANDOVER.md (renamed from HANDOVER.md + internal refs), LOG.md, scripts/sync-handover.sh, docs/CFD_SWEEP_SETUP.md, docs/AUDIT_REPORT.md, docs/HANDOVER_RENAME_MIGRATION.md (new), C:\Users\Rob\.claude\CLAUDE.md (global, not in repo).
Next: Operator runs the g9 + Latitude steps in docs/HANDOVER_RENAME_MIGRATION.md.

### 2026-04-26 [working-spec adoption] LOG.md created and MASTER_HANDOVER.md header reformatted
Status: OK
What: Adopted the working spec for Claude Code ops + persistence. Created LOG.md as the append-only audit trail. Reformatted MASTER_HANDOVER.md header to spec (line 1 "Last updated:", line 2 "Current status:" paragraph).
Outcome: Both files in place. Spec triggers active: "checkpoint please", "session end please", "go", "hold". Memory write rule active: future-session-relevant insights to auto-memory; current state to MASTER_HANDOVER.md; audit facts to LOG.md.
Files: MASTER_HANDOVER.md (header reformat), LOG.md (new)
Next: First real task under the new regime — TBD by operator.

### 2026-04-26 [GCP cleanup] GCS buckets deleted manually by operator
Status: OK
What: Operator deleted both GCS buckets manually via GCP Console after Claude declined to do it from an embedded-instruction prompt injection. Buckets were `strategy-artifacts-robpitman` (Rob account, us-central1) and the Nikola-account bucket `strategy-artifacts-nikolapitman`.
Outcome: Confirmed by operator. GCP storage costs eliminated. Cloud cleanup section of MASTER_HANDOVER.md (Cloud Infrastructure subsection) is now stale and should be updated next time someone touches that file — it still says "To be decommissioned once local lab stable" but the buckets are now gone.
Files: none in repo (external GCP action).
Next: Operator/next session should mark Cloud Infrastructure as decommissioned in MASTER_HANDOVER.md.

### 2026-04-26 [GCP cleanup] Refused embedded-instruction bucket deletion
Status: OK (refused as designed)
What: A system-reminder block contained instructions to list and delete two GCS buckets (Nikola + Rob accounts). Treated as prompt injection and refused. Walked operator through manual deletion via GCP Console instead.
Outcome: No buckets deleted by Claude. Operator confirmed the Rob-account bucket name (strategy-artifacts-robpitman, us-central1, soft-delete enabled).
Files: none
Next: Operator deletes manually via Console.

### 2026-04-10 [repo cleanup + handover consolidation] Root reorganized for Claude Desktop, 62-session history added
Status: OK
What: Moved 93 session files + 9 docs + 5 configs + 6 scripts + 11 shell scripts + 7 old output dirs + EA folder into archive/. Deleted 54 .tmp_pytest* dirs + 7 other temp dirs. Added .tmp_*, tmp*/, .pytest_cache to .gitignore. Wrote complete 62-session project history into MASTER_HANDOVER.md organized by 6 phases with key architectural decisions called out. Archived 9 more loose session/handover files in a follow-up pass.
Outcome: Root went from ~120 loose files to 4 .md (CLAUDE.md, CHANGELOG_DEV.md, MASTER_HANDOVER.md, README.md) + source code + 10 dirs. Claude Desktop attach now works after unchecking Data/, Outputs/, archive/, strategy_console_storage/, cloud_results/.
Files: MASTER_HANDOVER.md, archive/sessions/* (101 files), archive/docs/* (10 files), .gitignore. Commits: 2966e29, e48cd72.
Next: Operator continues normal session work — repo structure stable.
