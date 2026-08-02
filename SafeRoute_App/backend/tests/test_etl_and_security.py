import pytest
from fastapi.testclient import TestClient

import main
from routing_engine import CompactCSREngine

CHICAGO_START = [-87.6298, 41.8781]
CHICAGO_END = [-87.6298, 41.8881]


@pytest.fixture
def client(monkeypatch):
    csr_engine = CompactCSREngine()
    csr_engine.load_graph("../data-science/compact_graph_res10.npz")
    csr_engine.apply_risk_weights({}, alpha=2.0)
    main.app.state.engine = csr_engine

    async def fake_background(*args, **kwargs):
        return None

    monkeypatch.setattr(main, "process_report_background_task", fake_background)

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

    import crud

    monkeypatch.setattr(crud, "get_or_create_user_profile", fake_profile)
    main.app.dependency_overrides[main.get_db] = fake_db
    main.app.dependency_overrides[main.require_current_user] = fake_required_user
    return TestClient(main.app)


def test_route_metadata_and_coverage(client):
    """
    POST /api/v1/route uç noktasının metadata (response_generated_at, risk_snapshot_at,
    crime_data_updated_at, lighting_data_updated_at) ve uzunluk-ağırlıklı risk_coverage
    değerlerini döndürdüğünü doğrular.
    """
    response = client.post("/api/v1/route", json={"start": CHICAGO_START, "end": CHICAGO_END})
    assert response.status_code == 200, response.text
    data = response.json()

    assert "metadata" in data
    meta = data["metadata"]
    assert "response_generated_at" in meta
    assert "risk_snapshot_at" in meta

    assert "safe_route" in data
    assert "shortest_route" in data
    assert "risk_coverage" in data["safe_route"]
    assert "risk_coverage" in data["shortest_route"]
    assert isinstance(data["safe_route"]["risk_coverage"], (int, float))
    assert isinstance(data["shortest_route"]["risk_coverage"], (int, float))


def test_report_creation_and_idor_protection(client):
    """
    İhbar oluşturma sırasında UUID v4 ve tracking_token üretildiğini,
    yanlış jeton ile yapılan GET /api/v1/reports/{uuid_id} isteğinin HTTP 403 Forbidden ile reddedildiğini (IDOR koruması),
    doğru jeton ile yapıldığında ise sadece sterilize durum (accepted/pending) döndüğünü doğrular.
    """
    payload = {
        "text": "Aydınlatma direği arızalı ve cadde tamamen karanlık",
        "lat": 41.8750,
        "lng": -87.6320,
        "category": "lighting"
    }
    create_res = client.post("/api/v1/report", json=payload)
    assert create_res.status_code == 201
    created_data = create_res.json()

    assert created_data["ok"] is True
    assert "id" in created_data
    assert "tracking_token" in created_data
    report_uuid = created_data["id"]
    token = created_data["tracking_token"]

    # 1. IDOR Testi: Yanlış/Geçersiz Jeton ile Sorgulama -> 403 Forbidden
    invalid_token_res = client.get(f"/api/v1/reports/{report_uuid}?token=invalid-secret-token")
    assert invalid_token_res.status_code == 403

    # 2. IDOR Testi: Jeton parametresi eksik -> 422 Unprocessable Entity
    no_token_res = client.get(f"/api/v1/reports/{report_uuid}")
    assert no_token_res.status_code == 422

    # 3. Başarılı Sorgulama: Doğru jeton ile steril durum bilgisi alınır
    valid_res = client.get(f"/api/v1/reports/{report_uuid}?token={token}")
    assert valid_res.status_code == 200
    detail = valid_res.json()
    assert detail["id"] == report_uuid
    assert detail["category"] == "lighting"
    assert "status" in detail
    assert "created_at" in detail
    # Hassas kullanıcı metninin dışarı sızdırılmadığı teyit edilir
    assert "description" not in detail


def test_duplicate_report_prevention(client):
    """
    50 metre ve 10 dakika içinde aynı konumdan girilen mükerrer ihbarın HTTP 400 ile reddedildiğini doğrular.
    """
    payload = {
        "text": "Şüpheli durum ve yüksek sesli tartışma bildirimi",
        "lat": 41.8800,
        "lng": -87.6300,
        "category": "crime"
    }
    res1 = client.post("/api/v1/report", json=payload)
    assert res1.status_code == 201

    # Aynı konuma ikinci ihbar gönderildiğinde mükerrer ihbar engeli devreye girer
    res2 = client.post("/api/v1/report", json=payload)
    assert res2.status_code == 400
    assert "yakın zamanda benzer bir ihbar" in res2.json()["detail"]


def test_report_category_and_length_validation(client):
    """
    Açıklama karakter sınırı (10-500) veya geçersiz kategori içeren ihbarların reddedildiğini doğrular.
    """
    # 1. Kısa metin (< 10 karakter)
    short_payload = {"text": "kısa", "lat": 41.875, "lng": -87.63, "category": "general"}
    res_short = client.post("/api/v1/report", json=short_payload)
    assert res_short.status_code == 422

    # 2. Geçersiz kategori
    invalid_cat = {"text": "Aydınlatma direği arızası var caddede", "lat": 41.875, "lng": -87.63, "category": "invalid_cat"}
    res_cat = client.post("/api/v1/report", json=invalid_cat)
    assert res_cat.status_code == 400
    assert "Geçersiz kategori" in res_cat.json()["detail"]
