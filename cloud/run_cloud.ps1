# =============================================================
# Cloud Pipeline Runner for DigitalOcean (Windows PowerShell)
# Usage: .\cloud\run_cloud.ps1 [-ConfigFile config.yaml]
# =============================================================
param(
    [string]$ConfigFile = "config.yaml"
)

$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DropletName = "strategy-engine-$(Get-Date -Format 'yyyyMMdd-HHmm')"
$DropletSize = "c-8"
$DropletRegion = "syd1"
$DropletImage = "docker-24-04"

Write-Host "============================================"
Write-Host " Strategy Engine Cloud Runner"
Write-Host "============================================"
Write-Host "Droplet:  $DropletName"
Write-Host "Size:     $DropletSize"
Write-Host "Region:   $DropletRegion"
Write-Host "Config:   $ConfigFile"
Write-Host "============================================"

# Step 1: Create Droplet
Write-Host "`n[1/7] Creating droplet..."
$SshKeyId = (doctl compute ssh-key list --format ID --no-header | Select-Object -First 1).Trim()
$DropletId = (doctl compute droplet create $DropletName `
    --size $DropletSize `
    --image $DropletImage `
    --region $DropletRegion `
    --ssh-keys $SshKeyId `
    --wait `
    --format ID `
    --no-header).Trim()

Write-Host "Droplet created: ID=$DropletId"
$DropletIp = (doctl compute droplet get $DropletId --format PublicIPv4 --no-header).Trim()
Write-Host "IP: $DropletIp"

# Step 2: Wait for SSH
Write-Host "`n[2/7] Waiting for SSH..."
for ($i = 1; $i -le 30; $i++) {
    $result = ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@$DropletIp "echo ready" 2>$null
    if ($result -eq "ready") { break }
    Write-Host "  Attempt $i/30..."
    Start-Sleep -Seconds 10
}

# Step 3: Upload project
Write-Host "`n[3/7] Uploading project files..."
ssh root@$DropletIp "mkdir -p /app/Data /app/Outputs"
scp -r "$ProjectDir\modules" root@${DropletIp}:/app/
scp "$ProjectDir\master_strategy_engine.py" root@${DropletIp}:/app/
scp "$ProjectDir\config.yaml" root@${DropletIp}:/app/
scp "$ProjectDir\requirements.txt" root@${DropletIp}:/app/
scp "$ProjectDir\Dockerfile" root@${DropletIp}:/app/
scp "$ProjectDir\run_evaluator.py" root@${DropletIp}:/app/

# Step 4: Upload data
Write-Host "`n[4/7] Uploading data files..."
scp -r "$ProjectDir\Data\*" root@${DropletIp}:/app/Data/

# Step 5: Build and run
Write-Host "`n[5/7] Building Docker image..."
ssh root@$DropletIp "cd /app && docker build -t strategy-engine ."

Write-Host "`n[6/7] Running pipeline..."
$StartTime = Get-Date
ssh root@$DropletIp "docker run --rm -v /app/Data:/app/Data:ro -v /app/Outputs:/app/Outputs -v /app/config.yaml:/app/config.yaml:ro strategy-engine python master_strategy_engine.py --config config.yaml"
$Elapsed = (Get-Date) - $StartTime
Write-Host "Pipeline completed in $([math]::Round($Elapsed.TotalMinutes, 1)) minutes"

# Step 6: Download results
Write-Host "`n[7/7] Downloading results..."
$ResultsDir = "$ProjectDir\cloud_results\$DropletName"
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null
scp -r root@${DropletIp}:/app/Outputs/* $ResultsDir/
Write-Host "Results saved to: $ResultsDir"

# Step 7: Destroy droplet
Write-Host "`nDestroying droplet..."
doctl compute droplet delete $DropletId --force
Write-Host "Droplet destroyed."

# Summary
$EstCost = [math]::Round($Elapsed.TotalHours * 0.095, 2)
Write-Host "`n============================================"
Write-Host " CLOUD RUN COMPLETE"
Write-Host "============================================"
Write-Host "Results:    $ResultsDir"
Write-Host "Runtime:    $([math]::Round($Elapsed.TotalMinutes, 1)) minutes"
Write-Host "Est. cost:  ~`$$EstCost (at `$0.095/hr)"
Write-Host "============================================"
