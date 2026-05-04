"""Hierarchical Risk Parity clustering for the portfolio selector.

Sprint 96. López de Prado's HRP (2016) builds a hierarchical clustering of
strategies from the correlation distance matrix. The dendrogram cut yields
natural cluster groups: strategies in the same cluster trade similar
patterns; strategies in different clusters are structurally distinct.

For Rob's selector, this gives:
1. A replacement for `correlation_dedup`'s greedy connected-components
   approach with hierarchical-clustering nuance (multiple strategies per
   cluster are kept if they're above the cluster median).
2. A `cluster_diversity_score` that augments `sweep_combinations` composite
   scoring — combinations spanning more clusters score higher.

Default OFF (config flag `pipeline.portfolio_selector.use_hrp_clustering`).
Activates the feature; existing threshold-based gates remain available as
the fallback.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform


def cluster_strategies(
    corr_matrix: pd.DataFrame,
    cut_threshold: float = 0.5,
    linkage_method: str = "average",
) -> dict[str, int]:
    """HRP clustering of strategies by correlation distance.

    Args:
        corr_matrix: square pairwise correlation matrix indexed by strategy
            label. Values in [-1, 1].
        cut_threshold: distance at which to cut the dendrogram. With the
            HRP distance D = sqrt(0.5 * (1 - C)), the metric range is
            [0, 1] where 0 = perfectly positively correlated, 1 = perfectly
            anti-correlated. A cut of 0.5 yields tighter clusters than 0.7;
            lower cut = more clusters.
        linkage_method: passed to `scipy.cluster.hierarchy.linkage`. HRP
            standard is `"average"` (UPGMA).

    Returns:
        dict mapping strategy label -> cluster_id (1-indexed integers).
        Empty dict if `corr_matrix` is None or empty.
    """
    if corr_matrix is None or corr_matrix.empty:
        return {}
    if len(corr_matrix) == 1:
        return {corr_matrix.columns[0]: 1}

    labels = list(corr_matrix.columns)
    n = len(labels)

    # Symmetrise (averaging the upper + lower triangle smooths out floating-
    # point noise that can fail squareform's symmetry check).
    C = corr_matrix.reindex(index=labels, columns=labels).values.astype(float)
    C = 0.5 * (C + C.T)
    np.fill_diagonal(C, 1.0)

    # HRP distance: D[i,j] in [0, 1] (perfectly positive corr -> 0; perfectly
    # negative -> 1). Clip protects against minor floating-point excursions.
    D = np.sqrt(np.clip(0.5 * (1.0 - C), 0.0, 1.0))

    # Squareform expects condensed (upper-triangle, no diagonal) distance.
    condensed = squareform(D, checks=False)
    Z = linkage(condensed, method=linkage_method)
    cluster_ids = fcluster(Z, t=cut_threshold, criterion="distance")

    return {labels[i]: int(cluster_ids[i]) for i in range(n)}


def cluster_diversity_score(
    labels: Iterable[str],
    cluster_map: dict[str, int],
) -> float:
    """Fraction of distinct clusters represented by `labels`.

    Args:
        labels: iterable of strategy labels (the portfolio's members).
        cluster_map: output of `cluster_strategies`.

    Returns:
        Float in [0, 1]. 1.0 = every strategy in its own cluster (max
        diversity). 0.0 if labels is empty. Labels missing from
        cluster_map are assigned a sentinel cluster id of -1, so multiple
        unmapped labels collapse to the same diversity bucket.
    """
    label_list = list(labels)
    if not label_list:
        return 0.0
    cluster_ids = [cluster_map.get(label, -1) for label in label_list]
    return len(set(cluster_ids)) / len(label_list)


def cluster_size_violations(
    labels: Iterable[str],
    cluster_map: dict[str, int],
    max_per_cluster: int,
) -> int:
    """Count clusters in `labels` that exceed `max_per_cluster`.

    Returns 0 if no violations. Used by `sweep_combinations` to reject
    combinations that pile too many strategies into a single cluster.
    """
    if max_per_cluster <= 0:
        return 0
    counts: dict[int, int] = {}
    for label in labels:
        cid = cluster_map.get(label, -1)
        counts[cid] = counts.get(cid, 0) + 1
    return sum(1 for v in counts.values() if v > max_per_cluster)


def cluster_summary(cluster_map: dict[str, int]) -> dict[str, int]:
    """Compact summary: cluster_id -> count of strategies."""
    summary: dict[int, int] = {}
    for cid in cluster_map.values():
        summary[cid] = summary.get(cid, 0) + 1
    return {str(k): v for k, v in sorted(summary.items())}
