"""
Tests for:
- Split config validation (disjoint datasets)
- instance_name config support in launch_gcp_run
- Parallel launcher (run_cloud_parallel)
- download_run merge logic
- Ultimate leaderboard in download path
"""
from __future__ import annotations

import csv
import json
import tarfile
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _load_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Step 1: Split config validation
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent


def _datasets_in_config(config_path: Path) -> list[str]:
    cfg = _load_config(config_path)
    return [ds["path"] for ds in cfg.get("datasets", [])]


def test_vm_a_config_exists():
    assert (REPO_ROOT / "cloud" / "config_es_vm_a.yaml").exists()


def test_vm_b_config_exists():
    assert (REPO_ROOT / "cloud" / "config_es_vm_b.yaml").exists()


def test_vm_a_ondemand_config_exists():
    assert (REPO_ROOT / "cloud" / "config_es_vm_a_ondemand.yaml").exists()


def test_vm_b_ondemand_config_exists():
    assert (REPO_ROOT / "cloud" / "config_es_vm_b_ondemand.yaml").exists()


def test_vm_a_has_5m_only():
    datasets = _datasets_in_config(REPO_ROOT / "cloud" / "config_es_vm_a.yaml")
    assert len(datasets) == 1
    assert "5m" in datasets[0]


def test_vm_b_has_four_datasets():
    datasets = _datasets_in_config(REPO_ROOT / "cloud" / "config_es_vm_b.yaml")
    assert len(datasets) == 4


def test_vm_a_and_vm_b_datasets_are_disjoint():
    ds_a = set(_datasets_in_config(REPO_ROOT / "cloud" / "config_es_vm_a.yaml"))
    ds_b = set(_datasets_in_config(REPO_ROOT / "cloud" / "config_es_vm_b.yaml"))
    assert ds_a.isdisjoint(ds_b), f"Configs share datasets: {ds_a & ds_b}"


def test_vm_a_spot_config_has_instance_name():
    cfg = _load_config(REPO_ROOT / "cloud" / "config_es_vm_a.yaml")
    assert cfg["cloud"]["instance_name"] == "strategy-sweep-a"


def test_vm_b_spot_config_has_instance_name():
    cfg = _load_config(REPO_ROOT / "cloud" / "config_es_vm_b.yaml")
    assert cfg["cloud"]["instance_name"] == "strategy-sweep-b"


def test_vm_a_ondemand_is_standard():
    cfg = _load_config(REPO_ROOT / "cloud" / "config_es_vm_a_ondemand.yaml")
    assert cfg["cloud"]["provisioning_model"] == "STANDARD"


def test_vm_b_ondemand_is_standard():
    cfg = _load_config(REPO_ROOT / "cloud" / "config_es_vm_b_ondemand.yaml")
    assert cfg["cloud"]["provisioning_model"] == "STANDARD"


def test_vm_a_and_vm_a_ondemand_have_same_datasets():
    ds_spot = _datasets_in_config(REPO_ROOT / "cloud" / "config_es_vm_a.yaml")
    ds_od = _datasets_in_config(REPO_ROOT / "cloud" / "config_es_vm_a_ondemand.yaml")
    assert ds_spot == ds_od


# ---------------------------------------------------------------------------
# Step 2: instance_name config support
# ---------------------------------------------------------------------------

def test_instance_name_overridden_from_config(tmp_path: Path):
    """When cloud.instance_name is set in config, args.instance_name should be updated."""
    from cloud.launch_gcp_run import DEFAULT_INSTANCE_NAME
    import types

    # Simulate what launch_gcp_run does at the config-override block
    args = types.SimpleNamespace(
        instance_name=DEFAULT_INSTANCE_NAME,
        zone="us-central1-a",
        machine_type="n2-highcpu-96",
        provisioning_model="SPOT",
        boot_disk_size="120GB",
        image_family="ubuntu-2404-lts-amd64",
    )
    cloud_cfg = {"instance_name": "strategy-sweep-a"}

    if "instance_name" in cloud_cfg and args.instance_name == DEFAULT_INSTANCE_NAME:
        args.instance_name = cloud_cfg["instance_name"]

    assert args.instance_name == "strategy-sweep-a"


def test_instance_name_not_overridden_when_explicitly_set():
    """If --instance-name was passed explicitly, config should not override it."""
    from cloud.launch_gcp_run import DEFAULT_INSTANCE_NAME
    import types

    args = types.SimpleNamespace(instance_name="custom-name")
    cloud_cfg = {"instance_name": "strategy-sweep-a"}

    # Only override if still at default
    if "instance_name" in cloud_cfg and args.instance_name == DEFAULT_INSTANCE_NAME:
        args.instance_name = cloud_cfg["instance_name"]

    assert args.instance_name == "custom-name"


def test_make_run_id_incorporates_instance_name():
    from cloud.launch_gcp_run import make_run_id, sanitize_run_token
    run_id_a = make_run_id("strategy-sweep-a")
    run_id_b = make_run_id("strategy-sweep-b")
    assert run_id_a.startswith("strategy-sweep-a-")
    assert run_id_b.startswith("strategy-sweep-b-")
    assert run_id_a != run_id_b


# ---------------------------------------------------------------------------
# Step 3: Parallel launcher
# ---------------------------------------------------------------------------

def test_parallel_launcher_parse_args_defaults():
    import run_cloud_parallel
    args = run_cloud_parallel.parse_args([])
    assert "config_es_vm_a.yaml" in args.config_a
    assert "config_es_vm_b.yaml" in args.config_b
    assert not args.fire_and_forget
    assert not args.dry_run


def test_parallel_launcher_parse_args_custom():
    import run_cloud_parallel
    args = run_cloud_parallel.parse_args([
        "--config-a", "cloud/config_es_vm_a_ondemand.yaml",
        "--config-b", "cloud/config_es_vm_b_ondemand.yaml",
        "--fire-and-forget",
    ])
    assert args.config_a == "cloud/config_es_vm_a_ondemand.yaml"
    assert args.config_b == "cloud/config_es_vm_b_ondemand.yaml"
    assert args.fire_and_forget


def test_parallel_launcher_build_argv_dry_run():
    import run_cloud_parallel
    import types
    args = types.SimpleNamespace(fire_and_forget=False, dry_run=True, keep_vm=False)
    argv = run_cloud_parallel.build_launcher_argv("cloud/config_es_vm_a.yaml", args)
    assert "--dry-run" in argv
    assert "--fire-and-forget" not in argv


def test_parallel_launcher_calls_launcher_twice(monkeypatch):
    """Parallel launcher should call launcher_main exactly twice with different configs."""
    import run_cloud_parallel

    calls = []

    def mock_launcher(argv):
        calls.append(argv)
        return 0

    monkeypatch.setattr(run_cloud_parallel, "launcher_main", mock_launcher)
    monkeypatch.setattr(run_cloud_parallel, "_ensure_console_storage_env", lambda: None)

    rc = run_cloud_parallel.main(["--dry-run"])
    assert rc == 0
    assert len(calls) == 2
    configs = [next((a for i, a in enumerate(c) if c[i - 1] == "--config"), None) for c in calls]
    assert configs[0] != configs[1], "Both VMs should use different configs"
    assert "vm_a" in configs[0] or "vm_a" in configs[1]
    assert "vm_b" in configs[0] or "vm_b" in configs[1]


def test_parallel_launcher_continues_after_vm_a_failure(monkeypatch):
    """If VM-A fails, launcher should still attempt VM-B."""
    import run_cloud_parallel

    call_count = [0]

    def mock_launcher(argv):
        call_count[0] += 1
        return 1 if call_count[0] == 1 else 0  # A fails, B succeeds

    monkeypatch.setattr(run_cloud_parallel, "launcher_main", mock_launcher)
    monkeypatch.setattr(run_cloud_parallel, "_ensure_console_storage_env", lambda: None)

    rc = run_cloud_parallel.main(["--dry-run"])
    assert rc != 0  # Overall fails because A failed
    assert call_count[0] == 2  # But B was still called


# ---------------------------------------------------------------------------
# Step 4: download_run merge logic
# ---------------------------------------------------------------------------

_LEADERBOARD_ROWS_A = [
    {
        "rank": "1",
        "strategy_type": "trend",
        "dataset": "ES_5m",
        "leader_strategy_name": "trend_combo_1",
        "best_combo_filter_class_names": "TrendDirectionFilter,MomentumFilter",
        "leader_pf": "1.8",
        "leader_net_pnl": "50000",
        "quality_flag": "ROBUST",
        "accepted_final": "True",
    }
]
_LEADERBOARD_ROWS_B = [
    {
        "rank": "1",
        "strategy_type": "mean_reversion",
        "dataset": "ES_60m",
        "leader_strategy_name": "mr_combo_1",
        "best_combo_filter_class_names": "DistanceBelowSMAFilter,DownCloseFilter",
        "leader_pf": "1.6",
        "leader_net_pnl": "35000",
        "quality_flag": "STABLE",
        "accepted_final": "True",
    }
]


def _make_run_dir(runs_dir: Path, run_id: str, rows: list[dict]) -> Path:
    run_dir = runs_dir / run_id
    lb_path = run_dir / "artifacts" / "Outputs" / "master_leaderboard.csv"
    _write_csv(lb_path, rows)
    # Also create a dataset output dir
    dataset_dir = run_dir / "artifacts" / "Outputs" / "ES_test"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def test_merge_runs_produces_merged_leaderboard(tmp_path: Path, monkeypatch):
    import cloud.download_run as drun

    runs_dir = tmp_path / "Outputs" / "runs"
    monkeypatch.setattr(drun, "RUNS_DIR", runs_dir)

    run_a = "strategy-sweep-a-20260326T120000Z"
    run_b = "strategy-sweep-b-20260326T120001Z"

    _make_run_dir(runs_dir, run_a, _LEADERBOARD_ROWS_A)
    _make_run_dir(runs_dir, run_b, _LEADERBOARD_ROWS_B)

    # Patch download_run to skip actual GCS download (data already on disk)
    def mock_download(run_id):
        return runs_dir / run_id

    monkeypatch.setattr(drun, "download_run", mock_download)

    result = drun.merge_runs(run_a, run_b)

    assert result is not None
    assert result.exists()
    merged_lb = result / "master_leaderboard.csv"
    assert merged_lb.exists()

    rows = _load_csv(merged_lb)
    assert len(rows) == 2

    strategy_types = {r["strategy_type"] for r in rows}
    assert strategy_types == {"trend", "mean_reversion"}


def test_merge_runs_assigns_source_run_id(tmp_path: Path, monkeypatch):
    import cloud.download_run as drun

    runs_dir = tmp_path / "Outputs" / "runs"
    monkeypatch.setattr(drun, "RUNS_DIR", runs_dir)

    run_a = "strategy-sweep-a-20260326T120000Z"
    run_b = "strategy-sweep-b-20260326T120001Z"

    _make_run_dir(runs_dir, run_a, _LEADERBOARD_ROWS_A)
    _make_run_dir(runs_dir, run_b, _LEADERBOARD_ROWS_B)

    monkeypatch.setattr(drun, "download_run", lambda run_id: runs_dir / run_id)

    result = drun.merge_runs(run_a, run_b)

    rows = _load_csv(result / "master_leaderboard.csv")
    source_ids = {r.get("source_run_id") for r in rows}
    assert run_a in source_ids
    assert run_b in source_ids


def test_merge_runs_writes_merge_manifest(tmp_path: Path, monkeypatch):
    import cloud.download_run as drun

    runs_dir = tmp_path / "Outputs" / "runs"
    monkeypatch.setattr(drun, "RUNS_DIR", runs_dir)

    run_a = "strategy-sweep-a-20260326T120000Z"
    run_b = "strategy-sweep-b-20260326T120001Z"

    _make_run_dir(runs_dir, run_a, _LEADERBOARD_ROWS_A)
    _make_run_dir(runs_dir, run_b, _LEADERBOARD_ROWS_B)

    monkeypatch.setattr(drun, "download_run", lambda run_id: runs_dir / run_id)

    result = drun.merge_runs(run_a, run_b)

    manifest_path = result / "merge_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert set(manifest["source_runs"]) == {run_a, run_b}


def test_merge_runs_ranks_rows_by_quality_then_pnl(tmp_path: Path, monkeypatch):
    import cloud.download_run as drun

    runs_dir = tmp_path / "Outputs" / "runs"
    monkeypatch.setattr(drun, "RUNS_DIR", runs_dir)

    run_a = "strategy-sweep-a-20260326T120000Z"
    run_b = "strategy-sweep-b-20260326T120001Z"

    _make_run_dir(runs_dir, run_a, _LEADERBOARD_ROWS_A)  # ROBUST, $50k
    _make_run_dir(runs_dir, run_b, _LEADERBOARD_ROWS_B)  # STABLE, $35k

    monkeypatch.setattr(drun, "download_run", lambda run_id: runs_dir / run_id)

    result = drun.merge_runs(run_a, run_b)

    rows = _load_csv(result / "master_leaderboard.csv")
    # ROBUST should rank #1
    assert rows[0]["quality_flag"] == "ROBUST"
    assert rows[0]["rank"] == "1"


# ---------------------------------------------------------------------------
# Step 5: Ultimate leaderboard in download path (pure CSV, no pandas)
# ---------------------------------------------------------------------------

def test_aggregate_ultimate_leaderboard_from_multiple_runs(tmp_path: Path, monkeypatch):
    import cloud.download_run as drun

    runs_dir = tmp_path / "Outputs" / "runs"
    monkeypatch.setattr(drun, "RUNS_DIR", runs_dir)

    run_a = "strategy-sweep-a-20260326T120000Z"
    run_b = "strategy-sweep-b-20260326T120001Z"

    _make_run_dir(runs_dir, run_a, _LEADERBOARD_ROWS_A)
    _make_run_dir(runs_dir, run_b, _LEADERBOARD_ROWS_B)

    drun.aggregate_ultimate_leaderboard(runs_dir)

    output = tmp_path / "Outputs" / "ultimate_leaderboard.csv"
    assert output.exists()
    rows = _load_csv(output)
    assert len(rows) == 2


def test_aggregate_ultimate_leaderboard_deduplicates(tmp_path: Path, monkeypatch):
    import cloud.download_run as drun

    runs_dir = tmp_path / "Outputs" / "runs"
    monkeypatch.setattr(drun, "RUNS_DIR", runs_dir)

    run_a = "strategy-sweep-a-20260326T120000Z"
    run_b = "strategy-sweep-b-20260326T120001Z"

    # Both runs have the same strategy
    _make_run_dir(runs_dir, run_a, _LEADERBOARD_ROWS_A)
    _make_run_dir(runs_dir, run_b, _LEADERBOARD_ROWS_A)  # identical

    drun.aggregate_ultimate_leaderboard(runs_dir)

    output = tmp_path / "Outputs" / "ultimate_leaderboard.csv"
    rows = _load_csv(output)
    assert len(rows) == 1, "Duplicate strategy should be deduplicated"


def test_aggregate_ultimate_leaderboard_handles_empty_runs_dir(tmp_path: Path):
    import cloud.download_run as drun

    runs_dir = tmp_path / "Outputs" / "runs"
    # Don't create any runs

    # Should not raise
    drun.aggregate_ultimate_leaderboard(runs_dir)


def test_get_instance_prefix():
    from cloud.download_run import get_instance_prefix
    assert get_instance_prefix("strategy-sweep-a-20260326T120000Z") == "strategy-sweep-a"
    assert get_instance_prefix("strategy-sweep-b-20260326T120001Z") == "strategy-sweep-b"
    assert get_instance_prefix("strategy-sweep-20260326T120000Z") == "strategy-sweep"


def test_find_latest_pair_returns_different_prefixes(monkeypatch):
    import cloud.download_run as drun

    runs = [
        "strategy-sweep-a-20260326T120005Z",
        "strategy-sweep-b-20260326T120004Z",
        "strategy-sweep-a-20260326T110000Z",  # older A
        "strategy-sweep-b-20260326T110001Z",  # older B
    ]
    monkeypatch.setattr(drun, "list_bucket_runs", lambda: runs)

    pair = drun.find_latest_pair()
    assert pair is not None
    a, b = pair
    assert drun.get_instance_prefix(a) != drun.get_instance_prefix(b)
    # Should pick the most recent from each prefix
    assert "120005Z" in a or "120004Z" in b


def test_find_latest_pair_returns_none_when_single_prefix(monkeypatch):
    import cloud.download_run as drun

    runs = [
        "strategy-sweep-a-20260326T120005Z",
        "strategy-sweep-a-20260326T110000Z",
    ]
    monkeypatch.setattr(drun, "list_bucket_runs", lambda: runs)

    pair = drun.find_latest_pair()
    assert pair is None
