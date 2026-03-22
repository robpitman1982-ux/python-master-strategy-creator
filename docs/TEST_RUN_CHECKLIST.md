# Test Run Checklist

## Before The Run

1. Upload the dataset with WinSCP to `~/strategy_console_storage/uploads`.
2. Open the dashboard at `http://strategy-console:8501`.
3. Confirm the latest Git commit shown in the sidebar matches the branch tip.
4. Confirm the dashboard readiness panel says `ready` or clearly explains what is missing.

## Launch The Run

1. SSH to the launcher machine.
2. Start the run with the intended config, for example:
   `python run_cloud_sweep.py --config cloud/config_quick_test.yaml`
3. Keep the dashboard open during the run to watch run outcome, billing state, and operator actions.

## Where Results Should Land

- Uploaded datasets: `~/strategy_console_storage/uploads`
- Canonical run folders: `~/strategy_console_storage/runs`
- Exported files: `~/strategy_console_storage/exports`

## After The Run

1. Check the latest run outcome in the dashboard.
2. Confirm billing status is `stopped`, `maybe_stopped`, or `still_running`.
3. Review the operator action summary and any recovery commands.
4. If a leaderboard exists, preview it in the dashboard and then pull files from `~/strategy_console_storage/exports` or the run folder with WinSCP.

## If The VM Is Preserved

1. Use the recovery commands shown in the dashboard.
2. Download artifacts before deleting the VM.
3. Delete the instance only after outputs and logs are safely retrieved.
