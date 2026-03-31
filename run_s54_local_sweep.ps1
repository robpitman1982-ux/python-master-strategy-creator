# SESSION 54 LOCAL SWEEP - All 8 markets daily+60m
# Runs sequentially on local machine, ~2-3hrs per market
# Total estimated time: ~16-24 hours (overnight run)
$ErrorActionPreference = "Continue"
$basePath = "C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator"
Set-Location $basePath
$env:PYTHONPATH = "."

$startTime = Get-Date
Write-Host "SESSION 54 LOCAL SWEEP" -ForegroundColor Cyan
Write-Host "Started: $startTime" -ForegroundColor Cyan

# Market configs with correct dollars_per_point and tick_value per market
$markets = @(
    @{name="ES"; dpp=50.0; tv=12.50},
    @{name="NQ"; dpp=20.0; tv=5.0},
    @{name="CL"; dpp=1000.0; tv=10.0},
    @{name="GC"; dpp=100.0; tv=10.0},
    @{name="SI"; dpp=5000.0; tv=25.0},
    @{name="HG"; dpp=25000.0; tv=12.50},
    @{name="RTY"; dpp=50.0; tv=5.0},
    @{name="YM"; dpp=5.0; tv=5.0}
)

foreach ($m in $markets) {
    $market = $m.name
    $config = "cloud/config_s54_test_$($market.ToLower()).yaml"
    $marketStart = Get-Date
    Write-Host ""
    Write-Host "--- $market --- Starting at $marketStart ---" -ForegroundColor Yellow

    python master_strategy_engine.py --config $config

    $marketEnd = Get-Date
    $elapsed = ($marketEnd - $marketStart).TotalMinutes
    Write-Host "--- $market --- DONE in $([math]::Round($elapsed,1)) min ---" -ForegroundColor Green
}

$totalEnd = Get-Date
$totalElapsed = ($totalEnd - $startTime).TotalHours
Write-Host ""
Write-Host "ALL 8 MARKETS COMPLETE - $([math]::Round($totalElapsed,1)) hours" -ForegroundColor Cyan
