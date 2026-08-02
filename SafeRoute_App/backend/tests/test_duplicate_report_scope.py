"""Mükerrer ihbar engelinin kapsam testleri.

Olay doğrulaması iki bağımsız muhabir gerektirdiği için, mükerrer engeli aynı
muhabirin tekrarını durdurmalı ancak ikinci bağımsız muhabiri engellememelidir.
"""

from datetime import datetime, timedelta, timezone

import pytest

import crud


class _FakeReport:
    def __init__(self, *, latitude, longitude, reporter_hash=None, user_id=None, age_minutes=0.0):
        self.latitude = latitude
        self.longitude = longitude
        self.reporter_hash = reporter_hash
        self.user_id = user_id
        self.created_at = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)


@pytest.fixture(autouse=True)
def _clean_in_memory_reports():
    crud._in_memory_reports.clear()
    yield
    crud._in_memory_reports.clear()


@pytest.mark.anyio
async def test_same_reporter_nearby_report_is_duplicate():
    crud._in_memory_reports["a"] = _FakeReport(
        latitude=41.8800,
        longitude=-87.6300,
        reporter_hash="device-a",
    )
    assert await crud.check_duplicate_report(
        None,
        41.8800,
        -87.6300,
        reporter_hash="device-a",
    )


@pytest.mark.anyio
async def test_second_independent_reporter_is_not_duplicate():
    """İkinci bağımsız muhabir engellenirse hiçbir olay kabul edilemez."""
    crud._in_memory_reports["a"] = _FakeReport(
        latitude=41.8800,
        longitude=-87.6300,
        reporter_hash="device-a",
    )
    assert not await crud.check_duplicate_report(
        None,
        41.8800,
        -87.6300,
        reporter_hash="device-b",
    )


@pytest.mark.anyio
async def test_anonymous_report_keeps_location_based_block():
    crud._in_memory_reports["a"] = _FakeReport(
        latitude=41.8800,
        longitude=-87.6300,
        reporter_hash=None,
    )
    assert await crud.check_duplicate_report(None, 41.8800, -87.6300)


@pytest.mark.anyio
async def test_far_away_report_from_same_reporter_is_allowed():
    crud._in_memory_reports["a"] = _FakeReport(
        latitude=41.8800,
        longitude=-87.6300,
        reporter_hash="device-a",
    )
    assert not await crud.check_duplicate_report(
        None,
        41.9500,
        -87.7000,
        reporter_hash="device-a",
    )


@pytest.mark.anyio
async def test_expired_window_from_same_reporter_is_allowed():
    crud._in_memory_reports["a"] = _FakeReport(
        latitude=41.8800,
        longitude=-87.6300,
        reporter_hash="device-a",
        age_minutes=30.0,
    )
    assert not await crud.check_duplicate_report(
        None,
        41.8800,
        -87.6300,
        reporter_hash="device-a",
    )


@pytest.mark.anyio
async def test_authenticated_user_id_preferred_over_shared_device_hash():
    """Aynı emülatörde test1/test2 aynı installation_id paylaşır; user_id ayrı tutulmalı."""
    from uuid import uuid4

    user_a = uuid4()
    user_b = uuid4()
    crud._in_memory_reports["a"] = _FakeReport(
        latitude=41.8800,
        longitude=-87.6300,
        reporter_hash="shared-emulator-device",
        user_id=user_a,
    )
    # Aynı cihaz hash'i + farklı hesap → engellenmemeli
    assert not await crud.check_duplicate_report(
        None,
        41.8800,
        -87.6300,
        reporter_hash="shared-emulator-device",
        user_id=user_b,
    )
    # Aynı hesap tekrar → engellenmeli
    assert await crud.check_duplicate_report(
        None,
        41.8800,
        -87.6300,
        reporter_hash="shared-emulator-device",
        user_id=user_a,
    )
