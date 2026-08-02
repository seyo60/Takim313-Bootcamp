"""İhbar oluşturma artık oturum gerektirir (İhbarlarım eşleşmesi için)."""

from uuid import UUID

from fastapi.testclient import TestClient

import main
from auth import AuthenticatedUser
from config import settings


def test_report_requires_auth_when_missing_token(monkeypatch):
    monkeypatch.setattr(settings, "auth_required", True)

    async def fake_db():
        yield None

    main.app.dependency_overrides[main.get_db] = fake_db
    # require_current_user override yok → 401
    try:
        client = TestClient(main.app)
        resp = client.post(
            "/api/v1/report",
            json={
                "text": "Silahlı çatışma var sokak kapalı dikkat",
                "lat": 41.8781,
                "lng": -87.6298,
                "category": "crime",
                "reporter_installation_id": "device-anon-1",
            },
        )
        assert resp.status_code == 401, resp.text
    finally:
        main.app.dependency_overrides.clear()


def test_authenticated_report_allowed(monkeypatch):
    monkeypatch.setattr(settings, "auth_required", True)

    async def fake_db():
        yield None

    async def fake_required_user():
        return AuthenticatedUser(
            user_id=UUID("11111111-1111-1111-1111-111111111111"),
            role="authenticated",
            email="tester@saferoute.local",
        )

    async def fake_create_report(db, lat, lng, text, **kwargs):
        class FakeReport:
            uuid_id = "auth-report-1"
            tracking_token = "tok-1"
            status = "pending"
            id = 1

        return FakeReport()

    async def fake_check_duplicate(db, lat, lng, **kwargs):
        return False

    async def fake_clustering(db, report):
        class FakeEvent:
            uuid_id = "event-1"
            status = "accepted"
            validation_score = 0.85
            unique_reporter_count = 1

        return FakeEvent()

    async def fake_profile(db, user_id):
        class FakeProfile:
            deletion_requested_at = None

        return FakeProfile()

    import crud

    monkeypatch.setattr(crud, "create_report", fake_create_report)
    monkeypatch.setattr(crud, "check_duplicate_report", fake_check_duplicate)
    monkeypatch.setattr(crud, "process_report_and_event_clustering", fake_clustering)
    monkeypatch.setattr(crud, "get_or_create_user_profile", fake_profile)
    main._report_rate_limit_tracker.clear()

    main.app.dependency_overrides[main.get_db] = fake_db
    main.app.dependency_overrides[main.require_current_user] = fake_required_user
    try:
        client = TestClient(main.app)
        resp = client.post(
            "/api/v1/report",
            json={
                "text": "Silahlı çatışma var sokak kapalı dikkat",
                "lat": 41.8781,
                "lng": -87.6298,
                "category": "crime",
                "reporter_installation_id": "device-auth-1",
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["ok"] is True
        assert data["live_risk_applied"] is True
    finally:
        main.app.dependency_overrides.clear()
