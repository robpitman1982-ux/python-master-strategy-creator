# Audit Report — Session 68

**Generated:** 2026-04-19
**Host:** c240 (192.168.68.53)
**Commit at audit start:** fb27c53

---

## 1. Top-level inventory

| Item | Type | Size | Purpose | Notes |
|------|------|------|---------|-------|
| `modules/` | dir | 1.1 MB | Core engine modules | Active |
| `tests/` | dir | 312 KB | Test suite | Active |
| `scripts/` | dir | 44 KB | Utility scripts | Mixed active/deprecated |
| `configs/` | dir | 124 KB | YAML configs | Mixed active/deprecated |
| `cloud/` | dir | 440 KB | **Deprecated** GCP/cloud infra | DELETE in Session 69 |
| `docs/` | dir | 228 KB | Documentation | Active |
| `archive/` | dir | 12 MB | Archived old files | 162 tracked files |
| `Data/` | dir | 344 MB | TradeStation CSVs | **40 files tracked despite .gitignore** — added before gitignore entry |
| `Outputs/` | dir | 39 MB | Engine outputs | Properly gitignored, not tracked |
| `strategy_console_storage/` | dir | 331 MB | GCP console storage | **231 files tracked** — should be gitignored + untracked |
| `venv/` | dir | 653 MB | Python venv | Untracked (correct) |
| `.github/` | dir | — | CI/CD workflows | GCP deploy workflow — likely deprecated |
| `master_strategy_engine.py` | file | 60 KB | Main orchestrator | Active, largest .py |
| `dashboard.py` | file | 56 KB | Streamlit dashboard | Active |
| `dashboard_utils.py` | file | 44 KB | Dashboard helpers | Active |
| `MASTER_HANDOVER.md` | file | 40 KB | Ops handover doc | Active |
| `CLAUDE.md` | file | 32 KB | Project instructions | Active |
| `CHANGELOG_DEV.md` | file | 72 KB | Dev changelog | Active, very large |
| `config.yaml` | file | 4 KB | Pipeline config | Active |
| `generate_returns.py` | file | 8 KB | Strategy returns builder | Active |
| `paths.py` | file | 4 KB | Path constants | Active |
| `run_cloud_sweep.py` | file | 4 KB | Cloud sweep wrapper | **Deprecated** |
| `run_cloud_parallel.py` | file | 8 KB | Parallel cloud runner | **Deprecated** |
| `run_cloud_job.py` | file | 20 KB | Cloud job orchestrator | **Deprecated** |
| `run_spot_resilient.py` | file | 24 KB | SPOT VM runner | **Deprecated** |
| `run_cluster_sweep.py` | file | 16 KB | Local cluster orchestrator | Active |
| `run_local_sweep.py` | file | 8 KB | Single-market local runner | Active |
| `run_portfolio_all_programs.py` | file | 8 KB | Multi-program portfolio | Active |
| `run_evaluator.py` | file | 4 KB | Evaluator runner | Active |
| `run_high_stakes.py` | file | 4 KB | High Stakes runner | Active |
| `Dockerfile` | file | 4 KB | Docker build | Likely deprecated (cloud) |
| `requirements.txt` | file | 4 KB | Dependencies | Active |
| `sweep_manifest.json` | file | 4 KB | Sweep state | Gitignored |
| `SESSION_65_TASKS.md` | file | 12 KB | Old task file | Stale — should be in archive |
| `SESSION_68_PIPELINE_REVIEW.md` | file | 12 KB | Pipeline review doc | Active reference |
| `SESSION_68_TASKS.md` | file | 24 KB | This session's tasks | Active |

### Flags

- **> 100 MB tracked content:** `Data/` (344 MB, 40 tracked CSVs) and `strategy_console_storage/` (331 MB, 231 tracked files) are bloating the repo. Both are in .gitignore but were added before the gitignore entry was created. These need `git rm --cached` in Session 69.
- **Stale at top level:** `SESSION_65_TASKS.md` should be archived. Multiple `run_cloud_*.py` scripts are deprecated.
- **`archive/` tracked:** 162 files, 12 MB — already moved to archive but still tracked. Acceptable if intentional.

---

## 2. Module inventory

### File counts by directory

| Directory | .py files |
|-----------|-----------|
| Root (.) | 14 |
| modules/ | 26 |
| modules/strategy_types/ | 11 |
| scripts/ | 4 |
| tests/ | 21 |
| cloud/ | 2 |
| **Total** | **78** |

### Top 10 largest modules by LOC

| Module | LOC | Functions | Classes |
|--------|-----|-----------|---------|
| cloud.launch_gcp_run | 3,013 | 70 | 7 |
| modules.portfolio_selector | 2,294 | 34 | 0 |
| modules.filters | 1,664 | 163 | 60 |
| master_strategy_engine | 1,288 | 32 | 0 |
| tests.test_cloud_launcher | 1,214 | 69 | 2 |
| modules.prop_firm_simulator | 1,201 | 14 | 5 |
| dashboard_utils | 1,182 | 56 | 4 |
| dashboard | 1,134 | 7 | 0 |
| modules.engine | 871 | 17 | 3 |
| run_spot_resilient | 634 | 19 | 0 |

**Note:** The single largest module is `cloud.launch_gcp_run` (3,013 LOC) — deprecated cloud code.

### Dead code candidates

**None found.** Every `modules/` file is imported by at least one non-test, non-cloud module.

However, the following `modules/` are only used in cloud/deprecated contexts and should be reviewed during cleanup:
- No modules are *exclusively* imported by cloud code. Cloud scripts import `modules.ultimate_leaderboard` and `paths`, both of which are also used by active code.

### Cloud code import graph

Files that import cloud modules (would become orphaned if cloud/ is deleted):

| File | Cloud imports | Status |
|------|---------------|--------|
| `run_cloud_parallel.py` | cloud.download_run, cloud.launch_gcp_run | **Deprecated** — delete with cloud/ |
| `run_cloud_sweep.py` | cloud.download_run, cloud.launch_gcp_run | **Deprecated** — delete with cloud/ |
| `run_spot_resilient.py` | cloud.download_run, cloud.launch_gcp_run | **Deprecated** — delete with cloud/ |
| `tests/test_cloud_launcher.py` | cloud.download_run, cloud.launch_gcp_run | **Deprecated** — delete with cloud/ |
| `tests/test_parallel_vm.py` | cloud.download_run, cloud.launch_gcp_run | **Deprecated** — delete with cloud/ |

### Circular imports

None detected.

---

## 3. Configs

### Summary

| Location | Count | Purpose |
|----------|-------|---------|
| configs/cfd_markets.yaml | 1 | Master CFD market definitions (24 markets) |
| configs/local_sweeps/*.yaml | 25 | Per-market sweep configs |
| config.yaml (root) | 1 | Default pipeline config (legacy ES futures) |
| **Total** | **27** |

### Known bugs

| Config | Bug | Severity |
|--------|-----|----------|
| configs/local_sweeps/ES_daily_cfd_v1.yaml | dollars_per_point: 50.0 (futures) on Dukascopy CFD data = 50x P&L inflation | CRITICAL |
| configs/local_sweeps/ES_all_timeframes.yaml | Same bug: dollars_per_point: 50.0 on dukascopy data paths (5 datasets) | CRITICAL |
| config.yaml (root) | Points to Data/ES_60m_2008_2026_tradestation.csv which does not exist on c240 | Low (legacy) |

### Data file existence

Of 122 dataset paths across all sweep configs:
- 1 exists: Data/ES_daily_2012_2026_dukascopy.csv
- 121 missing: pending conversion from raw TDS exports

### Excluded markets / prop firm configs

- No excluded_markets field exists anywhere in configs or code
- No separate prop firm config files. The5ers configs are Python classes in modules/prop_firm_simulator.py
- Sweep engine does NOT read excluded_markets: confirmed correct (firm-agnostic discovery)
- Gap: per-firm tradeable universes need to be externalized to config files

### Recommendations

| Config | Action |
|--------|--------|
| ES_daily_cfd_v1.yaml | Delete: buggy, replaced in Session 69 |
| ES_all_timeframes.yaml | Fix: replace futures params with CFD params |
| cfd_markets.yaml | Keep: authoritative |
| 22 other all_timeframes.yaml | Keep: generated, params correct |
| config.yaml (root) | Fix: update data path or mark legacy |

---

## 4. Scripts

### Inventory (9 files in scripts/)

| Script | Category | Last Commit | Referenced By | Recommendation |
|--------|----------|-------------|---------------|----------------|
| convert_tds_to_engine.py | **active** | 2026-04-17 | run_local_sweep.py, run_cluster_sweep.py | Keep |
| generate_sweep_configs.py | **active** | 2026-04-17 | run_cluster_sweep.py, cfd_markets.yaml | Keep |
| run_console_job.py | deprecated | 2026-04-04 | archive refs only | Delete (GCP strategy-console) |
| setup_dashboard_venv.sh | deprecated | 2026-04-04 | CLAUDE.md docs only | Delete (GCP console) |
| start_dashboard.sh | deprecated | 2026-04-04 | no code refs | Delete (GCP console) |
| strategy-dashboard.service | deprecated | 2026-04-04 | CLAUDE.md docs only | Delete (GCP console) |
| update_console.sh | deprecated | 2026-04-04 | no code refs | Delete (GCP console) |
| audit_modules.py | audit | 2026-04-18 | Session 68 only | Keep (audit tooling) |
| audit_configs.py | audit | 2026-04-18 | Session 68 only | Keep (audit tooling) |

**Summary:** 2 active scripts, 5 deprecated (all GCP strategy-console related), 2 audit scripts created this session.

**Recommendation:** Delete the 5 deprecated scripts in Session 69 alongside cloud/ directory cleanup. They all relate to the GCP strategy-console VM which is deprecated.

---

## 5. Data layout

### Summary counts

| Location | Files | Size | Notes |
|----------|-------|------|-------|
| Repo Data/ | 41 | 344 MB | 36 TradeStation CSVs + 1 Dukascopy converted + 1 smoke + 3 TDS samples. **40 tracked in git despite .gitignore** |
| c240 /data/market_data/futures/ | 87 CSVs | 2.2 GB | All TradeStation futures exports |
| c240 /data/market_data/cfds/ohlc/ | 120 CSVs + 1 .bcf | ~1.7 GB | Dukascopy raw OHLC (24 markets x 5 TFs) |
| c240 /data/market_data/cfds/ohlc_engine/ | **0** | 0 | **DOES NOT EXIST** on c240 |
| c240 /data/market_data/cfds/ticks_dukascopy_tds/ | 24 dirs | 34 GB | Raw .bfc tick cache |
| c240 /data/market_data/cfds/ticks_dukascopy_raw/ | 0 | 0 | Empty, for future parquet |
| c240 /data/market_data/cfds/ticks_mt5_the5ers/ | 0 | 0 | Empty |

### Critical finding: ZERO engine-ready CFD files

The ohlc_engine/ directory does not exist on c240. The only converted file (ES_daily_2012_2026_dukascopy.csv) lives in the repo Data/ directory, not in the canonical c240 data location. This means:
- All 120 Dukascopy conversions are pending (not 92 as previously estimated)
- The converted ES daily file needs to be moved to c240 /data/market_data/cfds/ohlc_engine/

### Coverage matrix (24 CFD markets x 5 timeframes)

All 24 markets have complete Dukascopy raw OHLC for all 5 timeframes. None have engine-ready conversions.

| Market | Canonical | Raw OHLC D1 | Raw OHLC H1 | Raw OHLC M30 | Raw OHLC M15 | Raw OHLC M5 | Engine-Ready |
|--------|-----------|:-----------:|:-----------:|:------------:|:------------:|:-----------:|:------------:|
| USA_500_Index | ES | Y | Y | Y | Y | Y | repo Data/ only |
| USA_100_Technical_Index | NQ | Y | Y | Y | Y | Y | - |
| USA_30_Index | YM | Y | Y | Y | Y | Y | - |
| XAUUSD | GC | Y | Y | Y | Y | Y | - |
| XAGUSD | SI | Y | Y | Y | Y | Y | - |
| US_Light_Crude_Oil | CL | Y | Y | Y | Y | Y | - |
| US_Brent_Crude_Oil | BRENT | Y | Y | Y | Y | Y | - |
| EURUSD | EC | Y | Y | Y | Y | Y | - |
| USDJPY | JY | Y | Y | Y | Y | Y | - |
| GBPUSD | BP | Y | Y | Y | Y | Y | - |
| AUDUSD | AD | Y | Y | Y | Y | Y | - |
| USDCAD | USDCAD | Y | Y | Y | Y | Y | - |
| USDCHF | USDCHF | Y | Y | Y | Y | Y | - |
| NZDUSD | NZDUSD | Y | Y | Y | Y | Y | - |
| Natural_Gas | NG | Y | Y | Y | Y | Y | - |
| High_Grade_Copper | HG | Y | Y | Y | Y | Y | - |
| US_Small_Cap_2000 | RTY | Y | Y | Y | Y | Y | - |
| Bitcoin_vs_US_Dollar | BTC | Y | Y | Y | Y | Y | - |
| Ether_vs_US_Dollar | ETH | Y | Y | Y | Y | Y | - |
| Germany_40_Index | DAX | Y | Y | Y | Y | Y | - |
| France_40_Index | CAC | Y | Y | Y | Y | Y | - |
| Europe_50_Index | STOXX | Y | Y | Y | Y | Y | - |
| UK_100_Index | FTSE | Y | Y | Y | Y | Y | - |
| Japan_225 | N225 | Y | Y | Y | Y | Y | - |

### Repo Data/ duplicates

The 36 TradeStation CSVs in repo Data/ (AD, BP, BTC, EC, JY, NG, TY, US, W x 4 TFs) are duplicates of files in c240 /data/market_data/futures/. These are 344 MB tracked in git history.

**Recommendation:** git rm --cached Data/ in Session 69 to stop tracking. The .gitignore entry already exists but was added after files were committed.

### Conversion priority order

1. **The5ers-tradeable (highest priority):** ES, NQ, YM, GC, SI, CL (6 markets x 5 TF = 30 files)
2. **FX pairs:** EC, JY, BP, AD, USDCAD, USDCHF, NZDUSD (7 markets x 5 TF = 35 files)
3. **Remaining indices + crypto:** BRENT, DAX, CAC, STOXX, FTSE, N225, BTC, ETH (8 markets x 5 TF = 40 files)
4. **Excluded from The5ers but useful:** NG, HG, RTY (3 markets x 5 TF = 15 files)

Total: 120 conversions needed

---

## 6. Tests

### Summary

| Metric | Count |
|--------|-------|
| Test files | 20 |
| Tests passed | 313 |
| Tests failed | 11 |
| Tests skipped | 4 |
| Runtime | 162.57s (2m42s) |

### Failing tests

| Test | File | Failure | Root Cause | Priority |
|------|------|---------|------------|----------|
| test_daily_dd_breach | test_smoke.py | Expected 'Daily DD breach' in failure_reason, got 'Ran out of trades' | Known debt from Session 61 (pause-vs-terminate logic changed) | Medium |
| test_merge_runs_produces_merged_leaderboard | test_parallel_vm.py | FileNotFoundError: gcloud not installed | Deprecated cloud test — needs gcloud SDK | Delete |
| test_merge_runs_assigns_source_run_id | test_parallel_vm.py | Same: gcloud missing | Deprecated cloud test | Delete |
| test_merge_runs_writes_merge_manifest | test_parallel_vm.py | Same: gcloud missing | Deprecated cloud test | Delete |
| test_merge_runs_ranks_rows_by_quality_then_pnl | test_parallel_vm.py | Same | Deprecated cloud test | Delete |
| test_aggregate_ultimate_leaderboard_* (3 tests) | test_parallel_vm.py | Same | Deprecated cloud test | Delete |
| test_get_instance_prefix | test_parallel_vm.py | Same | Deprecated cloud test | Delete |
| test_find_latest_pair_* (2 tests) | test_parallel_vm.py | Same | Deprecated cloud test | Delete |

### Analysis

- **10 of 11 failures** are in test_parallel_vm.py which tests deprecated cloud functionality (requires gcloud SDK). Will be deleted with cloud/ in Session 69.
- **1 real failure** (test_daily_dd_breach) is known technical debt from Session 61.
- **4 skipped tests**: need investigation but not blocking.
- **313 passing tests**: core engine, strategies, portfolio selector, prop firm simulator, vectorized code all healthy.

### Recommendation

- Delete test_parallel_vm.py and test_cloud_launcher.py in Session 69 (cloud cleanup)
- Fix test_daily_dd_breach in Session 69 (update assertion for new behavior)
- After cleanup: expected test count ~265 passing, 0 failing

---

## 7. Cloud / deprecated code

### Complete inventory

| Item | Type | Files | LOC | Status |
|------|------|-------|-----|--------|
| cloud/ directory | GCP configs + launcher + download | 77 files | 6,793 (py+yaml+sh) | DELETE |
| cloud/launch_gcp_run.py | GCP VM orchestrator | 1 | 3,013 | DELETE |
| cloud/download_run.py | GCP result downloader | 1 | 563 | DELETE |
| cloud/*.yaml | 57 GCP sweep configs | 57 | 2,713 | DELETE |
| cloud/*.sh, *.ps1 | GCP shell scripts | 6 | 504 | DELETE |
| cloud/GCP_WINDOWS_RUNBOOK.md | GCP docs | 1 | ~100 | DELETE |
| cloud/SETUP.md | DigitalOcean setup | 1 | ~100 | DELETE |
| run_spot_resilient.py | SPOT VM runner | 1 | 634 | DELETE |
| run_cloud_sweep.py | Cloud sweep wrapper | 1 | 70 | DELETE |
| run_cloud_parallel.py | Parallel cloud runner | 1 | 143 | DELETE |
| run_cloud_job.py | Cloud job orchestrator | 1 | 480 | DELETE |
| tests/test_cloud_launcher.py | Cloud launcher tests | 1 | 1,214 | DELETE |
| tests/test_parallel_vm.py | Parallel VM tests | 1 | 476 | DELETE |
| Dockerfile | Docker build for cloud | 1 | ~20 | DELETE |
| .dockerignore | Docker ignore | 1 | ~10 | DELETE |
| .github/workflows/deploy_strategy_console.yml | GCP console deploy CI | 1 | ~50 | DELETE |
| scripts/run_console_job.py | Console job runner | 1 | 103 | DELETE |
| scripts/setup_dashboard_venv.sh | Console venv setup | 1 | ~40 | DELETE |
| scripts/start_dashboard.sh | Console dashboard start | 1 | ~10 | DELETE |
| scripts/strategy-dashboard.service | Console systemd service | 1 | ~15 | DELETE |
| scripts/update_console.sh | Console update script | 1 | ~15 | DELETE |
| strategy_console_storage/ | GCP console data | 231 tracked files | N/A | git rm --cached |

### Total LOC to delete: ~9,810

### Impact on remaining code

No core modules are exclusively imported by cloud code. The cloud scripts import:
- paths.py (also used by active code)
- modules/ultimate_leaderboard.py (also used by active code)

Deleting cloud code has zero impact on engine, strategies, portfolio selector, or prop firm simulator.

### Recommendation

All cloud code can be deleted in a single Session 69 commit. No modules become orphaned. The only remaining reference to clean up would be cloud-specific mentions in CLAUDE.md and CHANGELOG_DEV.md.

---

## 8. Documentation

### docs/ directory (17 files + audit/)

| Doc | Lines | Last Modified | Status |
|-----|-------|---------------|--------|
| FILTER_SUMMARY.md | 825 | 2026-04-04 | Current — comprehensive filter reference |
| EASYLANGUAGE_FILTER_MAP.md | 532 | 2026-04-04 | Current — EasyLanguage translation reference |
| STRATEGY_ENGINE_ANALYSIS.md | 448 | 2026-04-04 | Current — engine deep dive |
| PROJECT_STATE_REVIEW.md | 372 | 2026-04-19 | Current — written this session |
| CHALLENGE_VS_FUNDED_SPEC.md | 367 | 2026-04-17 | Current — challenge vs funded mode spec |
| SESSION_HANDOFF_SUMMARY_3.md | 330 | 2026-04-04 | Stale — superseded by MASTER_HANDOVER.md |
| ES_ALL_TIMEFRAMES_RESULTS_ANALYSIS.md | 295 | 2026-04-04 | Stale — futures-era analysis |
| IMPROVEMENT_ROADMAP.md | 294 | 2026-04-04 | Stale — superseded by PROJECT_STATE_REVIEW |
| PROJECT_SUMMARY_FOR_LLM.md | 279 | 2026-04-04 | Stale — old LLM context dump |
| SESSIONS_38_41_ROADMAP.md | 270 | 2026-04-04 | Stale — completed work |
| PORTFOLIO_SELECTOR_BRIEF.md | 247 | 2026-04-04 | Current — portfolio selector technical brief |
| LLM_CONSULTATION_PROMPT.md | 173 | 2026-04-04 | Stale — old LLM prompt template |
| BOOTCAMP_SCORING_ANALYSIS.md | 148 | 2026-04-04 | Current — bootcamp scoring reference |
| EXIT_VALIDATION_ANALYSIS.md | 142 | 2026-04-04 | Current — exit type validation results |
| SSH_HARDENING.md | 110 | 2026-04-18 | Current — c240 SSH hardening notes |
| TRADESTATION_EXPORT_GUIDE.md | 57 | 2026-04-04 | Stale — TradeStation no longer primary data source |
| TEST_RUN_CHECKLIST.md | 34 | 2026-04-04 | Stale — cloud-era test checklist |

### Top-level markdown (4 files)

| Doc | Size | Status |
|-----|------|--------|
| CLAUDE.md | 32 KB | Current but needs cloud refs removed |
| MASTER_HANDOVER.md | 38 KB | Current — primary ops handover |
| CHANGELOG_DEV.md | 72 KB | Current but very large (1,500+ lines) |
| README.md | 106 bytes | Minimal placeholder |

### Session handover docs

- 3 at top level: SESSION_65_TASKS.md, SESSION_68_PIPELINE_REVIEW.md, SESSION_68_TASKS.md
- 39 archived in archive/sessions/
- **Recommendation:** Move all SESSION_* files to docs/handovers/ or archive/sessions/

### Missing docs (identified in PROJECT_STATE_REVIEW.md)

| Needed Doc | Purpose | Partially Written? |
|------------|---------|-------------------|
| NAMING_CONVENTIONS.md | Three-naming system (canonical/MT5/Dukascopy) | No — only described in PROJECT_STATE_REVIEW |
| DATA_LAYOUT.md | Canonical data directory structure | No — only described in PROJECT_STATE_REVIEW |
| CLUSTER_ARCHITECTURE.md | Compute cluster topology | No — only described in PROJECT_STATE_REVIEW |
| PROP_FIRM_UNIVERSES.md | Per-firm tradeable markets + excluded_markets | No — not documented anywhere |

### Contradictions found

- CLAUDE.md describes GCP as active infrastructure; PROJECT_STATE_REVIEW.md marks it deprecated
- CLAUDE.md lists strategy-console VM at 35.223.104.173 as active; it is deprecated
- TRADESTATION_EXPORT_GUIDE.md implies TradeStation is primary data source; Dukascopy is now primary
- IMPROVEMENT_ROADMAP.md duplicates and contradicts PROJECT_STATE_REVIEW.md priorities

---

## 9. TODO / FIXME debt

### Summary

The codebase has remarkably few TODO/FIXME comments in Python code — only 1 hit (in our own audit script). The real technical debt is documented in markdown files.

### Found items

| File | Line | Category | Text | Assessment |
|------|------|----------|------|------------|
| docs/CHALLENGE_VS_FUNDED_SPEC.md | 211 | TODO | validate spreads against live The5ers via MT5 exports | Active — needed before trusting CFD cost model |
| docs/CHALLENGE_VS_FUNDED_SPEC.md | 236 | TODO | populate FTMO config when account active | Deferred — no FTMO account yet |
| docs/CHALLENGE_VS_FUNDED_SPEC.md | 243 | TODO | populate Darwinex config when account active | Deferred — no Darwinex account yet |
| MASTER_HANDOVER.md | 173 | DEPRECATED | Cloud infrastructure section | Session 69 cleanup target |
| MASTER_HANDOVER.md | 178 | DEPRECATED | Cloud files pending deletion | Session 69 cleanup target |

### Implicit debt (not marked in code)

The real technical debt is tracked in CLAUDE.md (issues list) and PROJECT_STATE_REVIEW.md (gaps section), not via inline TODOs. Key items:
1. CFD swap costs not in MC simulator (critical)
2. 120 Dukascopy conversions pending (blocking)
3. test_daily_dd_breach failure (medium)
4. ES config engine param bugs (critical, fix in Session 69)
5. Dashboard Live Monitor broken (low)

### Recommendation

No action needed for TODO comments in Session 69. The codebase uses CLAUDE.md as the issue tracker rather than inline TODOs — this is a valid pattern.

---

## 10. Git state

### Overview

| Metric | Value | Notes |
|--------|-------|-------|
| Branches | 1 (main only) | Clean |
| .git size | 366 MB | Bloated — CSVs in history |
| Pack size | 364.65 MB | Almost all from data files |
| Untracked files | 2 (venv/ + audit WIP) | Clean |
| Recent commits (30 days) | 63 | Active development |
| LFS | Not in use | |

### Suspicious tracked files

**Total: 128 files that should not be in git**

| Category | Count | Size Impact | Action |
|----------|-------|-------------|--------|
| Data/*.csv (TradeStation + Dukascopy) | 40 | ~344 MB | git rm --cached |
| archive/old_outputs/**/*.csv | 68 | ~20 MB | git rm --cached (or BFG to remove from history) |
| strategy_console_storage/**/* | 231 | ~331 MB | git rm --cached |
| docs/audit/*.csv | 4 | ~20 KB | Keep (audit artifacts) |

### Repo bloat analysis

The .git directory is 366 MB, almost entirely from CSV data files committed before .gitignore entries were added. The actual code (Python + YAML + markdown) would be under 5 MB.

**Options for Session 69:**
1. **Minimum:** git rm --cached for Data/ and strategy_console_storage/ (stops tracking, keeps local files)
2. **Full cleanup:** BFG Repo Cleaner to rewrite history and remove CSVs from pack files (reduces .git from 366 MB to ~5 MB, requires force push)

### Recommendation

Option 1 (git rm --cached) for Session 69 — stops the bleeding. Option 2 (BFG) is optional and can be done later when convenient, since it requires a force push and all clones to re-fetch.

---

## 11. Dependencies

### requirements.txt (7 packages)

| Package | Version | Used? | Notes |
|---------|---------|-------|-------|
| numpy | ==2.1.3 | Yes | Core — vectorized trades, MC |
| pandas | ==2.2.2 | Yes | Core — data loading, analysis |
| pyyaml | ==6.0.2 | Yes | Core — config loading |
| streamlit | ==1.37.1 | Yes | Dashboard |
| plotly | ==5.23.0 | Yes | Dashboard charts |
| altair | ==5.3.0 | **No direct import** | Transitive dep of streamlit |
| pytest | >=8.0.0 | Yes | Testing |

### Missing from requirements.txt

| Package | Where Imported | Action |
|---------|---------------|--------|
| paramiko | run_cloud_job.py | Deleted with cloud code in Session 69 |
| scp | run_cloud_job.py | Deleted with cloud code in Session 69 |
| requests | run_cloud_job.py | Deleted with cloud code in Session 69 |

All 3 missing packages are cloud-only dependencies. After cloud code deletion, requirements.txt will be complete.

### Recommendations

- **Remove altair** from requirements.txt — it is a transitive dep of streamlit, not directly imported
- **No packages need adding** — paramiko/scp/requests go away with cloud code deletion
- **Version pins look current** — numpy 2.1.3 and pandas 2.2.2 are recent

---

## 12. Session 69 cleanup recommendations

### Tier 1 — Delete (no risk, confirmed deprecated)

| Item | Files | Est. LOC | Notes |
|------|-------|----------|-------|
| cloud/ directory | 77 | 6,793 | All GCP code, configs, docs |
| run_spot_resilient.py | 1 | 634 | SPOT VM runner |
| run_cloud_sweep.py | 1 | 70 | Cloud sweep wrapper |
| run_cloud_parallel.py | 1 | 143 | Parallel cloud runner |
| run_cloud_job.py | 1 | 480 | Cloud job orchestrator |
| tests/test_cloud_launcher.py | 1 | 1,214 | Cloud launcher tests |
| tests/test_parallel_vm.py | 1 | 476 | Parallel VM tests |
| Dockerfile | 1 | ~20 | Docker build for cloud |
| .dockerignore | 1 | ~10 | Docker ignore |
| .github/workflows/deploy_strategy_console.yml | 1 | ~50 | GCP console deploy CI |
| scripts/run_console_job.py | 1 | 103 | GCP console job runner |
| scripts/setup_dashboard_venv.sh | 1 | ~40 | GCP console venv |
| scripts/start_dashboard.sh | 1 | ~10 | GCP console dashboard |
| scripts/strategy-dashboard.service | 1 | ~15 | GCP systemd service |
| scripts/update_console.sh | 1 | ~15 | GCP console updater |

**Total Tier 1: ~90 files, ~10,073 LOC**

### Tier 2 — Delete after dry-run (proven but cautious)

| Item | Action | Reason |
|------|--------|--------|
| configs/local_sweeps/ES_daily_cfd_v1.yaml | Delete | Buggy (futures params on CFD data) — replaced by corrected ES config |
| configs/local_sweeps/ES_all_timeframes.yaml | Fix | Same bug — update dollars_per_point to CFD value from cfd_markets.yaml |
| Data/ (40 tracked CSVs) | git rm --cached | .gitignore entry exists; stop tracking, keep local files |
| strategy_console_storage/ (231 tracked files) | git rm --cached | GCP console data; stop tracking |
| archive/old_outputs/ (~68 tracked CSVs) | git rm --cached | Historical outputs; stop tracking |

### Tier 3 — Reorganize (no deletions)

| Item | Action |
|------|--------|
| SESSION_65_TASKS.md | Move to archive/sessions/ |
| SESSION_68_TASKS.md | Move to archive/sessions/ (after this session) |
| SESSION_68_PIPELINE_REVIEW.md | Move to docs/ (active reference) |
| requirements.txt | Remove altair (transitive dep) |
| CLAUDE.md | Remove all cloud/GCP references, update deployment section |
| config.yaml | Update default data path or mark as template |

### Tier 4 — Document (write new docs)

| Doc | Purpose | Est. Size |
|-----|---------|-----------|
| docs/NAMING_CONVENTIONS.md | Three-naming system (canonical/MT5/Dukascopy) | ~50 lines |
| docs/DATA_LAYOUT.md | Canonical data directory structure on c240 | ~100 lines |
| docs/CLUSTER_ARCHITECTURE.md | Compute cluster topology | ~80 lines |
| docs/PROP_FIRM_UNIVERSES.md | Per-firm tradeable markets + excluded_markets. The5ers excludes W/NG/US/TY/RTY/HG. FTMO/Darwinex/FundedNext TBD. Critical: sweep = universal, portfolio selection = per-firm filter | ~60 lines |

### Tier 5 — Fix (correctness issues)

| Issue | Severity | Fix Session |
|-------|----------|-------------|
| ES config engine params bug (ES_all_timeframes.yaml) | Critical | 69 |
| test_daily_dd_breach assertion | Medium | 69 |
| Dashboard Live Monitor (engine log + promoted panels) | Low | 70+ |
| excluded_markets not implemented in portfolio selector | Medium | 73 (swap cost session) |

### Tier 6 — Defer (scope for later sessions)

| Item | Session |
|------|---------|
| CFD swap costs in MC simulator | 73 |
| 120 Dukascopy conversions | 71 |
| Gen 8 CPU upgrade (hardware) | When convenient |
| C240 CIMC IP capture | When convenient |
| BFG repo history cleanup (optional) | After Session 69 |
| Per-firm config files (FTMO/Darwinex/FundedNext) | When accounts active |
| ohlc_engine/ directory creation on c240 | 71 |
| MT5 tick export backfill (ticks_mt5_the5ers/) | When needed for spread validation |

### Session estimate

- **Session 69** (cleanup): Tiers 1-3, start Tier 4 = 1 session
- **Session 70** (first sweep): Tier 5 ES config fix + first clean CFD sweep = 1 session
- **Session 71** (conversions): 120 Dukascopy conversions = 1 session
- **Session 72** (full sweep): Distributed 24-market sweep = 1 session
- **Session 73** (swap costs): Tier 5 excluded_markets + Tier 6 swap costs = 1 session

---

*Report generated 2026-04-19 by Claude Code Session 68 audit.*
