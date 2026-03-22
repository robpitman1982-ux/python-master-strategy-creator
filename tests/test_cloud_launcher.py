from __future__ import annotations

import argparse
import json
import tarfile
from pathlib import Path

import run_cloud_sweep
from cloud.launch_gcp_run import (
    DestroyDecision,
    DatasetSpec,
    LATEST_RUN_FILE_NAME,
    RUN_OUTCOME_ARTIFACT_DOWNLOAD_FAILED,
    RUN_OUTCOME_ARTIFACT_VERIFICATION_FAILED,
    RUN_OUTCOME_COMPLETED_VERIFIED,
    RUN_OUTCOME_VM_MISSING_BEFORE_RETRIEVAL,
    VM_OUTCOME_ALREADY_GONE,
    build_destroy_decision,
    can_auto_destroy,
    download_and_extract_artifacts,
    inspect_preserved_artifacts,
    LauncherStatusStore,
    monitor_run,
    PreflightResult,
    RunManifest,
    build_remote_config,
    create_input_bundle,
    create_remote_runner_file,
    main,
    make_run_id,
    parse_status_json,
    remote_paths_for_run,
    resolve_dataset_path,
    run_preflight,
    resolve_required_datasets,
    should_restart_remote_orchestration,
    summarize_remote_progress,
    verify_preserved_results,
    verify_remote_runner_started,
    write_latest_run_pointer,
)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_manifest(tmp_path: Path, datasets: list[DatasetSpec]) -> RunManifest:
    return RunManifest(
        run_id="test-run",
        created_utc="2026-03-20T00:00:00+00:00",
        instance_name="strategy-sweep",
        zone="australia-southeast2-a",
        machine_type="n2-highcpu-96",
        provisioning_model="SPOT",
        boot_disk_size="120GB",
        image_family="ubuntu-2404-lts-amd64",
        config_path=str(tmp_path / "cloud" / "test_config.yaml"),
        config_sha256="abc123",
        project_id="test-project",
        datasets=[dataset.__dict__ for dataset in datasets],
        remote_run_root="/tmp/strategy_engine_runs/test-run",
        remote_bundle_path="/tmp/strategy_engine_runs/test-run/input_bundle.tar.gz",
        remote_runner_path="/tmp/strategy_engine_runs/test-run/remote_runner.sh",
        remote_status_path="/tmp/strategy_engine_runs/test-run/run_status.json",
        remote_artifact_tarball="/tmp/strategy_engine_runs/test-run/artifacts.tar.gz",
        local_results_dir=str(tmp_path / "cloud_results" / "test-run"),
    )


def test_resolve_required_datasets_only_uses_config_entries(tmp_path: Path):
    data_dir = tmp_path / "Data"
    _write_text(data_dir / "ES_60m.csv", "a,b\n1,2\n")
    _write_text(data_dir / "ES_15m.csv", "a,b\n3,4\n")
    _write_text(data_dir / "unused.csv", "a,b\n5,6\n")

    config = {
        "datasets": [
            {"path": "Data/ES_60m.csv", "market": "ES", "timeframe": "60m"},
            {"path": "Data/ES_15m.csv", "market": "ES", "timeframe": "15m"},
        ]
    }

    datasets = resolve_required_datasets(config, tmp_path)

    assert [dataset.file_name for dataset in datasets] == ["ES_60m.csv", "ES_15m.csv"]
    assert all("unused.csv" != dataset.file_name for dataset in datasets)


def test_resolve_dataset_path_prefers_console_uploads_over_repo_data(tmp_path: Path, monkeypatch):
    uploads_dir = tmp_path / "strategy_console_storage" / "uploads"
    repo_data_dir = tmp_path / "Data"
    _write_text(uploads_dir / "ES_60m.csv", "upload\n")
    _write_text(repo_data_dir / "ES_60m.csv", "repo\n")

    monkeypatch.setattr("cloud.launch_gcp_run.UPLOADS_DIR", uploads_dir)
    monkeypatch.setattr("cloud.launch_gcp_run.REPO_DATA_DIR", repo_data_dir)
    monkeypatch.setattr("cloud.launch_gcp_run.REPO_ROOT", tmp_path)

    resolved = resolve_dataset_path("ES_60m.csv")

    assert resolved == (uploads_dir / "ES_60m.csv").resolve()


def test_create_input_bundle_includes_only_selected_datasets(tmp_path: Path):
    repo_root = tmp_path
    _write_text(repo_root / "modules" / "dummy.py", "VALUE = 1\n")
    _write_text(repo_root / "Data" / "keep.csv", "x,y\n1,2\n")
    _write_text(repo_root / "Data" / "skip.csv", "x,y\n3,4\n")
    _write_text(repo_root / "requirements.txt", "pyyaml\n")

    datasets = [
        DatasetSpec(
            market="ES",
            timeframe="60m",
            local_path=str(repo_root / "Data" / "keep.csv"),
            file_name="keep.csv",
            bundle_repo_path="Data/keep.csv",
            size_bytes=(repo_root / "Data" / "keep.csv").stat().st_size,
            sha256="hash-keep",
        )
    ]
    manifest = _make_manifest(tmp_path, datasets)
    remote_config = build_remote_config(
        {"datasets": [{"path": "Data/keep.csv", "market": "ES", "timeframe": "60m"}]},
        datasets,
    )
    bundle_path = tmp_path / "bundle.tar.gz"

    create_input_bundle(
        bundle_path=bundle_path,
        repo_root=repo_root,
        manifest=manifest,
        remote_config=remote_config,
        datasets=datasets,
    )

    with tarfile.open(bundle_path, "r:gz") as tar:
        names = tar.getnames()

    assert "repo/Data/keep.csv" in names
    assert "repo/Data/skip.csv" not in names
    assert "repo/modules/dummy.py" in names
    assert "manifest.json" in names
    assert "config.yaml" in names


def test_create_input_bundle_excludes_local_temp_and_junk_dirs(tmp_path: Path):
    repo_root = tmp_path
    _write_text(repo_root / "modules" / "keep.py", "VALUE = 1\n")
    _write_text(repo_root / ".tmp_pytest_run" / "junk.txt", "junk\n")
    _write_text(repo_root / ".tmp_pytest" / "junk.txt", "junk\n")
    _write_text(repo_root / ".streamlit" / "secrets.toml", "token='x'\n")
    _write_text(repo_root / "cloud_results" / "run-1" / "artifacts" / "logs" / "runner.log", "old log\n")
    _write_text(repo_root / ".coverage", "coverage-data\n")
    _write_text(repo_root / "Data" / "keep.csv", "x,y\n1,2\n")

    datasets = [
        DatasetSpec(
            market="ES",
            timeframe="60m",
            local_path=str(repo_root / "Data" / "keep.csv"),
            file_name="keep.csv",
            bundle_repo_path="Data/keep.csv",
            size_bytes=(repo_root / "Data" / "keep.csv").stat().st_size,
            sha256="hash-keep",
        )
    ]
    manifest = _make_manifest(tmp_path, datasets)
    bundle_path = tmp_path / "bundle.tar.gz"

    create_input_bundle(
        bundle_path=bundle_path,
        repo_root=repo_root,
        manifest=manifest,
        remote_config=build_remote_config({"datasets": [{"path": "Data/keep.csv", "market": "ES", "timeframe": "60m"}]}, datasets),
        datasets=datasets,
    )

    with tarfile.open(bundle_path, "r:gz") as tar:
        names = set(tar.getnames())

    assert "repo/modules/keep.py" in names
    assert "repo/Data/keep.csv" in names
    assert "repo/.tmp_pytest_run/junk.txt" not in names
    assert "repo/.tmp_pytest/junk.txt" not in names
    assert "repo/.streamlit/secrets.toml" not in names
    assert "repo/cloud_results/run-1/artifacts/logs/runner.log" not in names
    assert "repo/.coverage" not in names


def test_status_helpers_parse_and_summarize_dataset_progress():
    remote_status = parse_status_json(json.dumps({"state": "running", "stage": "validated", "message": "ready"}))
    dataset_statuses = [
        {
            "dataset": "ES_60m",
            "current_family": "trend",
            "current_stage": "SWEEP",
            "progress_pct": 42.0,
        }
    ]

    summary = summarize_remote_progress(remote_status, dataset_statuses)

    assert remote_status["state"] == "running"
    assert "ES_60m:trend:SWEEP:42.0%" == summary


def test_verify_preserved_results_accepts_meaningful_completed_outputs(tmp_path: Path):
    extracted_dir = tmp_path / "artifacts"
    _write_text(extracted_dir / "run_status.json", "{}")
    _write_text(extracted_dir / "manifest.json", "{}")
    _write_text(extracted_dir / "config.yaml", "datasets: []\n")
    _write_text(extracted_dir / "logs" / "engine_run.log", "ok\n")
    _write_text(extracted_dir / "Outputs" / "ES_60m" / "status.json", "{}")
    _write_text(extracted_dir / "Outputs" / "ES_60m" / "family_summary_results.csv", "col\n1\n")

    verified, message = verify_preserved_results(extracted_dir, "completed")

    assert verified is True
    assert "dataset outputs" in message


def test_verify_preserved_results_rejects_completed_outputs_without_meaningful_files(tmp_path: Path):
    extracted_dir = tmp_path / "artifacts"
    _write_text(extracted_dir / "run_status.json", "{}")
    _write_text(extracted_dir / "manifest.json", "{}")
    _write_text(extracted_dir / "config.yaml", "datasets: []\n")
    _write_text(extracted_dir / "logs" / "engine_run.log", "ok\n")
    _write_text(extracted_dir / "Outputs" / "ES_60m" / "status.json", "{}")

    verified, message = verify_preserved_results(extracted_dir, "completed")

    assert verified is False
    assert "meaningful result files" in message


def test_verify_preserved_results_requires_metadata_for_failed_runs(tmp_path: Path):
    extracted_dir = tmp_path / "artifacts"
    _write_text(extracted_dir / "logs" / "runner.log", "failed\n")

    verified, message = verify_preserved_results(extracted_dir, "failed")

    assert verified is False
    assert "Missing preserved metadata" in message


def test_run_preflight_validates_config_gcloud_project_and_datasets(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "cloud" / "config.yaml"
    _write_text(
        config_path,
        "datasets:\n"
        "  - path: Data/ES_60m.csv\n"
        "    market: ES\n"
        "    timeframe: 60m\n",
    )
    _write_text(tmp_path / "Data" / "ES_60m.csv", "Date,Time,Open,High,Low,Close\n2020-01-01,09:30,1,2,0,1\n")

    monkeypatch.setattr("cloud.launch_gcp_run.REPO_ROOT", tmp_path)
    monkeypatch.setattr("cloud.launch_gcp_run.resolve_gcloud_binary", lambda: "gcloud.cmd")
    monkeypatch.setattr("cloud.launch_gcp_run.get_active_project", lambda _bin, _project: "test-project")

    result = run_preflight(config_path, None)

    assert isinstance(result, PreflightResult)
    assert result.project_id == "test-project"
    assert result.gcloud_bin == "gcloud.cmd"
    assert [dataset.file_name for dataset in result.datasets] == ["ES_60m.csv"]


def test_run_preflight_rejects_empty_dataset(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "cloud" / "config.yaml"
    _write_text(
        config_path,
        "datasets:\n"
        "  - path: Data/ES_60m.csv\n"
        "    market: ES\n"
        "    timeframe: 60m\n",
    )
    _write_text(tmp_path / "Data" / "ES_60m.csv", "")

    monkeypatch.setattr("cloud.launch_gcp_run.REPO_ROOT", tmp_path)
    monkeypatch.setattr("cloud.launch_gcp_run.resolve_gcloud_binary", lambda: "gcloud.cmd")
    monkeypatch.setattr("cloud.launch_gcp_run.get_active_project", lambda _bin, _project: "test-project")

    try:
        run_preflight(config_path, None)
    except ValueError as exc:
        assert "Dataset is empty" in str(exc)
    else:
        raise AssertionError("Expected run_preflight to reject an empty dataset.")


def test_launcher_status_store_writes_stable_top_level_fields(tmp_path: Path):
    run_dir = tmp_path / "cloud_results" / "test-run"
    run_dir.mkdir(parents=True)
    store = LauncherStatusStore(
        run_dir,
        run_id="test-run",
        instance_name="strategy-sweep",
        zone="australia-southeast2-a",
        config_path="cloud/config.yaml",
        local_results_dir=str(run_dir),
        remote_run_root="/tmp/strategy_engine_runs/test-run",
        created_utc="2026-03-20T00:00:00+00:00",
    )

    store.update("running", "bundle", "Input bundle created.", bundle_size_bytes=1234)

    payload = json.loads((run_dir / "launcher_status.json").read_text(encoding="utf-8"))
    assert payload["run_id"] == "test-run"
    assert payload["instance_name"] == "strategy-sweep"
    assert payload["zone"] == "australia-southeast2-a"
    assert payload["config_path"] == "cloud/config.yaml"
    assert payload["state"] == "running"
    assert payload["stage"] == "bundle"
    assert payload["message"] == "Input bundle created."
    assert payload["created_utc"] == "2026-03-20T00:00:00+00:00"
    assert "updated_utc" in payload
    assert payload["bundle_size_bytes"] == 1234
    assert payload["local_results_dir"] == str(run_dir)
    assert payload["remote_run_root"] == "/tmp/strategy_engine_runs/test-run"


def test_launcher_status_store_preserves_existing_non_none_fields(tmp_path: Path):
    run_dir = tmp_path / "cloud_results" / "test-run"
    run_dir.mkdir(parents=True)
    store = LauncherStatusStore(
        run_dir,
        run_id="test-run",
        instance_name="strategy-sweep",
        zone="australia-southeast2-a",
        config_path="cloud/config.yaml",
        local_results_dir=str(run_dir),
        remote_run_root="/tmp/strategy_engine_runs/test-run",
        created_utc="2026-03-20T00:00:00+00:00",
    )

    store.update(
        "prepared",
        "bundle",
        "Input bundle created.",
        bundle_size_bytes=1234,
        vm_outcome="vm_preserved_for_inspection",
        run_outcome="run_completed_unverified",
        extracted_dir=str(run_dir / "artifacts"),
    )
    store.update("running", "monitoring", "Still monitoring.", vm_outcome=None, run_outcome=None)

    payload = json.loads((run_dir / "launcher_status.json").read_text(encoding="utf-8"))
    assert payload["bundle_size_bytes"] == 1234
    assert payload["vm_outcome"] == "vm_preserved_for_inspection"
    assert payload["run_outcome"] == "run_completed_unverified"
    assert payload["extracted_dir"] == str(run_dir / "artifacts")
    assert payload["state"] == "running"
    assert payload["stage"] == "monitoring"
    assert payload["message"] == "Still monitoring."


def test_create_remote_runner_file_uses_unix_lf_only(tmp_path: Path):
    runner_path = create_remote_runner_file(tmp_path)

    raw = runner_path.read_bytes()

    assert b"\r\n" not in raw
    assert raw.startswith(b"#!/bin/bash\n")


def test_create_remote_runner_file_is_fail_fast_and_unbuffered(tmp_path: Path):
    runner_path = create_remote_runner_file(tmp_path)
    text = runner_path.read_text(encoding="utf-8")

    assert "set -euo pipefail" in text
    assert 'python -u master_strategy_engine.py --config "$RUN_ROOT/config.yaml"' in text


def test_write_latest_run_pointer_records_latest_run(tmp_path: Path):
    results_root = tmp_path / "cloud_results"
    run_dir = results_root / "strategy-sweep-20260321T000000Z"
    run_dir.mkdir(parents=True)

    latest_path = write_latest_run_pointer(results_root, run_dir)

    assert latest_path.name == LATEST_RUN_FILE_NAME
    content = latest_path.read_text(encoding="utf-8")
    assert "strategy-sweep-20260321T000000Z" in content
    assert str(run_dir) in content


def test_run_id_and_remote_paths_strip_hidden_carriage_returns(monkeypatch):
    class _FixedDatetime:
        @staticmethod
        def now(_tz):
            class _Stamp:
                @staticmethod
                def strftime(_fmt: str) -> str:
                    return "20260321T010203Z\r\n"

            return _Stamp()

    monkeypatch.setattr("cloud.launch_gcp_run.datetime", _FixedDatetime)

    run_id = make_run_id("strategy-sweep\r\n")
    remote = remote_paths_for_run("strategy-sweep-20260321T010203Z\r\n")

    assert run_id == "strategy-sweep-20260321T010203Z"
    assert remote["run_root"] == "/tmp/strategy_engine_runs/strategy-sweep-20260321T010203Z"
    assert "\r" not in remote["runner"]
    assert "\n" not in remote["runner"]


def test_run_cloud_sweep_defaults_to_gcp96_config(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_launcher_main(argv: list[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(run_cloud_sweep, "launcher_main", _fake_launcher_main)

    exit_code = run_cloud_sweep.main([])

    assert exit_code == 0
    assert captured["argv"] == ["--config", "cloud/config_es_all_timeframes_gcp96.yaml"]


def test_run_cloud_sweep_forwards_wrapper_flags(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_launcher_main(argv: list[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(run_cloud_sweep, "launcher_main", _fake_launcher_main)

    exit_code = run_cloud_sweep.main(["--dry-run", "--keep-vm", "--config", "cloud/config_quick_test.yaml"])

    assert exit_code == 0
    assert captured["argv"] == ["--config", "cloud/config_quick_test.yaml", "--dry-run", "--keep-vm"]


def test_should_restart_remote_orchestration_only_when_needed():
    restart, reason = should_restart_remote_orchestration({"runner_process_active": True})
    assert restart is False
    assert "already active" in reason

    restart, reason = should_restart_remote_orchestration({"status_terminal": True, "status_state": "completed"})
    assert restart is False
    assert "terminal" in reason

    restart, reason = should_restart_remote_orchestration({"artifact_exists": True})
    assert restart is False
    assert "artifacts tarball" in reason

    restart, reason = should_restart_remote_orchestration({"status_exists": False, "runner_log_non_empty": False})
    assert restart is True
    assert "not active" in reason


def test_verify_remote_runner_started_requires_more_than_process_only(monkeypatch):
    responses = iter(
        [
            {"runner_process_active": True, "runner_log_exists": False, "runner_log_non_empty": False, "status_exists": False},
            {"runner_process_active": False, "runner_log_exists": True, "runner_log_non_empty": True, "status_exists": False},
        ]
    )

    monkeypatch.setattr("cloud.launch_gcp_run.detect_remote_runner_state", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr("cloud.launch_gcp_run.time.sleep", lambda _seconds: None)

    started, guard = verify_remote_runner_started([], "inst", "zone", "/tmp/run", "/tmp/run/remote_runner.sh", "/tmp/run/run_status.json", "/tmp/run/artifacts.tar.gz", timeout_seconds=10)

    assert started is True
    assert guard["runner_log_non_empty"] is True


def test_download_and_extract_artifacts_requires_local_tarball(tmp_path: Path, monkeypatch):
    tarball_path = tmp_path / "artifacts.tar.gz"
    extracted_dir = tmp_path / "artifacts"

    monkeypatch.setattr("cloud.launch_gcp_run.scp_from_remote", lambda *args, **kwargs: None)

    try:
        download_and_extract_artifacts([], "inst", "zone", "/remote/artifacts.tar.gz", tarball_path, extracted_dir)
    except FileNotFoundError as exc:
        assert "was not downloaded" in str(exc)
    else:
        raise AssertionError("Expected missing tarball to fail.")


def test_download_and_extract_artifacts_rejects_empty_tarball(tmp_path: Path, monkeypatch):
    tarball_path = tmp_path / "artifacts.tar.gz"
    extracted_dir = tmp_path / "artifacts"

    def _fake_scp(*args, **kwargs):
        tarball_path.write_bytes(b"")

    monkeypatch.setattr("cloud.launch_gcp_run.scp_from_remote", _fake_scp)

    try:
        download_and_extract_artifacts([], "inst", "zone", "/remote/artifacts.tar.gz", tarball_path, extracted_dir)
    except ValueError as exc:
        assert "is empty" in str(exc)
    else:
        raise AssertionError("Expected empty tarball to fail.")


def test_can_auto_destroy_rejects_null_run_outcome():
    args = argparse.Namespace(keep_vm=False)
    allowed, reason = can_auto_destroy(
        {
            "run_outcome": None,
            "artifacts_downloaded": True,
            "artifact_verified": True,
            "extraction_verified": True,
            "expected_outputs_present": True,
            "remote_state": "completed",
        },
        args,
    )

    assert allowed is False
    assert "explicit success" in reason


def test_can_auto_destroy_rejects_missing_artifacts():
    args = argparse.Namespace(keep_vm=False)
    allowed, reason = can_auto_destroy(
        {
            "run_outcome": RUN_OUTCOME_ARTIFACT_DOWNLOAD_FAILED,
            "artifacts_downloaded": False,
            "artifact_verified": False,
            "extraction_verified": False,
            "expected_outputs_present": False,
            "remote_state": "completed",
        },
        args,
    )

    assert allowed is False
    assert "explicit success" in reason or "downloaded" in reason


def test_inspect_preserved_artifacts_rejects_extraction_missing_expected_outputs(tmp_path: Path):
    tarball = tmp_path / "artifacts.tar.gz"
    tarball.write_bytes(b"non-empty")
    extracted_dir = tmp_path / "artifacts"
    _write_text(extracted_dir / "run_status.json", "{}")
    _write_text(extracted_dir / "manifest.json", "{}")
    _write_text(extracted_dir / "config.yaml", "datasets: []\n")
    _write_text(extracted_dir / "logs" / "engine_run.log", "ok\n")
    _write_text(extracted_dir / "Outputs" / "ES_60m" / "status.json", "{}")

    verification = inspect_preserved_artifacts(
        tarball_path=tarball,
        extracted_dir=extracted_dir,
        remote_state="completed",
    )

    assert verification.artifacts_downloaded is True
    assert verification.extraction_verified is True
    assert verification.expected_outputs_present is False
    assert verification.artifact_verified is False


def test_monitor_run_timeout_returns_non_success_and_never_implies_destroy(monkeypatch, tmp_path: Path):
    run_dir = tmp_path / "cloud_results" / "test-run"
    run_dir.mkdir(parents=True)
    store = LauncherStatusStore(
        run_dir,
        run_id="test-run",
        instance_name="strategy-sweep",
        zone="australia-southeast2-a",
        config_path="cloud/config.yaml",
        local_results_dir=str(run_dir),
        remote_run_root="/tmp/strategy_engine_runs/test-run",
        created_utc="2026-03-20T00:00:00+00:00",
    )
    manifest = _make_manifest(tmp_path, [])
    args = argparse.Namespace(instance_name="strategy-sweep", zone="australia-southeast2-a", poll_seconds=0, keep_vm=False)
    clock = iter([0, 0, 2])

    monkeypatch.setattr("cloud.launch_gcp_run.time.time", lambda: next(clock))
    monkeypatch.setattr("cloud.launch_gcp_run.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("cloud.launch_gcp_run.describe_instance_status", lambda *args, **kwargs: "RUNNING")
    monkeypatch.setattr("cloud.launch_gcp_run.read_remote_file", lambda *args, **kwargs: "{}")
    monkeypatch.setattr("cloud.launch_gcp_run.read_remote_dataset_statuses", lambda *args, **kwargs: [])

    remote_status = monitor_run(
        gcloud_base=[],
        args=args,
        manifest=manifest,
        status_store=store,
        timeout_seconds=1,
    )

    assert remote_status["stage"] == "monitor_timeout"
    assert remote_status["state"] == "unknown"
    allowed, _reason = can_auto_destroy(
        {
            "run_outcome": "remote_monitor_failed",
            "artifacts_downloaded": False,
            "artifact_verified": False,
            "extraction_verified": False,
            "expected_outputs_present": False,
            "remote_state": remote_status["state"],
        },
        argparse.Namespace(keep_vm=False),
    )
    assert allowed is False


def test_can_auto_destroy_allows_only_verified_success():
    args = argparse.Namespace(keep_vm=False)
    allowed, reason = can_auto_destroy(
        {
            "run_outcome": RUN_OUTCOME_COMPLETED_VERIFIED,
            "artifacts_downloaded": True,
            "artifact_verified": True,
            "extraction_verified": True,
            "expected_outputs_present": True,
            "remote_state": "completed",
        },
        args,
    )

    assert allowed is True
    assert "verified success" in reason


def test_can_auto_destroy_keep_vm_still_wins():
    args = argparse.Namespace(keep_vm=True)
    allowed, reason = can_auto_destroy(
        {
            "run_outcome": RUN_OUTCOME_COMPLETED_VERIFIED,
            "artifacts_downloaded": True,
            "artifact_verified": True,
            "extraction_verified": True,
            "expected_outputs_present": True,
            "remote_state": "completed",
        },
        args,
    )

    assert allowed is False
    assert "--keep-vm" in reason


def test_build_destroy_decision_allows_verified_success():
    decision = build_destroy_decision(
        status={
            "run_outcome": RUN_OUTCOME_COMPLETED_VERIFIED,
            "artifacts_downloaded": True,
            "artifact_verified": True,
            "extraction_verified": True,
            "expected_outputs_present": True,
            "remote_state": "completed",
            "remote_artifact_exists": True,
        },
        args=argparse.Namespace(keep_vm=False, instance_name="strategy-sweep", zone="australia-southeast2-a"),
        instance_exists_at_end=True,
        remote_status_path="/tmp/run_status.json",
        remote_tarball_path="/tmp/artifacts.tar.gz",
        local_run_dir=Path("cloud_results/test-run"),
    )

    assert isinstance(decision, DestroyDecision)
    assert decision.destroy_allowed is True
    assert decision.billing_should_be_stopped is True
    assert decision.operator_action == "none"


def test_build_destroy_decision_preserves_when_keep_vm_requested():
    decision = build_destroy_decision(
        status={
            "run_outcome": RUN_OUTCOME_COMPLETED_VERIFIED,
            "artifacts_downloaded": True,
            "artifact_verified": True,
            "extraction_verified": True,
            "expected_outputs_present": True,
            "remote_state": "completed",
            "remote_artifact_exists": True,
        },
        args=argparse.Namespace(keep_vm=True, instance_name="strategy-sweep", zone="australia-southeast2-a"),
        instance_exists_at_end=True,
        remote_status_path="/tmp/run_status.json",
        remote_tarball_path="/tmp/artifacts.tar.gz",
        local_run_dir=Path("cloud_results/test-run"),
    )

    assert decision.destroy_allowed is False
    assert decision.billing_should_be_stopped is False
    assert "delete the instance manually" in decision.operator_action


def test_build_destroy_decision_handles_instance_already_gone():
    decision = build_destroy_decision(
        status={
            "run_outcome": RUN_OUTCOME_VM_MISSING_BEFORE_RETRIEVAL,
            "artifacts_downloaded": False,
            "artifact_verified": False,
            "extraction_verified": False,
            "expected_outputs_present": False,
            "remote_state": "missing",
            "remote_artifact_exists": False,
        },
        args=argparse.Namespace(keep_vm=False, instance_name="strategy-sweep", zone="australia-southeast2-a"),
        instance_exists_at_end=False,
        remote_status_path="/tmp/run_status.json",
        remote_tarball_path="/tmp/artifacts.tar.gz",
        local_run_dir=Path("cloud_results/test-run"),
    )

    assert decision.destroy_allowed is False
    assert decision.destroy_reason == "instance already gone"
    assert decision.billing_should_be_stopped is True
    assert decision.operator_action == "check local artifacts only"
    assert decision.recovery_commands == []


def test_build_destroy_decision_includes_recovery_commands_for_preserved_vm():
    decision = build_destroy_decision(
        status={
            "run_outcome": RUN_OUTCOME_ARTIFACT_DOWNLOAD_FAILED,
            "artifacts_downloaded": False,
            "artifact_verified": False,
            "extraction_verified": False,
            "expected_outputs_present": False,
            "remote_state": "failed",
            "remote_artifact_exists": True,
        },
        args=argparse.Namespace(keep_vm=False, instance_name="strategy-sweep", zone="australia-southeast2-a"),
        instance_exists_at_end=True,
        remote_status_path="/tmp/run_status.json",
        remote_tarball_path="/tmp/artifacts.tar.gz",
        local_run_dir=Path("cloud_results/test-run"),
    )

    assert decision.destroy_allowed is False
    assert decision.billing_should_be_stopped is False
    assert "download artifacts manually" in decision.operator_action
    assert any("gcloud compute ssh strategy-sweep" in command for command in decision.recovery_commands)


def test_terminal_failure_status_fields_can_be_persisted(tmp_path: Path):
    run_dir = tmp_path / "cloud_results" / "test-run"
    run_dir.mkdir(parents=True)
    store = LauncherStatusStore(
        run_dir,
        run_id="test-run",
        instance_name="strategy-sweep",
        zone="australia-southeast2-a",
        config_path="cloud/config.yaml",
        local_results_dir=str(run_dir),
        remote_run_root="/tmp/strategy_engine_runs/test-run",
        created_utc="2026-03-20T00:00:00+00:00",
    )

    store.update(
        RUN_OUTCOME_VM_MISSING_BEFORE_RETRIEVAL,
        "run_terminal",
        "VM disappeared before retrieval.",
        run_outcome=RUN_OUTCOME_VM_MISSING_BEFORE_RETRIEVAL,
        vm_outcome=VM_OUTCOME_ALREADY_GONE,
        failure_reason="vm_missing_before_retrieval",
        destroy_allowed=False,
        artifacts_downloaded=False,
        extraction_verified=False,
        expected_outputs_present=False,
        artifact_verified=False,
        instance_exists_at_end=False,
    )

    payload = json.loads((run_dir / "launcher_status.json").read_text(encoding="utf-8"))
    assert payload["run_outcome"] == RUN_OUTCOME_VM_MISSING_BEFORE_RETRIEVAL
    assert payload["vm_outcome"] == VM_OUTCOME_ALREADY_GONE
    assert payload["failure_reason"] == "vm_missing_before_retrieval"
    assert payload["destroy_allowed"] is False


def test_main_dry_run_stops_before_vm_creation(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "cloud" / "config.yaml"
    results_root = tmp_path / "cloud_results"
    _write_text(config_path, "datasets:\n  - path: Data/ES_60m.csv\n    market: ES\n    timeframe: 60m\n")
    _write_text(tmp_path / "Data" / "ES_60m.csv", "Date,Time,Open,High,Low,Close\n2020-01-01,09:30,1,2,0,1\n")

    monkeypatch.setattr("cloud.launch_gcp_run.REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "cloud.launch_gcp_run.parse_args",
        lambda: argparse.Namespace(
            config=str(config_path),
            instance_name="strategy-sweep",
            zone="australia-southeast2-a",
            machine_type="n2-highcpu-96",
            project=None,
            results_root=str(results_root),
            poll_seconds=60,
            boot_disk_size="120GB",
            image_family="ubuntu-2404-lts-amd64",
            image_project="ubuntu-os-cloud",
            dry_run=True,
            keep_vm=False,
            keep_remote=False,
            provisioning_model="SPOT",
        ),
    )
    monkeypatch.setattr("cloud.launch_gcp_run.resolve_gcloud_binary", lambda: "gcloud.cmd")
    monkeypatch.setattr("cloud.launch_gcp_run.get_active_project", lambda _bin, _project: "test-project")

    def _forbid_create(*args, **kwargs):
        raise AssertionError("VM creation must not happen in dry-run mode.")

    monkeypatch.setattr("cloud.launch_gcp_run.create_instance", _forbid_create)

    exit_code = main()

    run_dirs = list(results_root.iterdir())
    assert exit_code == 0
    assert len(run_dirs) == 1
    payload = json.loads((run_dirs[0] / "launcher_status.json").read_text(encoding="utf-8"))
    assert payload["state"] == "dry_run_complete"
    assert payload["run_outcome"] == "dry_run_complete"
    manifest = json.loads((run_dirs[0] / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["provisioning_model"] == "SPOT"
    assert manifest["machine_type"] == "n2-highcpu-96"
    assert manifest["zone"] == "australia-southeast2-a"
    latest_run = (results_root / LATEST_RUN_FILE_NAME).read_text(encoding="utf-8")
    assert run_dirs[0].name in latest_run
    assert (run_dirs[0] / "input_bundle.tar.gz").exists()
