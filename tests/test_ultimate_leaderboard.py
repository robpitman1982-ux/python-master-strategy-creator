from __future__ import annotations

import shutil
import uuid
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tmp() -> Path:
    tmp = Path.cwd() / ".tmp_pytest_ul" / uuid.uuid4().hex
    tmp.mkdir(parents=True, exist_ok=True)
    return tmp


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_leaderboard_csv(
    path: Path,
    *,
    strategy_type: str = "mean_reversion",
    dataset: str = "ES_60m",
    leader_strategy_name: str = "RefinedMR_HB12",
    filters: str = "DistanceBelowSMAFilter,DownCloseFilter",
    leader_pf: float = 1.5,
    leader_net_pnl: float = 5000.0,
    quality_flag: str = "ROBUST",
    accepted_final: bool = True,
) -> None:
    rows = (
        "strategy_type,dataset,leader_strategy_name,best_combo_filter_class_names,"
        "leader_pf,leader_net_pnl,quality_flag,accepted_final\n"
        f"{strategy_type},{dataset},{leader_strategy_name},{filters},"
        f"{leader_pf},{leader_net_pnl},{quality_flag},{accepted_final}\n"
    )
    _write_text(path, rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_aggregate_empty_runs_returns_empty_df(monkeypatch):
    """When the runs directory is empty, the result is an empty DataFrame."""
    import pandas as pd
    from modules.ultimate_leaderboard import aggregate_ultimate_leaderboard

    tmp = _make_tmp()
    try:
        storage_root = tmp / "storage"
        (storage_root / "runs").mkdir(parents=True, exist_ok=True)

        result = aggregate_ultimate_leaderboard(storage_root=storage_root)

        assert isinstance(result, pd.DataFrame)
        assert result.empty
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_aggregate_deduplicates_by_signature(monkeypatch):
    """When the same strategy appears in two runs, the one with higher PF is kept."""
    import pandas as pd
    from modules.ultimate_leaderboard import aggregate_ultimate_leaderboard

    tmp = _make_tmp()
    try:
        storage_root = tmp / "storage"

        # run-1: PF 1.5
        _make_leaderboard_csv(
            storage_root / "runs" / "run-1" / "artifacts" / "Outputs" / "master_leaderboard.csv",
            leader_pf=1.5,
        )
        # run-2: same strategy signature, higher PF 2.0
        _make_leaderboard_csv(
            storage_root / "runs" / "run-2" / "artifacts" / "Outputs" / "master_leaderboard.csv",
            leader_pf=2.0,
        )

        result = aggregate_ultimate_leaderboard(storage_root=storage_root)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1, f"Expected 1 row after dedup, got {len(result)}"
        assert float(result.iloc[0]["leader_pf"]) == 2.0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_aggregate_adds_rank_column(monkeypatch):
    """Result DataFrame has a rank column starting at 1."""
    from modules.ultimate_leaderboard import aggregate_ultimate_leaderboard

    tmp = _make_tmp()
    try:
        storage_root = tmp / "storage"

        _make_leaderboard_csv(
            storage_root / "runs" / "run-1" / "artifacts" / "Outputs" / "master_leaderboard.csv",
        )
        _make_leaderboard_csv(
            storage_root / "runs" / "run-2" / "artifacts" / "Outputs" / "master_leaderboard.csv",
            leader_strategy_name="RefinedMR_HB24",
            leader_pf=1.8,
        )

        result = aggregate_ultimate_leaderboard(storage_root=storage_root)

        assert "rank" in result.columns
        assert list(result["rank"]) == list(range(1, len(result) + 1))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_aggregate_filters_to_accepted_only(monkeypatch):
    """Non-accepted rows are excluded from the result."""
    import pandas as pd
    from modules.ultimate_leaderboard import aggregate_ultimate_leaderboard

    tmp = _make_tmp()
    try:
        storage_root = tmp / "storage"

        csv_path = storage_root / "runs" / "run-1" / "artifacts" / "Outputs" / "master_leaderboard.csv"
        rows = (
            "strategy_type,dataset,leader_strategy_name,best_combo_filter_class_names,"
            "leader_pf,leader_net_pnl,quality_flag,accepted_final\n"
            "mean_reversion,ES_60m,RefinedMR_HB12,DistanceBelowSMAFilter,1.5,5000,ROBUST,True\n"
            "trend,ES_60m,TrendCombo_HB8,TrendDirectionFilter,0.8,-2000,BROKEN_IN_OOS,False\n"
        )
        _write_text(csv_path, rows)

        result = aggregate_ultimate_leaderboard(storage_root=storage_root)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1
        assert result.iloc[0]["strategy_type"] == "mean_reversion"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_aggregate_splits_futures_and_cfd_exports(monkeypatch):
    """Futures-named exports must not contain Dukascopy/CFD rows."""
    import pandas as pd
    from modules.ultimate_leaderboard import aggregate_ultimate_leaderboard

    tmp = _make_tmp()
    try:
        storage_root = tmp / "storage"

        _make_leaderboard_csv(
            storage_root / "runs" / "run-cfd" / "artifacts" / "Outputs" / "master_leaderboard.csv",
            dataset="DAX_daily_dukascopy.csv",
            leader_strategy_name="CFDStrategy",
            filters="DistanceBelowSMAFilter",
            leader_pf=2.0,
        )
        _make_leaderboard_csv(
            storage_root / "runs" / "run-futures" / "artifacts" / "Outputs" / "master_leaderboard.csv",
            dataset="ES_daily_tradestation.csv",
            leader_strategy_name="FuturesStrategy",
            filters="TrendDirectionFilter",
            leader_pf=1.8,
        )

        result = aggregate_ultimate_leaderboard(storage_root=storage_root)

        futures = pd.read_csv(storage_root / "ultimate_leaderboard_FUTURES.csv")
        legacy = pd.read_csv(storage_root / "ultimate_leaderboard.csv")
        cfd = pd.read_csv(storage_root / "ultimate_leaderboard_cfd.csv")

        assert len(result) == 2
        assert list(futures["dataset"].astype(str)) == ["ES_daily_tradestation.csv"]
        assert list(legacy["dataset"].astype(str)) == ["ES_daily_tradestation.csv"]
        assert list(cfd["dataset"].astype(str)) == ["DAX_daily_dukascopy.csv"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
