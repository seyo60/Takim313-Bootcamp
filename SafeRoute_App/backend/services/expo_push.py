"""Expo Push API istemcisi (acil durum bildirimleri)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config import settings

logger = logging.getLogger("saferoute.push")


def _is_deliverable_expo_token(token: str) -> bool:
    """Yerel / kapalı / sahte token'ları Expo'ya gönderme."""
    t = (token or "").strip()
    if not t.startswith("ExponentPushToken["):
        return False
    lower = t.lower()
    if "local-" in lower or "disabled-" in lower or "fallback-" in lower:
        return False
    return True


async def send_expo_push_messages(
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Expo'ya toplu push gönderir. Boş liste veya kapalı bayrakta no-op."""
    if not messages or not settings.expo_push_enabled:
        return {"sent": 0, "tickets": []}

    messages = [
        m
        for m in messages
        if isinstance(m, dict) and _is_deliverable_expo_token(str(m.get("to") or ""))
    ]
    if not messages:
        return {"sent": 0, "tickets": []}

    # Expo tek istekte ~100 mesaj kabul eder.
    tickets: list[Any] = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
        for offset in range(0, len(messages), 100):
            chunk = messages[offset : offset + 100]
            try:
                response = await client.post(
                    settings.expo_push_url,
                    json=chunk,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                data = payload.get("data") or []
                if isinstance(data, list):
                    tickets.extend(data)
            except httpx.HTTPError:
                logger.exception("expo_push_chunk_failed", extra={"chunk_size": len(chunk)})

    return {"sent": len(messages), "tickets": tickets}


def build_expo_message(
    *,
    to: str,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "to": to,
        "sound": "default",
        "title": title[:80],
        "body": body[:220],
        "data": data or {},
        "priority": "high",
        "channelId": "emergency",
    }
