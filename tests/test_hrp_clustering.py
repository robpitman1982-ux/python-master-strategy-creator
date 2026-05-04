"""Tests for modules/hrp_clustering.py - Sprint 96."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.hrp_clustering import (
    cluster_diversity_score,
    cluster_size_violations,
    cluster_strategies,
    cluster_summary,
)


def _make_corr(n: int, base_corr: float = 0.0, seed: int = 0) -> pd.DataFrame:
    """Build an n×n symmetric correlation matrix with diagonal=1.

    Off-diagonal values are `base_corr` plus small noise so we don't get
    perfectly degenerate clusters in tests.
    """
    rng = np.random.default_rng(seed)
    M = np.full((n, n), base_corr)
    np.fill_diagonal(M, 1.0)
    # Add tiny symmetric noise
    noise = rng.normal(0, 0.01, (n, n))
    noise = 0.5 * (noise + noise.T)
    np.fill_diagonal(noise, 0.0)
    M = np.clip(M + noise, -1.0, 1.0)
    labels = [f"s{i}" for i in range(n)]
    return pd.DataFrame(M, index=labels, columns=labels)


def test_empty_corr_returns_empty_dict():
    df = pd.DataFrame()
    assert cluster_strategies(df) == {}


def test_none_corr_returns_empty_dict():
    assert cluster_strategies(None) == {}


def test_single_strategy_returns_one_cluster():
    df = pd.DataFrame([[1.0]], index=["a"], columns=["a"])
    result = cluster_strategies(df)
    assert result == {"a": 1}


def test_two_uncorrelated_strategies_get_distinct_clusters():
    df = pd.DataFrame(
        [[1.0, 0.0], [0.0, 1.0]],
        index=["a", "b"],
        columns=["a", "b"],
    )
    result = cluster_strategies(df, cut_threshold=0.5)
    assert result["a"] != result["b"]


def test_two_perfectly_correlated_strategies_same_cluster():
    df = pd.DataFrame(
        [[1.0, 0.99], [0.99, 1.0]],
        index=["a", "b"],
        columns=["a", "b"],
    )
    result = cluster_strategies(df, cut_threshold=0.5)
    assert result["a"] == result["b"]


def test_two_anticorrelated_strategies_distinct_clusters():
    """Anti-correlation has distance ~1.0 (max), so clusters are distinct
    regardless of any reasonable cut threshold."""
    df = pd.DataFrame(
        [[1.0, -1.0], [-1.0, 1.0]],
        index=["a", "b"],
        columns=["a", "b"],
    )
    result = cluster_strategies(df, cut_threshold=0.5)
    assert result["a"] != result["b"]


def test_clustering_is_deterministic():
    df = _make_corr(n=8, base_corr=0.3, seed=42)
    r1 = cluster_strategies(df)
    r2 = cluster_strategies(df)
    assert r1 == r2


def test_clustering_groups_correlated_blocks():
    """Construct a 6-strategy matrix with two clear blocks of 3 each (high
    intra-block, low inter-block). Expect exactly 2 clusters."""
    block_a = ["a1", "a2", "a3"]
    block_b = ["b1", "b2", "b3"]
    labels = block_a + block_b

    M = np.full((6, 6), 0.05)  # weak inter-block
    for i, j in [(0, 1), (1, 2), (0, 2), (3, 4), (4, 5), (3, 5)]:
        M[i, j] = M[j, i] = 0.85  # strong intra-block
    np.fill_diagonal(M, 1.0)
    df = pd.DataFrame(M, index=labels, columns=labels)

    result = cluster_strategies(df, cut_threshold=0.5)
    # All members of block_a should share cluster
    assert result["a1"] == result["a2"] == result["a3"]
    assert result["b1"] == result["b2"] == result["b3"]
    # Blocks should have different clusters
    assert result["a1"] != result["b1"]


def test_cluster_diversity_score_max_when_all_distinct():
    cluster_map = {"a": 1, "b": 2, "c": 3}
    assert cluster_diversity_score(["a", "b", "c"], cluster_map) == 1.0


def test_cluster_diversity_score_min_when_all_same_cluster():
    cluster_map = {"a": 1, "b": 1, "c": 1}
    score = cluster_diversity_score(["a", "b", "c"], cluster_map)
    assert score == pytest.approx(1 / 3)


def test_cluster_diversity_score_empty_labels():
    assert cluster_diversity_score([], {"a": 1}) == 0.0


def test_cluster_diversity_score_unmapped_label_uses_sentinel():
    """Labels not in cluster_map collapse to a single sentinel cluster id."""
    cluster_map = {"a": 1, "b": 2}
    # 'c' and 'd' both unmapped -> both get sentinel -1, count as one cluster
    score = cluster_diversity_score(["a", "b", "c", "d"], cluster_map)
    assert score == 0.75  # 3 distinct clusters out of 4 labels


def test_cluster_size_violations_returns_zero_when_under_cap():
    cluster_map = {"a": 1, "b": 1, "c": 2, "d": 3}
    assert cluster_size_violations(["a", "b", "c", "d"], cluster_map, max_per_cluster=2) == 0


def test_cluster_size_violations_counts_overflow():
    cluster_map = {"a": 1, "b": 1, "c": 1, "d": 2}
    # Cluster 1 has 3 members, max=2 -> 1 violation
    assert cluster_size_violations(["a", "b", "c", "d"], cluster_map, max_per_cluster=2) == 1


def test_cluster_size_violations_zero_cap_disables_check():
    cluster_map = {"a": 1, "b": 1, "c": 1}
    assert cluster_size_violations(["a", "b", "c"], cluster_map, max_per_cluster=0) == 0


def test_cluster_summary_counts_per_cluster():
    cluster_map = {"a": 1, "b": 1, "c": 2, "d": 3, "e": 3}
    summary = cluster_summary(cluster_map)
    assert summary == {"1": 2, "2": 1, "3": 2}


def test_cluster_summary_empty():
    assert cluster_summary({}) == {}


def test_cluster_strategies_handles_floating_point_asymmetry():
    """Real correlation matrices can have tiny asymmetric noise from
    accumulated floating-point operations. Function should symmetrise and
    not crash on squareform's symmetry check."""
    rng = np.random.default_rng(7)
    M = np.full((4, 4), 0.4)
    np.fill_diagonal(M, 1.0)
    M[0, 1] = 0.4 + 1e-12  # tiny asymmetry
    df = pd.DataFrame(M, index=["a", "b", "c", "d"], columns=["a", "b", "c", "d"])
    result = cluster_strategies(df, cut_threshold=0.5)
    assert len(result) == 4
