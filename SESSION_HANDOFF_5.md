MASTER STRATEGY ENGINE
System Handover — Post Session 19 / Pre Session 20
Owner

Robert Pitman

Project

python-master-strategy-creator

Repository

GitHub:
robpitman1982-ux/python-master-strategy-creator

1. PROJECT GOAL

This system is a cloud-based automated strategy discovery engine.

It performs large parameter sweeps across market datasets to discover profitable trading strategies and produce ranked leaderboards.

The architecture combines:

Python research engine
cloud compute (GCP VM)
automated run launcher
strategy console dashboard
persistent dataset storage
result export system

The goal is to run large sweeps across multiple markets and timeframes to discover systematic trading edges.

2. HIGH LEVEL ARCHITECTURE

Current components:

Research Engine

Runs strategy sweeps.

master_strategy_engine.py

Responsibilities:

load dataset
generate parameter combinations
run backtests
filter candidates
refine candidates
generate leaderboard
Cloud Launcher

Responsible for running sweeps on cloud compute.

run_cloud_sweep.py
cloud/launch_gcp_run.py

Responsibilities:

read configuration
perform preflight checks
launch GCP VM
upload repo bundle
execute strategy sweep
download results
destroy VM
Strategy Console

Web dashboard built with Streamlit.

dashboard.py

Runs on a persistent VM called:

strategy-console

Purpose:

monitor runs
view uploaded datasets
view exports
view run status
eventually launch runs
Persistent Storage

Console uses a dedicated storage root:

~/strategy_console_storage

Structure:

strategy_console_storage/
    uploads/
    runs/
    exports/
3. DATASETS

Datasets are uploaded to:

/home/robpitman1982/strategy_console_storage/uploads

Current uploaded datasets include:

ES_1m_2008_2026_tradestation.csv
ES_5m_2008_2026_tradestation.csv
ES_15m_2008_2026_tradestation.csv
ES_30m_2008_2026_tradestation.csv
ES_60m_2008_2026_tradestation.csv
ES_daily_2008_2026_tradestation.csv

CL_1m_2008_2026_tradestation.csv
CL_5m_2008_2026_tradestation.csv
CL_15m_2008_2026_tradestation.csv
CL_30m_2008_2026_tradestation.csv
CL_60m_2008_2026_tradestation.csv
CL_daily_2008_2026_tradestation.csv

Datasets range from daily → 1 minute resolution.

4. RUN CONFIGURATION

Current quick test config:

cloud/config_quick_test.yaml

Example dataset entry:

datasets:
  - path: "Data/ES_60m_2008_2026_tradestation.csv"

This originally assumed datasets were stored in the repo Data/ directory.

However the system now uses console storage.

5. DISCOVERED ISSUES

During the latest run attempts several architectural problems were discovered.

Issue 1 — Dataset Path Mismatch

The launcher expected:

repo/Data/

But datasets now exist in:

strategy_console_storage/uploads

Resulting error:

FileNotFoundError: Dataset not found

Solution implemented in Session 20:

Dataset resolver now searches:

absolute path
console uploads folder
repo Data folder
Issue 2 — Streamlit Compatibility

Dashboard used:

st.dataframe(... hide_index=True)

The VM Streamlit version does not support this.

Error:

DataFrameSelectorMixin.dataframe() got unexpected argument 'hide_index'

Fix:

Removed unsupported argument.

Issue 3 — Arrow / LargeUtf8 Error

Streamlit crashed when rendering tables:

Unrecognized type: LargeUtf8

Cause:

Arrow serialization incompatibility.

Fix implemented:

Tables now render using fallback logic:

try dataframe
except -> plain text table

This prevents dashboard crashes.

Issue 4 — Run History Detection

Dashboard initially showed:

No launcher-managed runs found

Even when runs existed.

Cause:

Run discovery logic only scanned one folder.

Fix:

Run discovery updated to read canonical runs directory.

Issue 5 — Dataset Display Panel

Dataset panel initially crashed due to dataframe rendering.

Now uses safe rendering.

Issue 6 — Manual Run Launch Confusion

Previously runs were launched manually via CLI.

Example:

python run_cloud_sweep.py --config cloud/config_quick_test.yaml

However configuration editing became confusing once datasets moved to console storage.

Session 20 introduces:

scripts/run_console_job.py

Which will build configs automatically from selected datasets.

6. CURRENT SYSTEM STATUS

At the end of Session 19 testing:

Dashboard

Working and stable.

Displays:

system readiness
storage paths
uploaded datasets
run history
exports
Console VM

Running correctly:

strategy-console

Dashboard accessible at:

http://VM_IP:8501
Dataset Storage

Working correctly.

Datasets successfully uploaded and visible.

Cloud Launcher

Working.

Preflight checks succeed.

VM launch pipeline operational.

Only remaining issue before run

Dataset path mismatch was preventing job start.

This is resolved in Session 20.

7. SESSION 20 OBJECTIVES

Session 20 focuses on system cleanup and stability.

Key improvements implemented:

1. Dataset resolver

Automatically finds datasets from console uploads.

2. Console table rendering

Rewritten to avoid Streamlit Arrow crashes.

3. Path normalization

Centralized path management.

4. Dashboard stability

All dataframe rendering made crash-safe.

5. Dataset metadata parsing

Market and timeframe derived from filenames.

6. Run discovery improvements

Dashboard reliably detects completed runs.

7. Simplified run launcher

New helper script will generate configs automatically.

8. Removal of hardcoded paths

System now uses path constants.

8. NEXT EXPECTED WORKFLOW

After Session 20 cleanup the intended workflow becomes:

1️⃣ Upload datasets to console
2️⃣ Open Strategy Console
3️⃣ Select datasets
4️⃣ Launch run
5️⃣ Cloud VM executes sweep
6️⃣ Results downloaded automatically
7️⃣ Dashboard displays leaderboard

9. FUTURE SYSTEM GOALS

Next development phases include:

Portfolio Builder

Automatically combine discovered strategies into diversified portfolios.

Multi-Market Sweeps

Run simultaneous sweeps across:

ES
CL
NQ
GC
ZN
Timeframe Expansion

Support multiple timeframes in same run.

Automated Leaderboard Analysis

Rank strategies by robustness metrics.

Fully Automated Runs

Schedule sweeps automatically.

10. KEY PROJECT PRINCIPLE

The system is designed to be:

edge discovery first
automation second
scaling third

Focus is on discovering real, robust trading edges before scaling compute.

11. CURRENT STATUS SUMMARY
Component	Status
Research engine	stable
Cloud launcher	stable
Console dashboard	stable
Dataset storage	working
Run discovery	improved
Table rendering	fixed
Dataset path handling	fixed
12. SESSION STATUS

Session 19 discovered multiple architectural bugs during real system testing.

Session 20 performs a full cleanup and stabilization pass across the console, launcher, and dataset handling logic.

FINAL NOTE

Session 20 tasks have now been implemented by Codex and pushed into the repository.

The system is ready for the next run cycle after validation.