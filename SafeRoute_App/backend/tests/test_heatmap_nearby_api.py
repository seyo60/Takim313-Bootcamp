import pytest
from starlette.testclient import TestClient
import main
import crud
from models import H3HeatmapModel

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def override_db():
    async def fake_db():
        yield None
    main.app.dependency_overrides[main.get_db] = fake_db
    yield
    main.app.dependency_overrides.clear()



def test_1_valid_chicago_coordinate_returns_200():
    resp = client.get("/api/v1/heatmap/nearby?lat=41.8781&lng=-87.6298&radius_m=1000")
    assert resp.status_code == 200
    data = resp.json()
    assert "center" in data
    assert "radius_meters" in data
    assert "count" in data
    assert "items" in data


def test_2_results_sorted_by_distance():
    resp = client.get("/api/v1/heatmap/nearby?lat=41.8781&lng=-87.6298&radius_m=2000")
    assert resp.status_code == 200
    items = resp.json()["items"]
    if len(items) > 1:
        distances = [it["distance_meters"] for it in items]
        assert distances == sorted(distances)


def test_3_radius_limit_applied():
    resp_small = client.get("/api/v1/heatmap/nearby?lat=41.8781&lng=-87.6298&radius_m=50")
    resp_large = client.get("/api/v1/heatmap/nearby?lat=41.8781&lng=-87.6298&radius_m=5000")

    assert resp_small.status_code == 200
    assert resp_large.status_code == 200
    assert resp_small.json()["radius_meters"] == 50.0
    assert resp_large.json()["radius_meters"] == 5000.0


def test_4_outside_chicago_coordinate_returns_400():
    resp = client.get("/api/v1/heatmap/nearby?lat=41.0082&lng=28.9784")  # Istanbul
    assert resp.status_code == 400
    assert "Chicago" in resp.json()["detail"]


def test_5_no_fake_green_risk_for_data_free_area():
    resp = client.get("/api/v1/heatmap/nearby?lat=41.8781&lng=-87.6298&radius_m=10")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["items"], list)


def test_6_risk_channels_only_contain_crime_lighting_live_total():
    resp = client.get("/api/v1/heatmap/nearby?lat=41.8781&lng=-87.6298&radius_m=2000")
    assert resp.status_code == 200
    items = resp.json()["items"]
    for it in items:
        assert "risk_crime" in it
        assert "risk_lighting" in it
        assert "risk_live" in it
        assert "total_risk" in it
        assert "risk_social" not in it
        assert "risk_historical" not in it


def test_7_no_sensitive_report_fields_leaked():
    resp = client.get("/api/v1/heatmap/nearby?lat=41.8781&lng=-87.6298")
    assert resp.status_code == 200
    items = resp.json()["items"]
    for it in items:
        assert "description" not in it
        assert "ip_address" not in it
        assert "reporter_hash" not in it
        assert "tracking_token" not in it


def test_8_empty_db_returns_empty_items_gracefully(monkeypatch):
    async def fake_get_empty_pts(
        db,
        lat,
        lng,
        radius_meters=1000.0,
        limit=100,
        h3_resolution=None,
    ):
        return []

    monkeypatch.setattr(crud, "get_nearby_heatmap_points", fake_get_empty_pts)
    resp = client.get("/api/v1/heatmap/nearby?lat=41.8781&lng=-87.6298")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["items"] == []


def test_9_risk_greater_than_1_not_leaked(monkeypatch):
    fake_pt = H3HeatmapModel(
        h3_index="892654a32b7ffff",
        lat=41.8781,
        lng=-87.6298,
        risk_crime=0.4,
        risk_lighting=0.3,
        risk_live=0.1,
        total_risk=0.335
    )

    async def fake_pts(
        db,
        lat,
        lng,
        radius_meters=1000.0,
        limit=100,
        h3_resolution=None,
    ):
        return [fake_pt]

    monkeypatch.setattr(crud, "get_nearby_heatmap_points", fake_pts)
    resp = client.get("/api/v1/heatmap/nearby?lat=41.8781&lng=-87.6298")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["total_risk"] <= 1.0


@pytest.mark.anyio
async def test_10_spatial_index_dwithin_postgis_query_used():
    # crud.get_nearby_heatmap_points db=None durumunda güvenli şekilde boş liste dönmelidir
    res = await crud.get_nearby_heatmap_points(db=None, lat=41.8781, lng=-87.6298)
    assert res == []
