# Cloud Setup Notes

For the current GCP Windows workflow, use the Python launcher:

```powershell
python cloud/launch_gcp_run.py --config cloud/config_es_all_timeframes_gcp96.yaml
```

See `cloud/GCP_WINDOWS_RUNBOOK.md` for the canonical single-command run flow.

The rest of this file is legacy DigitalOcean setup/reference material.

## One-time setup (do this once)

### 1. Create DigitalOcean account
- Go to https://www.digitalocean.com
- Sign up (they usually offer $200 free credit for new accounts)

### 2. Install doctl (DigitalOcean CLI)
Windows (PowerShell as admin):
```powershell
winget install DigitalOcean.Doctl
```
Or download from: https://docs.digitalocean.com/reference/doctl/how-to/install/

### 3. Authenticate doctl
```bash
doctl auth init
```
Paste your API token when prompted.
Generate a token at: https://cloud.digitalocean.com/account/api/tokens

### 4. Add SSH key
```bash
# Generate key if you don't have one
ssh-keygen -t ed25519 -C "strategy-engine"

# Add to DigitalOcean
doctl compute ssh-key import strategy-engine --public-key-file ~/.ssh/id_ed25519.pub
```

## Droplet size reference

| Size slug | vCPUs | RAM | $/hr | $/mo | Est. pipeline time (3 families) |
|-----------|-------|-----|------|------|-------------------------------|
| s-2vcpu-4gb | 2 | 4GB | $0.030 | $18 | ~15 hours |
| c-4 | 4 dedicated | 8GB | $0.048 | $32 | ~8 hours |
| **c-8** | **8 dedicated** | **16GB** | **$0.095** | **$63** | **~3 hours** |
| c-16 | 16 dedicated | 32GB | $0.190 | $126 | ~1.5 hours |

Recommended: **c-8** for most runs. Cost per full ES run: ~$0.30-0.50

Region: **syd1** (Sydney — closest to Melbourne)

## Running the pipeline

### Quick test (single family, ~30 min, ~$0.05)
```powershell
.\cloud\run_cloud.ps1 -ConfigFile cloud\config_quick_test.yaml
```

### Full ES run (all families, ~3 hours, ~$0.30)
```powershell
.\cloud\run_cloud.ps1 -ConfigFile cloud\config_full_es.yaml
```

### Check on a running droplet
```bash
doctl compute droplet list
ssh root@<DROPLET_IP> "docker logs -f $(docker ps -q)"
```

### Emergency: destroy all droplets
```bash
doctl compute droplet list --format ID --no-header | xargs -I {} doctl compute droplet delete {} --force
```

## Cost management
- Droplets are billed per hour while running
- The run script automatically destroys the droplet when done
- Set a billing alert at https://cloud.digitalocean.com/account/billing
- Typical full run cost: $0.30-0.50 per ES dataset
