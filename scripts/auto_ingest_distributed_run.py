#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

SSH_OPTS = [
    "-T",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=15",
    "-o",
    "ConnectionAttempts=2",
    "-o",
    "ServerAliveInterval=15",
    "-o",
    "ServerAliveCountMax=2",
    "-o",
    "StrictHostKeyChecking=no",
]
SCP_OPTS = [
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=15",
    "-o",
    "ConnectionAttempts=2",
    "-o",
    "ServerAliveInterval=15",
    "-o",
    "ServerAliveCountMax=2",
    "-o",
    "StrictHostKeyChecking=no",
]


def _run(
    cmd: list[str],
    *,
    check: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess:
    if timeout is None:
        cmd_name = Path(cmd[0]).name.lower() if cmd else ""
        # ingest-host CLI on multi-GB datasets can take several minutes;
        # SCP needs the most. Default short timeout only for plain ssh probes.
        if cmd_name == "scp":
            timeout = 1800
        elif "run_cluster_results.py" in " ".join(cmd):
            timeout = 1800
        else:
            timeout = 60
    try:
        return subprocess.run(cmd, text=True, capture_output=True, check=check, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        result = subprocess.CompletedProcess(
            cmd,
            124,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + f"\nCommand timed out after {timeout}s",
        )
        if check:
            raise subprocess.CalledProcessError(
                result.returncode,
                result.args,
                output=result.stdout,
                stderr=result.stderr,
            )
        return result


import socket as _socket


def _local_hostnames() -> set[str]:
    names = {"", ".", "local", "localhost", "127.0.0.1"}
    try:
        h = _socket.gethostname().lower()
        if h:
            names.add(h)
            names.add(h.split(".")[0])
    except Exception:
        pass
    return names


def _is_local_control(host: str) -> bool:
    return host.strip().lower() in _local_hostnames()


def _job_run_name(market: str, timeframe: str) -> str:
    return f"{market.lower()}_{timeframe}_cfd"


def _dataset_name(market: str, timeframe: str) -> str:
    return f"{market.upper()}_{timeframe}"


def _job_key(host: str, market: str, timeframe: str) -> str:
    return f"{host}:{market.upper()}:{timeframe}"


def _load_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _remote_text(host: str, remote_path: str) -> str | None:
    if _is_local_control(host):
        try:
            return Path(remote_path).read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return None
        except Exception:
            return None
    result = _run(["ssh", *SSH_OPTS, host, f"cat {remote_path} 2>/dev/null"], check=False)
    if result.returncode != 0:
        return None
    return result.stdout


def _remote_status(host: str, remote_root: str, market: str, timeframe: str) -> dict | None:
    run_name = _job_run_name(market, timeframe)
    dataset = _dataset_name(market, timeframe)
    status_text = _remote_text(
        host,
        f"{remote_root}/Outputs/{run_name}/{dataset}/status.json",
    )
    if not status_text:
        return None
    try:
        return json.loads(status_text)
    except json.JSONDecodeError:
        return None


def _remote_file_exists(host: str, remote_path: str) -> bool:
    if _is_local_control(host):
        try:
            return Path(remote_path).is_file() and Path(remote_path).stat().st_size > 0
        except Exception:
            return False
    result = _run(["ssh", *SSH_OPTS, host, f"test -s {remote_path}"], check=False)
    return result.returncode == 0


def _host_reachable(host: str) -> bool:
    if _is_local_control(host):
        return True
    result = _run(["ssh", *SSH_OPTS, host, "true"], check=False, timeout=8)
    return result.returncode == 0


def _load_plan(plan_path: Path) -> dict[str, list[tuple[str, str]]]:
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    hosts: dict[str, list[tuple[str, str]]] = {}
    for host_entry in plan.get("hosts", []):
        host = host_entry["host"]
        hosts[host] = [
            (job["market"].upper(), job["timeframe"])
            for job in host_entry.get("jobs", [])
        ]
    return hosts


def _load_canonical_manifest_jobs(
    *,
    control_host: str,
    storage_root: str,
    run_id: str,
) -> set[str]:
    manifest_path = f"{storage_root}/runs/{run_id}/cluster_run_manifest.json"
    if _is_local_control(control_host):
        path = Path(storage_root) / "runs" / run_id / "cluster_run_manifest.json"
        if not path.exists():
            return set()
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return set()
        ingested: set[str] = set()
        for key, value in manifest.get("jobs", {}).items():
            host = value.get("host")
            if host:
                ingested.add(f"{host}:{key}")
        return ingested
    result = _run(["ssh", *SSH_OPTS, control_host, f"cat {manifest_path} 2>/dev/null"], check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return set()
    try:
        manifest = json.loads(result.stdout)
    except json.JSONDecodeError:
        return set()
    ingested: set[str] = set()
    for key, value in manifest.get("jobs", {}).items():
        host = value.get("host")
        if host:
            ingested.add(f"{host}:{key}")
    return ingested


def _stage_remote_job_to_control_host(
    *,
    host: str,
    control_host: str,
    remote_root: str,
    run_id: str,
    market: str,
    timeframe: str,
    local_stage_root: Path,
) -> str:
    run_name = _job_run_name(market, timeframe)
    dataset = _dataset_name(market, timeframe)
    local_stage = local_stage_root / run_id / host / f"{market}_{timeframe}"
    if local_stage.exists():
        shutil.rmtree(local_stage)
    (local_stage / "Outputs").mkdir(parents=True, exist_ok=True)

    remote_output = f"{host}:{remote_root}/Outputs/{run_name}"
    _run(["scp", *SCP_OPTS, "-r", remote_output, str(local_stage / "Outputs" / run_name)])

    log_name = f"psc_10market_{host}.log"
    _run(
        ["scp", *SCP_OPTS, f"{host}:/tmp/psc_logs/{log_name}", str(local_stage / f"{host}.log")],
        check=False,
    )

    if _is_local_control(control_host):
        return str(local_stage)

    control_stage = f"/tmp/psc_auto_ingest/{run_id}/{host}/{market}_{timeframe}"
    _run(["ssh", *SSH_OPTS, control_host, f"rm -rf {control_stage} && mkdir -p {control_stage}"])
    _run(["scp", *SCP_OPTS, "-r", str(local_stage / "Outputs"), f"{control_host}:{control_stage}/Outputs"])
    log_path = local_stage / f"{host}.log"
    if log_path.exists():
        _run(["scp", *SCP_OPTS, str(log_path), f"{control_host}:{control_stage}/{host}.log"], check=False)
    return control_stage


def _ingest_on_control_host(
    *,
    control_host: str,
    control_repo: str,
    venv_python: str,
    run_id: str,
    host: str,
    source_root: str,
    market: str,
    timeframe: str,
    storage_root: str,
    log_path: str | None,
) -> str:
    log_arg = f" --log-path {log_path}" if log_path else ""
    if _is_local_control(control_host):
        result = _run(
            [
                sys.executable if venv_python.startswith("~") else venv_python,
                "run_cluster_results.py",
                "ingest-host",
                "--run-id",
                run_id,
                "--host",
                host,
                "--source-root",
                source_root,
                "--jobs",
                f"{market}:{timeframe}",
                "--storage-root",
                storage_root,
                *([] if not log_path else ["--log-path", log_path]),
            ],
            check=True,
        )
        return result.stdout
    command = (
        f"cd {control_repo} && {venv_python} run_cluster_results.py ingest-host "
        f"--run-id {run_id} --host {host} --source-root {source_root} "
        f"--jobs {market}:{timeframe}{log_arg} --storage-root {storage_root}"
    )
    result = _run(["ssh", *SSH_OPTS, control_host, command])
    return result.stdout


def _mirror_control_storage_to_backup(
    *,
    control_host: str,
    storage_root: str,
    run_id: str,
    backup_root: Path,
    local_mirror_root: Path,
) -> str:
    if _is_local_control(control_host):
        result = _run(
            [
                sys.executable,
                "run_cluster_results.py",
                "mirror-backup",
                "--storage-root",
                storage_root,
                "--backup-root",
                str(backup_root),
                "--run-id",
                run_id,
            ]
        )
        return result.stdout
    if local_mirror_root.exists():
        shutil.rmtree(local_mirror_root)
    local_mirror_root.mkdir(parents=True, exist_ok=True)
    _run(["scp", *SCP_OPTS, "-r", f"{control_host}:{storage_root}/exports", str(local_mirror_root / "exports")])
    (local_mirror_root / "runs").mkdir(parents=True, exist_ok=True)
    _run(
        ["scp", *SCP_OPTS, f"{control_host}:{storage_root}/runs/LATEST_RUN.txt", str(local_mirror_root / "runs" / "LATEST_RUN.txt")],
        check=False,
    )
    _run(
        ["scp", *SCP_OPTS, "-r", f"{control_host}:{storage_root}/runs/{run_id}", str(local_mirror_root / "runs" / run_id)]
    )
    result = _run(
        [
            sys.executable,
            "run_cluster_results.py",
            "mirror-backup",
            "--storage-root",
            str(local_mirror_root),
            "--backup-root",
            str(backup_root),
            "--run-id",
            run_id,
        ]
    )
    return result.stdout


def _find_actual_host_for_dataset(
    *,
    cluster_hosts: list[str],
    remote_root: str,
    market: str,
    timeframe: str,
) -> str | None:
    """Sprint 90: scan every cluster host for a completed dataset.

    Used as fallback when the planned host doesn't have status.json for
    a (market, timeframe) — handles operator host migrations (e.g. plan
    said c240 but operator manually re-ran on g9).

    Returns the first host that has a DONE status.json AND a
    family_leaderboard_results.csv on disk. None if no host is reachable
    or has the dataset finished.
    """
    run_name = _job_run_name(market, timeframe)
    dataset = _dataset_name(market, timeframe)
    leaderboard_path = (
        f"{remote_root}/Outputs/{run_name}/{dataset}/family_leaderboard_results.csv"
    )
    for host in cluster_hosts:
        if not _host_reachable(host):
            continue
        status = _remote_status(host, remote_root, market, timeframe)
        if not status:
            continue
        if status.get("current_stage") != "DONE":
            continue
        if not _remote_file_exists(host, leaderboard_path):
            continue
        return host
    return None


def run_once(args: argparse.Namespace, state: dict) -> bool:
    plan_hosts = _load_plan(Path(args.plan))
    already = set(state.get("ingested", []))
    already |= _load_canonical_manifest_jobs(
        control_host=args.control_host,
        storage_root=args.storage_root,
        run_id=args.run_id,
    )
    did_ingest = False

    # Sprint 90: cluster-host pool for cross-host orphan-dataset fallback.
    # If empty, fallback is disabled and watcher behaves as before.
    cluster_hosts: list[str] = list(getattr(args, "cluster_hosts", []) or [])

    for host, jobs in plan_hosts.items():
        if not _host_reachable(host):
            print(
                f"[{datetime.now(UTC).isoformat(timespec='seconds')}] skipping {host}: SSH not reachable",
                flush=True,
            )
            continue
        for market, timeframe in jobs:
            key = _job_key(host, market, timeframe)
            if key in already:
                continue
            status = _remote_status(host, args.remote_root, market, timeframe)

            actual_host = host
            run_name = _job_run_name(market, timeframe)
            dataset = _dataset_name(market, timeframe)
            leaderboard_path = (
                f"{args.remote_root}/Outputs/{run_name}/{dataset}/family_leaderboard_results.csv"
            )

            # Sprint 90: if planned host has no status.json (or not DONE),
            # scan ALL cluster hosts to find where it actually completed.
            primary_done = (
                status
                and status.get("current_stage") == "DONE"
                and _remote_file_exists(host, leaderboard_path)
            )
            if not primary_done and cluster_hosts:
                fallback_host = _find_actual_host_for_dataset(
                    cluster_hosts=[h for h in cluster_hosts if h != host],
                    remote_root=args.remote_root,
                    market=market,
                    timeframe=timeframe,
                )
                if fallback_host:
                    print(
                        f"[{datetime.now(UTC).isoformat(timespec='seconds')}] orphan-dataset detected: "
                        f"{market}:{timeframe} planned for {host}, found completed on {fallback_host}",
                        flush=True,
                    )
                    actual_host = fallback_host
                    primary_done = True
                    # Re-key so manifest tracking matches reality
                    key = _job_key(actual_host, market, timeframe)
                    if key in already:
                        continue

            if not primary_done:
                continue

            # Reassign host to the actual location for downstream stage/ingest
            host = actual_host  # noqa: PLW2901 (intentional reassignment)

            print(f"[{datetime.now(UTC).isoformat(timespec='seconds')}] ingesting {key}", flush=True)
            if host == args.control_host or _is_local_control(host):
                source_root = args.remote_root
                log_path = f"/tmp/psc_logs/psc_10market_{host}.log"
            else:
                source_root = _stage_remote_job_to_control_host(
                    host=host,
                    control_host=args.control_host,
                    remote_root=args.remote_root,
                    run_id=args.run_id,
                    market=market,
                    timeframe=timeframe,
                    local_stage_root=Path(args.local_stage_root),
                )
                log_path = f"{source_root}/{host}.log"

            ingest_output = _ingest_on_control_host(
                control_host=args.control_host,
                control_repo=args.control_repo,
                venv_python=args.venv_python,
                run_id=args.run_id,
                host=host,
                source_root=source_root,
                market=market,
                timeframe=timeframe,
                storage_root=args.storage_root,
                log_path=log_path,
            )
            print(ingest_output.rstrip(), flush=True)

            if args.backup_root:
                mirror_output = _mirror_control_storage_to_backup(
                    control_host=args.control_host,
                    storage_root=args.storage_root,
                    run_id=args.run_id,
                    backup_root=Path(args.backup_root),
                    local_mirror_root=Path(args.local_mirror_root),
                )
                print(mirror_output.rstrip(), flush=True)

            already.add(key)
            state.setdefault("ingested", [])
            if key not in state["ingested"]:
                state["ingested"].append(key)
            state["updated_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
            _write_json_file(Path(args.state_path), state)
            did_ingest = True
    return did_ingest


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-ingest completed distributed sweep datasets.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--remote-root", required=True)
    parser.add_argument("--storage-root", default="/data/sweep_results")
    parser.add_argument("--control-host", default="c240")
    parser.add_argument("--control-repo", default="/tmp/psc_10market_20260501")
    parser.add_argument("--venv-python", default="~/venv/bin/python")
    parser.add_argument("--backup-root", help="Local Google Drive backup root to mirror after each ingest")
    parser.add_argument("--poll-seconds", type=int, default=300)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--state-path", default=".tmp_auto_ingest_state.json")
    parser.add_argument("--local-stage-root", default=".tmp_auto_ingest_stage")
    parser.add_argument("--local-mirror-root", default=".tmp_auto_ingest_mirror")
    parser.add_argument(
        "--cluster-hosts",
        nargs="+",
        default=["c240", "r630", "gen8", "g9"],
        help="Sprint 90: hosts to scan for orphan datasets when the planned "
             "host has no status.json. Set to empty list to disable fallback.",
    )
    args = parser.parse_args()

    state_path = Path(args.state_path)
    state = _load_json_file(state_path)
    state.setdefault("run_id", args.run_id)
    state.setdefault("created_utc", datetime.now(UTC).isoformat(timespec="seconds"))
    state.setdefault("ingested", [])

    while True:
        try:
            did_ingest = run_once(args, state)
            if not did_ingest:
                print(
                    f"[{datetime.now(UTC).isoformat(timespec='seconds')}] no newly completed datasets",
                    flush=True,
                )
        except Exception as exc:
            print(f"[{datetime.now(UTC).isoformat(timespec='seconds')}] ERROR: {exc}", flush=True)
        if args.once:
            break
        time.sleep(args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
