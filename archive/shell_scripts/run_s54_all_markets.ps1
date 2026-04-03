# SESSION 54 — Fire-and-forget: All 8 markets × daily + 60m
# Run from: C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator\
# Each market uses its own config with correct $/point and tick values.
# Strategy types: "all" (15 families including new S54 filters)
# Estimated runtime: 4-8 hours locally depending on CPU cores

$ErrorActionPreference = "Continue"
$basePath = "C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator"
Set-Location $basePath

$markets = @("ES", "NQ", "CL", "GC", "SI", "HG", "RTY", "YM")
$startTime = Get-Date

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "SESSION 54 — All Markets Daily + 60m"   -ForegroundColor Cyan
Write-Host "Started: $startTime"                     -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

foreach ($market in $markets) {
    $config = "cloud/config_s54_test_$($market.ToLower()).yaml"
    $marketStart = Get-Date
    Write-Host "`n>>> $market — Starting at $marketStart <<<" -ForegroundColor Yellow
    Write-Host "Config: $config" -ForegroundColor Gray

    python master_strategy_engine.py --config $config

    $marketEnd = Get-Date
    $elapsed = ($marketEnd - $marketStart).TotalMinutes
    Write-Host ">>> $market — DONE in $([math]::Round($elapsed,1)) min <<<" -ForegroundColor Green
}

$totalEnd = Get-Date
$totalElapsed = ($totalEnd - $startTime).TotalMinutes
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "ALL MARKETS COMPLETE"                      -ForegroundColor Cyan
Write-Host "Total time: $([math]::Round($totalElapsed,1)) min" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan