"""Optional DeepSeek explanation adapter with deterministic fail-closed fallback."""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from config import settings


FORBIDDEN_CERTAINTY_WORDS = {
    "guarantee",
    "guaranteed",
    "safe",
    "safest",
    "güvenli",
    "tehlikesiz",
    "kesinlikle",
}


MAX_EXPLANATION_CHARS = 320
MAX_FACTORS = 3


class RiskExplanation(BaseModel):
    risk_level: Literal["low", "low_medium", "medium", "high", "very_high"]
    explanation: str = Field(min_length=10, max_length=MAX_EXPLANATION_CHARS)
    factors: list[str] = Field(min_length=1, max_length=MAX_FACTORS)

    @field_validator("explanation")
    @classmethod
    def reject_certainty_language(cls, value: str) -> str:
        lowered = value.casefold()
        if any(
            re.search(rf"(?<!\w){re.escape(word)}(?!\w)", lowered)
            for word in FORBIDDEN_CERTAINTY_WORDS
        ):
            raise ValueError("certainty language is not allowed")
        return value.strip()

    @field_validator("factors")
    @classmethod
    def validate_factors(cls, values: list[str]) -> list[str]:
        cleaned = [str(value).strip()[:100] for value in values if str(value).strip()]
        if not cleaned:
            raise ValueError("at least one factor is required")
        return cleaned[:3]


def _truncate_to_sentence(text: str, limit: int) -> str:
    """Metni sınıra indirirken mümkünse tam cümlede keser."""
    if len(text) <= limit:
        return text
    window = text[:limit]
    sentence_end = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if sentence_end >= 40:
        return window[: sentence_end + 1].strip()
    word_end = window.rfind(" ")
    return (window[:word_end] if word_end >= 40 else window).strip()


def parse_llm_explanation(raw_text: str) -> RiskExplanation:
    """LLM yanıtını biçim sınırlarına indirger ve doğrular.

    Açıklama uzunluğu ve faktör sayısı yalnızca sunum kısıtlarıdır; sağlayıcı
    bunları aştığında yanıtın tamamını atmak yerine kırpmak daha iyi sonuç
    verir. Risk seviyesi tutarlılığı ve yasaklı kesinlik ifadeleri denetimi
    ise şemada olduğu gibi uygulanmaya devam eder.
    """
    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        raise ValueError("LLM response is not a JSON object")

    explanation = str(payload.get("explanation", "")).strip()
    factors = payload.get("factors") or []
    if isinstance(factors, str):
        factors = [factors]

    payload["explanation"] = _truncate_to_sentence(explanation, MAX_EXPLANATION_CHARS)
    payload["factors"] = [str(factor) for factor in factors][:MAX_FACTORS]
    return RiskExplanation.model_validate(payload)


class DeepSeekRiskExplainer:
    def __init__(self) -> None:
        self._failure_count = 0
        self._opened_until = 0.0
        self._lock = asyncio.Lock()

    async def explain(
        self,
        *,
        crime: float,
        lighting: float,
        live: float,
        total: float,
        deterministic: RiskExplanation,
    ) -> tuple[RiskExplanation, str]:
        if settings.llm_mode != "live" or settings.llm_provider != "deepseek":
            return deterministic, "deterministic_rules"
        if not settings.deepseek_api_key:
            return deterministic, "deterministic_fallback_missing_key"
        if time.monotonic() < self._opened_until:
            return deterministic, "deterministic_fallback_circuit_open"

        system_prompt = (
            "You explain aggregate pedestrian risk signals. Return only one valid JSON object. "
            'Use exactly this JSON shape: {"risk_level":"low|low_medium|medium|high|very_high",'
            '"explanation":"Turkish explanation","factors":["factor"]}. '
            "Do not claim certainty, safety, danger-free conditions, or tell the user that a place "
            "is safe. Describe the observed estimate and changing conditions. Do not invent facts. "
            "Keep the explanation under 280 characters and return at most 3 short factors."
        )
        user_prompt = (
            "Return JSON in Turkish for these canonical inputs. "
            f"Canonical inputs (0..1): crime={crime:.4f}, lighting={lighting:.4f}, "
            f"community={live:.4f}, weighted_total={total:.4f}.\n"
            f"The deterministic level that must not change is: {deterministic.risk_level}."
        )
        request_body = {
            "model": settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": settings.llm_temperature,
            "max_tokens": min(settings.llm_max_tokens, 512),
            "stream": False,
        }
        url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"

        try:
            result = await self._request_with_retry(url, request_body)
            candidate = result["choices"][0]
            if candidate.get("finish_reason") != "stop":
                raise ValueError("DeepSeek response did not finish normally")
            parsed = parse_llm_explanation(candidate["message"]["content"])
            if parsed.risk_level != deterministic.risk_level:
                raise ValueError("DeepSeek attempted to change the canonical risk level")
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, ValidationError, json.JSONDecodeError):
            async with self._lock:
                self._failure_count += 1
                if self._failure_count >= 3:
                    self._opened_until = time.monotonic() + 60.0
            return deterministic, "deterministic_fallback_provider_error"

        async with self._lock:
            self._failure_count = 0
            self._opened_until = 0.0
        return parsed, "deepseek_structured_output"

    async def explain_route(
        self,
        *,
        crime: float,
        lighting: float,
        live: float,
        total: float,
        profile: str,
        distance_m: float,
        detour_pct: float,
        risk_reduction_pct: float,
        high_risk_share_pct: float,
        deterministic: RiskExplanation,
    ) -> tuple[RiskExplanation, str]:
        """Rotanın tamamı için açıklama üretir.

        Tek nokta açıklamasından farkı, LLM'e rota bağlamının (profil, sapma,
        en kısa rotaya göre risk değişimi, yüksek riskli bölüm oranı) de
        verilmesidir. Deterministik risk seviyesi burada da değiştirilemez.
        """
        if settings.llm_mode != "live" or settings.llm_provider != "deepseek":
            return deterministic, "deterministic_rules"
        if not settings.deepseek_api_key:
            return deterministic, "deterministic_fallback_missing_key"
        if time.monotonic() < self._opened_until:
            return deterministic, "deterministic_fallback_circuit_open"

        system_prompt = (
            "You explain aggregate pedestrian risk signals for a walking route. "
            "Return only one valid JSON object. Use exactly this JSON shape: "
            '{"risk_level":"low|low_medium|medium|high|very_high",'
            '"explanation":"Turkish explanation","factors":["factor"]}. '
            "Describe the route as a whole, not a single spot. Do not claim certainty, "
            "safety, or danger-free conditions, and never tell the user a route is safe. "
            "Do not invent facts or street names. Keep the explanation under 280 characters "
            "and return at most 3 short factors."
        )
        user_prompt = (
            "Return JSON in Turkish describing this walking route's aggregate risk. "
            f"Route-averaged canonical inputs (0..1): crime={crime:.4f}, "
            f"lighting={lighting:.4f}, community={live:.4f}, weighted_total={total:.4f}.\n"
            f"Profile requested: {profile}. Route length: {distance_m:.0f} meters, "
            f"{detour_pct:.1f}% longer than the shortest route, and the estimated risk "
            f"is {risk_reduction_pct:.1f}% lower than the shortest route. "
            f"About {high_risk_share_pct:.1f}% of the route length falls in "
            "higher-risk cells.\n"
            f"The deterministic level that must not change is: {deterministic.risk_level}."
        )
        request_body = {
            "model": settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": settings.llm_temperature,
            "max_tokens": min(settings.llm_max_tokens, 512),
            "stream": False,
        }
        url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"

        try:
            result = await self._request_with_retry(url, request_body)
            candidate = result["choices"][0]
            if candidate.get("finish_reason") != "stop":
                raise ValueError("DeepSeek response did not finish normally")
            parsed = parse_llm_explanation(candidate["message"]["content"])
            if parsed.risk_level != deterministic.risk_level:
                raise ValueError("DeepSeek attempted to change the canonical risk level")
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
            return deterministic, "deterministic_fallback_provider_error"

        async with self._lock:
            self._failure_count = 0
            self._opened_until = 0.0
        return parsed, "deepseek_structured_output"

    async def _request_with_retry(self, url: str, body: dict) -> dict:
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
        raise httpx.HTTPError("DeepSeek request exhausted retries")


_explainer = DeepSeekRiskExplainer()


async def explain_risk_with_llm(
    *,
    crime: float,
    lighting: float,
    live: float,
    total: float,
    deterministic: RiskExplanation,
) -> tuple[RiskExplanation, str]:
    return await _explainer.explain(
        crime=crime,
        lighting=lighting,
        live=live,
        total=total,
        deterministic=deterministic,
    )


async def explain_route_with_llm(
    *,
    crime: float,
    lighting: float,
    live: float,
    total: float,
    profile: str,
    distance_m: float,
    detour_pct: float,
    risk_reduction_pct: float,
    high_risk_share_pct: float,
    deterministic: RiskExplanation,
) -> tuple[RiskExplanation, str]:
    return await _explainer.explain_route(
        crime=crime,
        lighting=lighting,
        live=live,
        total=total,
        profile=profile,
        distance_m=distance_m,
        detour_pct=detour_pct,
        risk_reduction_pct=risk_reduction_pct,
        high_risk_share_pct=high_risk_share_pct,
        deterministic=deterministic,
    )
