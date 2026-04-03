# SESSION 54 CLOUD SWEEP - All 8 markets on GCP on-demand
$ErrorActionPreference = "Continue"
$basePath = "C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator"
Set-Location $basePath
$env:PYTHONPATH = "."

$markets = @("ES", "NQ", "CL", "GC", "SI", "HG", "RTY", "YM")
$startTime = Get-Date

Write-Host "SESSION 54 CLOUD SWEEP" -ForegroundColor Cyan
Write-Host "Started: $startTime" -ForegroundColor Cyan

foreach ($market in $markets) {
    $config = "cloud/config_s54_test_$($market.ToLower()).yaml"
    $marketStart = Get-Date
    Write-Host ""
    Write-Host "--- $market --- Starting at $marketStart ---" -ForegroundColor Yellow
    Write-Host "Config: $config" -ForegroundColor Gray

    python cloud/launch_gcp_run.py --config $config --zone us-central1-c --provisioning-model STANDARD --instance-name "s54-$($market.ToLower())"

    $marketEnd = Get-Date
    $elapsed = ($marketEnd - $marketStart).TotalMinutes
    Write-Host "--- $market --- DONE in $([math]::Round($elapsed,1)) min ---" -ForegroundColor Green

    Start-Sleep -Seconds 10
}

$totalEnd = Get-Date
$totalElapsed = ($totalEnd - $startTime).TotalHours
Write-Host ""
Write-Host "ALL 8 MARKETS COMPLETE - $([math]::Round($totalElapsed,1)) hours" -ForegroundColor Cyan
