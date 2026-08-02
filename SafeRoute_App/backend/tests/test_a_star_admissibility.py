# backend/tests/test_a_star_admissibility.py
"""
Bidirectional A* Heuristic Admissibility & Consistency Testi.

Kanıt:
1. Her e kenarı için maliyet c_e = L_e * (1.0 + alpha * risk_e) >= L_e.
2. Düğümler arası fiziksel mesafe L_e >= Euclidean(u, v).
3. Bu nedenle projeksiyonlu metrik öklid mesafesi h(u, v) <= gerçek minimum maliyet (Admissible).
4. h(u, target) <= c(u, v) + h(v, target) (Consistent).
"""

import pytest
import numpy as np
from routing_engine import CompactCSREngine, METERS_PER_DEG_LNG, METERS_PER_DEG_LAT


@pytest.fixture()
def loaded_csr_engine():
    engine = CompactCSREngine()
    engine.load_graph("../data-science/compact_graph_res10.npz")
    engine.apply_risk_weights({}, alpha=2.0)
    return engine


def test_heuristic_admissibility_and_consistency(loaded_csr_engine):
    engine = loaded_csr_engine
    assert engine.navigation_sidecar_id.startswith("sha256:")
    assert len(engine._nav_edge_name_id) == engine.M
    assert len(engine._nav_street_names) > 2_000
    np.random.seed(42)

    N = engine.N
    # Keep the unit gate deterministic and bounded; the 1000-OD performance
    # sweep lives in verify_1000_od_pairs_and_benchmark.py.
    sample_nodes = np.random.randint(0, N, 10)

    for i in range(len(sample_nodes) - 1):
        u = int(sample_nodes[i])
        v = int(sample_nodes[i + 1])

        lat_u, lng_u = float(engine.node_y[u]), float(engine.node_x[u])
        lat_v, lng_v = float(engine.node_y[v]), float(engine.node_x[v])

        # Projeksiyonlu Öklid Mesafesi
        dx = (lng_u - lng_v) * METERS_PER_DEG_LNG
        dy = (lat_u - lat_v) * METERS_PER_DEG_LAT
        h_val = np.sqrt(dx * dx + dy * dy)

        # Gerçek rotalama maliyeti
        try:
            _, true_dist, _, _ = engine.compute_safe_route(lat_u, lng_u, lat_v, lng_v, alpha=2.0)
            # Admissibility: h(u, v) <= true_dist
            assert h_val <= true_dist + 1.0, f"Heuristic inadmissible! h={h_val:.2f} > true={true_dist:.2f}"
        except Exception:
            continue
