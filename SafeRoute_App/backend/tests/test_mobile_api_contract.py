# backend/tests/test_mobile_api_contract.py
"""
SafeRoute Backend & Mobil API Kontrat Testi.

ÖNEMLİ BİLGİLENDİRME:
Bu dosya HTTP/API düzeyinde backend veri yapısı ve Pydantic kontrat uyumluluğunu test eder.
Gerçek Android cihaz/emülatör dokunma/ekran E2E testi (UI/Maestro) değildir.

Test Edilen Özellikler:
1. POST /api/v1/route: safe_route, shortest_route, comparison, metadata nesnelerinin doğrulanması.
2. GeoJSON LineString [longitude, latitude] boylam/enlem koordinat sırası.
3. Chicago dışı koordinatlar (İstanbul) için HTTP 400 Bad Request.
4. Canlı İhbar Gönderimi (POST /api/v1/report) -> { ok: true, id: "42", status: "pending" }.
5. İhbar Durum Sorgulama (GET /api/v1/reports/{id}) -> ReportDetailResponse.
6. Heatmap Şeması (GET /api/v1/heatmap) -> flat array.
"""

import pytest
from fastapi.testclient import TestClient
import main
import crud
from routing_engine import CompactCSREngine


class FakePoint:
    def __init__(self, h3, lat, lng, c, lighting, v, tot):
        self.h3_index = h3
        self.lat = lat
        self.lng = lng
        self.risk_crime = c
        self.risk_lighting = lighting
        self.risk_live = v
        self.total_risk = tot


class FakeReport:
    id = 42
    uuid_id = "42"
    tracking_token = "mock-token"
    status = "accepted"
    category = "general"
    latitude = 41.8750
    longitude = -87.6300
    description = "Test ihbarı"
    created_at = None


@pytest.fixture()
def client(monkeypatch):
    csr_engine = CompactCSREngine()
    csr_engine.load_graph("../data-science/compact_graph_res10.npz")
    csr_engine.apply_risk_weights({}, alpha=2.0)
    main.app.state.engine = csr_engine

    async def fake_create_report(db, lat, lng, text, **kwargs):
        return FakeReport()

    async def fake_get_report_by_uuid_and_token(db, uuid_id, token):
        if uuid_id == "42" and token == "mock-token":
            return FakeReport()
        return None

    async def fake_get_report_by_id(db, report_id):
        if str(report_id) == "42":
            return FakeReport()
        return None

    async def fake_get_all(db, h3_resolution=None):
        return [
            FakePoint("cell1", 41.88, -87.63, 0.5, 0.1, 0.05, 0.65),
            FakePoint("cell2", 41.89, -87.64, 0.1, 0.0, 0.0, 0.125)
        ]

    async def fake_clustering(db, report):
        class FakeEvent:
            uuid_id = "event-42"
            status = "pending"
            validation_score = 0.55
            unique_reporter_count = 1

        return FakeEvent()

    async def fake_bg(*args, **kwargs):
        return None

    monkeypatch.setattr(crud, "create_report", fake_create_report)
    monkeypatch.setattr(crud, "process_report_and_event_clustering", fake_clustering)
    monkeypatch.setattr(crud, "get_report_by_uuid_and_token", fake_get_report_by_uuid_and_token)
    monkeypatch.setattr(crud, "get_report_by_id", fake_get_report_by_id)
    monkeypatch.setattr(crud, "get_all_heatmap_points", fake_get_all)
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


def test_chicago_neighborhood_routes_contract(client):
    """Loop, Austin, Rogers Park ve Englewood rota kontratlarını doğrular."""
    scenarios = [
        {"name": "Loop", "start": [-87.6300, 41.8800], "end": [-87.6200, 41.8750]},
        {"name": "Austin", "start": [-87.7700, 41.8900], "end": [-87.7500, 41.8850]},
        {"name": "Rogers Park", "start": [-87.6700, 42.0100], "end": [-87.6600, 42.0000]},
        {"name": "Englewood", "start": [-87.6500, 41.7800], "end": [-87.6400, 41.7700]},
    ]

    for sc in scenarios:
        resp = client.post("/api/v1/route", json={"start": sc["start"], "end": sc["end"]})
        assert resp.status_code == 200, f"{sc['name']} senaryosu başarısız: {resp.text}"
        data = resp.json()

        # Alt Nesne Yapısı Doğrulaması
        assert "safe_route" in data
        assert "shortest_route" in data
        assert "comparison" in data
        assert "metadata" in data

        safe_r = data["safe_route"]
        shortest_r = data["shortest_route"]

        assert safe_r["geometry"]["type"] == "LineString"
        assert shortest_r["geometry"]["type"] == "LineString"

        # GeoJSON [longitude, latitude] sırası kontrolü
        start_coord = safe_r["geometry"]["coordinates"][0]
        assert -88.0 <= start_coord[0] <= -87.0, f"GeoJSON Boylam sırası yanlış: {start_coord[0]}"
        assert 41.0 <= start_coord[1] <= 43.0, f"GeoJSON Enlem sırası yanlış: {start_coord[1]}"

        # Detay Metrik Alanlarının Varlığı ve Değer Aralıkları
        for r_obj in (safe_r, shortest_r):
            assert r_obj["distance_m"] > 0
            assert r_obj["duration_s"] > 0
            assert 0 <= r_obj["risk_score"] <= 100
            assert 0 <= r_obj["safety_score"] <= 100
            assert 0.0 <= r_obj["route_risk"] <= 1.0
            assert r_obj["risk_coverage"] >= 0.0

        # Karşılaştırma ve Metadata Alanları
        comp = data["comparison"]
        assert comp["risk_reduction_pct"] >= 0.0
        assert comp["extra_distance_m"] >= 0.0
        assert comp["extra_distance_pct"] >= 0.0
        assert comp["time_difference_s"] >= 0.0

        meta = data["metadata"]
        assert "risk_snapshot_at" in meta
        assert meta["routing_engine"] == "compact"
        assert meta["algorithm"] == "scipy_dijkstra"


def test_outside_chicago_boundary_rejection_contract(client):
    """Chicago dışı (İstanbul) koordinatlarının HTTP 400 ile reddedildiğini doğrular."""
    resp = client.post("/api/v1/route", json={"start": [28.9784, 41.0082], "end": [-87.6000, 41.8700]})
    assert resp.status_code == 400
    assert "Chicago" in resp.json()["detail"]


def test_live_report_submission_and_status_query_contract(client):
    """POST /api/v1/report ve GET /api/v1/reports/{id} uç noktalarını doğrular."""
    payload = {"text": "Aydınlatma direği arızalı ve bölge karanlık", "lat": 41.8750, "lng": -87.6300}
    resp = client.post("/api/v1/report", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["ok"] is True
    assert data["id"] == "42"
    token = data.get("tracking_token", "mock-token")
    # Durum Sorgulama (GET /api/v1/reports/42?token=...)
    resp_get = client.get(f"/api/v1/reports/42?token={token}")
    assert resp_get.status_code == 200
    get_data = resp_get.json()
    assert get_data["id"] == "42"
    assert get_data["status"] == "accepted"


def test_heatmap_schema_matching_contract(client):
    """GET /api/v1/heatmap şemasını doğrular."""
    resp = client.get("/api/v1/heatmap")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if len(data) > 0:
        point = data[0]
        assert "h3_index" in point
        assert "lat" in point
        assert "lng" in point
        assert "risk_crime" in point
        assert "risk_lighting" in point
        assert "risk_live" in point
        assert "total_risk" in point
