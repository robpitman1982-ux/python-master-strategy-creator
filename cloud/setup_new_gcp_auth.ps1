# setup_new_gcp_auth.ps1 — Configure gcloud CLI for new GCP account (Nikola Pitman)
# Run once on any machine that needs to interact with the new GCP project.

Write-Host "=== Setting up gcloud configuration for new GCP account ===" -ForegroundColor Cyan

# Step 1: Create a new gcloud configuration called "nikola"
Write-Host "`n[1/5] Creating gcloud configuration 'nikola'..." -ForegroundColor Yellow
gcloud config configurations create nikola 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Configuration 'nikola' may already exist — activating it." -ForegroundColor Gray
}
gcloud config configurations activate nikola

# Step 2: Set project
Write-Host "`n[2/5] Setting project to project-c6c16a27-e123-459c-b7a..." -ForegroundColor Yellow
gcloud config set project project-c6c16a27-e123-459c-b7a

# Step 3: Set default zone and region
Write-Host "`n[3/5] Setting default zone (us-central1-c) and region (us-central1)..." -ForegroundColor Yellow
gcloud config set compute/zone us-central1-c
gcloud config set compute/region us-central1

# Step 4: Authenticate
Write-Host "`n[4/5] Opening browser for authentication..." -ForegroundColor Yellow
Write-Host "  Log in with the Nikola Pitman Google account." -ForegroundColor Gray
gcloud auth login

# Step 5: Verify
Write-Host "`n[5/5] Verifying configuration..." -ForegroundColor Yellow
gcloud config configurations list

Write-Host "`n=== Setup complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "To switch between accounts:" -ForegroundColor Cyan
Write-Host "  gcloud config configurations activate nikola    # New account (Nikola)" -ForegroundColor White
Write-Host "  gcloud config configurations activate default   # Old account (Rob)" -ForegroundColor White
Write-Host ""
Write-Host "To verify current configuration:" -ForegroundColor Cyan
Write-Host "  gcloud config configurations list" -ForegroundColor White
Write-Host "  gcloud config get-value project" -ForegroundColor White
