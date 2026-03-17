# Cloud Launcher Setup — One-Time Steps

## 1. Install dependencies (on your local Windows machine)

Open PowerShell and run:

```
pip install requests paramiko scp
```

## 2. Get a DigitalOcean API token

1. Go to https://cloud.digitalocean.com/account/api/tokens
2. Click "Generate New Token"
3. Name it "strategy-engine" (or anything)
4. Check both Read and Write scopes
5. Copy the token — you'll only see it once

## 3. Make sure your SSH key is on DigitalOcean

1. Go to https://cloud.digitalocean.com/account/security
2. Under "SSH Keys", check your key is listed
3. If not, click "Add SSH Key" and paste your public key
   - Your public key is usually at: `C:\Users\Rob\.ssh\id_rsa.pub` or `id_ed25519.pub`
   - Open it in notepad and copy the contents

## 4. Set the token as an environment variable (optional, avoids typing it every time)

PowerShell (current session only):
```
$env:DO_API_TOKEN = "dop_v1_your_token_here"
```

Or permanently (via System Properties > Environment Variables > User variables):
- Variable name: `DO_API_TOKEN`
- Variable value: `dop_v1_your_token_here`

## 5. Run it

Put `run_cloud_job.py` in your repo root, then from your project directory:

```powershell
cd "C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator"

# Basic run — creates droplet, runs engine, downloads outputs, destroys droplet
python run_cloud_job.py --repo https://github.com/YOUR_USERNAME/python-master-strategy-creator.git --csv "Data\ES_60m_2008_2026_tradestation.csv"

# Watch the log in real-time (Ctrl+C to detach, engine keeps running)
python run_cloud_job.py --repo https://github.com/YOUR_USERNAME/python-master-strategy-creator.git --csv "Data\ES_60m_2008_2026_tradestation.csv" --watch

# Keep the droplet alive after run (for debugging)
python run_cloud_job.py --repo https://github.com/YOUR_USERNAME/python-master-strategy-creator.git --csv "Data\ES_60m_2008_2026_tradestation.csv" --keep
```

## 6. Outputs

Results are downloaded to `cloud_outputs/Outputs/` in your project directory (or wherever you specify with `--output-dir`).

## What happens under the hood

1. Creates a $32/mo droplet in Sydney (Premium Intel, 4 GB, 2 CPUs, 120 GB NVMe)
2. Cloud-init auto-installs Python 3.11, clones your repo, creates venv, installs deps
3. Uploads your CSV data file via SCP
4. Starts the engine with nohup (survives SSH disconnect)
5. Polls until the engine finishes
6. Tars and downloads the Outputs/ folder
7. Destroys the droplet — billing stops immediately

## Cost

Typically ~$0.05–0.15 per run depending on how long the engine takes. The droplet bills at $0.048/hour and gets destroyed when the job finishes.

## Troubleshooting

- **"No SSH keys found"**: Add your key at https://cloud.digitalocean.com/account/security
- **"SSH connection refused"**: The droplet is still booting. The script auto-retries 12 times.
- **"Cloud-init timeout"**: SSH in manually (`ssh root@<IP>`) and check `/var/log/cloud-init-engine.log`
- **Engine seems stuck**: Use `--watch` flag to tail the log, or SSH in and run `htop`
