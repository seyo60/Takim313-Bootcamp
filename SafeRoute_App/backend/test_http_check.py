import sys
import json
from pathlib import Path
from fastapi.testclient import TestClient
import h3 as h3lib

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402
import crud  # noqa: E402

class FakePoint:
    def __init__(self, lat, lng, crime=0.4, lighting=0.3, live=0.1):
        self.h3_index = h3lib.latlng_to_cell(lat, lng, 9)
        self.lat = lat
        self.lng = lng
        self.risk_crime = crime
        self.risk_lighting = lighting
        self.risk_live = live
        self.total_risk = 0.65 * crime + 0.20 * lighting + 0.15 * live

async def fake_pts(db):
    return [FakePoint(41.8781, -87.6298, crime=0.4, lighting=0.3, live=0.1)]

async def fake_etl(db):
    return {"risk_snapshot_at": "2026-07-27T00:00:00Z"}

async def fake_db():
    yield None

crud.get_all_heatmap_points = fake_pts
crud.get_latest_etl_runs = fake_etl
main.app.dependency_overrides[main.get_db] = fake_db

client = TestClient(main.app)
response = client.post("/api/v1/street-risk-explanation", json={"lat": 41.8781, "lng": -87.6298})

print("HTTP Status Code:", response.status_code)
print("Response JSON:")
print(json.dumps(response.json(), indent=2, ensure_ascii=False))
