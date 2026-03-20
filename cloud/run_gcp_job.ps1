<#
.SYNOPSIS
    Fully automated GCP cloud run for the Strategy Discovery Engine.
    Creates VM -> uploads data -> waits for engine -> downloads results -> destroys VM.

.PARAMETER ConfigFile
    Path to the YAML config file. Default: cloud/config_es_all_timeframes_gcp96.yaml

.PARAMETER MachineType
    GCP machine type. Default: n2-highcpu-96

.PARAMETER Zone
    GCP zone. Default: australia-southeast2-a (Melbourne)

.PARAMETER DataDir
    Local directory containing CSV data files. Default: Data

.PARAMETER OutputDir
    Local directory prefix for results. Default: cloud_outputs

.PARAMETER InstanceName
    VM instance name. Default: strategy-sweep

.PARAMETER SkipDestroy
    If set, don't destroy the VM after downloading results.

.EXAMPLE
    .\cloud\run_gcp_job.ps1
    .\cloud\run_gcp_job.ps1 -ConfigFile cloud/config_es_5m_only.yaml -OutputDir cloud_outputs_5m
#>

param(
    [string]$ConfigFile = "cloud/config_es_all_timeframes_gcp96.yaml",
    [string]$MachineType = "n2-highcpu-96",
    [string]$Zone = "australia-southeast2-a",
    [string]$DataDir = "Data",
    [string]$OutputDir = "cloud_outputs",
    [string]$InstanceName = "strategy-sweep",
    [switch]$SkipDestroy = $false
)

# --- Critical PowerShell settings ---
# Use gcloud.cmd via full path — "gcloud.cmd" alone fails when Cloud SDK is not on PATH
# (e.g. when run as a subprocess from Claude Code / bash / Task Scheduler).
# The Cloud SDK installs to AppData\Local, which is only added to PATH by the user's
# interactive shell profile, not by subprocess environments.
$GcloudBin = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin"
$Gcloud = "$GcloudBin\gcloud.cmd"
if (-not (Test-Path $Gcloud)) {
    # Fallback: hope it's on PATH (interactive terminal use)
    $Gcloud = "gcloud.cmd"
}
# Don't terminate on stderr warnings from gcloud
$ErrorActionPreference = "Continue"
# Use native OpenSSH instead of PuTTY (fixes freezing and tilde issues)
$env:CLOUDSDK_SSH_NATIVE = "1"

# --- Resolve paths ---
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
# Ensure we work from the project directory so relative paths work
Push-Location $ProjectDir

$StartupScript = "cloud/gcp_startup.sh"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmm"

# --- Detect GCP username (OS Login maps to lowercase email prefix) ---
$GcpAccount = (& $Gcloud config get-value account 2>$null).Trim()
$GcpUser = ($GcpAccount -split "@")[0] -replace "\.", "_"
if (-not $GcpUser) { $GcpUser = "rob" }
$RemoteHome = "/home/$GcpUser"
Write-Host "Detected GCP user: $GcpUser (home: $RemoteHome)" -ForegroundColor Gray

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " GCP Strategy Engine - Automated Run" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Instance:  $InstanceName"
Write-Host "Machine:   $MachineType"
Write-Host "Zone:      $Zone"
Write-Host "Config:    $ConfigFile"
Write-Host "Data dir:  $DataDir"
Write-Host "Output:    $OutputDir"
Write-Host "GCP user:  $GcpUser"
Write-Host "============================================" -ForegroundColor Cyan

# ---------------------------------------------------------------
# STEP 1: Create VM with startup script
# ---------------------------------------------------------------
Write-Host "`n[1/7] Creating VM..." -ForegroundColor Yellow

# Check if instance already exists
$existing = & $Gcloud compute instances list --filter="name=$InstanceName" --format="value(name)" 2>$null
if ($existing) {
    Write-Host "  Instance '$InstanceName' already exists. Deleting..." -ForegroundColor Red
    & $Gcloud compute instances delete $InstanceName --zone=$Zone --quiet
    Start-Sleep -Seconds 15
}

& $Gcloud compute instances create $InstanceName `
    --zone=$Zone `
    --machine-type=$MachineType `
    --provisioning-model=SPOT `
    --instance-termination-action=STOP `
    --image-family=ubuntu-2404-lts-amd64 `
    --image-project=ubuntu-os-cloud `
    --boot-disk-size=120GB `
    --boot-disk-type=pd-ssd `
    --metadata-from-file startup-script=$StartupScript

Write-Host "  VM created." -ForegroundColor Green

# ---------------------------------------------------------------
# STEP 2: Wait for SSH
# ---------------------------------------------------------------
Write-Host "`n[2/7] Waiting for SSH..." -ForegroundColor Yellow

$sshReady = $false
for ($i = 1; $i -le 40; $i++) {
    $result = & $Gcloud compute ssh $InstanceName --zone=$Zone --command="echo ready" 2>$null
    if ($result -match "ready") {
        $sshReady = $true
        Write-Host "  SSH ready (attempt $i)" -ForegroundColor Green
        break
    }
    Write-Host "  Attempt $i/40..."
    Start-Sleep -Seconds 10
}

if (-not $sshReady) {
    Write-Host "ERROR: SSH not ready after 400s." -ForegroundColor Red
    Pop-Location
    exit 1
}

# ---------------------------------------------------------------
# STEP 3: Create uploads directory
# ---------------------------------------------------------------
Write-Host "`n[3/7] Creating upload directory..." -ForegroundColor Yellow

& $Gcloud compute ssh $InstanceName --zone=$Zone --command="mkdir -p $RemoteHome/uploads"

# ---------------------------------------------------------------
# STEP 4: Upload data files and config
# ---------------------------------------------------------------
Write-Host "`n[4/7] Uploading data files..." -ForegroundColor Yellow

# Upload CSVs — use FULL remote path (not ~, pscp can't expand it)
$csvFiles = Get-ChildItem -Path $DataDir -Filter "*.csv" -ErrorAction SilentlyContinue
if ($csvFiles.Count -eq 0) {
    Write-Host "ERROR: No CSV files found in $DataDir" -ForegroundColor Red
    Pop-Location
    exit 1
}

foreach ($csv in $csvFiles) {
    Write-Host "  Uploading $($csv.Name) ($([math]::Round($csv.Length / 1MB, 1)) MB)..."
    & $Gcloud compute scp "$($csv.FullName)" "${InstanceName}:${RemoteHome}/uploads/$($csv.Name)" --zone=$Zone
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  RETRY with --tunnel-through-iap..." -ForegroundColor Yellow
        & $Gcloud compute scp "$($csv.FullName)" "${InstanceName}:${RemoteHome}/uploads/$($csv.Name)" --zone=$Zone --tunnel-through-iap
    }
}

# Upload config
Write-Host "  Uploading config: $ConfigFile..."
& $Gcloud compute scp "$ConfigFile" "${InstanceName}:${RemoteHome}/uploads/config.yaml" --zone=$Zone

Write-Host "  All uploads complete." -ForegroundColor Green

# ---------------------------------------------------------------
# STEP 5: Poll for engine completion
# ---------------------------------------------------------------
Write-Host "`n[5/7] Waiting for engine to complete..." -ForegroundColor Yellow
Write-Host "  Startup script installs deps, clones repo, copies data, runs engine."
Write-Host "  Typical runtime: 4-5 hours for 4-timeframe ES sweep on 96 cores."
Write-Host ""

$pollStart = Get-Date
$engineDone = $false
$lastStatus = ""

while (-not $engineDone) {
    Start-Sleep -Seconds 60

    $elapsed = (Get-Date) - $pollStart
    $elapsedStr = "{0:hh\:mm\:ss}" -f $elapsed

    try {
        $status = & $Gcloud compute ssh $InstanceName --zone=$Zone --command="cat /tmp/engine_status 2>/dev/null || echo PENDING" 2>$null
        $status = ($status | Out-String).Trim()
    } catch {
        $status = "SSH_ERROR"
    }

    if ($status -ne $lastStatus) {
        Write-Host "  [$elapsedStr] Status changed: $status" -ForegroundColor Cyan
        $lastStatus = $status
    }

    # Detailed progress every 5 minutes
    $minElapsed = [math]::Floor($elapsed.TotalMinutes)
    if ($minElapsed -gt 0 -and $minElapsed % 5 -eq 0) {
        try {
            $logTail = & $Gcloud compute ssh $InstanceName --zone=$Zone --command="sudo tail -3 /tmp/engine_run.log 2>/dev/null" 2>$null
            if ($logTail) {
                $lastLine = ($logTail | Out-String).Trim().Split("`n")[-1]
                Write-Host "  [$elapsedStr] $lastLine" -ForegroundColor Gray
            }
        } catch { }
    }

    if ($status -match "COMPLETED") {
        Write-Host "`n  Engine completed!" -ForegroundColor Green
        $engineDone = $true
    }
    elseif ($status -match "FAILED") {
        Write-Host "`n  Engine FAILED. Downloading logs..." -ForegroundColor Red
        $engineDone = $true
    }

    # Check for SPOT preemption
    if (-not $engineDone) {
        try {
            $vmStatus = & $Gcloud compute instances describe $InstanceName --zone=$Zone --format="value(status)" 2>$null
            $vmStatus = ($vmStatus | Out-String).Trim()
            if ($vmStatus -eq "TERMINATED" -or $vmStatus -eq "STOPPED") {
                Write-Host "  [$elapsedStr] SPOT preempted! Restarting VM..." -ForegroundColor Red
                & $Gcloud compute instances start $InstanceName --zone=$Zone
                Start-Sleep -Seconds 60
            }
        } catch { }
    }
}

# ---------------------------------------------------------------
# STEP 6: Download results
# ---------------------------------------------------------------
Write-Host "`n[6/7] Downloading results..." -ForegroundColor Yellow

# First, copy outputs to user-accessible location on VM
& $Gcloud compute ssh $InstanceName --zone=$Zone --command="sudo cp -r /root/python-master-strategy-creator/Outputs $RemoteHome/outputs 2>/dev/null; sudo cp /tmp/engine_run.log $RemoteHome/outputs/ 2>/dev/null; sudo chown -R ${GcpUser}:${GcpUser} $RemoteHome/outputs/ 2>/dev/null"

$localOutputDir = "${OutputDir}_${Timestamp}"
New-Item -ItemType Directory -Path $localOutputDir -Force | Out-Null

& $Gcloud compute scp --recurse "${InstanceName}:${RemoteHome}/outputs" "$localOutputDir/" --zone=$Zone

if ($LASTEXITCODE -eq 0) {
    Write-Host "  Results saved to: $localOutputDir" -ForegroundColor Green

    $leaderboard = Get-ChildItem -Path $localOutputDir -Recurse -Filter "master_leaderboard.csv" | Select-Object -First 1
    if ($leaderboard) {
        Write-Host "`n  === MASTER LEADERBOARD ===" -ForegroundColor Cyan
        Get-Content $leaderboard.FullName | Select-Object -First 12
    }
} else {
    Write-Host "  WARNING: Download may have failed." -ForegroundColor Red
}

# ---------------------------------------------------------------
# STEP 7: DESTROY VM (always, unless -SkipDestroy)
# ---------------------------------------------------------------
if ($SkipDestroy) {
    Write-Host "`n[7/7] SKIPPING destroy (-SkipDestroy)" -ForegroundColor Yellow
    Write-Host "  Destroy manually: gcloud compute instances delete $InstanceName --zone=$Zone --quiet"
} else {
    Write-Host "`n[7/7] Destroying VM to stop billing..." -ForegroundColor Yellow
    & $Gcloud compute instances delete $InstanceName --zone=$Zone --quiet

    if ($LASTEXITCODE -eq 0) {
        Write-Host "  VM DESTROYED. No more charges." -ForegroundColor Green
    } else {
        Write-Host "  WARNING: Destroy may have failed! Run manually:" -ForegroundColor Red
        Write-Host "  gcloud compute instances delete $InstanceName --zone=$Zone --quiet" -ForegroundColor Red
    }
}

# ---------------------------------------------------------------
# Done
# ---------------------------------------------------------------
Pop-Location

$totalElapsed = (Get-Date) - $pollStart
Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host " Run Complete" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Total time:  $("{0:hh\:mm\:ss}" -f $totalElapsed)"
Write-Host "Results in:  $localOutputDir"
if (-not $SkipDestroy) {
    Write-Host "VM status:   DESTROYED" -ForegroundColor Green
}
Write-Host "============================================" -ForegroundColor Cyan
