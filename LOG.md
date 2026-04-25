# LOG.md — Append-only audit log

> Every meaningful task (success or failure) gets an entry. Append only — never edit retroactively.
> Format: date, session/task, status, what, outcome, files, next.

---

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
