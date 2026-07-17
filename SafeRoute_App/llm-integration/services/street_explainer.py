# llm-integration/services/street_explainer.py
"""
Görev 1: Sokakların neden güvensiz olduğunu kısa bir metinle açıklar.

Şimdilik: mock JSON'dan StreetRiskData alır.
Sonra:    h3_heatmap tablosundan veri çekilir (repository katmanı eklenecek).
"""
from schemas.types import StreetRiskData, StreetExplanation
from services.llm_client import generate_text
from config import settings
from prompts.guardrails import (
    STREET_EXPLAINER_PROMPT,
    STREET_EXPLAINER_PROMPT_COMPACT,
    validate_llm_output,
)


async def explain_street_risk(street: StreetRiskData) -> StreetExplanation:
    """
    Bir sokağın risk verisini alır, LLM ile kısa açıklama üretir.

    Args:
        street: Sokak risk verisi (mock veya DB'den)

    Returns:
        StreetExplanation: Kullanıcıya gösterilecek açıklama
    """
    prompt = _build_prompt(street)
    system_prompt = STREET_EXPLAINER_PROMPT_COMPACT if settings.llm_mode == "live" else STREET_EXPLAINER_PROMPT
    raw_response = await generate_text(prompt, system_prompt)
    parsed = validate_llm_output(raw_response, task="street")

    return StreetExplanation(
        h3_index=street.h3_index,
        summary=parsed["summary"],
        risk_level=parsed["risk_level"],
        factors=parsed.get("factors", []),
    )


def _build_prompt(street: StreetRiskData) -> str:
    return (
        f"Sokak: {street.location_description or street.h3_index}\n"
        f"H3 Index: {street.h3_index}\n"
        f"Koordinat: ({street.lat}, {street.lng})\n"
        f"Geçmiş suç riski: {street.risk_historical}/100\n"
        f"Anlık ihbar riski: {street.risk_live}/100\n"
        f"Sosyal medya riski: {street.risk_social}/100\n"
        f"Toplam risk: {street.total_risk}/100\n"
        f"Bu sokak neden güvensiz olabilir? Sadece verilen skorlara dayanarak kısa açıkla."
    )
