"""Tests for Sprint 84 canonical trade emission and parity status patching."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pandas as pd
import pytest

from modules.trade_emission import (
    PARITY_ABS_TOLERANCE,
    PARITY_REL_TOLERANCE,
    StrategyEmissionResult,
    _parity_status,
    _strategy_key,
    apply_parity_status,
)


def _make_tmp() -> Path:
    tmp = Path.cwd() / ".tmp_trade_emission" / uuid.uuid4().hex
    tmp.mkdir(parents=True, exist_ok=True)
    return tmp


def test_parity_status_passes_within_relative_tolerance():
    # Within 0.5%, well under the 1% threshold
    status, ratio = _parity_status(rebuilt=10000.0, leader=10050.0)
    assert status == "OK"
    assert ratio == pytest.approx(10000.0 / 10050.0)


def test_parity_status_passes_within_absolute_tolerance_when_leader_small():
    # Leader is small; abs diff is $50 which is <= $100 absolute tolerance.
    status, ratio = _parity_status(rebuilt=200.0, leader=150.0)
    assert status == "OK"


def test_parity_status_fails_when_relative_diff_exceeds_threshold():
    # 5% divergence on a non-trivial leader value should fail.
    status, ratio = _parity_status(rebuilt=10000.0, leader=10500.0)
    assert status == "PARITY_FAILED"
    assert ratio == pytest.approx(10000.0 / 10500.0)


def test_parity_status_fails_when_leader_zero_and_rebuilt_large():
    status, ratio = _parity_status(rebuilt=5000.0, leader=0.0)
    assert status == "PARITY_FAILED"
    assert pd.isna(ratio)


def test_parity_status_handles_nan_leader_gracefully():
    status, ratio = _parity_status(rebuilt=1000.0, leader=float("nan"))
    assert status == "OK"
    assert pd.isna(ratio)


def test_parity_tolerance_constants_are_within_spec():
    # Sprint 84 freezes these — guard against accidental loosening.
    assert PARITY_REL_TOLERANCE == 0.01
    assert PARITY_ABS_TOLERANCE == 100.0


def test_strategy_key_combines_type_and_name():
    row = pd.Series({"strategy_type": "mean_reversion", "leader_strategy_name": "FooBar"})
    assert _strategy_key(row) == "mean_reversion_FooBar"


def test_strategy_key_handles_missing_type():
    row = pd.Series({"strategy_type": "", "leader_strategy_name": "Lone"})
    assert _strategy_key(row) == "Lone"


def test_apply_parity_status_writes_expected_columns_and_values():
    tmp = _make_tmp()
    try:
        leaderboard_path = tmp / "family_leaderboard_results.csv"
        df = pd.DataFrame(
            [
                {
                    "strategy_type": "mean_reversion",
                    "leader_strategy_name": "Alpha",
                    "accepted_final": True,
                    "leader_net_pnl": 5000.0,
                },
                {
                    "strategy_type": "trend",
                    "leader_strategy_name": "Beta",
                    "accepted_final": True,
                    "leader_net_pnl": 8000.0,
                },
                {
                    "strategy_type": "breakout",
                    "leader_strategy_name": "Charlie",
                    "accepted_final": False,
                    "leader_net_pnl": 1000.0,
                },
            ]
        )
        df.to_csv(leaderboard_path, index=False)

        results = {
            "mean_reversion_Alpha": StrategyEmissionResult(
                strategy_key="mean_reversion_Alpha",
                status="OK",
                n_trades=120,
                rebuilt_net_pnl=5010.0,
                leader_net_pnl=5000.0,
                parity_ratio=1.002,
            ),
            "trend_Beta": StrategyEmissionResult(
                strategy_key="trend_Beta",
                status="PARITY_FAILED",
                n_trades=80,
                rebuilt_net_pnl=2000.0,
                leader_net_pnl=8000.0,
                parity_ratio=0.25,
            ),
        }

        apply_parity_status(leaderboard_path, results)

        out = pd.read_csv(leaderboard_path)
        assert "trade_artifact_status" in out.columns
        assert "trade_artifact_n_trades" in out.columns
        assert "trade_artifact_rebuilt_net_pnl" in out.columns
        assert "trade_artifact_parity_ratio" in out.columns

        alpha = out[out["leader_strategy_name"] == "Alpha"].iloc[0]
        beta = out[out["leader_strategy_name"] == "Beta"].iloc[0]
        charlie = out[out["leader_strategy_name"] == "Charlie"].iloc[0]

        assert alpha["trade_artifact_status"] == "OK"
        assert int(alpha["trade_artifact_n_trades"]) == 120
        assert float(alpha["trade_artifact_rebuilt_net_pnl"]) == pytest.approx(5010.0)

        assert beta["trade_artifact_status"] == "PARITY_FAILED"
        assert int(beta["trade_artifact_n_trades"]) == 80

        # Non-accepted rows are marked SKIPPED regardless of any results dict.
        assert charlie["trade_artifact_status"] == "SKIPPED"


    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_apply_parity_status_marks_rebuild_failed_for_missing_results():
    """If a strategy is accepted_final but absent from results, mark REBUILD_FAILED."""
    tmp = _make_tmp()
    try:
        leaderboard_path = tmp / "family_leaderboard_results.csv"
        df = pd.DataFrame(
            [
                {
                    "strategy_type": "mean_reversion",
                    "leader_strategy_name": "Ghost",
                    "accepted_final": True,
                    "leader_net_pnl": 3000.0,
                },
            ]
        )
        df.to_csv(leaderboard_path, index=False)

        # Empty results dict: rebuild was attempted but produced nothing for this row.
        apply_parity_status(leaderboard_path, {})

        out = pd.read_csv(leaderboard_path)
        ghost = out.iloc[0]
        assert ghost["trade_artifact_status"] == "REBUILD_FAILED"
        assert int(ghost["trade_artifact_n_trades"]) == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_apply_parity_status_handles_missing_leaderboard_silently():
    # Should not raise even if the file does not exist.
    apply_parity_status(Path("/nonexistent/family_leaderboard_results.csv"), {})


def test_apply_parity_status_handles_empty_leaderboard():
    tmp = _make_tmp()
    try:
        empty_path = tmp / "family_leaderboard_results.csv"
        pd.DataFrame().to_csv(empty_path, index=False)
        apply_parity_status(empty_path, {})
        # No exception raised; file unchanged content-wise
        assert empty_path.exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
