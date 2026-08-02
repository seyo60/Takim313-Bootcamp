"""Geliştirme ortamı solo ihbar kabulü testleri."""

import asyncio

import pytest

import crud
from config import settings


@pytest.fixture(autouse=True)
def reset_in_memory_reports():
    crud._in_memory_reports.clear()
    crud._in_memory_report_events.clear()
    yield
    crud._in_memory_reports.clear()
    crud._in_memory_report_events.clear()


def test_solo_dev_accept_accepts_single_report(monkeypatch):
    monkeypatch.setattr(settings, "report_dev_solo_accept", True)
    monkeypatch.setattr(settings, "app_environment", "staging")

    async def _run():
        rep = await crud.create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="Silahlı çatışma var, sokak kapalı lütfen dikkat",
            category="crime",
            priority="urgent",
            reporter_installation_id="solo-device-1",
        )
        event = await crud.process_report_and_event_clustering(db=None, report=rep)
        assert event.status == "accepted"
        live_risk = await crud.recalculate_h3_live_risk(db=None, h3_index=event.h3_index)
        assert live_risk > 0.0

    asyncio.run(_run())


def test_solo_dev_accept_disabled_in_production(monkeypatch):
    monkeypatch.setattr(settings, "report_dev_solo_accept", True)
    monkeypatch.setattr(settings, "app_environment", "production")

    async def _run():
        rep = await crud.create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="Silahlı çatışma var, sokak kapalı lütfen dikkat",
            category="crime",
            reporter_installation_id="solo-device-2",
        )
        event = await crud.process_report_and_event_clustering(db=None, report=rep)
        assert event.status == "pending"

    asyncio.run(_run())
