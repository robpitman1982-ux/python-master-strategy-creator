# SESSION 59 — Bulletproof SPOT Runner + 9 New Market Sweeps
# Date: 2026-04-03
# Execute with: claude --dangerously-skip-permissions
# Console: SSH to pitman_nikola@35.223.104.173, repo at ~/python-master-strategy-creator
# GCP Project: project-c6c16a27-e123-459c-b7a
# Bucket: gs://strategy-artifacts-nikolapitman/
# Credit: $435.26 (expires July 2, 2026)

# IMPORTANT: This session runs on Nikola's GCP account, NOT Rob's old account.
# The launcher already uses DEFAULT_BUCKET_NAME = "strategy-artifacts-nikolapitman"
# The strategy-console user is pitman_nikola, NOT robpitman1982.
# Update DEFAULT_STRATEGY_CONSOLE_REMOTE_ROOT and DEFAULT_STRATEGY_CONSOLE_REMOTE_USER.

# ============================================================
# CONTEXT
# ============================================================
# 9 new markets have been downloaded from TradeStation and pushed to git:
#   EC (Euro FX), JY (Japanese Yen), BP (British Pound), AD (Australian Dollar),
#   NG (Natural Gas), US (30-Year Treasury Bond), TY (10-Year Treasury Note),
#   W (Wheat), BTC (Bitcoin)
#
# We sweep ONLY daily + 60m + 30m (skip 15m — too long, preemption risk on SPOT).
# That's 9 markets × 3 timeframes = 27 individual SPOT jobs.
#
# Each job is ONE timeframe for ONE market on its own VM.
# VM spins up, runs sweep, uploads to GCS, self-deletes.
# If preempted, the runner retries on a different zone.
#
# EXISTING 8 markets (ES, CL, NQ, SI, HG, RTY, YM, GC) are NOT re-run.
# They already have 315 strategies in Outputs/ultimate_leaderboard_bootcamp.csv.

# ============================================================
# CONTRACT SPECIFICATIONS FOR NEW MARKETS
# ============================================================
# These specs are needed for the config YAML files.
#
# | Market | Full Name           | $/Point     | Tick Size | $/Tick  | Slippage Ticks |
# |--------|---------------------|-------------|-----------|---------|----------------|
# | EC     | Euro FX             | $125,000    | 0.00005   | $6.25   | 2              |
# | JY     | Japanese Yen        | $125,000    | 0.0000005 | $6.25   | 2              |
# | BP     | British Pound       | $62,500     | 0.0001    | $6.25   | 2              |
# | AD     | Australian Dollar   | $100,000    | 0.0001    | $10.00  | 2              |
# | NG     | Natural Gas         | $10,000     | 0.001     | $10.00  | 2              |
# | US     | 30-Year T-Bond      | $1,000      | 0.03125   | $31.25  | 2              |
# | TY     | 10-Year T-Note      | $1,000      | 0.015625  | $15.625 | 2              |
# | W      | Wheat (CBOT)        | $50         | 0.25      | $12.50  | 2              |
# | BTC    | Bitcoin (CME)       | $5          | 5.0       | $25.00  | 2              |
#
# NOTE: For the engine, what matters is dollars_per_point and tick_value.
# The engine computes PnL as: (exit_price - entry_price) * dollars_per_point
# Slippage is: slippage_ticks * tick_value deducted per trade
#
# SPECIAL NOTES:
# - EC/JY/BP/AD: These are currency futures priced in USD per unit of foreign currency.
#   Prices are small decimals (e.g., EC ~1.08, JY ~0.0063, BP ~1.26, AD ~0.66).
#   The engine should handle these fine — filters use ATR which adapts automatically.
# - NG: Extremely volatile. Prices ~$2-5 per MMBtu. $10,000 per point.
# - US/TY: Bond prices quoted in 32nds. TradeStation exports decimal prices.
#   US ~120, TY ~110. $1,000 per point.
# - W: Wheat priced in cents per bushel. ~$550. $50 per point.
# - BTC: Shorter data history (CME BTC futures started Dec 2017).
#   Use oos_split_date: "2021-01-01" for BTC (gives ~3yr IS, ~5yr OOS).

# ============================================================
# TASK 1: Fix launcher defaults for Nikola's console
# ============================================================
# File: cloud/launch_gcp_run.py
# Update these constants:
#   DEFAULT_STRATEGY_CONSOLE_REMOTE_ROOT = "/home/pitman_nikola/strategy_console_storage"
#   DEFAULT_STRATEGY_CONSOLE_REMOTE_USER = "pitman_nikola"
#
# Also verify DEFAULT_BUCKET_NAME = "strategy-artifacts-nikolapitman" (should already be set).
#
# Create the storage directory on the console if it doesn't exist:
#   The runner script may need to mkdir -p this path on the console.
#
# Commit: "fix: update launcher defaults for Nikola's GCP console"

# ============================================================
# TASK 2: Create 9 config YAML files (one per market, 3 TF each)
# ============================================================
# Create cloud/config_<market>_3tf_spot.yaml for each new market.
# Each config has 3 datasets (daily, 60m, 30m) for that market.
# All configs use:
#   - provisioning_model: "SPOT"
#   - zone: "us-central1-f" (default, runner will override per-job)
#   - machine_type: "n2-highcpu-96"
#   - max_workers_sweep: 94
#   - max_workers_refinement: 94
#   - max_candidates_to_refine: 5
#   - oos_split_date: "2019-01-01" (except BTC: "2021-01-01")
#
# Market-specific engine settings from the contract specs table above.
# Use commission_per_contract: 2.00 for all.
#
# Files to create:
#   cloud/config_ec_3tf_spot.yaml
#   cloud/config_jy_3tf_spot.yaml
#   cloud/config_bp_3tf_spot.yaml
#   cloud/config_ad_3tf_spot.yaml
#   cloud/config_ng_3tf_spot.yaml
#   cloud/config_us_3tf_spot.yaml
#   cloud/config_ty_3tf_spot.yaml
#   cloud/config_w_3tf_spot.yaml
#   cloud/config_btc_3tf_spot.yaml
#
# Commit: "config: add 9 new market configs for SPOT sweeps (EC JY BP AD NG US TY W BTC)"

# ============================================================
# TASK 3: Build run_spot_resilient.py — the SPOT runner
# ============================================================
# File: run_spot_resilient.py (in repo root, next to run_cloud_sweep.py)
#
# This is the main deliverable. A single script that:
#   1. Manages a queue of sweep jobs (YAML file: spot_queue.yaml)
#   2. Picks the next PENDING job
#   3. Generates a single-timeframe config on the fly (or uses pre-built)
#   4. Launches it via run_cloud_sweep.py or launch_gcp_run.py
#   5. Monitors for completion (VM gone + artifacts in bucket)
#   6. If preempted: rotates to next zone, retries
#   7. If completed: marks job DONE, moves to next
#   8. Repeats until all jobs are DONE
#
# QUEUE FILE FORMAT (spot_queue.yaml):
# ---
# created: "2026-04-03T12:00:00Z"
# jobs:
#   - market: EC
#     timeframe: daily
#     config: cloud/config_ec_3tf_spot.yaml
#     status: pending          # pending | running | completed | failed
#     zone: null
#     run_id: null
#     attempts: 0
#     last_error: null
#     completed_at: null
#   - market: EC
#     timeframe: 60m
#     config: cloud/config_ec_3tf_spot.yaml
#     status: pending
#     ...
# (27 total jobs: 9 markets × 3 timeframes)
#
# KEY DESIGN DECISIONS:
#
# A) ONE TIMEFRAME PER VM: Each job runs a SINGLE timeframe for a single market.
#    This means the config passed to the launcher should only contain ONE dataset entry.
#    The runner dynamically creates a temporary config with just that one dataset,
#    inheriting engine/pipeline/promotion/leaderboard settings from the market's base config.
#
# B) ZONE ROTATION ORDER:
#    ZONE_ROTATION = [
#        "us-central1-f",     # Best SPOT availability (proven)
#        "us-central1-c",     # Second choice
#        "us-central1-b",     # Third
#        "us-east1-b",        # East US fallback
#        "us-east1-c",        # East US fallback
#        "us-west1-b",        # West US fallback
#        "us-west1-a",        # West US fallback
#    ]
#    On preemption, try next zone. After exhausting all zones, wait 10 minutes
#    and restart from the top.
#
# C) MAX RETRIES PER JOB: 5. After 5 failed attempts, mark as "failed" and move on.
#    The user can manually retry failed jobs later.
#
# D) RUNNING FROM STRATEGY CONSOLE: This script is designed to run on the
#    strategy-console VM (35.223.104.173) via SSH. It calls launch_gcp_run.py
#    which handles all the VM creation, bundle upload, monitoring, and cleanup.
#    The runner just orchestrates the queue.
#
# E) FIRE-AND-FORGET MODE: Each job should use --fire-and-forget flag.
#    The launcher uploads the bundle to GCS first (avoiding SCP timeout),
#    creates the VM with a startup script, and exits immediately.
#    The runner then polls for completion by checking:
#      - gcloud compute instances list (VM gone = completed or preempted)
#      - gcloud storage ls gs://strategy-artifacts-nikolapitman/runs/<run_id>/
#        (artifacts present = completed successfully)
#
# F) COMPLETION DETECTION:
#    After launching fire-and-forget, poll every 60 seconds:
#      1. Is the VM still running? (gcloud compute instances describe)
#      2. If VM is gone:
#         a. Check bucket for artifacts.tar.gz
#         b. If present → job COMPLETED
#         c. If absent → job was preempted → retry with next zone
#
# G) DOWNLOAD AFTER COMPLETION:
#    After each job completes, run: python3 cloud/download_run.py --run-id <run_id>
#    This downloads results locally. After ALL jobs complete, run the
#    master leaderboard aggregator to consolidate everything.

# CLI INTERFACE:
#
# # Generate the queue for all 9 new markets
# python3 run_spot_resilient.py --generate-queue
#
# # Start grinding (runs for 1-2 days unattended on console)
# python3 run_spot_resilient.py
#
# # Check status without running
# python3 run_spot_resilient.py --status
#
# # Resume after interruption (Ctrl-C, console reboot, etc.)
# python3 run_spot_resilient.py  # just run again, picks up from queue
#
# # Run only specific markets
# python3 run_spot_resilient.py --markets EC,JY,BP
#
# # Run only specific timeframes
# python3 run_spot_resilient.py --timeframes daily,60m
#
# # Retry failed jobs
# python3 run_spot_resilient.py --retry-failed
#
# IMPLEMENTATION NOTES:
# - Use subprocess to call: python3 run_cloud_sweep.py --config <tmp_config> --fire-and-forget
# - Or call launch_gcp_run.py directly with the right args
# - Read spot_queue.yaml at startup, write back after each job state change
# - Use proper YAML loading (PyYAML should be available)
# - Log everything to spot_runner.log
# - Print clear progress: "[3/27] EC 60m — SPOT us-central1-f — launching..."
# - On completion print summary: "22/27 completed, 3 failed, 2 pending"
#
# Commit: "feat: build bulletproof SPOT runner with queue management and zone rotation"

# ============================================================
# TASK 4: Test with one cheap market
# ============================================================
# Before unleashing on all 27 jobs, test the runner with a single cheap job:
#   python3 run_spot_resilient.py --generate-queue --markets AD --timeframes daily
#
# This creates a queue with just 1 job: AD daily.
# Run it and verify:
#   - Config generated correctly (dollars_per_point, tick_value match AD specs)
#   - VM created on SPOT
#   - Sweep completes
#   - Artifacts uploaded to gs://strategy-artifacts-nikolapitman/
#   - Results downloaded
#   - Queue file updated with status=completed
#
# If the test passes, the runner is ready for the full 27-job sweep.
#
# Commit: "test: verify SPOT runner with AD daily test sweep"

# ============================================================
# TASK 5: Update CLAUDE.md and CHANGELOG
# ============================================================
# Update CLAUDE.md with:
#   - 9 new markets and their contract specs
#   - run_spot_resilient.py usage instructions
#   - New console details (pitman_nikola, 35.223.104.173)
#
# Update CHANGELOG_DEV.md with session 59 entry.
#
# Commit: "docs: update CLAUDE.md and CHANGELOG for Session 59"

# ============================================================
# TASK 6: Write SESSION_HANDOVER_59.md
# ============================================================
# Include:
#   - SPOT runner status (working/tested?)
#   - Queue state (how many jobs done/pending/failed)
#   - Any issues encountered
#   - Instructions for launching the full 27-job sweep
#   - Contract specs for all 9 new markets
#   - CFD mapping status (pending — Rob to check MT5 symbols)
#
# Commit: "docs: Session 59 handover"

# ============================================================
# EXECUTION ORDER
# ============================================================
# 1. Task 1 — Fix launcher console defaults
# 2. Task 2 — Create 9 market configs
# 3. Task 3 — Build run_spot_resilient.py
# 4. Task 4 — Test with AD daily
# 5. Task 5 — Update docs
# 6. Task 6 — Handover

# ============================================================
# SAFETY RAILS
# ============================================================
# - Always use provisioning_model: "SPOT" in configs (never "STANDARD")
# - Always use --fire-and-forget to avoid SCP timeout on SPOT
# - Never run 15m timeframes in this session (too long for SPOT)
# - Max 1 VM at a time (100 vCPU quota = exactly 1 n2-highcpu-96)
# - If a VM doesn't self-delete after 2 hours, manually delete it
# - Check GCP billing after the test run to verify costs are reasonable
# - The strategy-console user is pitman_nikola, NOT robpitman1982
# - The bucket is gs://strategy-artifacts-nikolapitman/, NOT gs://strategy-artifacts-robpitman/
