"""DeepSeek ile acil durum push metni üretimi.

Risk seviyesi kararı vermez; yalnızca kısa, tarafsız bildirim metni üretir.
Başarısız olursa deterministik Türkçe şablona düşer.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from config import settings


class AlertCopy(BaseModel):
    title: str = Field(min_length=4, max_length=80)
    body: str = Field(min_length=10, max_length=240)

    @field_validator("title", "body")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = re.sub(r"\s+", " ", str(value)).strip()
        if not cleaned:
            raise ValueError("empty alert text")
        return cleaned


_CATEGORY_LABELS = {
    "crime": "şüpheli / suç",
    "armed_violence": "silahlı olay",
    "harassment": "taciz",
    "lighting": "aydınlatma sorunu",
    "obstacle": "yol engeli",
    "general": "güvenlik",
    "general_safety": "güvenlik",
}


def _fallback_copy(
    *,
    phase: Literal["witness_request", "broadcast"],
    category: str,
    description: str,
) -> AlertCopy:
    label = _CATEGORY_LABELS.get(category, "güvenlik")
    snippet = re.sub(r"\s+", " ", description).strip()[:90]
    if not snippet:
        snippet = f"{label} ile ilgili bir durum"
    if phase == "witness_request":
        return AlertCopy(
            title=f"Yakınınızda {label} ihbarı",
            body=(
                f"Bildirilen olay: {snippet}. "
                "1 km içindesiniz — bu olayı gördünüz mü?"
            ),
        )
    return AlertCopy(
        title=f"Doğrulandı: {label}",
        body=(
            f"Tanık onayıyla doğrulandı. Olay özeti: {snippet}. "
            "Bölgede dikkatli olun."
        ),
    )


class DeepSeekAlertCopyWriter:
    def __init__(self) -> None:
        self._failure_count = 0
        self._opened_until = 0.0
        self._lock = asyncio.Lock()

    async def compose(
        self,
        *,
        phase: Literal["witness_request", "broadcast"],
        category: str,
        description: str,
        priority: str,
    ) -> tuple[AlertCopy, str]:
        fallback = _fallback_copy(
            phase=phase, category=category, description=description
        )
        if settings.llm_mode != "live" or not settings.deepseek_api_key:
            return fallback, "deterministic_fallback"

        async with self._lock:
            if time.monotonic() < self._opened_until:
                return fallback, "deterministic_fallback_circuit_open"

        phase_instruction = (
            "Ask nearby users if they witnessed the incident. Keep a calm tone."
            if phase == "witness_request"
            else "Announce that the incident was confirmed by an independent witness."
        )
        system_prompt = (
            "You write short Turkish mobile push notifications for a pedestrian "
            "safety app. Return JSON only with keys title and body. "
            "title <= 60 chars, body <= 220 chars. "
            "CRITICAL: body MUST briefly say what kind of incident was reported "
            "(from category + raw report text) so the user understands the event. "
            "Example pattern: 'Olay: ... . Tanık doğruladı; dikkatli olun.' "
            "No certainty words like 'güvenli', 'kesinlikle', 'garanti'. "
            "Do not invent police/ambulance facts. Do not include coordinates."
        )
        user_prompt = (
            f"Phase: {phase}. {phase_instruction}\n"
            f"Category: {category}. Priority: {priority}.\n"
            f"Raw report text: {description[:400]}\n"
            "Write a concise Turkish notification that names the incident type "
            "and summarizes what happened using the report text."
        )
        request_body = {
            "model": settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": min(settings.llm_temperature, 0.4),
            "max_tokens": 220,
            "stream": False,
        }
        url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
        try:
            result = await self._request(url, request_body)
            content = result["choices"][0]["message"]["content"]
            parsed = AlertCopy.model_validate(json.loads(content))
        except (
            httpx.HTTPError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            ValidationError,
            json.JSONDecodeError,
        ):
            async with self._lock:
                self._failure_count += 1
                if self._failure_count >= 3:
                    self._opened_until = time.monotonic() + 60.0
            return fallback, "deterministic_fallback_provider_error"

        async with self._lock:
            self._failure_count = 0
            self._opened_until = 0.0
        return parsed, "deepseek_structured_output"

    async def _request(self, url: str, body: dict) -> dict:
        timeout = httpx.Timeout(6.0, connect=3.0)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.deepseek_api_key}",
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(2):
                response = await client.post(url, headers=headers, json=body)
                if response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                    await asyncio.sleep(0.25)
                    continue
                response.raise_for_status()
                return response.json()
        raise httpx.HTTPError("DeepSeek alert copy request failed")


_writer = DeepSeekAlertCopyWriter()


async def compose_emergency_alert_copy(
    *,
    phase: Literal["witness_request", "broadcast"],
    category: str,
    description: str,
    priority: str = "urgent",
) -> tuple[AlertCopy, str]:
    return await _writer.compose(
        phase=phase,
        category=category,
        description=description,
        priority=priority,
    )
