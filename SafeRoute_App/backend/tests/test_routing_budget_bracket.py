"""Alpha bütçe ikili arama testleri."""

import numpy as np
from scipy.sparse import csr_matrix

from routing_budget_bracket import bracket_alpha_candidates


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


def test_bracket_alpha_finds_mid_budget_path():
    # S=0, E=1, A=2: S->A->E (120), S->E (100)
    src = np.array([0, 0, 2], dtype=np.int32)
    dst = np.array([1, 2, 1], dtype=np.int32)
    edge_length = np.array([100.0, 60.0, 60.0], dtype=np.float64)
    edge_risk = np.array([0.5, 0.1, 0.1], dtype=np.float64)
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

    def candidate_from_path(path_nodes, alpha, edge_costs=None):
        from routing_profiles import RouteCandidate

        sig = tuple(str(n) for n in path_nodes)
        dist = 100.0 if sig == ("0", "1") else 120.0
        risk = 0.5 if sig == ("0", "1") else 0.1
        return RouteCandidate(
            coordinates=[[0.0, 0.0], [1.0, 1.0]],
            path_signature=sig,
            distance_m=dist,
            safety_score=(1.0 - risk) * 100.0,
            route_risk=risk,
            risk_coverage=100.0,
            alpha=float(alpha),
        )

    candidates = bracket_alpha_candidates(
        start_idx=0,
        end_idx=1,
        shortest_distance_m=100.0,
        edge_length=edge_length,
        edge_risk=edge_risk,
        red_threshold=0.6,
        red_penalty=6.0,
        target_detour_pcts=(25.0,),
        build_csr_pair=build_csr,
        path_for_matrices=_toy_path_finder,
        candidate_from_path=candidate_from_path,
        max_steps=8,
    )

    assert len(candidates) >= 1
    assert any(c.path_signature == ("0", "2", "1") for c in candidates)
