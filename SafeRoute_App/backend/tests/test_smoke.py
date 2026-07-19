# backend/tests/test_smoke.py
"""
Hafif smoke testleri: uygulama ayakta mi ve sozlesme uclari kayitli mi?

Bu testler DB veya graf GEREKTIRMEZ (lifespan calismaz) — CI'da hizli bir
"is it alive" kontrolu saglar. Endpoint'lerin is mantigini test_backend.py
ayrintili dogrular; burada sadece varliklarini/sagligini kontrol ederiz.

Calistirma (backend/ klasorunden):
    python -m pytest tests/test_smoke.py -v
"""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402


client = TestClient(main.app)


def test_health_ok():
    """Render/Railway health-check ucu 200 donmeli."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_root_ok():
    resp = client.get("/")
    assert resp.status_code == 200


def test_core_endpoints_registered():
    """Mobil sozlesmesinin uc ucu da uygulamaya kayitli olmali."""
    paths = {route.path for route in main.app.routes}
    assert "/api/v1/route" in paths
    assert "/api/v1/heatmap" in paths
    assert "/api/v1/report" in paths


def test_removed_webhook_not_registered():
    """Kapsam disi sosyal medya webhook'u kayitli OLMAMALI."""
    paths = {route.path for route in main.app.routes}
    assert "/api/v1/webhook/social-risk" not in paths
