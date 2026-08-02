"""Kenar cezalandırarak alternatif rota geometrileri üretir.

Alpha ızgarası bütçe bandında boşluk bıraktığında (Lagrange/dualite boşluğu),
fiziksel mesafe grafında kısa-yol aramasını tekrarlayıp kullanılan kenarlara
ceza uygulayarak farklı aday yollar keşfedilir.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
from scipy.sparse import csr_matrix

from routing_edge_lookup import EdgeIndexLookup


PathNodes = list[int]
PathFinder = Callable[
    [int, int, csr_matrix, csr_matrix | None],
    PathNodes,
]


def penalty_diversify_paths(
    *,
    start_idx: int,
    end_idx: int,
    base_costs: np.ndarray,
    edge_src: np.ndarray,
    edge_dst: np.ndarray,
    build_csr: Callable[[np.ndarray], tuple[csr_matrix, csr_matrix | None]],
    path_finder: PathFinder,
    max_iterations: int = 8,
    penalty_factor: float = 2.5,
    max_distance_m: float | None = None,
    physical_lengths: np.ndarray | None = None,
    edge_lookup: EdgeIndexLookup | None = None,
) -> list[PathNodes]:
    """Aynı maliyet fonksiyonunda kenar cezalandırarak benzersiz yollar üretir.

    ``edge_lookup`` verilmezse çağrı başına bir kez kurulur; motor kendi hazır
    kenar indeksini geçirerek bu maliyeti de ortadan kaldırır.
    """
    if max_iterations <= 0:
        return []

    costs = np.asarray(base_costs, dtype=np.float64).copy()
    if edge_lookup is None:
        edge_lookup = EdgeIndexLookup(
            node_count=int(max(int(edge_src.max()), int(edge_dst.max())) + 1)
            if edge_src.size
            else 1,
            edge_src=edge_src,
            edge_dst=edge_dst,
        )

    paths: list[PathNodes] = []
    seen: set[tuple[str, ...]] = set()

    for _ in range(max_iterations):
        matrix_f, matrix_b = build_csr(costs)
        try:
            path_nodes = path_finder(start_idx, end_idx, matrix_f, matrix_b)
        except ValueError:
            break

        signature = tuple(str(node) for node in path_nodes)
        if signature in seen:
            break
        seen.add(signature)
        paths.append(path_nodes)

        if max_distance_m is not None and physical_lengths is not None:
            path_distance = _approximate_path_distance(
                path_nodes,
                physical_lengths,
                edge_lookup,
            )
            if path_distance > max_distance_m:
                break

        penalize_path_edges(
            costs,
            path_nodes,
            edge_src,
            edge_dst,
            penalty_factor=penalty_factor,
            edge_lookup=edge_lookup,
        )

    return paths


def penalize_path_edges(
    costs: np.ndarray,
    path_nodes: Sequence[int],
    edge_src: np.ndarray,
    edge_dst: np.ndarray,
    *,
    penalty_factor: float,
    edge_lookup: EdgeIndexLookup | None = None,
) -> None:
    """Yolda kullanılan tüm kenarların maliyetini çarpan ile artırır."""
    if len(path_nodes) < 2:
        return
    if edge_lookup is None:
        edge_lookup = EdgeIndexLookup(
            node_count=int(max(int(edge_src.max()), int(edge_dst.max())) + 1),
            edge_src=edge_src,
            edge_dst=edge_dst,
        )
    indices = edge_lookup.all_edge_indices(path_nodes)
    if indices.size:
        costs[indices] *= penalty_factor


def _approximate_path_distance(
    path_nodes: Sequence[int],
    costs: np.ndarray,
    edge_lookup: EdgeIndexLookup,
) -> float:
    indices = edge_lookup.min_cost_edge_indices(path_nodes, costs)
    if indices.size == 0:
        return 0.0
    return float(np.asarray(costs)[indices].sum())
