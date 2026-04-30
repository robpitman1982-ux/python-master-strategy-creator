from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from modules.master_leaderboard import aggregate_master_leaderboard, write_master_leaderboards


_FIXTURE_ROOT = Path(".tmp_master_leaderboard_fixture")


def _write_family_files(root: Path, dataset_name: str, classic_rows: list[dict], bootcamp_rows: list[dict]) -> None:
    ds_dir = root / dataset_name
    ds_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(classic_rows).to_csv(ds_dir / "family_leaderboard_results.csv", index=False)
    pd.DataFrame(bootcamp_rows).to_csv(ds_dir / "family_leaderboard_bootcamp.csv", index=False)


def _fresh_fixture_root(case_name: str) -> Path:
    root = _FIXTURE_ROOT / case_name
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_aggregate_master_leaderboard_bootcamp_sorting():
    root = _fresh_fixture_root("aggregate")
    _write_family_files(
        root,
        "ES_60m",
        classic_rows=[
            {
                "strategy_type": "trend",
                "leader_strategy_name": "TrendClassic",
                "accepted_final": True,
                "quality_flag": "STABLE",
                "leader_pf": 1.10,
                "leader_net_pnl": 40000.0,
                "leader_trades": 120,
                "is_pf": 1.02,
                "oos_pf": 1.15,
                "recent_12m_pf": 1.10,
            }
        ],
        bootcamp_rows=[
            {
                "strategy_type": "trend",
                "leader_strategy_name": "TrendBootcamp",
                "accepted_final": True,
                "quality_flag": "STABLE",
                "leader_pf": 1.10,
                "leader_net_pnl": 40000.0,
                "leader_trades": 120,
                "bootcamp_score": 58.0,
                "is_pf": 1.02,
                "oos_pf": 1.15,
                "recent_12m_pf": 1.10,
            }
        ],
    )
    _write_family_files(
        root,
        "ES_30m",
        classic_rows=[
            {
                "strategy_type": "breakout",
                "leader_strategy_name": "BreakoutClassic",
                "accepted_final": True,
                "quality_flag": "ROBUST",
                "leader_pf": 1.05,
                "leader_net_pnl": 45000.0,
                "leader_trades": 90,
                "is_pf": 1.00,
                "oos_pf": 1.05,
                "recent_12m_pf": 1.02,
            }
        ],
        bootcamp_rows=[
            {
                "strategy_type": "breakout",
                "leader_strategy_name": "BreakoutBootcamp",
                "accepted_final": True,
                "quality_flag": "ROBUST",
                "leader_pf": 1.05,
                "leader_net_pnl": 45000.0,
                "leader_trades": 90,
                "bootcamp_score": 71.0,
                "is_pf": 1.00,
                "oos_pf": 1.05,
                "recent_12m_pf": 1.02,
            }
        ],
    )

    classic = aggregate_master_leaderboard(outputs_root=root, ranking="classic")
    bootcamp = aggregate_master_leaderboard(outputs_root=root, ranking="bootcamp")

    assert list(classic["leader_strategy_name"]) == ["BreakoutClassic", "TrendClassic"]
    assert list(bootcamp["leader_strategy_name"]) == ["BreakoutBootcamp", "TrendBootcamp"]
    assert "bootcamp_score" in bootcamp.columns


def test_write_master_leaderboards_writes_both_outputs():
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
                "is_pf": 1.10,
                "oos_pf": 1.35,
                "recent_12m_pf": 1.30,
            }
        ],
        bootcamp_rows=[
            {
                "strategy_type": "mean_reversion",
                "leader_strategy_name": "BootcampMR",
                "accepted_final": True,
                "quality_flag": "ROBUST",
                "leader_pf": 1.40,
                "leader_net_pnl": 60000.0,
                "leader_trades": 180,
                "bootcamp_score": 75.5,
                "is_pf": 1.10,
                "oos_pf": 1.35,
                "recent_12m_pf": 1.30,
            }
        ],
    )

    classic, bootcamp = write_master_leaderboards(outputs_root=root)

    assert not classic.empty
    assert not bootcamp.empty
    assert (root / "master_leaderboard.csv").exists()
    assert (root / "master_leaderboard_bootcamp.csv").exists()


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
                "dataset": "ES_daily_dukascopy.csv",
                "is_pf": 1.10,
                "oos_pf": 1.35,
                "recent_12m_pf": 1.30,
            }
        ],
        bootcamp_rows=[],
    )

    classic, bootcamp = write_master_leaderboards(
        outputs_root=root,
        include_bootcamp_scores=False,
    )

    assert not classic.empty
    assert bootcamp.empty
    assert (root / "master_leaderboard.csv").exists()
    assert (root / "master_leaderboard_cfd.csv").exists()
    assert not (root / "master_leaderboard_bootcamp.csv").exists()
