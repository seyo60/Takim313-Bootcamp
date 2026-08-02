# backend/tests/test_backend.py
"""
SafeRoute backend doğrulama testleri (DB gerektirmez).

Çalıştırma (backend/ klasöründen):
    python -m pytest tests/ -v
"""
import sys
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


def build_synthetic_graph():
    g = nx.MultiDiGraph()
    g.graph["crs"] = "epsg:4326"

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

    add_bidirectional("S", "E", 100.0)   # doğrudan (riskli olacak)
    add_bidirectional("S", "A", 100.0)   # dolambaçlı güvenli yol
    add_bidirectional("A", "E", 100.0)

    return g


class FakePoint:
    def __init__(self, h3_index, lat, lng, total_risk):
        self.h3_index = h3_index
        self.lat = lat
        self.lng = lng
        self.total_risk = total_risk
        self.risk_crime = total_risk
        self.risk_lighting = 0.0
        self.risk_live = 0.0


def is_within_chicago(lat: float, lng: float) -> bool:
    b = routing.CHICAGO_BOUNDS
    return b["min_lat"] <= lat <= b["max_lat"] and b["min_lng"] <= lng <= b["max_lng"]


@pytest.fixture()
def risky_graph(monkeypatch):
    """Doğrudan S-E kenarının H3 hücresine yüksek risk atanmış graf."""
    g = build_synthetic_graph()

    import h3 as h3lib
    mid_lat, mid_lng = 41.8700, -87.6200
    risky_cell = h3lib.latlng_to_cell(mid_lat, mid_lng, routing.H3_RESOLUTION)

    risk_lookup = {risky_cell: 1.0}
    h3_to_edges = routing.build_h3_spatial_index(g)
    routing.update_graph_risks(g, risk_lookup, h3_to_edges)

    def fake_nearest(graph, X, Y, return_dist=False, **kwargs):
        best, best_d = None, float("inf")
        for n, d in graph.nodes(data=True):
            dist = (d["x"] - X) ** 2 + (d["y"] - Y) ** 2
            if dist < best_d:
                best, best_d = n, dist
        if return_dist:
            return best, 10.0
        return best

    monkeypatch.setattr(routing.ox, "nearest_nodes", fake_nearest)
    return g, h3_to_edges, risky_cell


def test_safe_route_avoids_risky_edge(risky_graph):
    g, _, _ = risky_graph
    coords, dist, safety, risk = routing.compute_safe_route(g, 41.8700, -87.6400, 41.8700, -87.6000)
    assert dist == pytest.approx(200.0)
    assert len(coords) == 3
    assert 0 <= safety <= 100


def test_shortest_route_ignores_risk(risky_graph):
    g, _, _ = risky_graph
    coords, dist, safety, risk = routing.compute_shortest_route(g, 41.8700, -87.6400, 41.8700, -87.6000)
    assert dist == pytest.approx(100.0)
    assert len(coords) == 2


def test_o1_risk_update_changes_route(risky_graph):
    g, h3_to_edges, risky_cell = risky_graph
    direct_edge = ("S", "E", 0)
    direct_cells = [cell for cell, edges in h3_to_edges.items() if direct_edge in edges]
    assert direct_cells
    for cell in direct_cells:
        routing.set_absolute_risk_for_h3(g, h3_to_edges, cell, 0.0)
    coords, dist, safety, risk = routing.compute_safe_route(g, 41.8700, -87.6400, 41.8700, -87.6000)
    assert dist == pytest.approx(100.0)


def test_chicago_bounds():
    assert is_within_chicago(41.8781, -87.6298)      # Loop
    assert not is_within_chicago(41.0082, 28.9784)   # Istanbul
    assert not is_within_chicago(40.7128, -74.0060)  # New York


def test_snap_distance_exceeded(risky_graph, monkeypatch):
    g, _, _ = risky_graph

    def fake_far_nearest(graph, X, Y, return_dist=False, **kwargs):
        if return_dist:
            return "S", 300.0
        return "S"

    monkeypatch.setattr(routing.ox, "nearest_nodes", fake_far_nearest)
    with pytest.raises(ValueError, match="çok uzak"):
        routing.compute_safe_route(g, 41.8700, -87.6400, 41.8700, -87.6000)


@pytest.fixture()
def client(risky_graph, monkeypatch):
    g, h3_to_edges, _ = risky_graph
    from routing_engine import NetworkXEngine
    nx_eng = NetworkXEngine()
    nx_eng.graph = g
    nx_eng.h3_to_edges = h3_to_edges
    main.app.state.engine = nx_eng
    main.app.state.graph = g
    main.app.state.h3_to_edges = h3_to_edges

    class FakeReport:
        id = 42
        uuid_id = "42"
        tracking_token = "tok_42"
        status = "pending"

    async def fake_create_report(db, lat, lng, text, **kwargs):
        return FakeReport()

    async def fake_get_all(db, h3_resolution=None):
        return [FakePoint("cell1", 41.88, -87.63, 0.65), FakePoint("cell2", 41.89, -87.64, 0.125)]

    async def fake_etl_runs(db):
        return {"risk_snapshot_at": "2026-07-27T00:00:00Z", "crime_data_updated_at": None, "lighting_data_updated_at": None}

    async def fake_clustering(db, report):
        """Olay kümeleme ayrı testlerde doğrulanır; sözleşme testinde izole edilir."""

        class FakeEvent:
            uuid_id = "event-42"
            status = "pending"
            validation_score = 0.42
            unique_reporter_count = 1

        return FakeEvent()

    monkeypatch.setattr(crud, "create_report", fake_create_report)
    monkeypatch.setattr(crud, "process_report_and_event_clustering", fake_clustering)
    monkeypatch.setattr(crud, "get_all_heatmap_points", fake_get_all)
    monkeypatch.setattr(crud, "get_latest_etl_runs", fake_etl_runs)

    async def fake_bg(*args, **kwargs):
        return None

    monkeypatch.setattr(main, "process_report_background_task", fake_bg)

    async def fake_db():
        yield None

    async def fake_required_user():
        from uuid import UUID
        from auth import AuthenticatedUser

        return AuthenticatedUser(
            user_id=UUID("11111111-1111-1111-1111-111111111111"),
            role="authenticated",
            email="tester@saferoute.local",
        )

    async def fake_profile(db, user_id):
        class FakeProfile:
            deletion_requested_at = None

        return FakeProfile()

    async def fake_check_duplicate(*args, **kwargs):
        return False

    monkeypatch.setattr(crud, "get_or_create_user_profile", fake_profile)
    monkeypatch.setattr(crud, "check_duplicate_report", fake_check_duplicate)

    main.app.dependency_overrides[main.get_db] = fake_db
    main.app.dependency_overrides[main.require_current_user] = fake_required_user
    return TestClient(main.app)


def test_route_contract(client):
    body = {
        "start": [-87.6400, 41.8700],
        "end": [-87.6000, 41.8700],
        "hour": 21,
        "profile": "balanced",
    }
    resp = client.post("/api/v1/route", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert {"safe_route", "shortest_route", "comparison", "metadata"}.issubset(set(data.keys()))
    assert data["safe_route"]["geometry"]["type"] == "LineString"
    assert isinstance(data["safe_route"]["geometry"]["coordinates"][0], list)
    assert data["comparison"]["selected_profile"] == "balanced"
    assert data["comparison"]["candidate_count"] >= 1
    assert data["metadata"]["selection_method"] == "detour_budget_multi_candidate"
    assert resp.headers["X-Route-Candidate-Count"]


def test_route_rejects_unknown_profile(client):
    body = {
        "start": [-87.6400, 41.8700],
        "end": [-87.6000, 41.8700],
        "profile": "extreme",
    }
    resp = client.post("/api/v1/route", json=body)
    assert resp.status_code == 422


def test_route_outside_chicago_returns_400(client):
    body = {"start": [28.9784, 41.0082], "end": [-87.6000, 41.8700]}
    resp = client.post("/api/v1/route", json=body)
    assert resp.status_code == 400
    assert "Chicago" in resp.json()["detail"]


def test_heatmap_contract_flat_array(client):
    resp = client.get("/api/v1/heatmap")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert {"lat", "lng", "total_risk"}.issubset(set(data[0].keys()))


def test_report_contract(client):
    body = {"text": "birisi beni takip ediyor", "lat": 41.88, "lng": -87.63, "category": "general"}
    resp = client.post("/api/v1/report", json=body)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["id"] == "42"


def test_report_outside_chicago_returns_400(client):
    body = {"text": "test ihbar aciklamasi metni", "lat": 41.0082, "lng": 28.9784}
    resp = client.post("/api/v1/report", json=body)
    assert resp.status_code == 400


def test_webhook_social_risk_endpoint_not_available(client):
    """Social-risk webhook endpoint'i MVP kapsamında OLMAMALI.
    POST isteği 404 veya 405 dönmeli ve OpenAPI paths'te bulunmamalı."""
    body = {"latitude": 41.88, "longitude": -87.63, "risk_score": 85.0, "source": "twitter"}
    resp = client.post("/api/v1/webhook/social-risk", json=body)
    assert resp.status_code in (404, 405), (
        f"Webhook endpoint hâlâ aktif: {resp.status_code} {resp.text}"
    )

    openapi = client.get("/openapi.json").json()
    openapi_paths = list(openapi.get("paths", {}).keys())
    assert "/api/v1/webhook/social-risk" not in openapi_paths, (
        f"Webhook endpoint OpenAPI'de hâlâ görünüyor: {openapi_paths}"
    )



def test_llm_non_live_mode_never_changes_canonical_level():
    settings.llm_mode = "mock"
    deterministic = llm_service.RiskExplanation(
        risk_level="high",
        explanation="Gözlemlenen birleşik risk sinyali yüksek düzeydedir.",
        factors=["Toplu risk sinyali"],
    )
    explanation, method = asyncio.run(
        llm_service.explain_risk_with_llm(
            crime=0.8,
            lighting=0.5,
            live=0.2,
            total=0.65,
            deterministic=deterministic,
        )
    )
    assert explanation == deterministic
    assert method == "deterministic_rules"


def test_llm_live_mode_graceful_fallback_without_key():
    settings.llm_mode = "live"
    settings.llm_provider = "deepseek"
    settings.deepseek_api_key = ""
    try:
        deterministic = llm_service.RiskExplanation(
            risk_level="medium",
            explanation="Gözlemlenen birleşik risk sinyali orta düzeydedir.",
            factors=["Toplu risk sinyali"],
        )
        explanation, method = asyncio.run(
            llm_service.explain_risk_with_llm(
                crime=0.5,
                lighting=0.2,
                live=0.1,
                total=0.38,
                deterministic=deterministic,
            )
        )
    finally:
        settings.llm_mode = "mock"
    assert explanation == deterministic
    assert method == "deterministic_fallback_missing_key"
