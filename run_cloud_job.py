"""
run_cloud_job.py — Automated DigitalOcean cloud runner for Strategy Discovery Engine

Usage:
    python run_cloud_job.py --repo https://github.com/YOU/python-master-strategy-creator.git --csv Data/ES_60m.csv

Requirements (local machine):
    pip install requests paramiko scp

Set DO_API_TOKEN env var or pass --token.
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests")
    sys.exit(1)

try:
    import paramiko
    from scp import SCPClient
except ImportError:
    print("ERROR: 'paramiko' and 'scp' not installed. Run: pip install paramiko scp")
    sys.exit(1)


# =============================================================================
# DEFAULTS
# =============================================================================

DO_API_BASE = "https://api.digitalocean.com/v2"
DEFAULT_DROPLET_NAME = "strategy-engine-run"
DEFAULT_REGION = "syd1"
DEFAULT_SIZE = "s-2vcpu-4gb-intel"
DEFAULT_IMAGE = "ubuntu-24-04-x64"
SSH_USER = "root"
SSH_PORT = 22

CLOUD_INIT_TIMEOUT_SECONDS = 900   # 15 minutes — pip install numpy can be slow
POLL_INTERVAL_SECONDS = 15
ENGINE_POLL_INTERVAL_SECONDS = 30

REMOTE_PROJECT_DIR = "/root/python-master-strategy-creator"
REMOTE_LOG_PATTERN = f"{REMOTE_PROJECT_DIR}/Outputs/logs/run_*.log"
DONE_MARKER = f"{REMOTE_PROJECT_DIR}/.engine_done"


# =============================================================================
# CLOUD-INIT SCRIPT
# =============================================================================

def build_cloud_init(repo_url: str, branch: str = "main") -> str:
    return f"""#!/bin/bash
set -euo pipefail
exec > /var/log/cloud-init-engine.log 2>&1

echo "=== [1/7] System update ==="
apt-get update -qq
apt-get install -y python3 python3-venv python3-dev python3-pip git

echo "=== [2/7] Check Python version ==="
PYTHON=$(command -v python3)
$PYTHON --version

echo "=== [3/7] Clone repo ==="
cd /root
git clone --branch {branch} {repo_url} python-master-strategy-creator
cd python-master-strategy-creator

echo "=== [4/7] Create venv ==="
$PYTHON -m venv venv
./venv/bin/pip install --upgrade pip --quiet

echo "=== [5/7] Install dependencies ==="
./venv/bin/pip install -r requirements.txt
echo "Installed packages:"
./venv/bin/pip list --format=columns | grep -iE "numpy|pandas|pyyaml"

echo "=== [6/7] Create directories and configure ==="
mkdir -p Data Outputs/logs
if [ -f config.yaml ]; then
    sed -i 's/max_workers_sweep:.*/max_workers_sweep: 2/' config.yaml
    sed -i 's/max_workers_refinement:.*/max_workers_refinement: 2/' config.yaml
fi

echo "=== [7/7] Cloud-init complete ==="
touch /root/.cloud_init_done
echo "Ready for CSV upload and engine start at $(date)"
"""


# =============================================================================
# DIGITALOCEAN API
# =============================================================================

class DigitalOceanAPI:
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str) -> dict:
        r = requests.get(f"{DO_API_BASE}{path}", headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, data: dict) -> dict:
        r = requests.post(f"{DO_API_BASE}{path}", headers=self.headers, json=data, timeout=30)
        r.raise_for_status()
        return r.json()

    def _delete(self, path: str) -> None:
        r = requests.delete(f"{DO_API_BASE}{path}", headers=self.headers, timeout=30)
        r.raise_for_status()

    def get_ssh_keys(self) -> list[dict]:
        return self._get("/account/keys").get("ssh_keys", [])

    def create_droplet(
        self,
        cloud_init: str,
        ssh_key_ids: list[int],
        size: str = DEFAULT_SIZE,
        region: str = DEFAULT_REGION,
    ) -> dict:
        payload = {
            "name": DEFAULT_DROPLET_NAME,
            "region": region,
            "size": size,
            "image": DEFAULT_IMAGE,
            "ssh_keys": ssh_key_ids,
            "user_data": cloud_init,
            "monitoring": True,
            "tags": ["strategy-engine"],
        }
        result = self._post("/droplets", payload)
        return result["droplet"]

    def get_droplet(self, droplet_id: int) -> dict:
        return self._get(f"/droplets/{droplet_id}")["droplet"]

    def destroy_droplet(self, droplet_id: int) -> None:
        self._delete(f"/droplets/{droplet_id}")

    def wait_for_active(self, droplet_id: int, timeout: int = 300) -> str:
        print("Waiting for droplet to become active", end="", flush=True)
        start = time.time()
        while time.time() - start < timeout:
            droplet = self.get_droplet(droplet_id)
            if droplet["status"] == "active":
                for net in droplet["networks"]["v4"]:
                    if net["type"] == "public":
                        ip = net["ip_address"]
                        print(f"\nDroplet active at {ip}")
                        return ip
            print(".", end="", flush=True)
            time.sleep(10)
        raise TimeoutError(f"Droplet did not become active within {timeout}s")


# =============================================================================
# SSH HELPERS
# =============================================================================

def get_ssh_key_path() -> Path:
    env_path = os.environ.get("DO_SSH_KEY_PATH")
    if env_path:
        return Path(env_path)

    if platform.system() == "Windows":
        home = Path(os.environ.get("USERPROFILE", ""))
    else:
        home = Path.home()

    for name in ["id_ed25519", "id_rsa"]:
        p = home / ".ssh" / name
        if p.exists():
            return p

    raise FileNotFoundError(
        "No SSH private key found. Set DO_SSH_KEY_PATH or place a key in ~/.ssh/"
    )


def create_ssh_client(ip: str, key_path: Path, retries: int = 20, delay: int = 15) -> paramiko.SSHClient:
    """Connect with generous retries — cloud-init takes a while."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    key = None
    for key_class in [paramiko.Ed25519Key, paramiko.RSAKey]:
        try:
            key = key_class.from_private_key_file(str(key_path))
            break
        except Exception:
            continue
    if key is None:
        raise ValueError(f"Could not load SSH key from {key_path}")

    for attempt in range(1, retries + 1):
        try:
            client.connect(ip, port=SSH_PORT, username=SSH_USER, pkey=key, timeout=20)
            print(f"  SSH connected on attempt {attempt}")
            return client
        except Exception as e:
            if attempt == retries:
                raise ConnectionError(f"Could not SSH to {ip} after {retries} attempts: {e}")
            if attempt <= 3 or attempt % 5 == 0:
                print(f"  SSH attempt {attempt}/{retries} — {e}, retrying in {delay}s...")
            else:
                print(".", end="", flush=True)
            time.sleep(delay)
    return client


def ssh_exec(client: paramiko.SSHClient, cmd: str, check: bool = True, timeout: int = 60) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    if check and exit_code != 0:
        raise RuntimeError(f"Command failed (exit {exit_code}): {cmd}\n{err}")
    return out


def wait_for_cloud_init(client: paramiko.SSHClient, timeout: int = CLOUD_INIT_TIMEOUT_SECONDS):
    print("Waiting for cloud-init to finish", end="", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        result = ssh_exec(client, "test -f /root/.cloud_init_done && echo DONE || echo WAITING", check=False)
        if "DONE" in result:
            elapsed = time.time() - start
            print(f"\nCloud-init complete ({elapsed:.0f}s)")
            # Print the cloud-init log summary
            log = ssh_exec(client, "tail -5 /var/log/cloud-init-engine.log", check=False)
            if log:
                print(f"  Last lines: {log}")
            return
        print(".", end="", flush=True)
        time.sleep(POLL_INTERVAL_SECONDS)

    # Timeout — print the log to help debug
    print(f"\nCloud-init did not finish within {timeout}s!")
    print("Fetching cloud-init log for debugging...")
    log = ssh_exec(client, "cat /var/log/cloud-init-engine.log 2>/dev/null || echo 'No log file found'", check=False)
    print(log)
    raise TimeoutError(f"Cloud-init did not finish within {timeout}s")


def upload_csv(client: paramiko.SSHClient, local_csv: Path):
    remote_path = f"{REMOTE_PROJECT_DIR}/Data/{local_csv.name}"
    size_mb = local_csv.stat().st_size / 1_000_000
    print(f"Uploading {local_csv.name} ({size_mb:.1f} MB)...")
    with SCPClient(client.get_transport()) as scp:
        scp.put(str(local_csv), remote_path)
    print(f"Uploaded to {remote_path}")


def start_engine(client: paramiko.SSHClient) -> str:
    cmd = (
        f"cd {REMOTE_PROJECT_DIR} && "
        f"nohup ./venv/bin/python master_strategy_engine.py "
        f"> Outputs/logs/run_$(date +%Y%m%d_%H%M%S).log 2>&1 & "
        f"echo $!"
    )
    pid = ssh_exec(client, cmd)
    print(f"Engine started (PID {pid})")
    ssh_exec(
        client,
        f"nohup bash -c 'while kill -0 {pid} 2>/dev/null; do sleep 10; done; touch {DONE_MARKER}' &",
        check=False,
    )
    return pid


def tail_log(client: paramiko.SSHClient):
    log_file = ssh_exec(client, f"ls -t {REMOTE_LOG_PATTERN} 2>/dev/null | head -1", check=False)
    if not log_file:
        print("No log file found yet, waiting 15s...")
        time.sleep(15)
        log_file = ssh_exec(client, f"ls -t {REMOTE_LOG_PATTERN} 2>/dev/null | head -1", check=False)
    if not log_file:
        print("WARNING: Still no log file. Engine may not have started.")
        return

    print(f"\n{'=' * 60}")
    print(f"Tailing: {log_file}")
    print(f"Press Ctrl+C to stop watching (engine keeps running)")
    print(f"{'=' * 60}\n")

    transport = client.get_transport()
    channel = transport.open_session()
    channel.exec_command(f"tail -f {log_file}")
    try:
        while True:
            if channel.recv_ready():
                data = channel.recv(4096).decode("utf-8", errors="replace")
                print(data, end="", flush=True)
            if channel.exit_status_ready():
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n\n[Detached from log — engine is still running on the droplet]")
    finally:
        channel.close()


def wait_for_engine(client: paramiko.SSHClient, timeout: int = 14400):
    print("\nWaiting for engine to complete", end="", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        result = ssh_exec(client, f"test -f {DONE_MARKER} && echo DONE || echo RUNNING", check=False)
        if "DONE" in result:
            elapsed = time.time() - start
            print(f"\nEngine finished in {elapsed / 60:.1f} minutes.")
            return
        print(".", end="", flush=True)
        time.sleep(ENGINE_POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"Engine did not finish within {timeout}s")


def download_outputs(client: paramiko.SSHClient, local_dest: Path):
    local_dest.mkdir(parents=True, exist_ok=True)
    tar_name = "outputs_bundle.tar.gz"
    remote_tar = f"/root/{tar_name}"
    print("Compressing outputs on droplet...")
    ssh_exec(client, f"cd {REMOTE_PROJECT_DIR} && tar czf {remote_tar} Outputs/", timeout=120)

    local_tar = local_dest / tar_name
    print(f"Downloading {tar_name}...")
    with SCPClient(client.get_transport()) as scp:
        scp.get(remote_tar, str(local_tar))

    import tarfile
    with tarfile.open(local_tar, "r:gz") as tf:
        tf.extractall(path=str(local_dest))

    local_tar.unlink()
    print(f"Outputs saved to {local_dest / 'Outputs'}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Automated DigitalOcean cloud runner")
    parser.add_argument("--token", default=os.environ.get("DO_API_TOKEN"),
                        help="DigitalOcean API token (or set DO_API_TOKEN)")
    parser.add_argument("--repo", required=True, help="GitHub repo URL")
    parser.add_argument("--branch", default="main", help="Git branch (default: main)")
    parser.add_argument("--csv", required=True, help="Local CSV data file path")
    parser.add_argument("--output-dir", default="cloud_outputs", help="Local output dir")
    parser.add_argument("--watch", action="store_true", help="Tail engine log")
    parser.add_argument("--keep", action="store_true", help="Don't destroy droplet when done")
    parser.add_argument("--size", default=DEFAULT_SIZE, help=f"Droplet size (default: {DEFAULT_SIZE})")
    parser.add_argument("--region", default=DEFAULT_REGION, help=f"Region (default: {DEFAULT_REGION})")

    args = parser.parse_args()

    if not args.token:
        print("ERROR: No API token. Pass --token or set DO_API_TOKEN.")
        sys.exit(1)

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"ERROR: CSV not found: {csv_path}")
        sys.exit(1)

    output_dir = Path(args.output_dir)
    key_path = get_ssh_key_path()
    print(f"Using SSH key: {key_path}")

    api = DigitalOceanAPI(args.token)
    droplet_id = None
    destroy_needed = True

    try:
        # --- Step 1 ---
        print("\n[1/7] Fetching SSH keys...")
        ssh_keys = api.get_ssh_keys()
        if not ssh_keys:
            print("ERROR: No SSH keys on your DO account. Add one at:")
            print("  https://cloud.digitalocean.com/account/security")
            sys.exit(1)
        ssh_key_ids = [k["id"] for k in ssh_keys]
        print(f"  Found {len(ssh_keys)} key(s): {', '.join(k['name'] for k in ssh_keys)}")

        # --- Step 2 ---
        print(f"\n[2/7] Creating droplet ({args.size} in {args.region})...")
        cloud_init = build_cloud_init(args.repo, args.branch)
        droplet = api.create_droplet(cloud_init, ssh_key_ids, size=args.size, region=args.region)
        droplet_id = droplet["id"]
        print(f"  Droplet ID: {droplet_id}")

        # --- Step 3 ---
        print(f"\n[3/7] Waiting for droplet to boot...")
        ip = api.wait_for_active(droplet_id)

        # --- Step 4 ---
        print(f"\n[4/7] Connecting via SSH and waiting for cloud-init...")
        client = create_ssh_client(ip, key_path)
        wait_for_cloud_init(client)

        # --- Step 5 ---
        print(f"\n[5/7] Uploading data file...")
        upload_csv(client, csv_path)

        # --- Step 6 ---
        print(f"\n[6/7] Starting strategy engine...")
        pid = start_engine(client)

        if args.watch:
            print("\nTailing engine log (Ctrl+C to detach)...")
            tail_log(client)

        wait_for_engine(client)

        # --- Step 7 ---
        print(f"\n[7/7] Downloading outputs...")
        download_outputs(client, output_dir)
        client.close()

        print(f"\n{'=' * 60}")
        print("JOB COMPLETE")
        print(f"  Results in: {output_dir / 'Outputs'}")
        print(f"{'=' * 60}")

    except KeyboardInterrupt:
        print("\n\nInterrupted.")
        if droplet_id:
            answer = input("Destroy the droplet? (y/n): ").strip().lower()
            if answer != "y":
                print(f"Droplet {droplet_id} kept alive at the IP above.")
                destroy_needed = False
            else:
                api.destroy_droplet(droplet_id)
                print("Droplet destroyed.")
                destroy_needed = False
        sys.exit(0)

    except Exception as e:
        print(f"\nERROR: {e}")
        if droplet_id:
            answer = input("\nDestroy droplet to stop billing? (y/n): ").strip().lower()
            if answer == "y":
                api.destroy_droplet(droplet_id)
                print("Droplet destroyed.")
                destroy_needed = False
            else:
                print(f"Droplet kept alive. Destroy manually when done.")
                destroy_needed = False
        raise

    finally:
        if droplet_id and destroy_needed and not args.keep:
            try:
                print("\nDestroying droplet to stop billing...")
                api.destroy_droplet(droplet_id)
                print("Droplet destroyed. Billing stopped.")
            except Exception as e:
                print(f"WARNING: Failed to destroy droplet {droplet_id}: {e}")
                print(f"  Destroy manually: https://cloud.digitalocean.com/droplets/{droplet_id}")


if __name__ == "__main__":
    main()
