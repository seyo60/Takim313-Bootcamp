"""Acil bildirim metni: DeepSeek kapalıyken deterministik şablon."""

import asyncio

from services.emergency_alert_llm import compose_emergency_alert_copy


def test_witness_request_fallback_copy(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "llm_mode", "off")

    async def _run():
        copy, method = await compose_emergency_alert_copy(
            phase="witness_request",
            category="armed_violence",
            description="Silahlı çatışma var sokak kapalı",
            priority="urgent",
        )
        assert method.startswith("deterministic")
        assert "gördünüz mü" in copy.body.casefold() or "gördünüz mü" in copy.body
        assert len(copy.title) >= 4
        assert len(copy.body) >= 10

    asyncio.run(_run())


def test_broadcast_fallback_copy(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "llm_mode", "off")

    async def _run():
        copy, method = await compose_emergency_alert_copy(
            phase="broadcast",
            category="crime",
            description="Şüpheli durum bildirildi",
        )
        assert "doğrul" in copy.title.casefold() or "doğrul" in copy.body.casefold()
        assert method.startswith("deterministic")

    asyncio.run(_run())
