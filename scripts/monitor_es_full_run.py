from __future__ import annotations

import argparse
import subprocess
import time
from datetime import datetime
from pathlib import Path


DEFAULT_HOST_LOGS = {
    "r630": "/tmp/psc_logs/psc_693bb26_es_full_r630.log",
    "c240": "/tmp/psc_logs/psc_693bb26_es_full_c240.log",
    "gen8": "/tmp/psc_logs/psc_693bb26_es_full_gen8.log",
    "g9": "/tmp/psc_logs/psc_693bb26_es_full_g9.log",
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_ssh(host: str, remote_cmd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", host, remote_cmd],
        text=True,
        capture_output=True,
        check=False,
    )


def batch_complete(host: str, log_path: str) -> bool:
    result = run_ssh(host, f"grep -q 'BATCH SWEEP COMPLETE' {log_path}")
    return result.returncode == 0


def tail_log(host: str, log_path: str, lines: int = 20) -> str:
    result = run_ssh(host, f"tail -n {lines} {log_path}")
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        return f"[tail failed] {stderr or 'unknown error'}"
    return result.stdout.rstrip()


def write_snapshot(log_file: Path, host_logs: dict[str, str]) -> bool:
    all_done = True
    with log_file.open("a", encoding="utf-8") as f:
        f.write(f"\n===== {now_text()} =====\n")
        for host, log_path in host_logs.items():
            done = batch_complete(host, log_path)
            status = "COMPLETE" if done else "RUNNING"
            if not done:
                all_done = False
            f.write(f"\n[{host}] {status}\n")
            f.write(tail_log(host, log_path, lines=20))
            f.write("\n")
    return all_done


def main() -> int:
    parser = argparse.ArgumentParser(description="Hourly monitor for the full ES cluster sweep.")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=3600,
        help="Polling interval in seconds (default: 3600)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path("logs") / "es_full_run_monitor.log",
        help="Local log file for status snapshots",
    )
    args = parser.parse_args()

    args.log_file.parent.mkdir(parents=True, exist_ok=True)

    while True:
        all_done = write_snapshot(args.log_file, DEFAULT_HOST_LOGS)
        if all_done:
            return 0
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
