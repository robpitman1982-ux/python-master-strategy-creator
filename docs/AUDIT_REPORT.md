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
