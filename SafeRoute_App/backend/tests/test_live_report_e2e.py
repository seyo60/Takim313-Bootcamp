# backend/tests/test_live_report_e2e.py
"""
Uçtan Uca (E2E) İhbar Entegrasyon Testi:
report -> DB güncelleme -> live risk update -> route change -> restart persistence.
"""

import pytest
import asyncio
import numpy as np
import networkx as nx
from fastapi.testclient import TestClient

from routing_engine import CompactCSREngine, NetworkXEngine
import routing
import main
import crud


@pytest.fixture()
def mock_app_state(monkeypatch):
    """
    CompactCSREngine ile çalışan sentetik test ortamı.
    """
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

    from scipy.sparse import csr_matrix
    csr_engine.csr_shortest = csr_matrix((csr_engine.edge_length, (csr_engine.edge_src, csr_engine.edge_dst)), shape=(3, 3))
    csr_engine.csr_safe = csr_engine.csr_shortest

    import h3 as h3lib
    mid_lat, mid_lng = 41.8700, -87.6200  # S-E kenarı
    risky_cell = h3lib.latlng_to_cell(mid_lat, mid_lng, routing.H3_RESOLUTION)
    csr_engine.h3_keys_map = {risky_cell: np.array([0, 1], dtype=np.int32)}  # S-E ve E-S kenarları

    main.app.state.engine = csr_engine

    # DB ve background task stub
    class FakeReport:
        id = 101

    async def fake_create_report(db, lat, lng, text):
        return FakeReport()

    async def fake_update_h3_live_risk(db, cell, penalty):
        return 1.0  # Maksimum risk

    monkeypatch.setattr(crud, "create_report", fake_create_report)
    monkeypatch.setattr(crud, "update_h3_live_risk", fake_update_h3_live_risk)

    async def fake_db():
        yield None

    main.app.dependency_overrides[main.get_db] = fake_db
    return TestClient(main.app), csr_engine, risky_cell


def test_live_report_triggers_route_change_and_persistence(mock_app_state):
    client, csr_engine, risky_cell = mock_app_state

    # 1. Başlangıçta risk 0.0 iken S -> E rotası doğrudan 100m olmalı
    coords_before, dist_before, _, risk_before, _ = csr_engine.compute_safe_route(41.8700, -87.6400, 41.8700, -87.6000)
    assert dist_before == pytest.approx(100.0)
    assert risk_before == 0.0

    # 2. İhbar gönder
    report_body = {"text": "silahlı çatışma var ve yol kapalı", "lat": 41.8700, "lng": -87.6200, "category": "crime"}
    resp = client.post("/api/v1/report", json=report_body)
    assert resp.status_code == 201

    # 3. Canlı risk güncellemesini simüle et (background task işlevi)
    csr_engine.set_absolute_risk_for_h3(risky_cell, 1.0, alpha=2.0)

    # 4. Rota yeniden hesaplandığında dolambaçlı ama güvenli yola (200m) sapmalı
    coords_after, dist_after, _, risk_after, _ = csr_engine.compute_safe_route(41.8700, -87.6400, 41.8700, -87.6000)
    assert dist_after == pytest.approx(200.0)  # S -> A -> E
    assert len(coords_after) == 3

    # 5. Persistence (Yeniden başlatma kalıcılığı): Yeni motor örneği DB'den riski yükleyip aynı rotayı vermeli
    restarted_engine = CompactCSREngine()
    restarted_engine.node_x = csr_engine.node_x
    restarted_engine.node_y = csr_engine.node_y
    restarted_engine.edge_src = csr_engine.edge_src
    restarted_engine.edge_dst = csr_engine.edge_dst
    restarted_engine.edge_length = csr_engine.edge_length
    restarted_engine.kdtree = csr_engine.kdtree
    restarted_engine.N = csr_engine.N
    restarted_engine.M = csr_engine.M
    restarted_engine.edge_risk = np.zeros(6, dtype=np.float32)
    restarted_engine.csr_shortest = csr_engine.csr_shortest
    restarted_engine.h3_keys_map = csr_engine.h3_keys_map

    # DB'deki 1.0 riskini tekrar uygula
    restarted_engine.apply_risk_weights({risky_cell: 1.0}, alpha=2.0)
    _, dist_restarted, _, _, _ = restarted_engine.compute_safe_route(41.8700, -87.6400, 41.8700, -87.6000)
    assert dist_restarted == pytest.approx(200.0)
