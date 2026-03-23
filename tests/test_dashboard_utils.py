from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from dashboard_utils import (
    badge_for_value,
    billing_status_for_launcher,
    build_test_run_readiness,
    build_run_choice_label,
    canonical_runs_root,
    choose_default_result_source,
    classify_run_status,
    collect_console_run_records,
    collect_result_sources,
    discover_launcher_run_dirs,
    discover_storage_run_dirs,
    estimate_run_cost,
    list_export_files,
    list_uploaded_datasets,
    operator_action_summary,
    parse_dataset_filename,
    pick_best_candidate_file,
    resolve_console_storage_paths,
)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_status(run_dir: Path, payload: dict) -> None:
    _write_text(run_dir / "launcher_status.json", json.dumps(payload))


def _make_workspace_temp_dir() -> Path:
    temp_dir = Path.cwd() / ".tmp_dashboard_utils" / uuid.uuid4().hex
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def test_resolve_console_storage_paths_uses_expected_layout():
    root = Path("/tmp/strategy_console_storage")

    paths = resolve_console_storage_paths(root)

    assert paths.uploads == root / "uploads"
    assert paths.runs == root / "runs"
    assert paths.exports == root / "exports"
    assert paths.backups == root / "backups"


def test_canonical_runs_root_points_to_storage_runs():
    root = Path("/tmp/strategy_console_storage")
    assert canonical_runs_root(resolve_console_storage_paths(root)) == root / "runs"


def test_discover_launcher_run_dirs_newest_first():
    tmp_path = _make_workspace_temp_dir()
    try:
        older = tmp_path / "cloud_results" / "run-older"
        newer = tmp_path / "cloud_results" / "run-newer"
        _write_status(older, {"run_id": "run-older"})
        _write_status(newer, {"run_id": "run-newer"})

        older_time = 1_700_000_000
        newer_time = older_time + 60
        import os

        os.utime(older, (older_time, older_time))
        os.utime(newer, (newer_time, newer_time))

        result = discover_launcher_run_dirs(tmp_path / "cloud_results")

        assert [path.name for path in result] == ["run-newer", "run-older"]
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_discover_storage_run_dirs_sorts_newest_first():
    tmp_path = _make_workspace_temp_dir()
    try:
        storage = resolve_console_storage_paths(tmp_path / "strategy_console_storage")
        older = storage.runs / "run-older"
        newer = storage.runs / "run-newer"
        _write_status(older, {"run_id": "run-older"})
        _write_status(newer, {"run_id": "run-newer"})

        older_time = 1_700_000_000
        newer_time = older_time + 60
        import os

        os.utime(older, (older_time, older_time))
        os.utime(newer, (newer_time, newer_time))

        result = discover_storage_run_dirs(storage)

        assert [path.name for path in result] == ["run-newer", "run-older"]
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_list_uploaded_datasets_returns_expected_files():
    tmp_path = _make_workspace_temp_dir()
    try:
        storage = resolve_console_storage_paths(tmp_path / "strategy_console_storage")
        _write_text(storage.uploads / "ES_60m.csv", "a,b\n1,2\n")
        _write_text(storage.uploads / "README.md", "ignore me\n")

        entries = list_uploaded_datasets(storage)

        assert [entry.name for entry in entries] == ["ES_60m.csv"]
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_parse_dataset_filename_extracts_market_and_timeframe():
    parsed = parse_dataset_filename("ES_60m_2008_2026_tradestation.csv")

    assert parsed["market"] == "ES"
    assert parsed["timeframe"] == "60m"


def test_list_export_files_returns_expected_files():
    tmp_path = _make_workspace_temp_dir()
    try:
        storage = resolve_console_storage_paths(tmp_path / "strategy_console_storage")
        _write_text(storage.exports / "leaderboard.csv", "rank\n1\n")
        _write_text(storage.exports / "notes.txt", "ignore me\n")

        entries = list_export_files(storage)

        assert [entry.name for entry in entries] == ["leaderboard.csv"]
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_collect_console_run_records_prefers_storage_runs(monkeypatch):
    tmp_path = _make_workspace_temp_dir()
    try:
        monkeypatch.chdir(tmp_path)
        storage = resolve_console_storage_paths(tmp_path / "strategy_console_storage")
        _write_status(
            storage.runs / "run-storage",
            {"run_id": "run-storage", "run_outcome": "run_completed_verified", "updated_utc": "2026-03-21T02:00:00+00:00"},
        )
        _write_text(storage.runs / "run-storage" / "run_manifest.json", json.dumps({"machine_type": "n2-highcpu-96"}))
        _write_status(
            tmp_path / "cloud_results" / "run-repo",
            {"run_id": "run-repo", "run_outcome": "artifact_download_failed", "updated_utc": "2026-03-21T01:00:00+00:00"},
        )
        import os

        os.utime(storage.runs / "run-storage", (1_700_000_060, 1_700_000_060))
        os.utime(tmp_path / "cloud_results" / "run-repo", (1_700_000_000, 1_700_000_000))

        records = collect_console_run_records(
            storage=storage,
            repo_results_root=tmp_path / "cloud_results",
            include_legacy_fallback=True,
        )

        assert [record["launcher_status"].get("run_id") for record in records] == ["run-storage", "run-repo"]
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_collect_console_run_records_can_disable_legacy_fallback(monkeypatch):
    tmp_path = _make_workspace_temp_dir()
    try:
        monkeypatch.chdir(tmp_path)
        storage = resolve_console_storage_paths(tmp_path / "strategy_console_storage")
        _write_status(storage.runs / "run-storage", {"run_id": "run-storage"})
        _write_status(tmp_path / "cloud_results" / "run-repo", {"run_id": "run-repo"})

        records = collect_console_run_records(
            storage=storage,
            repo_results_root=tmp_path / "cloud_results",
            include_legacy_fallback=False,
        )

        assert [record["launcher_status"].get("run_id") for record in records] == ["run-storage"]
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_collect_result_sources_prefers_cloud_runs_with_artifacts(monkeypatch):
    tmp_path = _make_workspace_temp_dir()
    try:
        monkeypatch.chdir(tmp_path)
        storage = resolve_console_storage_paths(tmp_path / "strategy_console_storage")
        run_dir = storage.runs / "run-1"
        _write_status(
            run_dir,
            {
                "run_id": "run-1",
                "run_outcome": "run_completed_verified",
                "updated_utc": "2026-03-21T02:00:00+00:00",
            },
        )
        _write_text(run_dir / "run_manifest.json", json.dumps({"machine_type": "n2-highcpu-96"}))
        _write_text(run_dir / "artifacts" / "Outputs" / "master_leaderboard.csv", "rank\n1\n")

        sources = collect_result_sources(storage=storage, results_root=tmp_path / "cloud_results")
        default_key = choose_default_result_source(sources)

        assert any(source.category == "Cloud Runs" for source in sources)
        assert default_key is not None
        assert default_key.startswith("cloud::")
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_pick_best_candidate_file_prefers_master_leaderboard():
    tmp_path = _make_workspace_temp_dir()
    try:
        _write_text(tmp_path / "family_summary_results.csv", "strategy_type\ntrend\n")
        _write_text(tmp_path / "master_leaderboard.csv", "rank\n1\n")

        best = pick_best_candidate_file(tmp_path)

        assert best is not None
        assert best.name == "master_leaderboard.csv"
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_estimate_run_cost_uses_local_price_map():
    record = {
        "launcher_status": {
            "created_utc": "2026-03-21T00:00:00+00:00",
            "updated_utc": "2026-03-21T02:00:00+00:00",
            "vm_outcome": "vm_preserved_for_inspection",
            "instance_exists_at_end": True,
            "state": "running",
        },
        "run_manifest": {
            "machine_type": "n2-highcpu-96",
            "provisioning_model": "SPOT",
        },
    }

    estimate = estimate_run_cost(record)

    assert estimate["machine_type"] == "n2-highcpu-96"
    assert estimate["provisioning_model"] == "SPOT"
    assert estimate["elapsed_seconds"] == 7200
    assert round(float(estimate["estimated_total_cost"]), 2) == 1.44  # $0.72/hr SPOT × 2h
    assert estimate["billing_active"] is True


def test_badges_and_run_classification_are_readable():
    assert badge_for_value("run_completed_verified") == "Verified Complete"
    assert classify_run_status({"state": "dry_run_complete"}) == "dry-run"
    label = build_run_choice_label(
        {
            "run_dir": Path("cloud_results/run-1"),
            "launcher_status": {"run_id": "run-1", "state": "running", "updated_utc": "2026-03-21T02:00:00+00:00"},
        }
    )
    assert "Running" in label


def test_billing_status_for_launcher_distinguishes_preserved_and_stopped():
    assert billing_status_for_launcher({"vm_outcome": "vm_destroyed"}) == "stopped"
    assert billing_status_for_launcher({"vm_outcome": "vm_preserved_for_inspection", "instance_exists_at_end": True}) == "still_running"
    assert billing_status_for_launcher({"vm_outcome": "vm_already_gone", "artifact_verified": False}) == "maybe_stopped"


def test_operator_action_summary_prefers_persisted_action():
    assert operator_action_summary({"operator_action": "inspect VM and download artifacts manually"}) == "inspect VM and download artifacts manually"
    assert "No manual action required" in operator_action_summary({"run_outcome": "run_completed_verified"})


def test_build_test_run_readiness_reports_ready_when_storage_and_dataset_exist():
    tmp_path = _make_workspace_temp_dir()
    try:
        storage = resolve_console_storage_paths(tmp_path / "strategy_console_storage")
        storage.uploads.mkdir(parents=True, exist_ok=True)
        storage.runs.mkdir(parents=True, exist_ok=True)
        storage.exports.mkdir(parents=True, exist_ok=True)
        _write_text(storage.uploads / "ES_60m.csv", "a,b\n1,2\n")

        readiness = build_test_run_readiness(storage=storage, run_records=[], uploaded_datasets=list_uploaded_datasets(storage))

        assert readiness.state == "ready"
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
