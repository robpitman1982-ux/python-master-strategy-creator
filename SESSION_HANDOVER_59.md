# SESSION 59 HANDOVER — Bulletproof SPOT Runner + 9 New Markets

**Date**: 2026-04-03
**Console**: pitman_nikola@35.223.104.173
**GCP Project**: project-c6c16a27-e123-459c-b7a
**Bucket**: gs://strategy-artifacts-nikolapitman/
**Credit**: ~$435 (expires July 2, 2026)

---

## What was done

### Task 1: Launcher defaults fixed
- `cloud/launch_gcp_run.py`: `DEFAULT_STRATEGY_CONSOLE_REMOTE_ROOT` and `DEFAULT_STRATEGY_CONSOLE_REMOTE_USER` updated from `robpitman1982` to `pitman_nikola`
- `run_cloud_sweep.py`: fallback path updated to `/home/pitman_nikola/strategy_console_storage`

### Task 2: 9 new market configs created
All in `cloud/` directory with SPOT provisioning:

| Config File | Market | $/Point | $/Tick | OOS Split |
|-------------|--------|---------|--------|-----------|
| config_ec_3tf_spot.yaml | Euro FX | $125,000 | $6.25 | 2019-01-01 |
| config_jy_3tf_spot.yaml | Japanese Yen | $125,000 | $6.25 | 2019-01-01 |
| config_bp_3tf_spot.yaml | British Pound | $62,500 | $6.25 | 2019-01-01 |
| config_ad_3tf_spot.yaml | Australian Dollar | $100,000 | $10.00 | 2019-01-01 |
| config_ng_3tf_spot.yaml | Natural Gas | $10,000 | $10.00 | 2019-01-01 |
| config_us_3tf_spot.yaml | 30-Year T-Bond | $1,000 | $31.25 | 2019-01-01 |
| config_ty_3tf_spot.yaml | 10-Year T-Note | $1,000 | $15.625 | 2019-01-01 |
| config_w_3tf_spot.yaml | Wheat | $50 | $12.50 | 2019-01-01 |
| config_btc_3tf_spot.yaml | Bitcoin (CME) | $5 | $25.00 | 2021-01-01 |

Each config has 3 timeframes: daily, 60m, 30m. All use n2-highcpu-96 SPOT with 94 workers.

### Task 3: SPOT runner built
`run_spot_resilient.py` — queue-based runner that:
- Manages a YAML queue of single-TF sweep jobs
- Generates single-TF configs on-the-fly from multi-TF base configs
- Launches via `run_cloud_sweep.py --fire-and-forget`
- Polls GCS bucket for completion (artifacts.tar.gz)
- On preemption: rotates through 7 US zones, retries up to 5 times
- Downloads results after each completed job
- Queue survives Ctrl-C / console reboot — just re-run to resume

### Task 4: Test run — DEFERRED
Needs to run on the strategy-console VM, not locally. See instructions below.

---

## How to launch the full sweep

### Step 1: Test with one cheap job
```bash
ssh pitman_nikola@35.223.104.173
cd ~/python-master-strategy-creator
git pull

# Generate a 1-job queue (AD daily only)
python3 run_spot_resilient.py --generate-queue --markets AD --timeframes daily

# Run it
python3 run_spot_resilient.py

# Verify:
# - VM created on SPOT
# - Sweep completes (~20-40 min for daily)
# - Artifacts in gs://strategy-artifacts-nikolapitman/runs/<run_id>/
# - Results downloaded to cloud_results/
# - spot_queue.yaml shows status: completed
```

### Step 2: Generate full queue
```bash
# Delete the test queue and generate all 27 jobs
python3 run_spot_resilient.py --generate-queue

# Check it
python3 run_spot_resilient.py --status
# Should show: 27 total, 0 completed, 0 failed, 27 pending
```

### Step 3: Start grinding
```bash
# Run in tmux/screen so it survives SSH disconnect
tmux new -s sweep
python3 run_spot_resilient.py

# Detach: Ctrl-B then D
# Reattach later: tmux attach -t sweep
```

Expected runtime: ~1-2 days for all 27 jobs (each job ~30-60 min + overhead).
At ~$0.75/hour for SPOT n2-highcpu-96, total cost estimate: ~$20-40.

### Step 4: After completion
```bash
# Check final status
python3 run_spot_resilient.py --status

# If any failed, retry them
python3 run_spot_resilient.py --retry-failed

# Regenerate ultimate leaderboard (all 17 markets)
python3 cloud/download_run.py --latest
```

---

## Issues / risks

1. **Zone capacity**: SPOT availability varies. The runner rotates through 7 zones automatically. If all zones fail, it waits 10 min and retries.

2. **Long sweeps on SPOT**: 30m timeframes may take 60+ min and risk preemption. The runner handles this — it just retries. 15m timeframes are intentionally excluded (too long).

3. **100 vCPU quota**: Only 1 VM at a time with n2-highcpu-96. The runner processes jobs sequentially.

4. **BTC shorter history**: Only ~6 years of data (CME futures started Dec 2017). May produce fewer robust strategies.

5. **Currency futures price scale**: EC/JY/BP/AD have small decimal prices. The engine handles this fine — ATR adapts automatically. But dollar values per trade will be large (e.g., 1 EC point = $125,000).

---

## CFD mapping status
**Pending** — Rob to check MT5 symbols for the 9 new markets. This is needed for The5ers EA deployment but not for the sweep itself.

---

## Existing results (not re-run)
8 markets already swept with 315 accepted strategies in `Outputs/ultimate_leaderboard_bootcamp.csv`:
ES, CL, NQ, SI, HG, RTY, YM, GC
