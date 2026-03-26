# GCP Windows Runbook

## Recommended one-click flow

Use the top-level wrapper from the project root. It delegates to the Windows-first Python launcher, which builds a manifest, bundles only the datasets required by the selected config, uploads one bundle to a deterministic `/tmp` staging path on the VM, waits for validated startup, monitors structured status, downloads a preserved artifacts tarball, verifies the results locally, and destroys the VM when the run is safely complete.

## Recommended commands

Dry run only:

```powershell
python run_cloud_sweep.py --dry-run
```

Safe first real run that preserves the VM:

```powershell
python run_cloud_sweep.py --keep-vm
```

Normal one-click run:

```powershell
python run_cloud_sweep.py
```

## Equivalent launcher commands

Dry run:

```powershell
python -m cloud.launch_gcp_run --config cloud/config_es_all_timeframes_gcp96.yaml --dry-run
```

Safe first real run:

```powershell
python -m cloud.launch_gcp_run --config cloud/config_es_all_timeframes_gcp96.yaml --keep-vm
```

Normal one-click run:

```powershell
python -m cloud.launch_gcp_run --config cloud/config_es_all_timeframes_gcp96.yaml
```

Use a different config:

```powershell
python run_cloud_sweep.py --config cloud/config_quick_test.yaml
```

## What the launcher does

1. Loads the selected config.
2. Resolves only the datasets listed in that config.
3. Builds `cloud_results/<run-id>/run_manifest.json`.
4. Creates `cloud_results/<run-id>/input_bundle.tar.gz`.
5. If `--dry-run` is used, stops there with a local-only validation result.
6. Otherwise creates the VM and waits for SSH readiness.
7. Uploads the bundle, manifest, and remote runner to a fixed `/tmp/strategy_engine_runs/<run-id>/` path.
8. Validates the remote payload before starting the engine.
9. Confirms the remote runner really launched before monitoring.
10. Monitors remote run status plus existing dataset `status.json` progress files.
11. Downloads `artifacts.tar.gz` first, checks it exists and is non-empty, extracts it locally, verifies preserved results, and only then destroys the VM unless `--keep-vm` is set.

## Local outputs

Each run lands in:

```text
cloud_results/<run-id>/
```

That folder includes:

- `run_manifest.json`
- `launcher_status.json`
- `launcher_status.jsonl`
- `input_bundle.tar.gz`
- `artifacts.tar.gz`
- `artifacts/` extracted logs, status, and outputs
- `cloud_results/LATEST_RUN.txt` pointing to the newest run directory

At the end of each run the launcher prints a final summary including:

- `run_id`
- local results path
- `run_outcome`
- `vm_outcome`
- whether verification passed
- whether billing should now be stopped

## Parallel dual-VM runs

To halve wall-clock time, split the workload across two VMs (VM-A handles ES 5m, VM-B handles daily/60m/30m/15m).

Launch both VMs (fire-and-forget, both self-delete after uploading results):

```powershell
python run_cloud_parallel.py --fire-and-forget
```

Dry run to verify manifests only:

```powershell
python run_cloud_parallel.py --dry-run
```

Use on-demand VMs when SPOT is unavailable:

```powershell
python run_cloud_parallel.py --config-a cloud/config_es_vm_a_ondemand.yaml --config-b cloud/config_es_vm_b_ondemand.yaml --fire-and-forget
```

After both VMs complete, merge and download results:

```powershell
# Auto-discover and merge the two most recent runs
python cloud/download_run.py --latest-pair

# Or manually specify run IDs
python cloud/download_run.py --merge strategy-sweep-a-20260326T120000Z strategy-sweep-b-20260326T120001Z
```

Download a single run (original flow, still supported):

```powershell
python cloud/download_run.py --latest
python cloud/download_run.py strategy-sweep-20260326T120000Z
```

After any download, `ultimate_leaderboard.csv` is automatically regenerated from all locally available runs.

## Prerequisites

- Windows machine with Python available as `python`
- `gcloud` installed and authenticated
- Access to the selected GCP project and zone
- The datasets referenced by the chosen config present locally
