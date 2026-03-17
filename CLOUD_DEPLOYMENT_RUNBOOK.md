# Cloud Deployment Runbook — Strategy Discovery Engine

> DigitalOcean Basic Droplet · Premium Intel · $32/mo
> 4 GB RAM · 2 Intel CPUs · 120 GB NVMe SSD · Sydney (SYD1) region

---

## Step 1: Create the Droplet

1. Go to [cloud.digitalocean.com](https://cloud.digitalocean.com) → Create → Droplets
2. **Region**: Sydney (SYD1)
3. **Image**: Ubuntu 24.04 LTS
4. **Plan**: Basic → Premium Intel → $32/mo (4 GB / 2 CPUs / 120 GB NVMe / 4 TB transfer)
5. **Authentication**: SSH key (recommended) or password
6. **Hostname**: `strategy-engine` (or whatever you like)
7. Click **Create Droplet** — note the IP address when ready

---

## Step 2: SSH In and Install Dependencies

```bash
# From your local machine
ssh root@<DROPLET_IP>

# Update system
apt update && apt upgrade -y

# Install Python 3.11+ and git
apt install -y python3.11 python3.11-venv python3.11-dev git

# Install Claude Code (Node.js required)
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt install -y nodejs
npm install -g @anthropic-ai/claude-code
```

---

## Step 3: Clone the Repo

```bash
cd /root
git clone https://github.com/<YOUR_USERNAME>/python-master-strategy-creator.git
cd python-master-strategy-creator
```

---

## Step 4: Upload Your Data File

From your **local Windows machine** (PowerShell or terminal):

```bash
scp "C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator\Data\ES_60m_2008_2026_tradestation.csv" root@<DROPLET_IP>:/root/python-master-strategy-creator/Data/
```

Or from the droplet, if you have the file hosted somewhere:
```bash
mkdir -p Data
# wget/curl your CSV into Data/
```

---

## Step 5: Run Server Setup

```bash
cd /root/python-master-strategy-creator
bash setup_server.sh
```

This will:
- Verify Python 3.11+ is available
- Create a `venv/` virtual environment
- Install pinned dependencies (numpy, pandas, pyyaml)
- Create `Data/` and `Outputs/logs/` directories

---

## Step 6: Configure for 2-Core Droplet

Edit `config.yaml` to match the droplet's 2 CPUs:

```bash
nano config.yaml
```

Change the pipeline section to:

```yaml
pipeline:
  max_workers_sweep: 2        # match CPU cores
  max_workers_refinement: 2   # match CPU cores
  max_candidates_to_refine: 3
  oos_split_date: "2019-01-01"
```

Save and exit (`Ctrl+X`, `Y`, `Enter`).

---

## Step 7: Quick Test Run (Optional but Recommended)

Verify everything works before going overnight:

```bash
source venv/bin/activate
python master_strategy_engine.py
```

Watch for `[OK] Loaded config from config.yaml` and the first sweep starting. `Ctrl+C` to stop once you're satisfied it's running.

---

## Step 8: Run Overnight with Claude Code

This is the main event — Claude Code runs autonomously, fixing issues and iterating as needed.

```bash
cd /root/python-master-strategy-creator

# Start a tmux session so it survives SSH disconnect
tmux new -s engine

# Run Claude Code in auto-accept mode
claude --dangerously-skip-permissions
```

Then give Claude Code your prompt (e.g., "Run the full pipeline, review the outputs, then expand to additional timeframes...").

**To disconnect safely:**
- Press `Ctrl+B`, then `D` (detaches tmux)
- Close your SSH session
- The engine keeps running

**To reconnect later:**
```bash
ssh root@<DROPLET_IP>
tmux attach -t engine
```

---

## Alternative: Run Without Claude Code (Just the Engine)

If you just want a straight pipeline run without Claude Code iterating:

```bash
cd /root/python-master-strategy-creator
bash run_engine.sh
```

This runs under `nohup` — you can disconnect SSH and it keeps going.

```bash
# Check progress
tail -f Outputs/logs/run_*.log

# Check if still running
cat engine.pid | xargs ps -p

# Stop it
kill $(cat engine.pid)
```

---

## Monitoring & Troubleshooting

### Check disk space
```bash
df -h /
```
120 GB NVMe is plenty, but keep an eye on it if running many datasets.

### Check memory usage
```bash
free -h
htop
```
4 GB should handle ES 60m (107K bars). If you see heavy swap usage when expanding to multiple instruments, upgrade to the $48/mo tier (8 GB).

### Check outputs
```bash
ls -la Outputs/ES_60m/
cat Outputs/ES_60m/family_leaderboard_results.csv
```

### View logs
```bash
# Most recent log
ls -t Outputs/logs/ | head -1 | xargs -I {} cat Outputs/logs/{}
```

---

## Cost Management

- **$32/mo** while the droplet is running
- **Snapshots**: Power off the droplet when not in use → create a snapshot → destroy the droplet → restore from snapshot when needed. Snapshots cost $0.06/GB/mo (much cheaper than keeping the droplet running 24/7)
- **Resize up**: If you need more power for multi-instrument sweeps, resize to $48/mo (8 GB / 2 CPUs) or $96/mo (8 GB / 4 CPUs dedicated) temporarily

---

## Expansion: Adding More Datasets

When you're ready to sweep more instruments/timeframes, upload the CSVs and update `config.yaml`:

```yaml
datasets:
  - path: "Data/ES_60m_2008_2026_tradestation.csv"
    market: "ES"
    timeframe: "60m"
  - path: "Data/ES_5m_2008_2026_tradestation.csv"
    market: "ES"
    timeframe: "5m"
  - path: "Data/CL_60m_2008_2026_tradestation.csv"
    market: "CL"
    timeframe: "60m"
```

Each dataset gets its own output subdirectory (`Outputs/ES_60m/`, `Outputs/ES_5m/`, `Outputs/CL_60m/`).

---

## Quick Reference

| Task | Command |
|------|---------|
| SSH in | `ssh root@<DROPLET_IP>` |
| Reattach to session | `tmux attach -t engine` |
| Detach tmux | `Ctrl+B` then `D` |
| Follow log | `tail -f Outputs/logs/run_*.log` |
| Check memory | `free -h` |
| Check disk | `df -h /` |
| Stop engine | `kill $(cat engine.pid)` |
| Pull latest code | `git pull origin main` |
| Upload data | `scp file.csv root@<IP>:~/python-master-strategy-creator/Data/` |
