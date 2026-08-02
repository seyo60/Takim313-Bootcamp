"""Bütçe elipsi alt graf kırpma testleri."""

import numpy as np

from routing_subgraph import EllipseSubgraph, build_budget_subgraph


def _toy_graph():
    """S=0, E=1 yakın; A=2 arada; F=3 çok uzakta (elips dışı olmalı)."""
    node_x = np.array([-87.6400, -87.6300, -87.6350, -87.9000], dtype=np.float32)
    node_y = np.array([41.8700, 41.8700, 41.8750, 42.2000], dtype=np.float32)
    edge_src = np.array([0, 1, 0, 2, 2, 1, 0, 3], dtype=np.int32)
    edge_dst = np.array([1, 0, 2, 0, 1, 2, 3, 0], dtype=np.int32)
    return node_x, node_y, edge_src, edge_dst


def test_far_node_is_pruned_but_route_nodes_survive():
    node_x, node_y, edge_src, edge_dst = _toy_graph()
    subgraph = EllipseSubgraph(
        node_x=node_x,
        node_y=node_y,
        edge_src=edge_src,
        edge_dst=edge_dst,
        start_idx=0,
        end_idx=1,
        max_distance_m=2000.0,
        margin=1.10,
    )

    assert subgraph.node_count == 3
    assert subgraph.total_nodes == 4
    # Uzak düğüme bağlı kenarlar da atılmalı.
    assert subgraph.edge_count == 6


def test_path_finder_returns_full_graph_indices():
    node_x, node_y, edge_src, edge_dst = _toy_graph()
    subgraph = EllipseSubgraph(
        node_x=node_x,
        node_y=node_y,
        edge_src=edge_src,
        edge_dst=edge_dst,
        start_idx=0,
        end_idx=1,
        max_distance_m=2000.0,
    )

    # 0->1 doğrudan pahalı, 0->2->1 ucuz olacak şekilde maliyet ver.
    costs = np.array([100.0, 100.0, 10.0, 10.0, 10.0, 10.0, 5.0, 5.0])
    matrix_f, matrix_b = subgraph.build_csr(costs)
    assert matrix_b is None

    path = subgraph.path_finder(0, 1, matrix_f)
    assert path[0] == 0 and path[-1] == 1
    assert path == [0, 2, 1]


def test_start_and_end_always_kept_even_with_tiny_budget():
    node_x, node_y, edge_src, edge_dst = _toy_graph()
    subgraph = EllipseSubgraph(
        node_x=node_x,
        node_y=node_y,
        edge_src=edge_src,
        edge_dst=edge_dst,
        start_idx=0,
        end_idx=1,
        max_distance_m=1.0,
    )
    assert subgraph.node_count >= 2


def test_build_budget_subgraph_returns_none_when_pruning_is_useless():
    node_x, node_y, edge_src, edge_dst = _toy_graph()
    # Çok geniş bütçe -> tüm düğümler içeride -> kırpma anlamsız.
    result = build_budget_subgraph(
        node_x=node_x,
        node_y=node_y,
        edge_src=edge_src,
        edge_dst=edge_dst,
        start_idx=0,
        end_idx=1,
        max_distance_m=500_000.0,
        min_nodes=1,
    )
    assert result is None


def test_build_budget_subgraph_rejects_non_positive_budget():
    node_x, node_y, edge_src, edge_dst = _toy_graph()
    assert (
        build_budget_subgraph(
            node_x=node_x,
            node_y=node_y,
            edge_src=edge_src,
            edge_dst=edge_dst,
            start_idx=0,
            end_idx=1,
            max_distance_m=0.0,
        )
        is None
    )
