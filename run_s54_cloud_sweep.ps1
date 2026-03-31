# SESSION 54 CLOUD SWEEP — Sequential on-demand VMs
# Launches one market at a time, waits for completion, then next.
# Uses --fire-and-forget so the VM self-uploads and self-deletes.
# Total estimated time: ~8-16 hours (each market ~1-2hrs on 96-core)
# Total estimated cost: ~$10-20 USD
#
# IMPORTANT: Only one VM runs at a time (100 vCPU quota).
# Each VM: creates, runs engine, uploads to GCS, self-deletes.
# After all done: download results with python cloud/download_run.py --latest
#
# Run from repo root:
#   .\run_s54_cloud_sweep.ps1

$ErrorActionPreference = "Continue"
$basePath = "C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator"
Set-Location $basePath
$env:PYTHONPATH = "."

$markets = @("ES", "NQ", "CL", "GC", "SI", "HG", "RTY", "YM")
$startTime = Get-Date

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "SESSION 54 CLOUD SWEEP"                  -ForegroundColor Cyan
Write-Host "On-demand n2-highcpu-96, us-central1-c"  -ForegroundColor Cyan
Write-Host "Started: $startTime"                     -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

foreach ($market in $markets) {
    $config = "cloud/config_s54_test_$($market.ToLower()).yaml"
    $marketStart = Get-Date
    Write-Host "`n========================================" -ForegroundColor Yellow
    Write-Host ">>> $market — Starting at $marketStart <<<" -ForegroundColor Yellow
    Write-Host "Config: $config" -ForegroundColor Gray
    Write-Host "========================================" -ForegroundColor Yellow

    # Launch VM, wait for completion, VM self-deletes
    python cloud/launch_gcp_run.py `
        --config $config `
        --zone us-central1-c `
        --provisioning-model STANDARD `
        --instance-name "s54-$($market.ToLower())"

    $marketEnd = Get-Date
    $elapsed = ($marketEnd - $marketStart).TotalMinutes
    Write-Host ">>> $market — DONE in $([math]::Round($elapsed,1)) min <<<" -ForegroundColor Green
    Write-Host ""

    # Brief pause between launches
    Start-Sleep -Seconds 10
}

$totalEnd = Get-Date
$totalElapsed = ($totalEnd - $startTime).TotalHours
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "ALL 8 MARKETS COMPLETE"                    -ForegroundColor Cyan
Write-Host "Total: $([math]::Round($totalElapsed,1)) hours" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next: Download results and run portfolio selector:" -ForegroundColor White
Write-Host "  python cloud/download_run.py --latest" -ForegroundColor White
