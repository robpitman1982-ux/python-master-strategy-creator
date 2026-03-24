from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from modules.bootcamp_report import build_bootcamp_report, format_bootcamp_report, load_bootcamp_leaderboard


_FIXTURE_ROOT = Path(".tmp_bootcamp_report_fixture")


def _fresh_fixture_root(case_name: str) -> Path:
    root = _FIXTURE_ROOT / case_name
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_load_bootcamp_leaderboard_prefers_master_file():
    root = _fresh_fixture_root("master")
    df = pd.DataFrame(
        [
            {
                "rank": 1,
                "market": "ES",
                "timeframe": "30m",
                "strategy_type": "breakout",
                "leader_strategy_name": "BreakoutBootcamp",
                "bootcamp_score": 72.5,
                "leader_pf": 1.20,
                "oos_pf": 1.35,
                "leader_max_drawdown": 15000.0,
                "leader_trades_per_year": 8.0,
                "quality_flag": "ROBUST",
            }
        ]
    )
    df.to_csv(root / "master_leaderboard_bootcamp.csv", index=False)

    loaded = load_bootcamp_leaderboard(root)
    assert list(loaded["leader_strategy_name"]) == ["BreakoutBootcamp"]


def test_build_and_format_bootcamp_report():
    root = _fresh_fixture_root("report")
    ds_dir = root / "ES_60m"
    ds_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "strategy_type": "trend",
                "leader_strategy_name": "TrendBootcampA",
                "accepted_final": True,
                "bootcamp_score": 61.0,
                "leader_pf": 1.15,
                "oos_pf": 1.22,
                "leader_net_pnl": 42000.0,
                "leader_max_drawdown": 13000.0,
                "leader_trades_per_year": 6.0,
                "quality_flag": "STABLE",
            },
            {
                "strategy_type": "mean_reversion",
                "leader_strategy_name": "MRBootcampB",
                "accepted_final": True,
                "bootcamp_score": 74.0,
                "leader_pf": 1.32,
                "oos_pf": 1.44,
                "leader_net_pnl": 51000.0,
                "leader_max_drawdown": 12000.0,
                "leader_trades_per_year": 10.0,
                "quality_flag": "ROBUST",
            },
        ]
    ).to_csv(ds_dir / "family_leaderboard_bootcamp.csv", index=False)

    report_df = build_bootcamp_report(root, top_n=1)
    text = format_bootcamp_report(report_df)

    assert len(report_df) == 1
    assert report_df.iloc[0]["leader_strategy_name"] == "MRBootcampB"
    assert "MRBootcampB" in text
    assert "bootcamp_score" in text
