"""Kabul edilmiş olaya sonradan katılan ihbarların durum testleri.

Bir olay iki bağımsız ihbarla kabul edildikten sonra aynı kümeye katılan üçüncü
ihbar 'pending' kalmamalıdır: kullanıcıya yanlış durum gösterilir ve canlı risk
hesabı yalnızca 'accepted' ihbarları saydığı için o ihbar riske katkı vermez.
"""

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


TEXTS = (
    "Silahlı çatışma var, sokak kapalı lütfen dikkat",
    "Burada silahlı kavga çıktı, çok tehlikeli",
    "Silahlı saldırı oldu, polis geldi",
    "Silahlı çatışma devam ediyor, buradan geçmeyin",
)


async def _submit(device: str, text: str):
    report = await crud.create_report(
        db=None,
        lat=41.8781,
        lng=-87.6298,
        text=text,
        category="crime",
        priority="urgent",
        reporter_installation_id=device,
    )
    event = await crud.process_report_and_event_clustering(db=None, report=report)
    return report, event


def test_late_report_joining_accepted_event_becomes_accepted(monkeypatch):
    monkeypatch.setattr(settings, "report_dev_solo_accept", False)
    monkeypatch.setattr(settings, "app_environment", "production")

    async def _run():
        _, first_event = await _submit("device-a", TEXTS[0])
        assert first_event.status == "pending"

        await _submit("device-b", TEXTS[1])
        _, accepted_event = await _submit("device-c", TEXTS[2])
        assert accepted_event.status == "accepted"

        # Olay artık kabul edilmiş durumda; bu noktadan sonra katılan ihbar da
        # doğrulanmış sayılmalı.
        late_report, late_event = await _submit("device-d", TEXTS[3])
        assert late_event.id == accepted_event.id
        assert late_event.status == "accepted"
        assert late_report.status == "accepted"

        # Kümedeki tüm ihbarlar kabul edilmiş olmalı ki canlı risk hesabına
        # girsinler.
        cluster = [
            r
            for r in crud._in_memory_reports.values()
            if r.event_id == late_event.id
        ]
        assert len(cluster) == 4
        assert {r.status for r in cluster} == {"accepted"}

        live_risk = await crud.recalculate_h3_live_risk(
            db=None, h3_index=late_event.h3_index
        )
        assert live_risk > 0.0

    asyncio.run(_run())
