from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from modules.master_leaderboard import aggregate_master_leaderboard, write_master_leaderboards


_FIXTURE_ROOT = Path(".tmp_master_leaderboard_fixture")


def _write_family_files(root: Path, dataset_name: str, classic_rows: list[dict]) -> None:
    ds_dir = root / dataset_name
    ds_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(classic_rows).to_csv(ds_dir / "family_leaderboard_results.csv", index=False)


def _fresh_fixture_root(case_name: str) -> Path:
    root = _FIXTURE_ROOT / case_name
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_aggregate_master_leaderboard_prefers_robust_oos_and_low_dd():
    root = _fresh_fixture_root("aggregate")
    _write_family_files(
        root,
        "ES_60m",
        classic_rows=[
            {
                "strategy_type": "trend",
                "leader_strategy_name": "StableHigherPnl",
                "accepted_final": True,
                "quality_flag": "STABLE",
                "leader_pf": 1.60,
                "leader_net_pnl": 90000.0,
                "leader_trades": 120,
                "leader_trades_per_year": 8.0,
                "leader_max_drawdown": 30000.0,
                "calmar_ratio": 0.8,
                "is_pf": 1.10,
                "oos_pf": 1.25,
                "recent_12m_pf": 1.18,
            }
        ],
    )
    _write_family_files(
        root,
        "ES_30m",
        classic_rows=[
            {
                "strategy_type": "breakout",
                "leader_strategy_name": "RobustLowerDd",
                "accepted_final": True,
                "quality_flag": "ROBUST",
                "leader_pf": 1.45,
                "leader_net_pnl": 70000.0,
                "leader_trades": 150,
                "leader_trades_per_year": 10.0,
                "leader_max_drawdown": 12000.0,
                "calmar_ratio": 1.9,
                "is_pf": 1.08,
                "oos_pf": 1.55,
                "recent_12m_pf": 1.34,
            }
        ],
    )

    classic = aggregate_master_leaderboard(outputs_root=root)

    assert list(classic["leader_strategy_name"]) == ["RobustLowerDd", "StableHigherPnl"]


def test_write_master_leaderboards_writes_only_neutral_outputs():
    root = _fresh_fixture_root("write")
    _write_family_files(
        root,
        "ES_60m",
        classic_rows=[
            {
                "strategy_type": "mean_reversion",
                "leader_strategy_name": "ClassicMR",
                "accepted_final": True,
                "quality_flag": "ROBUST",
                "leader_pf": 1.40,
                "leader_net_pnl": 60000.0,
                "leader_trades": 180,
                "leader_trades_per_year": 9.0,
                "leader_max_drawdown": 15000.0,
                "calmar_ratio": 1.6,
                "is_pf": 1.10,
                "oos_pf": 1.35,
                "recent_12m_pf": 1.30,
            }
        ],
    )

    classic, bootcamp = write_master_leaderboards(outputs_root=root)

    assert not classic.empty
    assert bootcamp.empty
    assert (root / "master_leaderboard.csv").exists()
    assert not (root / "master_leaderboard_cfd.csv").exists()
    assert not (root / "master_leaderboard_bootcamp.csv").exists()


def test_write_master_leaderboards_cfd_skips_bootcamp_output():
    root = _fresh_fixture_root("write_cfd")
    _write_family_files(
        root,
        "ES_daily",
        classic_rows=[
            {
                "strategy_type": "mean_reversion",
                "leader_strategy_name": "CFDMR",
                "accepted_final": True,
                "quality_flag": "ROBUST",
                "leader_pf": 1.40,
                "leader_net_pnl": 60000.0,
                "leader_trades": 180,
                "leader_trades_per_year": 9.0,
                "leader_max_drawdown": 15000.0,
                "calmar_ratio": 1.6,
                "dataset": "ES_daily_dukascopy.csv",
                "is_pf": 1.10,
                "oos_pf": 1.35,
                "recent_12m_pf": 1.30,
            }
        ],
    )

    classic, bootcamp = write_master_leaderboards(
        outputs_root=root,
        include_bootcamp_scores=False,
        emit_cfd_alias=True,
    )

    assert not classic.empty
    assert bootcamp.empty
    assert (root / "master_leaderboard.csv").exists()
    assert (root / "master_leaderboard_cfd.csv").exists()
    assert not (root / "master_leaderboard_bootcamp.csv").exists()
