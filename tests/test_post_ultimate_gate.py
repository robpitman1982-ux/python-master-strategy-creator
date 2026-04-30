from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pandas as pd

from modules.post_ultimate_gate import build_post_ultimate_gate


def _make_tmp() -> Path:
    tmp = Path.cwd() / ".tmp_post_gate" / uuid.uuid4().hex
    tmp.mkdir(parents=True, exist_ok=True)
    return tmp


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _master_row(
    *,
    leader_strategy_name: str,
    run_id: str,
    hold_bars: int,
    stop_atr: float,
    oos_pf: float,
    dataset: str = "ES_30m_dukascopy.csv",
    strategy_type: str = "mean_reversion",
    filters: str = "FilterA,FilterB",
    exit_type: str = "time_stop",
) -> dict:
    return {
        "strategy_type": strategy_type,
        "leader_strategy_name": leader_strategy_name,
        "accepted_final": True,
        "quality_flag": "ROBUST",
        "leader_pf": 1.6,
        "leader_avg_trade": 100.0,
        "leader_net_pnl": 5000.0,
        "leader_trades": 120,
        "leader_trades_per_year": 12.0,
        "oos_pf": oos_pf,
        "recent_12m_pf": 1.2,
        "leader_max_drawdown": -1000.0,
        "calmar_ratio": 1.5,
        "best_combo_filter_class_names": filters,
        "dataset": dataset,
        "leader_hold_bars": hold_bars,
        "leader_stop_distance_atr": stop_atr,
        "leader_exit_type": exit_type,
        "run_id": run_id,
    }


def _write_run(storage_root: Path, run_id: str, rows: list[dict], trade_map: dict[str, list[float]] | None = None) -> None:
    outputs = storage_root / "runs" / run_id / "artifacts" / "Outputs"
    _write_csv(outputs / "master_leaderboard.csv", rows)
    dataset_folder = rows[0]["dataset"].replace(".csv", "")
    parts = dataset_folder.split("_")
    if len(parts) >= 2:
        dataset_folder = f"{parts[0]}_{parts[1]}"
    if trade_map:
        trades_rows: list[dict] = []
        for strategy_name, pnls in trade_map.items():
            for pnl in pnls:
                trades_rows.append(
                    {
                        "strategy": f"mean_reversion_{strategy_name}",
                        "net_pnl": pnl,
                    }
                )
        _write_csv(outputs / dataset_folder / "strategy_trades.csv", trades_rows)


def test_build_post_ultimate_gate_creates_audit_and_culls_fragile_or_concentrated_rows() -> None:
    tmp = _make_tmp()
    try:
        storage_root = tmp / "storage"
        exports_root = storage_root / "exports"
        exports_root.mkdir(parents=True, exist_ok=True)

        _write_run(
            storage_root,
            "run-fragile",
            [
                _master_row(leader_strategy_name="FragileA", run_id="run-fragile", hold_bars=5, stop_atr=0.50, oos_pf=2.0),
            ],
            trade_map={"FragileA": [1000.0] + [5.0] * 40},
        )
        _write_run(
            storage_root,
            "run-neighbor-1",
            [_master_row(leader_strategy_name="FragileA_HB4", run_id="run-neighbor-1", hold_bars=4, stop_atr=0.50, oos_pf=0.80)],
        )
        _write_run(
            storage_root,
            "run-neighbor-2",
            [_master_row(leader_strategy_name="FragileA_HB6", run_id="run-neighbor-2", hold_bars=6, stop_atr=0.50, oos_pf=0.90)],
        )
        _write_run(
            storage_root,
            "run-neighbor-3",
            [_master_row(leader_strategy_name="FragileA_ATR75", run_id="run-neighbor-3", hold_bars=5, stop_atr=0.75, oos_pf=0.85)],
        )
        _write_run(
            storage_root,
            "run-robust",
            [
                _master_row(leader_strategy_name="RobustB", run_id="run-robust", hold_bars=7, stop_atr=0.75, oos_pf=1.8, dataset="NQ_30m_dukascopy.csv"),
            ],
            trade_map={"RobustB": [80.0, 75.0, 60.0, 55.0, 50.0, -20.0, -15.0, 40.0, 35.0, 30.0]},
        )
        _write_run(
            storage_root,
            "run-r-neighbor-1",
            [_master_row(leader_strategy_name="RobustB_HB6", run_id="run-r-neighbor-1", hold_bars=6, stop_atr=0.75, oos_pf=1.50, dataset="NQ_30m_dukascopy.csv")],
        )
        _write_run(
            storage_root,
            "run-r-neighbor-2",
            [_master_row(leader_strategy_name="RobustB_HB8", run_id="run-r-neighbor-2", hold_bars=8, stop_atr=0.75, oos_pf=1.40, dataset="NQ_30m_dukascopy.csv")],
        )
        _write_run(
            storage_root,
            "run-r-neighbor-3",
            [_master_row(leader_strategy_name="RobustB_ATR1", run_id="run-r-neighbor-3", hold_bars=7, stop_atr=1.00, oos_pf=1.60, dataset="NQ_30m_dukascopy.csv")],
        )

        source_df = pd.DataFrame(
                [
                    _master_row(leader_strategy_name="FragileA", run_id="run-fragile", hold_bars=5, stop_atr=0.50, oos_pf=2.0),
                    _master_row(leader_strategy_name="RobustB", run_id="run-robust", hold_bars=7, stop_atr=0.75, oos_pf=1.8, dataset="NQ_30m_dukascopy.csv"),
                ]
            )
        source_df.insert(0, "rank", [1, 2])
        source_path = exports_root / "ultimate_leaderboard_FUTURES.csv"
        source_df.to_csv(source_path, index=False)

        result = build_post_ultimate_gate(
            storage_root=storage_root,
            source_path=source_path,
            output_dir=exports_root,
        )

        audit = pd.read_csv(result["audit_path"])
        gated = pd.read_csv(result["gated_path"])

        fragile = audit.loc[audit["leader_strategy_name"] == "FragileA"].iloc[0]
        robust = audit.loc[audit["leader_strategy_name"] == "RobustB"].iloc[0]

        assert bool(fragile["gate_concentration_pass"]) is False
        assert fragile["gate_fragility_status"] == "EVIDENCED"
        assert bool(fragile["gate_fragility_pass"]) is False
        assert bool(fragile["post_gate_pass"]) is False

        assert bool(robust["gate_concentration_pass"]) is True
        assert robust["gate_fragility_status"] == "EVIDENCED"
        assert bool(robust["gate_fragility_pass"]) is True
        assert bool(robust["post_gate_pass"]) is True

        assert list(gated["leader_strategy_name"]) == ["RobustB"]
        assert (exports_root / "ultimate_leaderboard_post_gate_audit.csv").exists()
        assert (exports_root / "ultimate_leaderboard_gated.csv").exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
