# backend/tests/test_routing_engine.py
"""
BaseRoutingEngine, NetworkXEngine ve CompactCSREngine Birim Testleri.
"""

import pytest
import numpy as np
import networkx as nx
from routing_engine import NetworkXEngine, CompactCSREngine, get_routing_engine, BaseRoutingEngine


@pytest.fixture()
def sample_engines(monkeypatch):
    """
    Testler için hem NetworkXEngine hem de CompactCSREngine örneklerini hazırlar.
    """
    # 4 düğümlü sentetik graf
    g = nx.MultiDiGraph()
    g.graph["crs"] = "epsg:4326"

    # Chicago Loop koordinatları civarında
    g.add_node("S", x=-87.6400, y=41.8700)
    g.add_node("E", x=-87.6000, y=41.8700)
    g.add_node("A", x=-87.6200, y=41.9000)

    g.add_edge("S", "E", 0, length=100.0)
    g.add_edge("E", "S", 0, length=100.0)
    g.add_edge("S", "A", 0, length=100.0)
    g.add_edge("A", "S", 0, length=100.0)
    g.add_edge("A", "E", 0, length=100.0)
    g.add_edge("E", "A", 0, length=100.0)

    nx_engine = NetworkXEngine()
    nx_engine.graph = g
    nx_engine.h3_to_edges = {}

    # CompactCSREngine için el ile düğüm/kenar yapısı yükle
    csr_engine = CompactCSREngine()
    csr_engine.node_x = np.array([-87.6400, -87.6000, -87.6200], dtype=np.float32)  # S=0, E=1, A=2
    csr_engine.node_y = np.array([41.8700, 41.8700, 41.9000], dtype=np.float32)
    csr_engine.edge_src = np.array([0, 1, 0, 2, 2, 1], dtype=np.int32)
    csr_engine.edge_dst = np.array([1, 0, 2, 0, 1, 2], dtype=np.int32)
    csr_engine.edge_length = np.array([100.0, 100.0, 100.0, 100.0, 100.0, 100.0], dtype=np.float32)
    csr_engine.edge_risk = np.zeros(6, dtype=np.float32)

    from scipy.spatial import KDTree
    coords = np.column_stack((csr_engine.node_x, csr_engine.node_y))
    csr_engine.kdtree = KDTree(coords)
    csr_engine.N = 3
    csr_engine.M = 6
    csr_engine.csr_shortest = csr_engine.csr_matrix = None
    from scipy.sparse import csr_matrix
    csr_engine.csr_shortest = csr_matrix((csr_engine.edge_length, (csr_engine.edge_src, csr_engine.edge_dst)), shape=(3, 3))
    csr_engine.csr_safe = csr_engine.csr_shortest

    # Fake nearest nodes override for nx_engine
    def fake_nearest(graph, X, Y, return_dist=False, **kwargs):
        best, best_d = "S", float("inf")
        for n, d in graph.nodes(data=True):
            dist = (d["x"] - X) ** 2 + (d["y"] - Y) ** 2
            if dist < best_d:
                best, best_d = n, dist
        if return_dist:
            return best, 5.0
        return best

    import routing
    monkeypatch.setattr(routing.ox, "nearest_nodes", fake_nearest)

    return nx_engine, csr_engine


def test_base_routing_engine_conformance():
    assert issubclass(NetworkXEngine, BaseRoutingEngine)
    assert issubclass(CompactCSREngine, BaseRoutingEngine)


def test_nearest_node_lookup(sample_engines):
    nx_eng, csr_eng = sample_engines

    # S düğümüne yakın koordinat
    s_idx, s_dist = csr_eng.find_nearest_node(41.8700, -87.6400)
    assert s_idx == 0  # S
    assert s_dist < 50.0


def test_shortest_route_equivalence(sample_engines):
    nx_eng, csr_eng = sample_engines

    coords_nx, dist_nx, safety_nx, risk_nx, _ = nx_eng.compute_shortest_route(41.8700, -87.6400, 41.8700, -87.6000)
    coords_csr, dist_csr, safety_csr, risk_csr, _ = csr_eng.compute_shortest_route(41.8700, -87.6400, 41.8700, -87.6000)

    assert dist_nx == pytest.approx(dist_csr, rel=1e-3)
    assert safety_nx == pytest.approx(safety_csr, rel=1e-3)
    assert risk_nx == pytest.approx(risk_csr, rel=1e-3)
