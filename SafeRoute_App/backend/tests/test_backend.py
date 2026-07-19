# backend/tests/test_backend.py
"""
SafeRoute backend dogrulama testleri (DB gerektirmez).

Calistirma (backend/ klasorunden):
    python -m pytest tests/ -v

Kapsam:
  1. routing: guvenli rota riskli sokaktan kacinir, en kisa rota kacinmaz
  2. API kontratlari: /route, /heatmap, /report mobil semalarla birebir
  3. Chicago disi istek -> HTTP 400
  4. LLM graceful fallback (live modda anahtar yokken cokmez)
"""
import sys
import types
import asyncio
from pathlib import Path

import networkx as nx
import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import routing  # noqa: E402
import crud  # noqa: E402
import main  # noqa: E402
import llm_service  # noqa: E402
from config import settings  # noqa: E402


# ---------------------------------------------------------------------------
# Sentetik test grafi: Chicago Loop icinde 4 dugum, 2 alternatif yol
#
#   S ──(kisa ama RISKLI, 100m)── E
#   S ──(A uzerinden uzun ama GUVENLI, 2x100m)── E
# ---------------------------------------------------------------------------
def build_synthetic_graph():
    g = nx.MultiDiGraph()
    g.graph["crs"] = "epsg:4326"

    # Chicago Loop civari - dugumler arasi ~2km, boylece her kenarin orta
    # noktasi FARKLI bir H3 (res 9) hucresine duser ve risk izole atanabilir.
    nodes = {
        "S": (-87.6400, 41.8700),
        "E": (-87.6000, 41.8700),
        "A": (-87.6200, 41.9000),
    }
    for name, (x, y) in nodes.items():
        g.add_node(name, x=x, y=y)

    def add_bidirectional(u, v, length):
        g.add_edge(u, v, 0, length=length)
        g.add_edge(v, u, 0, length=length)

    add_bidirectional("S", "E", 100.0)   # dogrudan (riskli olacak)
    add_bidirectional("S", "A", 100.0)   # dolambacli guvenli yol
    add_bidirectional("A", "E", 100.0)

    return g


class FakePoint:
    def __init__(self, h3_index, lat, lng, total_risk):
        self.h3_index = h3_index
        self.lat = lat
        self.lng = lng
        self.total_risk = total_risk


@pytest.fixture()
def risky_graph(monkeypatch):
    """Dogrudan S-E kenarinin H3 hucresine yuksek risk atanmis graf."""
    g = build_synthetic_graph()

    import h3 as h3lib
    # S-E kenarinin orta noktasi
    mid_lat, mid_lng = 41.8700, -87.6200
    risky_cell = h3lib.latlng_to_cell(mid_lat, mid_lng, routing.H3_RESOLUTION)

    # S-A ve A-E orta noktalarinin hucreleri risky_cell ile ayni cikarsa
    # test anlamsizlasir; resolution 9'da bu koordinatlarda farklilar.
    risk_lookup = {risky_cell: 90.0}
    h3_to_edges = routing.apply_risk_weights(g, risk_lookup)

    # nearest_nodes'i sentetik graf icin basitlestir (scipy bagimliligindan bagimsiz)
    def fake_nearest(graph, X, Y):
        best, best_d = None, float("inf")
        for n, d in graph.nodes(data=True):
            dist = (d["x"] - X) ** 2 + (d["y"] - Y) ** 2
            if dist < best_d:
                best, best_d = n, dist
        return best

    monkeypatch.setattr(routing.ox, "nearest_nodes", fake_nearest)
    return g, h3_to_edges, risky_cell


def test_safe_route_avoids_risky_edge(risky_graph):
    g, _, _ = risky_graph
    coords, dist, safety = routing.compute_safe_route(g, 41.8700, -87.6400, 41.8700, -87.6000)
    # Guvenli rota A uzerinden gitmeli -> 200m
    assert dist == pytest.approx(200.0)
    assert len(coords) == 3  # S -> A -> E
    assert 0 <= safety <= 100


def test_shortest_route_ignores_risk(risky_graph):
    g, _, _ = risky_graph
    coords, dist = routing.compute_shortest_route(g, 41.8700, -87.6400, 41.8700, -87.6000)
    # En kisa rota risk umursamaz -> dogrudan 100m
    assert dist == pytest.approx(100.0)
    assert len(coords) == 2  # S -> E


def test_o1_risk_update_changes_route(risky_graph):
    """Ihbar sonrasi set_absolute_risk_for_h3 rotayi degistirebilmeli."""
    g, h3_to_edges, risky_cell = risky_graph
    # Riski sifirla -> artik dogrudan yol tercih edilmeli
    routing.set_absolute_risk_for_h3(g, h3_to_edges, risky_cell, 0.0)
    coords, dist, _ = routing.compute_safe_route(g, 41.8700, -87.6400, 41.8700, -87.6000)
    assert dist == pytest.approx(100.0)


def test_chicago_bounds():
    assert routing.is_within_chicago(41.8781, -87.6298)      # Loop
    assert not routing.is_within_chicago(41.0082, 28.9784)   # Istanbul
    assert not routing.is_within_chicago(40.7128, -74.0060)  # New York


# ---------------------------------------------------------------------------
# API kontrat testleri (TestClient, DB ve lifespan stublanir)
# ---------------------------------------------------------------------------
@pytest.fixture()
def client(risky_graph, monkeypatch):
    g, h3_to_edges, _ = risky_graph
    main.app.state.graph = g
    main.app.state.h3_to_edges = h3_to_edges

    # DB bagimliligini stubla
    class FakeReport:
        id = 42

    async def fake_create_report(db, lat, lng, text):
        return FakeReport()

    async def fake_get_all(db):
        return [FakePoint("cell1", 41.88, -87.63, 65.0), FakePoint("cell2", 41.89, -87.64, 12.5)]

    monkeypatch.setattr(crud, "create_report", fake_create_report)
    monkeypatch.setattr(crud, "get_all_heatmap_points", fake_get_all)

    async def fake_bg(*args, **kwargs):
        return None

    monkeypatch.setattr(main, "process_report_background_task", fake_bg)

    async def fake_db():
        yield None

    main.app.dependency_overrides[main.get_db] = fake_db
    # NOT: context manager KULLANMIYORUZ -> lifespan (graf/DB yukleme) calismaz
    return TestClient(main.app)


def test_route_contract(client):
    body = {"start": [-87.6400, 41.8700], "end": [-87.6000, 41.8700], "hour": 21}
    resp = client.post("/api/v1/route", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Mobil kontrat alanlari
    assert set(data.keys()) == {"route", "distance_m", "duration_s", "risk_score", "shortest"}
    assert data["route"]["type"] == "LineString"
    assert isinstance(data["route"]["coordinates"][0], list)
    assert data["shortest"]["type"] == "LineString"
    # Guvenli rota 200m, en kisa 100m olmali
    assert data["distance_m"] == pytest.approx(200.0)
    assert len(data["shortest"]["coordinates"]) == 2
    # duration = distance / 1.2
    assert data["duration_s"] == pytest.approx(200.0 / 1.2, rel=1e-3)
    assert 0 <= data["risk_score"] <= 100


def test_route_outside_chicago_returns_400(client):
    # Istanbul koordinatlari -> HTTP 400 + aciklayici mesaj
    body = {"start": [28.9784, 41.0082], "end": [-87.6000, 41.8700]}
    resp = client.post("/api/v1/route", json=body)
    assert resp.status_code == 400
    assert "Chicago" in resp.json()["detail"]


def test_heatmap_contract_flat_array(client):
    resp = client.get("/api/v1/heatmap")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)  # wrapper object DEGIL
    assert set(data[0].keys()) == {"lat", "lng", "total_risk"}
    assert data[0]["total_risk"] == 65.0


def test_report_contract(client):
    body = {"text": "birisi beni takip ediyor", "lat": 41.88, "lng": -87.63}
    resp = client.post("/api/v1/report", json=body)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data == {"ok": True, "id": "42"}


def test_report_outside_chicago_returns_400(client):
    body = {"text": "test", "lat": 41.0082, "lng": 28.9784}
    resp = client.post("/api/v1/report", json=body)
    assert resp.status_code == 400


def test_webhook_endpoint_removed(client):
    """Sosyal medya webhook'u kapsam disi - endpoint aktif olmamali."""
    resp = client.post("/api/v1/webhook/social-risk", json={})
    assert resp.status_code in (404, 405)


# ---------------------------------------------------------------------------
# LLM servis testleri
# ---------------------------------------------------------------------------
def test_llm_mock_mode_scores():
    settings.llm_mode = "mock"
    assert asyncio.run(llm_service.analyze_report_risk_with_llm("silahlı saldırı var")) == 100.0
    assert asyncio.run(llm_service.analyze_report_risk_with_llm("kavga çıktı")) == 50.0
    assert asyncio.run(llm_service.analyze_report_risk_with_llm("sokak karanlık")) == 20.0
    assert asyncio.run(llm_service.analyze_report_risk_with_llm("sakin")) == 10.0


def test_llm_live_mode_graceful_fallback_without_key():
    """LIVE modda API anahtari yokken ASLA exception yukari cikmamali."""
    settings.llm_mode = "live"
    settings.llm_provider = "gemini"
    settings.gemini_api_key = ""
    try:
        score = asyncio.run(llm_service.analyze_report_risk_with_llm("taciz", 41.88, -87.63))
    finally:
        settings.llm_mode = "mock"
    assert 0.0 <= score <= 100.0
    assert score == 100.0  # kural tabanli fallback "taciz" -> 100
