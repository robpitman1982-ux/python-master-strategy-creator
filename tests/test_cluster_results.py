from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pandas as pd

from modules.cluster_results import (
    finalize_cluster_run,
    ingest_host_results,
    mirror_storage_to_backup,
    resolve_cluster_run_paths,
)


def _make_tmp() -> Path:
    tmp = Path.cwd() / ".tmp_cluster_results" / uuid.uuid4().hex
    tmp.mkdir(parents=True, exist_ok=True)
    return tmp


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_dataset_output(
    source_root: Path,
    market: str,
    timeframe: str,
    *,
    accepted_final: bool = True,
    leader_pf: float = 1.5,
    oos_pf: float = 1.2,
    recent_12m_pf: float = 1.1,
    quality_flag: str = "ROBUST",
) -> None:
    run_name = f"{market.lower()}_{timeframe}_cfd"
    dataset_dir = source_root / "Outputs" / run_name / f"{market}_{timeframe}"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [
            {
                "strategy_type": "mean_reversion",
                "leader_strategy_name": f"{market}_{timeframe}_MR",
                "accepted_final": accepted_final,
                "quality_flag": quality_flag,
                "leader_pf": leader_pf,
                "leader_avg_trade": 100.0,
                "leader_net_pnl": 5000.0,
                "leader_trades": 100,
                "leader_trades_per_year": 10.0,
                "oos_pf": oos_pf,
                "recent_12m_pf": recent_12m_pf,
                "leader_max_drawdown": 1000.0,
                "calmar_ratio": 1.5,
                "best_combo_filter_class_names": "FilterA,FilterB",
                "dataset": f"{market}_{timeframe}_dukascopy",
            }
        ]
    )
    df.to_csv(dataset_dir / "family_leaderboard_results.csv", index=False)
    trades_df = pd.DataFrame(
        [
            {
                "strategy": f"mean_reversion_{market}_{timeframe}_MR",
                "net_pnl": 125.0,
            }
        ]
    )
    trades_df.to_csv(dataset_dir / "strategy_trades.csv", index=False)
    _write_text(dataset_dir / "status.json", '{"stage":"DONE"}\n')
    sweep_csv = dataset_dir / "mean_reversion_filter_combination_sweep_results.csv"
    sweep_csv.write_text("x\n1\n2\n3\n", encoding="utf-8")


def test_ingest_host_results_copies_dataset_dirs_and_log() -> None:
    tmp = _make_tmp()
    try:
        source_root = tmp / "source"
        storage_root = tmp / "storage"
        _write_dataset_output(source_root, "ES", "30m")
        log_path = tmp / "logs" / "c240.log"
        _write_text(log_path, "hello log\n")

        result = ingest_host_results(
            run_id="run-1",
            host="c240",
            source_root=source_root,
            jobs=[("ES", "30m")],
            log_path=log_path,
            storage_root=storage_root,
            commit="abc123",
        )

        paths = resolve_cluster_run_paths("run-1", storage_root=storage_root)
        assert result["copied_datasets"] == ["ES_30m"]
        assert result["finalized"] is True
        assert result["finalization"]["master_rows"] == 1
        assert (paths.outputs_dir / "ES_30m" / "family_leaderboard_results.csv").exists()
        assert (paths.outputs_dir / "ES_30m" / "strategy_trades.csv").exists()
        assert (storage_root / "exports" / "master_leaderboard.csv").exists()
        assert (storage_root / "exports" / "ultimate_leaderboard_FUTURES.csv").exists()
        assert (storage_root / "exports" / "ultimate_leaderboard_cfd.csv").exists()
        assert (paths.logs_dir / "c240.log").exists()
        manifest = paths.manifest_path.read_text(encoding="utf-8")
        assert "ES:30m" in manifest
        assert "abc123" in manifest
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_finalize_cluster_run_writes_master_and_exports() -> None:
    tmp = _make_tmp()
    try:
        storage_root = tmp / "storage"
        source_root = tmp / "source"
        _write_dataset_output(source_root, "ES", "30m")
        _write_dataset_output(source_root, "NQ", "60m", leader_pf=1.7, oos_pf=1.3, recent_12m_pf=1.25)
        ingest_host_results(
            run_id="run-2",
            host="host-a",
            source_root=source_root,
            jobs=[("ES", "30m"), ("NQ", "60m")],
            storage_root=storage_root,
            commit="def456",
        )

        result = finalize_cluster_run(run_id="run-2", storage_root=storage_root)

        paths = resolve_cluster_run_paths("run-2", storage_root=storage_root)
        assert result["master_rows"] == 2
        assert (paths.outputs_dir / "master_leaderboard.csv").exists()
        assert (paths.outputs_dir / "master_leaderboard_cfd.csv").exists()
        assert (storage_root / "exports" / "master_leaderboard.csv").exists()
        assert (storage_root / "exports" / "master_leaderboard_cfd.csv").exists()
        assert (storage_root / "exports" / "ultimate_leaderboard_FUTURES.csv").exists()
        assert (storage_root / "exports" / "ultimate_leaderboard.csv").exists()
        assert (storage_root / "exports" / "ultimate_leaderboard_cfd.csv").exists()
        assert (storage_root / "exports" / "ultimate_leaderboard_FUTURES_post_gate_audit.csv").exists()
        assert (storage_root / "exports" / "ultimate_leaderboard_FUTURES_gated.csv").exists()
        assert (storage_root / "exports" / "ultimate_leaderboard_post_gate_audit.csv").exists()
        assert (storage_root / "exports" / "ultimate_leaderboard_gated.csv").exists()
        assert (storage_root / "exports" / "ultimate_leaderboard_cfd_post_gate_audit.csv").exists()
        assert (storage_root / "exports" / "ultimate_leaderboard_cfd_gated.csv").exists()
        assert (storage_root / "runs" / "LATEST_RUN.txt").read_text(encoding="utf-8").strip() == "run-2"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_partial_run_still_flows_into_ultimate() -> None:
    tmp = _make_tmp()
    try:
        storage_root = tmp / "storage"

        es_root = tmp / "es_only"
        _write_dataset_output(es_root, "ES", "5m", leader_pf=1.9, oos_pf=1.4, recent_12m_pf=1.3)
        ingest_host_results(
            run_id="run-es-5m",
            host="c240",
            source_root=es_root,
            jobs=[("ES", "5m")],
            storage_root=storage_root,
        )
        finalize_cluster_run(run_id="run-es-5m", storage_root=storage_root)

        nq_root = tmp / "nq_hg_15m"
        _write_dataset_output(nq_root, "NQ", "15m", leader_pf=1.6, oos_pf=1.25, recent_12m_pf=1.2)
        _write_dataset_output(nq_root, "HG", "15m", leader_pf=1.55, oos_pf=1.22, recent_12m_pf=1.18)
        ingest_host_results(
            run_id="run-nq-hg-15m",
            host="r630",
            source_root=nq_root,
            jobs=[("NQ", "15m"), ("HG", "15m")],
            storage_root=storage_root,
        )
        result = finalize_cluster_run(run_id="run-nq-hg-15m", storage_root=storage_root)

        ultimate = pd.read_csv(storage_root / "exports" / "ultimate_leaderboard_cfd.csv")
        datasets = set(ultimate["dataset"].astype(str))
        assert "ES_5m_dukascopy" in datasets
        assert "NQ_15m_dukascopy" in datasets
        assert "HG_15m_dukascopy" in datasets
        assert result["ultimate_rows"] == 3
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_mirror_storage_to_backup_copies_exports_and_latest_run() -> None:
    tmp = _make_tmp()
    try:
        storage_root = tmp / "storage"
        backup_root = tmp / "gdrive"

        source_root = tmp / "source"
        _write_dataset_output(source_root, "ES", "30m")
        ingest_host_results(
            run_id="run-mirror",
            host="c240",
            source_root=source_root,
            jobs=[("ES", "30m")],
            storage_root=storage_root,
        )
        finalize_cluster_run(run_id="run-mirror", storage_root=storage_root)
        (backup_root / "leaderboards").mkdir(parents=True, exist_ok=True)
        (backup_root / "leaderboards" / "old_master.csv").write_text("stale\n", encoding="utf-8")

        result = mirror_storage_to_backup(storage_root=storage_root, backup_root=backup_root)

        assert result["latest_run_id"] == "run-mirror"
        assert result["archived_existing"] == [str(backup_root / "leaderboards" / "storage" / "old_master.csv")]
        assert not (backup_root / "leaderboards" / "old_master.csv").exists()
        assert (backup_root / "leaderboards" / "storage" / "old_master.csv").exists()
        assert (backup_root / "leaderboards" / "ultimate_leaderboard_FUTURES.csv").exists()
        assert (backup_root / "leaderboards" / "ultimate_leaderboard_cfd.csv").exists()
        assert (backup_root / "leaderboards" / "ultimate_leaderboard_FUTURES_gated.csv").exists()
        assert (backup_root / "leaderboards" / "ultimate_leaderboard_cfd_gated.csv").exists()
        assert not (backup_root / "leaderboards" / "master_leaderboard.csv").exists()
        assert not (backup_root / "leaderboards" / "master_leaderboard_cfd.csv").exists()
        assert not (backup_root / "leaderboards" / "ultimate_leaderboard.csv").exists()
        assert (backup_root / "leaderboards" / "storage" / "master_leaderboard.csv").exists()
        assert (backup_root / "leaderboards" / "storage" / "master_leaderboard_cfd.csv").exists()
        assert (backup_root / "leaderboards" / "storage" / "ultimate_leaderboard.csv").exists()
        assert (backup_root / "leaderboards" / "storage" / "ultimate_leaderboard_FUTURES_post_gate_audit.csv").exists()
        assert (backup_root / "leaderboards" / "storage" / "ultimate_leaderboard_post_gate_audit.csv").exists()
        assert (backup_root / "leaderboards" / "storage" / "ultimate_leaderboard_gated.csv").exists()
        assert (backup_root / "leaderboards" / "storage" / "ultimate_leaderboard_cfd_post_gate_audit.csv").exists()
        assert (backup_root / "recovery" / "README.txt").exists()
        assert (backup_root / "recovery" / "recovery_manifest.json").exists()
        assert (backup_root / "recovery" / "ultimate_leaderboard_FUTURES_recovery.csv").exists()
        assert (backup_root / "recovery" / "ultimate_leaderboard_cfd_recovery.csv").exists()
        assert (backup_root / "sweep_results" / "LATEST_RUN.txt").read_text(encoding="utf-8").strip() == "run-mirror"
        assert (backup_root / "sweep_results" / "runs" / "run-mirror" / "cluster_run_manifest.json").exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_finalize_can_mirror_to_backup_root() -> None:
    tmp = _make_tmp()
    try:
        storage_root = tmp / "storage"
        backup_root = tmp / "gdrive"

        source_root = tmp / "source"
        _write_dataset_output(source_root, "ES", "30m")
        ingest_host_results(
            run_id="run-auto-mirror",
            host="c240",
            source_root=source_root,
            jobs=[("ES", "30m")],
            storage_root=storage_root,
        )

        result = finalize_cluster_run(
            run_id="run-auto-mirror",
            storage_root=storage_root,
            backup_root=backup_root,
            mirror_backup=True,
        )

        assert result["backup_mirror"]["backup_root"] == str(backup_root)
        assert (backup_root / "leaderboards" / "storage" / "master_leaderboard_cfd.csv").exists()
        assert (backup_root / "leaderboards" / "ultimate_leaderboard_cfd.csv").exists()
        assert (
            backup_root
            / "sweep_results"
            / "runs"
            / "run-auto-mirror"
            / "cluster_run_manifest.json"
        ).exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_mirror_storage_to_backup_can_copy_all_runs() -> None:
    tmp = _make_tmp()
    try:
        storage_root = tmp / "storage"
        backup_root = tmp / "gdrive"

        source_a = tmp / "source-a"
        _write_dataset_output(source_a, "ES", "30m")
        ingest_host_results(
            run_id="run-a",
            host="c240",
            source_root=source_a,
            jobs=[("ES", "30m")],
            storage_root=storage_root,
        )
        finalize_cluster_run(run_id="run-a", storage_root=storage_root)

        source_b = tmp / "source-b"
        _write_dataset_output(source_b, "NQ", "60m")
        ingest_host_results(
            run_id="run-b",
            host="r630",
            source_root=source_b,
            jobs=[("NQ", "60m")],
            storage_root=storage_root,
        )
        finalize_cluster_run(run_id="run-b", storage_root=storage_root)

        result = mirror_storage_to_backup(
            storage_root=storage_root,
            backup_root=backup_root,
            include_all_runs=True,
        )

        assert set(Path(path_text).name for path_text in result["copied_runs"]) == {"run-a", "run-b"}
        assert (backup_root / "sweep_results" / "runs" / "run-a" / "cluster_run_manifest.json").exists()
        assert (backup_root / "sweep_results" / "runs" / "run-b" / "cluster_run_manifest.json").exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cfd_ultimate_is_written_from_mixed_corpus() -> None:
    tmp = _make_tmp()
    try:
        storage_root = tmp / "storage"

        cfd_source = tmp / "cfd-source"
        _write_dataset_output(cfd_source, "ES", "30m", leader_pf=1.8)
        ingest_host_results(
            run_id="run-cfd",
            host="c240",
            source_root=cfd_source,
            jobs=[("ES", "30m")],
            storage_root=storage_root,
        )

        futures_run_outputs = storage_root / "runs" / "run-futures" / "artifacts" / "Outputs"
        futures_run_outputs.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            [
                {
                    "strategy_type": "trend",
                    "leader_strategy_name": "FuturesTrend",
                    "accepted_final": True,
                    "quality_flag": "ROBUST",
                    "leader_pf": 2.0,
                    "leader_avg_trade": 200.0,
                    "leader_net_pnl": 10000.0,
                    "leader_trades": 100,
                    "oos_pf": 1.5,
                    "recent_12m_pf": 1.3,
                    "dataset": "ES_30m_tradestation.csv",
                }
            ]
        ).to_csv(futures_run_outputs / "master_leaderboard.csv", index=False)

        result = finalize_cluster_run(run_id="run-cfd", storage_root=storage_root)

        futures = pd.read_csv(storage_root / "exports" / "ultimate_leaderboard_FUTURES.csv")
        cfd = pd.read_csv(storage_root / "exports" / "ultimate_leaderboard_cfd.csv")
        assert result["ultimate_rows"] == 2
        assert list(futures["dataset"].astype(str)) == ["ES_30m_tradestation.csv"]
        assert list(cfd["dataset"].astype(str)) == ["ES_30m_dukascopy"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
