from __future__ import annotations

import pytest

from modules.distributed_sweep import (
    HostSpec,
    assign_jobs_to_hosts,
    build_host_command,
    parse_host_specs,
)
from run_cluster_sweep import (
    build_auto_ingest_command,
    build_distributed_plan,
    build_job_list,
    parse_job_specs,
)


def test_parse_job_specs_deduplicates_and_normalizes_market():
    assert parse_job_specs(["es:daily", "NQ:60m", "ES:daily"]) == [
        ("ES", "daily"),
        ("NQ", "60m"),
    ]


def test_parse_job_specs_rejects_bad_format():
    with pytest.raises(ValueError, match="MARKET:TIMEFRAME"):
        parse_job_specs(["ES_daily"])


def test_build_job_list_exact_jobs_does_not_cross_product():
    all_markets = {
        "ES": {"data_files": {"daily": "ES_daily.csv", "60m": "ES_60m.csv"}},
        "NQ": {"data_files": {"daily": "NQ_daily.csv", "60m": "NQ_60m.csv"}},
    }

    jobs = build_job_list(
        all_markets,
        markets=["ES", "NQ"],
        timeframes=["daily", "60m"],
        explicit_jobs=[("ES", "daily"), ("NQ", "60m")],
    )

    assert jobs == [("ES", "daily"), ("NQ", "60m")]


def test_build_job_list_rejects_unavailable_exact_job():
    all_markets = {"ES": {"data_files": {"daily": "ES_daily.csv"}}}
    with pytest.raises(ValueError, match="unavailable timeframe"):
        build_job_list(all_markets, None, None, explicit_jobs=[("ES", "15m")])


def test_parse_host_specs_validates_workers():
    assert parse_host_specs(["c240:36", "gen8:24"]) == [
        HostSpec("c240", 36),
        HostSpec("gen8", 24),
    ]
    with pytest.raises(ValueError, match="Workers must be >= 1"):
        parse_host_specs(["r630:0"])


def test_assign_jobs_to_hosts_accounts_for_worker_capacity():
    jobs = [
        ("ES", "15m"),
        ("NQ", "15m"),
        ("YM", "15m"),
        ("GC", "daily"),
        ("CL", "daily"),
    ]
    assignments = assign_jobs_to_hosts(
        jobs,
        [HostSpec("big", 40), HostSpec("small", 10)],
    )

    assert sum(len(host_jobs) for host_jobs in assignments.values()) == len(jobs)
    assert len(assignments["big"]) > len(assignments["small"])


def test_build_host_command_uses_exact_jobs():
    command = build_host_command(
        [("ES", "daily"), ("NQ", "60m")],
        data_dir="/data/market_data/cfds/ohlc_engine",
        workers=36,
        remote_root="/tmp/psc",
        dry_run=True,
    )

    assert "cd /tmp/psc" in command
    assert "--jobs ES:daily NQ:60m" in command
    assert "--data-dir /data/market_data/cfds/ohlc_engine" in command
    assert "--workers 36" in command
    assert "--dry-run" in command


def test_build_distributed_plan_includes_commands_and_weights():
    plan = build_distributed_plan(
        [("ES", "5m"), ("NQ", "daily"), ("GC", "30m")],
        host_specs=["c240:80", "g9:80", "gen8:48"],
        data_dir="/data/market_data/cfds/ohlc_engine",
        remote_root="/tmp/psc",
        dry_run=True,
        run_id="run-test",
        backup_root=r"G:\My Drive\strategy-data-backup",
    )

    assert plan["total_jobs"] == 3
    assert plan["run_id"] == "run-test"
    assert plan["auto_ingest"]["enabled"] is True
    assert "scripts/auto_ingest_distributed_run.py" in plan["auto_ingest"]["command"]
    assert "--run-id run-test" in plan["auto_ingest"]["command"]
    assert '--backup-root "G:\\My Drive\\strategy-data-backup"' in plan["auto_ingest"]["command"]
    assert "scripts\\start_auto_ingest_watcher.ps1" in plan["auto_ingest"]["powershell_start_command"]
    assert len(plan["hosts"]) == 3
    assigned = sum(len(host["job_specs"]) for host in plan["hosts"])
    assert assigned == 3
    for host in plan["hosts"]:
        if host["job_specs"]:
            assert host["command"].startswith("cd /tmp/psc && python run_cluster_sweep.py --jobs ")
            assert "--data-dir /data/market_data/cfds/ohlc_engine" in host["command"]
            assert "--dry-run" in host["command"]


def test_build_auto_ingest_command_includes_plan_and_run_id():
    command = build_auto_ingest_command(
        run_id="run-123",
        plan_path=".tmp_plan.json",
        remote_root="/tmp/psc_run",
        backup_root=r"G:\My Drive\strategy-data-backup",
        poll_seconds=60,
    )

    assert "--run-id run-123" in command
    assert "--plan .tmp_plan.json" in command
    assert "--remote-root /tmp/psc_run" in command
    assert "--poll-seconds 60" in command
    assert '--backup-root "G:\\My Drive\\strategy-data-backup"' in command
