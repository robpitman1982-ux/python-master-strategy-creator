<#
.SYNOPSIS
    Fully automated GCP cloud run for the Strategy Discovery Engine.
    Creates VM -> uploads data -> waits for engine -> downloads results -> destroys VM.

.DESCRIPTION
    One command to run a full strategy sweep on GCP. Uses SPOT pricing for cost savings.
    The VM self-destructs logic is handled by this script polling for completion then
    deleting the instance. If the script is interrupted, run:
        gcloud compute instances delete strategy-sweep --zone=australia-southeast2-a --quiet

.PARAMETER ConfigFile
    Path to the YAML config file. Default: cloud/config_es_all_timeframes_gcp96.yaml

.PARAMETER MachineType
    GCP machine type. Default: n2-highcpu-96

.PARAMETER Zone
    GCP zone. Default: australia-southeast2-a (Melbourne)

.PARAMETER DataDir
    Local directory containing CSV data files. Default: Data

.PARAMETER OutputDir
    Local directory to save results. Default: cloud_outputs

.PARAMETER InstanceName
    VM instance name. Default: strategy-sweep

.PARAMETER SkipDestroy
    If set, don't destroy the VM after downloading results (for debugging).

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

$ErrorActionPreference = "Continue"

# Use native OpenSSH instead of PuTTY (fixes freezing issues)
$env:CLOUDSDK_SSH_NATIVE = "1"

# Use gcloud.cmd explicitly — avoids gcloud.ps1 routing Python stderr through
# PowerShell's error pipeline, which turns benign WARNINGs into terminating errors.
$GcloudBinDir = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin"
$Gcloud = "$GcloudBinDir\gcloud.cmd"
if (-not (Test-Path $Gcloud)) {
    # Fallback: try system PATH
    $Gcloud = "gcloud"
}

$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$StartupScript = Join-Path $ProjectDir "cloud/gcp_startup.sh"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmm"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " GCP Strategy Engine -- Automated Run" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Instance:  $InstanceName"
Write-Host "Machine:   $MachineType"
Write-Host "Zone:      $Zone"
Write-Host "Config:    $ConfigFile"
Write-Host "Data dir:  $DataDir"
Write-Host "Output:    $OutputDir"
Write-Host "Timestamp: $Timestamp"
Write-Host "============================================" -ForegroundColor Cyan

# ---------------------------------------------------------------
# STEP 1: Create VM with startup script
# ---------------------------------------------------------------
Write-Host "`n[1/7] Creating VM with startup script..." -ForegroundColor Yellow

# Check if instance already exists
$existing = & $Gcloud compute instances list --filter="name=$InstanceName" --format="value(name)" 2>$null
if ($existing) {
    Write-Host "  WARNING: Instance '$InstanceName' already exists!" -ForegroundColor Red
    $confirm = Read-Host "  Delete it and create fresh? (y/n)"
    if ($confirm -ne "y") {
        Write-Host "  Aborted." -ForegroundColor Red
        exit 1
    }
    & $Gcloud compute instances delete $InstanceName --zone=$Zone --quiet
    Start-Sleep -Seconds 10
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

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to create instance." -ForegroundColor Red
    exit 1
}

Write-Host "  VM created successfully." -ForegroundColor Green

# ---------------------------------------------------------------
# STEP 2: Wait for SSH to be ready
# ---------------------------------------------------------------
Write-Host "`n[2/7] Waiting for SSH..." -ForegroundColor Yellow

$sshReady = $false
for ($i = 1; $i -le 30; $i++) {
    try {
        $result = & $Gcloud compute ssh $InstanceName --zone=$Zone --command="echo ready" 2>$null
        if ($result -match "ready") {
            $sshReady = $true
            Write-Host "  SSH ready after attempt $i" -ForegroundColor Green
            break
        }
    } catch { }
    Write-Host "  Attempt $i/30..."
    Start-Sleep -Seconds 10
}

if (-not $sshReady) {
    Write-Host "ERROR: SSH not ready after 5 minutes. Check the VM." -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------
# STEP 3: Create uploads directory on VM
# ---------------------------------------------------------------
Write-Host "`n[3/7] Preparing upload directory..." -ForegroundColor Yellow

& $Gcloud compute ssh $InstanceName --zone=$Zone --command="mkdir -p ~/uploads"

# ---------------------------------------------------------------
# STEP 4: Upload data files and config
# ---------------------------------------------------------------
Write-Host "`n[4/7] Uploading data files and config..." -ForegroundColor Yellow

# Upload all CSV files from the Data directory that match config datasets
$csvFiles = Get-ChildItem -Path $DataDir -Filter "*.csv" -ErrorAction SilentlyContinue
if ($csvFiles.Count -eq 0) {
    Write-Host "ERROR: No CSV files found in $DataDir" -ForegroundColor Red
    exit 1
}

foreach ($csv in $csvFiles) {
    Write-Host "  Uploading $($csv.Name) ($([math]::Round($csv.Length / 1MB, 1)) MB)..."
    & $Gcloud compute scp "$($csv.FullName)" "${InstanceName}:~/uploads/$($csv.Name)" --zone=$Zone
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  WARNING: Failed to upload $($csv.Name)" -ForegroundColor Red
    }
}

# Upload config file
Write-Host "  Uploading config: $ConfigFile..."
& $Gcloud compute scp "$ConfigFile" "${InstanceName}:~/uploads/config.yaml" --zone=$Zone

Write-Host "  All files uploaded." -ForegroundColor Green

# ---------------------------------------------------------------
# STEP 5: Poll for engine completion
# ---------------------------------------------------------------
Write-Host "`n[5/7] Waiting for engine to complete..." -ForegroundColor Yellow
Write-Host "  (startup script installs deps, clones repo, then runs engine)"
Write-Host "  This typically takes 4-5 hours for a 4-timeframe ES sweep on 96 cores."
Write-Host "  Press Ctrl+C to stop polling (VM keeps running, re-run to resume)."
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
        $status = $status.Trim()
    } catch {
        $status = "SSH_ERROR"
    }

    if ($status -ne $lastStatus) {
        Write-Host "  [$elapsedStr] Status: $status" -ForegroundColor Cyan
        $lastStatus = $status
    } else {
        # Show heartbeat every 5 minutes
        if ($elapsed.TotalMinutes % 5 -lt 1.1) {
            # Also try to read status.json for detailed progress
            try {
                $statusJson = & $Gcloud compute ssh $InstanceName --zone=$Zone --command="cat /root/python-master-strategy-creator/Outputs/*/status.json 2>/dev/null | tail -1" 2>$null
                if ($statusJson) {
                    $parsed = $statusJson | ConvertFrom-Json -ErrorAction SilentlyContinue
                    if ($parsed) {
                        $dataset = $parsed.dataset
                        $family = $parsed.current_family
                        $stage = $parsed.current_stage
                        $pct = $parsed.progress_pct
                        Write-Host "  [$elapsedStr] $dataset / $family / $stage -- ${pct}% complete" -ForegroundColor Gray
                    }
                }
            } catch {
                Write-Host "  [$elapsedStr] Still running..." -ForegroundColor Gray
            }
        }
    }

    if ($status -match "COMPLETED") {
        Write-Host "`n  Engine completed successfully!" -ForegroundColor Green
        $engineDone = $true
    }
    elseif ($status -match "FAILED") {
        Write-Host "`n  Engine FAILED! Downloading logs..." -ForegroundColor Red
        $engineDone = $true
    }

    # Safety: check if VM still exists (SPOT can be preempted)
    try {
        $vmStatus = & $Gcloud compute instances describe $InstanceName --zone=$Zone --format="value(status)" 2>$null
        if ($vmStatus -ne "RUNNING") {
            Write-Host "`n  WARNING: VM status is '$vmStatus' (may have been preempted)" -ForegroundColor Red
            if ($vmStatus -eq "TERMINATED" -or $vmStatus -eq "STOPPED") {
                Write-Host "  SPOT instance was preempted. Restarting..." -ForegroundColor Yellow
                & $Gcloud compute instances start $InstanceName --zone=$Zone
                Start-Sleep -Seconds 60
            }
        }
    } catch { }
}

# ---------------------------------------------------------------
# STEP 6: Download results
# ---------------------------------------------------------------
Write-Host "`n[6/7] Downloading results..." -ForegroundColor Yellow

$localOutputDir = "${OutputDir}_${Timestamp}"
New-Item -ItemType Directory -Path $localOutputDir -Force | Out-Null

& $Gcloud compute scp --recurse "${InstanceName}:~/outputs/*" "$localOutputDir/" --zone=$Zone

if ($LASTEXITCODE -eq 0) {
    Write-Host "  Results saved to: $localOutputDir" -ForegroundColor Green

    # Show quick summary if master_leaderboard.csv exists
    $leaderboard = Join-Path $localOutputDir "master_leaderboard.csv"
    if (Test-Path $leaderboard) {
        Write-Host "`n  === MASTER LEADERBOARD ===" -ForegroundColor Cyan
        Get-Content $leaderboard | Select-Object -First 15
    }
} else {
    Write-Host "  WARNING: Some files may not have downloaded." -ForegroundColor Red
}

# Also download the engine log
try {
    & $Gcloud compute scp "${InstanceName}:~/outputs/engine_run.log" "$localOutputDir/" --zone=$Zone 2>$null
} catch { }

# ---------------------------------------------------------------
# STEP 7: Destroy VM
# ---------------------------------------------------------------
if ($SkipDestroy) {
    Write-Host "`n[7/7] SKIPPING VM destruction (-SkipDestroy flag set)" -ForegroundColor Yellow
    Write-Host "  Remember to manually destroy: gcloud compute instances delete $InstanceName --zone=$Zone --quiet"
} else {
    Write-Host "`n[7/7] Destroying VM..." -ForegroundColor Yellow
    & $Gcloud compute instances delete $InstanceName --zone=$Zone --quiet

    if ($LASTEXITCODE -eq 0) {
        Write-Host "  VM destroyed. No more billing." -ForegroundColor Green
    } else {
        Write-Host "  WARNING: Failed to destroy VM! Run manually:" -ForegroundColor Red
        Write-Host "  gcloud compute instances delete $InstanceName --zone=$Zone --quiet" -ForegroundColor Red
    }
}

# ---------------------------------------------------------------
# Summary
# ---------------------------------------------------------------
$totalElapsed = (Get-Date) - $pollStart
Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host " Run Complete" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Total time:  $("{0:hh\:mm\:ss}" -f $totalElapsed)"
Write-Host "Results in:  $localOutputDir"
if (-not $SkipDestroy) {
    Write-Host "VM status:   DESTROYED (no ongoing charges)" -ForegroundColor Green
}
Write-Host "============================================" -ForegroundColor Cyan
