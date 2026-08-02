# backend/tests/test_street_risk_explanation_api.py
"""
POST /api/v1/street-risk-explanation endpoint unit & integration testleri.
"""
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402
import crud  # noqa: E402


class FakeHeatmapPoint:
    def __init__(self, h3_index, lat, lng, crime=0.0, lighting=0.0, live=0.0):
        self.h3_index = h3_index
        self.lat = lat
        self.lng = lng
        self.risk_crime = crime
        self.risk_lighting = lighting
        self.risk_live = live
        self.total_risk = 0.65 * crime + 0.20 * lighting + 0.15 * live


@pytest.fixture()
def client(monkeypatch):
    import h3 as h3lib
    cell_downtown = h3lib.latlng_to_cell(41.8781, -87.6298, 10)
    cell_high_risk = h3lib.latlng_to_cell(41.8850, -87.6350, 10)
    cell_regression = h3lib.latlng_to_cell(41.8900, -87.6400, 10)

    mock_points = [
        FakeHeatmapPoint(cell_downtown, 41.8781, -87.6298, crime=0.1, lighting=0.0, live=0.0),
        FakeHeatmapPoint(cell_high_risk, 41.8850, -87.6350, crime=0.8, lighting=0.5, live=0.2),
        FakeHeatmapPoint(cell_regression, 41.8900, -87.6400, crime=0.4, lighting=0.3, live=0.1),
    ]

    async def fake_get_point(db, h3_index):
        return next((point for point in mock_points if point.h3_index == h3_index), None)

    async def fake_etl_runs(db):
        return {"risk_snapshot_at": "2026-07-27T00:00:00Z"}

    async def fake_db():
        yield None

    monkeypatch.setattr(crud, "get_heatmap_point", fake_get_point)
    monkeypatch.setattr(crud, "get_latest_etl_runs", fake_etl_runs)
    main.app.dependency_overrides[main.get_db] = fake_db

    return TestClient(main.app)


def test_street_risk_explanation_success(client):
    """1. Endpoint geçerli H3/risk verisiyle HTTP 200 döndürür."""
    body = {"lat": 41.8850, "lng": -87.6350, "hour": 21}
    resp = client.post("/api/v1/street-risk-explanation", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["data_available"] is True
    assert data["risk_level"] in ("low", "low_medium", "medium", "high", "very_high")
    assert "explanation" in data
    assert isinstance(data["factors"], list)
    assert len(data["factors"]) > 0


def test_exact_regression_formula_and_channels(client):
    """2. Regresyon Testi: crime=0.4, lighting=0.3, live=0.1 -> total_risk=0.335, low_medium."""
    body = {"lat": 41.8900, "lng": -87.6400}
    resp = client.post("/api/v1/street-risk-explanation", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # 0.65 * 0.4 + 0.20 * 0.3 + 0.15 * 0.1 = 0.26 + 0.06 + 0.015 = 0.335
    assert data["total_risk"] == 0.335
    assert data["crime_risk"] == 0.4
    assert data["lighting_risk"] == 0.3
    assert data["live_risk"] == 0.1

    assert data["channels"]["crime"] == 40.0
    assert data["channels"]["lighting"] == 30.0
    assert data["channels"]["live"] == 10.0
    assert data["channels"]["total"] == 33.5

    assert data["risk_level"] == "low_medium"
    assert data["observed_risk_level"] == "Düşük-Orta Gözlemlenen Risk"
    assert "historical" not in data["channels"]
    assert "social" not in data["channels"]


def test_street_risk_no_data_handling(client, monkeypatch):
    """3. No-data durumunda total_risk=null, data_available=false, risk_level=no_data, snapshot=null."""
    async def fake_empty_etl(db):
        return {}  # snapshot verisi yok

    monkeypatch.setattr(crud, "get_latest_etl_runs", fake_empty_etl)

    # Chicago sınırları içinde ancak fake mock_points listesinde verisi olmayan başka bir Res-9 hücresi
    body = {"lat": 41.7500, "lng": -87.7000}
    resp = client.post("/api/v1/street-risk-explanation", json=body)
    assert resp.status_code == 200
    data = resp.json()

    assert data["data_available"] is False
    assert data["total_risk"] is None
    assert data["risk_level"] == "no_data"
    assert data["observed_risk_level"] == "Veri Yok / Belirsiz"
    assert data["explanation"] == "Bu bölge için yeterli risk verisi bulunmuyor."
    assert data["risk_snapshot_at"] is None


def test_street_risk_outside_chicago(client):
    """4. Geçersiz / Chicago dışı koordinat HTTP 400 döndürür."""
    body = {"lat": 41.0082, "lng": 28.9784}  # İstanbul
    resp = client.post("/api/v1/street-risk-explanation", json=body)
    assert resp.status_code == 400
    assert "Chicago" in resp.json()["detail"]


def test_street_risk_no_sensitive_fields(client):
    """5. Hassas kullanıcı ve sistem alanları (IP, token, e-posta, ham metin) cevapta yer almaz."""
    body = {"lat": 41.8781, "lng": -87.6298}
    resp = client.post("/api/v1/street-risk-explanation", json=body)
    assert resp.status_code == 200
    data = resp.json()

    forbidden_fields = {"ip", "user_id", "email", "tracking_token", "text_snippet", "raw_text", "historical", "social"}
    for field in forbidden_fields:
        assert field not in data


def test_street_risk_disclaimer_present(client):
    """6. Kesin güvenlik garantisi verilmez (yasal uyarı yer alır)."""
    body = {"lat": 41.8781, "lng": -87.6298}
    resp = client.post("/api/v1/street-risk-explanation", json=body)
    assert resp.status_code == 200
    data = resp.json()

    assert "disclaimer" in data
    assert "kesin güvenlik garantisi değildir" in data["disclaimer"]


def test_existing_endpoints_unaffected(client):
    """7. Mevcut endpoint testleri bozulmaz."""
    resp = client.get("/api/v1/heatmap")
    assert resp.status_code == 200
