# backend/tests/test_heatmap_map_api.py
import pytest
from fastapi.testclient import TestClient
from main import app
import main
import crud

client = TestClient(app)


class FakeH3Point:
    def __init__(self, h3_index, lat, lng, crime, lighting, live, total, extra_features=None):
        self.h3_index = h3_index
        self.lat = lat
        self.lng = lng
        self.risk_crime = crime
        self.risk_lighting = lighting
        self.risk_live = live
        self.total_risk = total
        self.extra_features = extra_features or {}


@pytest.fixture(autouse=True)
def override_db_dependency():
    fake_points = [
        FakeH3Point("892654131cbffff", 41.8781, -87.6298, 0.50, 0.20, 0.10, 0.42),
        FakeH3Point("892654131c7ffff", 41.8850, -87.6350, 0.10, 0.10, 0.00, 0.095),
        FakeH3Point("892654131c3ffff", 41.8900, -87.6400, 0.00, 0.00, 0.00, 0.00),
        FakeH3Point(
            "892654131d7ffff",
            41.8920,
            -87.6420,
            0.00,
            0.00,
            0.00,
            0.00,
            {"open_311_lighting_count": 0, "completed_311_lighting_count": 3},
        ),
    ]

    async def fake_get_all_heatmap_points(db, h3_resolution=None):
        return fake_points

    async def fake_get_latest_etl_runs(db):
        return {
            "crime_data_updated_at": "2026-07-26T12:00:00+00:00",
            "lighting_data_updated_at": "2026-07-26T12:00:00+00:00",
            "risk_snapshot_at": "2026-07-26T12:00:00+00:00",
        }

    async def fake_get_db():
        yield None

    app.dependency_overrides[main.get_db] = fake_get_db
    monkey_get_all = crud.get_all_heatmap_points
    monkey_get_etl = crud.get_latest_etl_runs

    crud.get_all_heatmap_points = fake_get_all_heatmap_points
    crud.get_latest_etl_runs = fake_get_latest_etl_runs

    yield

    app.dependency_overrides.clear()
    crud.get_all_heatmap_points = monkey_get_all
    crud.get_latest_etl_runs = monkey_get_etl


def test_get_heatmap_map_contract_and_structure():
    response = client.get("/api/v1/heatmap/map?channel=total")
    assert response.status_code == 200
    data = response.json()

    assert data["type"] == "FeatureCollection"
    assert "metadata" in data
    assert "features" in data

    meta = data["metadata"]
    assert meta["h3_resolution"] == 10
    assert meta["channel"] == "total"
    assert meta["feature_count"] == 4
    assert meta["data_coverage_pct"] > 0.0

    features = data["features"]
    assert len(features) == 4

    feat = features[0]
    assert feat["type"] == "Feature"
    assert feat["id"] == "892654131cbffff"
    assert feat["geometry"]["type"] == "Polygon"

    coords = feat["geometry"]["coordinates"][0]
    assert len(coords) >= 4
    # POLİGON HALKA KAPALI OLMALI (ilk == son)
    assert coords[0] == coords[-1]

    # KOORDİNAT SIRASI [longitude, latitude]
    lng, lat = coords[0]
    assert -180.0 <= lng <= 180.0
    assert -90.0 <= lat <= 90.0

    props = feat["properties"]
    assert props["h3_index"] == "892654131cbffff"
    assert props["risk"] == 0.42
    assert props["data_available"] is True


def test_get_heatmap_map_channels():
    for ch in ["total", "crime", "lighting", "live"]:
        res = client.get(f"/api/v1/heatmap/map?channel={ch}")
        assert res.status_code == 200
        data = res.json()
        assert data["metadata"]["channel"] == ch


def test_get_heatmap_map_invalid_channel():
    res = client.get("/api/v1/heatmap/map?channel=invalid_channel")
    assert res.status_code == 400
    assert "Geçersiz risk kanalı" in res.json()["detail"]


def test_get_heatmap_map_bbox_filtering():
    # Chicago Loop bbox (-87.65, 41.85, -87.60, 41.90) -> matches
    res = client.get("/api/v1/heatmap/map?bbox=-87.65,41.85,-87.60,41.90")
    assert res.status_code == 200
    data = res.json()
    assert data["metadata"]["feature_count"] >= 1

    # Out of bounds bbox -> 0 features
    res_far = client.get("/api/v1/heatmap/map?bbox=0.0,0.0,1.0,1.0")
    assert res_far.status_code == 200
    assert res_far.json()["metadata"]["feature_count"] == 0
    assert len(res_far.json()["features"]) == 0


def test_get_heatmap_map_no_data_cells():
    res_inc = client.get("/api/v1/heatmap/map?include_no_data=true")
    assert res_inc.status_code == 200
    assert res_inc.json()["metadata"]["feature_count"] == 4

    res_exc = client.get("/api/v1/heatmap/map?include_no_data=false")
    assert res_exc.status_code == 200
    assert res_exc.json()["metadata"]["feature_count"] == 3  # observed zero is data; unobserved zero is excluded


def test_lighting_zero_distinguishes_observation_from_no_data():
    response = client.get("/api/v1/heatmap/map?channel=lighting&include_no_data=true")
    assert response.status_code == 200
    by_id = {feature["id"]: feature["properties"] for feature in response.json()["features"]}

    observed_zero = by_id["892654131d7ffff"]
    assert observed_zero["data_available"] is True
    assert observed_zero["risk"] == 0.0

    unobserved_zero = by_id["892654131c3ffff"]
    assert unobserved_zero["data_available"] is False
    assert unobserved_zero["risk"] is None


def test_existing_get_heatmap_backward_compatibility():
    res = client.get("/api/v1/heatmap")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 4
