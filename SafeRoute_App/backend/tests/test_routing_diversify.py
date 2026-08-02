"""Kenar cezalandırma ile rota çeşitlendirme testleri."""

import numpy as np
from scipy.sparse import csr_matrix

from routing_diversify import penalty_diversify_paths


def _toy_path_finder(
    start_idx: int,
    end_idx: int,
    matrix_f: csr_matrix,
    _matrix_b: csr_matrix | None,
) -> list[int]:
    from scipy.sparse.csgraph import dijkstra

    _dist, predecessors = dijkstra(
        csgraph=matrix_f,
        directed=True,
        indices=start_idx,
        return_predecessors=True,
    )
    path_nodes: list[int] = []
    curr = end_idx
    while curr != -9999 and curr != start_idx:
        path_nodes.append(int(curr))
        curr = int(predecessors[curr])
    if curr == start_idx:
        path_nodes.append(start_idx)
    path_nodes.reverse()
    if not path_nodes:
        raise ValueError("no path")
    return path_nodes


def test_penalty_diversify_finds_multiple_paths():
    # S=0, E=1, A=2: S->A->E (120), S->E (100)
    src = np.array([0, 0, 2], dtype=np.int32)
    dst = np.array([1, 2, 1], dtype=np.int32)
    costs = np.array([100.0, 60.0, 60.0], dtype=np.float64)
    n = 3

    def build_csr(edge_costs: np.ndarray) -> tuple[csr_matrix, None]:
        uv = src.astype(np.int64) * n + dst.astype(np.int64)
        order = np.argsort(edge_costs)
        sorted_keys = uv[order]
        sorted_src = src[order]
        sorted_dst = dst[order]
        sorted_costs = edge_costs[order]
        _, unique_indices = np.unique(sorted_keys, return_index=True)
        matrix = csr_matrix(
            (
                sorted_costs[unique_indices],
                (sorted_src[unique_indices], sorted_dst[unique_indices]),
            ),
            shape=(n, n),
        )
        return matrix, None

    paths = penalty_diversify_paths(
        start_idx=0,
        end_idx=1,
        base_costs=costs,
        edge_src=src,
        edge_dst=dst,
        build_csr=build_csr,
        path_finder=_toy_path_finder,
        max_iterations=4,
        penalty_factor=3.0,
    )

    signatures = {tuple(path) for path in paths}
    assert len(signatures) >= 2
    assert (0, 2, 1) in signatures
