"""Sokak risk açıklaması — deterministik kurallar + isteğe bağlı LLM."""

from __future__ import annotations

import h3
from sqlalchemy.ext.asyncio import AsyncSession

import crud
from config import settings
from h3_policy import validate_h3_resolution, LEGACY_H3_RESOLUTION
from llm_service import RiskExplanation, explain_risk_with_llm


async def build_street_risk_explanation(
    db: AsyncSession,
    *,
    lat: float,
    lng: float,
) -> dict:
    """Rota orta noktası veya harita tıklaması için risk açıklaması üretir."""
    selected_resolution = validate_h3_resolution(
        getattr(settings, "routing_h3_resolution", LEGACY_H3_RESOLUTION)
    )
    h3_idx = h3.latlng_to_cell(lat, lng, selected_resolution)
    target_point = await crud.get_heatmap_point(db, h3_idx)
    etl_info = await crud.get_latest_etl_runs(db)
    snapshot_at = etl_info.get("risk_snapshot_at")
    disclaimer = "Güvenlik skoru kesin güvenlik garantisi değildir."

    if not target_point:
        return {
            "h3_index": h3_idx,
            "risk_level": "no_data",
            "explanation": "Bu bölge için yeterli risk verisi bulunmuyor.",
            "factors": ["Tarihsel suç verisi yok", "Aydınlatma arıza bildirimi yok"],
            "channels": {"crime": 0.0, "lighting": 0.0, "live": 0.0, "total": 0.0},
            "total_risk": None,
            "crime_risk": 0.0,
            "lighting_risk": 0.0,
            "live_risk": 0.0,
            "data_available": False,
            "observed_risk_level": "Veri Yok / Belirsiz",
            "risk_snapshot_at": snapshot_at,
            "explanation_method": "deterministic_rules",
            "disclaimer": disclaimer,
        }

    risk_crime = getattr(target_point, "risk_crime", 0.0) or 0.0
    risk_lighting = getattr(target_point, "risk_lighting", 0.0) or 0.0
    risk_live = getattr(target_point, "risk_live", 0.0) or 0.0
    total_risk = max(
        0.0,
        min(1.0, float(0.65 * risk_crime + 0.20 * risk_lighting + 0.15 * risk_live)),
    )
    has_data = (
        total_risk > 0.0
        or risk_crime > 0.0
        or risk_lighting > 0.0
        or risk_live > 0.0
    )

    if not has_data:
        return {
            "h3_index": h3_idx,
            "risk_level": "no_data",
            "explanation": "Bu bölge için yeterli risk verisi bulunmuyor.",
            "factors": ["Tarihsel suç verisi yok", "Aydınlatma arıza bildirimi yok"],
            "channels": {"crime": 0.0, "lighting": 0.0, "live": 0.0, "total": 0.0},
            "total_risk": None,
            "crime_risk": round(risk_crime, 4),
            "lighting_risk": round(risk_lighting, 4),
            "live_risk": round(risk_live, 4),
            "data_available": False,
            "observed_risk_level": "Veri Yok / Belirsiz",
            "risk_snapshot_at": snapshot_at,
            "explanation_method": "deterministic_rules",
            "disclaimer": disclaimer,
        }

    if total_risk < 0.20:
        level = "low"
        obs_level = "Düşük Gözlemlenen Risk"
        exp = "Bu bölgede gözlemlenen risk verileri düşük seviyededir. Rutin güvenlik önlemlerinize devam edin."
    elif total_risk < 0.40:
        level = "low_medium"
        obs_level = "Düşük-Orta Gözlemlenen Risk"
        exp = "Bu bölgede düşük-orta seviyede risk kaydedilmiştir. Çevrenize karşı dikkatli olmanız önerilir."
    elif total_risk < 0.60:
        level = "medium"
        obs_level = "Orta Gözlemlenen Risk"
        exp = "Bu bölgede orta seviyede risk kaydedilmiştir. Çevrenize karşı dikkatli olmanız önerilir."
    elif total_risk < 0.80:
        level = "high"
        obs_level = "Yüksek Gözlemlenen Risk"
        exp = (
            "Bu bölgede yüksek suç yoğunluğu veya aydınlatma yetersizliği sinyali "
            "gözlemlenmiştir. Daha düşük tahmini riskli seçenekleri karşılaştırın."
        )
    else:
        level = "very_high"
        obs_level = "Çok Yüksek Gözlemlenen Risk"
        exp = (
            "Bu bölge için çok yüksek gözlemlenen risk sinyali vardır. "
            "Koşullar değişebilir; çevrenizi izleyin ve rota seçeneklerini karşılaştırın."
        )

    factors: list[str] = []
    if risk_crime > 0.4:
        factors.append("Tarihsel suç yoğunluğu yüksek")
    elif risk_crime > 0.1:
        factors.append("Kısmi suç geçmişi kaydedilmiş")
    if risk_lighting > 0.3:
        factors.append("Sokak aydınlatma arızaları mevcut")
    if risk_live > 0.1:
        factors.append("Son 60 dakikada canlı ihbar yapılmış")
    if not factors:
        factors = ["Gözlemlenen genel çevre analizi"]
    factors = factors[:3]

    explanation_result, explanation_method = await explain_risk_with_llm(
        crime=risk_crime,
        lighting=risk_lighting,
        live=risk_live,
        total=total_risk,
        deterministic=RiskExplanation(
            risk_level=level,
            explanation=exp,
            factors=factors,
        ),
    )

    return {
        "h3_index": h3_idx,
        "risk_level": level,
        "explanation": explanation_result.explanation,
        "factors": explanation_result.factors,
        "channels": {
            "crime": round(risk_crime * 100.0, 1),
            "lighting": round(risk_lighting * 100.0, 1),
            "live": round(risk_live * 100.0, 1),
            "total": round(total_risk * 100.0, 1),
        },
        "total_risk": round(total_risk, 4),
        "crime_risk": round(risk_crime, 4),
        "lighting_risk": round(risk_lighting, 4),
        "live_risk": round(risk_live, 4),
        "data_available": True,
        "observed_risk_level": obs_level,
        "risk_snapshot_at": snapshot_at,
        "explanation_method": explanation_method,
        "disclaimer": disclaimer,
    }
