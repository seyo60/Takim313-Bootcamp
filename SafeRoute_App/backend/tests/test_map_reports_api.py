# backend/tests/test_map_reports_api.py
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from main import app
import crud

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_in_memory_reports():
    crud._in_memory_reports.clear()
    yield
    crud._in_memory_reports.clear()


def test_get_map_reports_empty():
    response = client.get("/api/v1/reports/map?minutes=60")
    assert response.status_code == 200
    data = response.json()
    assert "generated_at" in data
    assert data["window_minutes"] == 60
    assert data["count"] == 0
    assert data["reports"] == []


def test_get_map_reports_privacy_and_anonymization():
    now_utc = datetime.now(timezone.utc)
    rep = crud.ReportModel(
        id=1,
        uuid_id="secret-uuid-12345",
        tracking_token="super-secret-tracking-token-67890",
        latitude=41.8781,
        longitude=-87.6298,
        description="Gizli kullanıcı metni — asla sızdırılmamalı",
        category="safety_concern",
        status="accepted",
        ip_address="192.168.1.100",
        created_at=now_utc - timedelta(minutes=15)
    )
    crud._in_memory_reports["secret-uuid-12345"] = rep

    response = client.get("/api/v1/reports/map?minutes=60")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    report_item = data["reports"][0]

    # GİZLİLİK DOĞRULAMALARI (CRITICAL PRIVACY CHECKS)
    assert "tracking_token" not in report_item
    assert "ip_address" not in report_item
    assert "description" not in report_item
    assert "uuid_id" not in report_item
    assert report_item["public_id"] != "secret-uuid-12345"
    assert len(report_item["public_id"]) == 16
    assert report_item["verification_label"] == "community_report"

    # KONUM ANONİMLEŞTİRME DOĞRULAMASI
    # H3 Res-9 yuvarlaması tam koordinatı değiştirmeli
    assert isinstance(report_item["lat"], float)
    assert isinstance(report_item["lng"], float)
    assert report_item["minutes_ago"] >= 14 and report_item["minutes_ago"] <= 16


def test_get_map_reports_time_window_filtering():
    now_utc = datetime.now(timezone.utc)

    # 20 dk önceki geçerli rapor
    rep_recent = crud.ReportModel(
        id=10,
        uuid_id="uuid-recent-20m",
        tracking_token="token-20m",
        latitude=41.88,
        longitude=-87.63,
        description="Yakın zamanlı ihbar",
        category="safety_concern",
        status="accepted",
        created_at=now_utc - timedelta(minutes=20)
    )

    # 90 dk önceki (zaman aşımına uğramış) rapor
    rep_old = crud.ReportModel(
        id=11,
        uuid_id="uuid-old-90m",
        tracking_token="token-90m",
        latitude=41.89,
        longitude=-87.64,
        description="Eski ihbar",
        category="safety_concern",
        status="accepted",
        created_at=now_utc - timedelta(minutes=90)
    )

    crud._in_memory_reports["uuid-recent-20m"] = rep_recent
    crud._in_memory_reports["uuid-old-90m"] = rep_old

    # 60 dakikalık pencere sorgusu
    res = client.get("/api/v1/reports/map?minutes=60")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 1
    assert data["reports"][0]["minutes_ago"] >= 19 and data["reports"][0]["minutes_ago"] <= 21

    # 15 dakikalık dar pencere sorgusu (hiçbir şey dönmemeli)
    res_15 = client.get("/api/v1/reports/map?minutes=15")
    assert res_15.status_code == 200
    assert res_15.json()["count"] == 0


def test_get_map_reports_status_filtering():
    now_utc = datetime.now(timezone.utc)

    rep_accepted = crud.ReportModel(
        id=20,
        uuid_id="uuid-accepted",
        tracking_token="token-accepted",
        latitude=41.87,
        longitude=-87.62,
        description="Kabul edilen ihbar",
        category="lighting",
        status="accepted",
        created_at=now_utc - timedelta(minutes=10)
    )
    rep_rejected = crud.ReportModel(
        id=21,
        uuid_id="uuid-rejected",
        tracking_token="token-rejected",
        latitude=41.87,
        longitude=-87.62,
        description="Reddedilen ihbar",
        category="lighting",
        status="rejected",
        created_at=now_utc - timedelta(minutes=10)
    )
    rep_expired = crud.ReportModel(
        id=22,
        uuid_id="uuid-expired",
        tracking_token="token-expired",
        latitude=41.87,
        longitude=-87.62,
        description="Süresi dolan ihbar",
        category="lighting",
        status="expired",
        created_at=now_utc - timedelta(minutes=10)
    )

    crud._in_memory_reports["uuid-accepted"] = rep_accepted
    crud._in_memory_reports["uuid-rejected"] = rep_rejected
    crud._in_memory_reports["uuid-expired"] = rep_expired

    res = client.get("/api/v1/reports/map?minutes=60")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 1
    assert data["reports"][0]["category"] == "lighting"


def test_get_map_reports_category_and_bbox_filtering():
    now_utc = datetime.now(timezone.utc)

    # Chicago Loop içinde
    rep_loop = crud.ReportModel(
        id=30,
        uuid_id="uuid-loop",
        tracking_token="token-loop",
        latitude=41.88,
        longitude=-87.63,
        description="Loop ihbar",
        category="obstacle",
        status="accepted",
        created_at=now_utc - timedelta(minutes=5)
    )
    # Chicago Loop dışında
    rep_far = crud.ReportModel(
        id=31,
        uuid_id="uuid-far",
        tracking_token="token-far",
        latitude=42.00,
        longitude=-87.90,
        description="Uzak ihbar",
        category="obstacle",
        status="accepted",
        created_at=now_utc - timedelta(minutes=5)
    )

    crud._in_memory_reports["uuid-loop"] = rep_loop
    crud._in_memory_reports["uuid-far"] = rep_far

    # Kategori filtresi
    res_cat = client.get("/api/v1/reports/map?category=obstacle")
    assert res_cat.status_code == 200
    assert res_cat.json()["count"] == 2

    res_cat_other = client.get("/api/v1/reports/map?category=lighting")
    assert res_cat_other.status_code == 200
    assert res_cat_other.json()["count"] == 0

    # Bbox filtresi (west=-87.7, south=41.8, east=-86.0, north=41.9)
    res_bbox = client.get("/api/v1/reports/map?bbox=-87.7,41.8,-86.0,41.9")
    assert res_bbox.status_code == 200
    data_bbox = res_bbox.json()
    assert data_bbox["count"] == 1


def test_get_map_reports_limit_and_query_validation():
    now_utc = datetime.now(timezone.utc)
    for i in range(15):
        crud._in_memory_reports[f"uuid-{i}"] = crud.ReportModel(
            id=i+100,
            uuid_id=f"uuid-{i}",
            tracking_token=f"token-{i}",
            latitude=41.88 + (i * 0.001),
            longitude=-87.63,
            description=f"İhbar {i}",
            category="general",
            status="accepted",
            created_at=now_utc - timedelta(minutes=i+1)
        )

    res_limit = client.get("/api/v1/reports/map?limit=5")
    assert res_limit.status_code == 200
    assert res_limit.json()["count"] == 5

    # Query validation (minutes > 60 -> HTTP 422 Unprocessable Entity)
    res_invalid = client.get("/api/v1/reports/map?minutes=120")
    assert res_invalid.status_code == 422
