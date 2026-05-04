"""Tests for modules/engine_resume.py - Sprint 93."""

from __future__ import annotations

import pandas as pd

from modules.engine_resume import (
    FINGERPRINT_FILENAME,
    ResumeCheck,
    compute_dataset_fingerprint,
    is_family_resumable,
    load_resumed_family,
    make_synthetic_sanity_check,
    read_fingerprint,
    write_fingerprint,
)


# ---------------------------------------------------------------------------
# Stage 1 - fingerprint
# ---------------------------------------------------------------------------

def test_fingerprint_is_deterministic_for_same_payload():
    p1 = compute_dataset_fingerprint({"a": 1, "b": 2}, engine_version="abc")
    p2 = compute_dataset_fingerprint({"b": 2, "a": 1}, engine_version="abc")
    assert p1 == p2  # dict order must not matter
    assert len(p1) == 64  # sha256 hex


def test_fingerprint_changes_when_payload_changes():
    p1 = compute_dataset_fingerprint({"a": 1}, engine_version="abc")
    p2 = compute_dataset_fingerprint({"a": 2}, engine_version="abc")
    assert p1 != p2


def test_fingerprint_changes_when_engine_version_changes():
    p1 = compute_dataset_fingerprint({"a": 1}, engine_version="abc")
    p2 = compute_dataset_fingerprint({"a": 1}, engine_version="def")
    assert p1 != p2


def test_fingerprint_string_payload_supported():
    p1 = compute_dataset_fingerprint("hello", engine_version="v")
    p2 = compute_dataset_fingerprint(b"hello", engine_version="v")
    assert p1 == p2


def test_write_and_read_fingerprint_roundtrip(tmp_path):
    fp = "deadbeef" * 8
    written = write_fingerprint(tmp_path, fp)
    assert written.name == FINGERPRINT_FILENAME
    assert written.is_file()
    assert read_fingerprint(tmp_path) == fp


def test_read_fingerprint_returns_none_when_missing(tmp_path):
    assert read_fingerprint(tmp_path) is None


def test_read_fingerprint_returns_none_when_empty(tmp_path):
    (tmp_path / FINGERPRINT_FILENAME).write_text("", encoding="utf-8")
    assert read_fingerprint(tmp_path) is None


# ---------------------------------------------------------------------------
# Stage 2 - is_family_resumable
# ---------------------------------------------------------------------------

def _write_combo_csv(dir_path, family, n_rows):
    df = pd.DataFrame(
        {
            "strategy_name": [f"s{i}" for i in range(n_rows)],
            "profit_factor": [1.5] * n_rows,
            "oos_pf": [1.6] * n_rows,
            "total_trades": [80] * n_rows,
            "net_pnl": [1000.0] * n_rows,
        }
    )
    path = dir_path / f"{family}_filter_combination_sweep_results.csv"
    df.to_csv(path, index=False)
    return path


def _write_promoted_csv(dir_path, family, n_rows):
    df = pd.DataFrame(
        {
            "strategy_name": [f"p{i}" for i in range(n_rows)],
            "profit_factor": [1.5] * n_rows,
        }
    )
    path = dir_path / f"{family}_promoted_candidates.csv"
    df.to_csv(path, index=False)
    return path


def test_resumable_when_csvs_present_and_complete(tmp_path):
    family = "mean_reversion"
    _write_combo_csv(tmp_path, family, 1000)
    _write_promoted_csv(tmp_path, family, 5)

    check = is_family_resumable(tmp_path, family, expected_n_combos=1000)
    assert check.resumable, check.reason
    assert check.combo_csv is not None
    assert check.promoted_csv is not None


def test_not_resumable_when_combo_csv_missing(tmp_path):
    family = "trend"
    _write_promoted_csv(tmp_path, family, 5)

    check = is_family_resumable(tmp_path, family, expected_n_combos=500)
    assert not check.resumable
    assert "filter_combination_sweep_results" in check.reason


def test_not_resumable_when_promoted_csv_missing(tmp_path):
    family = "breakout"
    _write_combo_csv(tmp_path, family, 500)

    check = is_family_resumable(tmp_path, family, expected_n_combos=500)
    assert not check.resumable
    assert "promoted_candidates" in check.reason


def test_not_resumable_when_combo_csv_too_short(tmp_path):
    """Truncated CSV (only 50% of expected rows) must be rejected."""
    family = "mean_reversion"
    _write_combo_csv(tmp_path, family, 500)  # only 50% of expected
    _write_promoted_csv(tmp_path, family, 1)

    check = is_family_resumable(tmp_path, family, expected_n_combos=1000)
    assert not check.resumable
    assert "rows" in check.reason


def test_resumable_with_5pct_dedup_loss(tmp_path):
    """Lightweight dedup may shrink CSV by ~5% - should still resume."""
    family = "mean_reversion"
    _write_combo_csv(tmp_path, family, 960)  # 96% of 1000
    _write_promoted_csv(tmp_path, family, 5)

    check = is_family_resumable(tmp_path, family, expected_n_combos=1000)
    assert check.resumable, check.reason


def test_resumable_with_refinement_csv_present(tmp_path):
    family = "mean_reversion"
    _write_combo_csv(tmp_path, family, 1000)
    _write_promoted_csv(tmp_path, family, 5)
    refinement_path = tmp_path / f"{family}_top_combo_refinement_results_narrow.csv"
    pd.DataFrame({"strategy_name": ["r1", "r2"], "net_pnl": [100, 200]}).to_csv(
        refinement_path, index=False
    )

    check = is_family_resumable(tmp_path, family, expected_n_combos=1000)
    assert check.resumable
    assert check.refinement_csv is not None


def test_load_resumed_family_returns_three_dfs(tmp_path):
    family = "mean_reversion"
    _write_combo_csv(tmp_path, family, 1000)
    _write_promoted_csv(tmp_path, family, 5)
    refinement_path = tmp_path / f"{family}_top_combo_refinement_results_narrow.csv"
    pd.DataFrame({"strategy_name": ["r1"], "net_pnl": [100.0]}).to_csv(
        refinement_path, index=False
    )

    check = is_family_resumable(tmp_path, family, expected_n_combos=1000)
    combo_df, promoted_df, refinement_df = load_resumed_family(check)
    assert len(combo_df) == 1000
    assert len(promoted_df) == 5
    assert refinement_df is not None and len(refinement_df) == 1


def test_load_resumed_family_returns_none_for_missing_refinement(tmp_path):
    family = "trend"
    _write_combo_csv(tmp_path, family, 500)
    _write_promoted_csv(tmp_path, family, 3)

    check = is_family_resumable(tmp_path, family, expected_n_combos=500)
    combo_df, promoted_df, refinement_df = load_resumed_family(check)
    assert refinement_df is None


def test_load_resumed_family_raises_if_check_not_resumable():
    check = ResumeCheck(resumable=False, reason="missing csv")
    try:
        load_resumed_family(check)
    except ValueError as exc:
        assert "not resumable" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_synthetic_sanity_check_shape():
    sanity = make_synthetic_sanity_check()
    assert sanity["passed"] is True
    assert sanity["resumed_from_disk"] is True
    # build_family_summary_row consumes these keys
    assert "trades" in sanity
    assert "net_pnl" in sanity
    assert "profit_factor" in sanity
