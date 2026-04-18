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
| `HANDOVER.md` | file | 40 KB | Ops handover doc | Active |
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
