"""Rotanın tamamı için risk açıklaması — deterministik kurallar + isteğe bağlı LLM.

Tek nokta açıklaması (``street_risk_service``) rotanın orta noktasındaki hücreyi
anlatır ve rotanın gerçek risk profilinden belirgin şekilde sapabilir. Burada
rota geometrisi boyunca örneklenen H3 hücrelerinin risk kanalları uzunluk
ağırlıklı olarak birleştirilir, böylece açıklama kullanıcıya gösterilen
``route_risk`` değeriyle tutarlı olur.
"""

from __future__ import annotations

import math

import h3
from sqlalchemy.ext.asyncio import AsyncSession

import crud
from config import settings
from h3_policy import LEGACY_H3_RESOLUTION, validate_h3_resolution
from llm_service import RiskExplanation, explain_route_with_llm


# Kanal ağırlıkları crud._compute_total_risk ile aynı kanonik politikadır.
CRIME_WEIGHT = 0.65
LIGHTING_WEIGHT = 0.20
LIVE_WEIGHT = 0.15

# Rota ne kadar uzun olsa da açıklama için sabit sayıda örnek yeterlidir.
MAX_SAMPLE_POINTS = 60
HIGH_RISK_THRESHOLD = 0.40

DISCLAIMER = "Güvenlik skoru kesin güvenlik garantisi değildir."


async def build_route_risk_explanation(
    db: AsyncSession,
    *,
    coordinates: list[list[float]],
    route_risk: float,
    profile: str,
    distance_m: float,
    detour_pct: float,
    risk_reduction_pct: float,
) -> dict:
    """Rota geometrisi boyunca birleştirilmiş risk açıklaması üretir."""
    etl_info = await crud.get_latest_etl_runs(db)
    snapshot_at = etl_info.get("risk_snapshot_at")

    resolution = validate_h3_resolution(
        getattr(settings, "routing_h3_resolution", LEGACY_H3_RESOLUTION)
    )
    samples = _sample_route_cells(coordinates, resolution)

    if not samples:
        return _no_data_response(
            snapshot_at=snapshot_at,
            route_risk=route_risk,
            sampled_cell_count=0,
        )

    points = await crud.get_heatmap_points_by_indices(
        db,
        [cell for cell, _weight in samples],
        h3_resolution=resolution,
    )

    total_weight = 0.0
    covered_weight = 0.0
    high_risk_weight = 0.0
    crime_sum = 0.0
    lighting_sum = 0.0
    live_sum = 0.0

    for cell, weight in samples:
        total_weight += weight
        point = points.get(cell)
        if point is None:
            continue
        crime = float(getattr(point, "risk_crime", 0.0) or 0.0)
        lighting = float(getattr(point, "risk_lighting", 0.0) or 0.0)
        live = float(getattr(point, "risk_live", 0.0) or 0.0)
        cell_total = _weighted_total(crime, lighting, live)
        if cell_total <= 0.0 and crime <= 0.0 and lighting <= 0.0 and live <= 0.0:
            continue

        covered_weight += weight
        crime_sum += crime * weight
        lighting_sum += lighting * weight
        live_sum += live * weight
        if cell_total >= HIGH_RISK_THRESHOLD:
            high_risk_weight += weight

    if covered_weight <= 0.0:
        return _no_data_response(
            snapshot_at=snapshot_at,
            route_risk=route_risk,
            sampled_cell_count=len(samples),
        )

    crime_avg = crime_sum / covered_weight
    lighting_avg = lighting_sum / covered_weight
    live_avg = live_sum / covered_weight
    total_avg = _weighted_total(crime_avg, lighting_avg, live_avg)
    coverage_pct = (covered_weight / total_weight * 100.0) if total_weight > 0 else 0.0
    high_risk_share_pct = (
        (high_risk_weight / covered_weight * 100.0) if covered_weight > 0 else 0.0
    )

    level, observed_level, deterministic_text = _classify(
        total_avg,
        profile=profile,
        high_risk_share_pct=high_risk_share_pct,
        risk_reduction_pct=risk_reduction_pct,
    )
    factors = _build_factors(
        crime=crime_avg,
        lighting=lighting_avg,
        live=live_avg,
        high_risk_share_pct=high_risk_share_pct,
        risk_reduction_pct=risk_reduction_pct,
    )

    explanation_result, explanation_method = await explain_route_with_llm(
        crime=crime_avg,
        lighting=lighting_avg,
        live=live_avg,
        total=total_avg,
        profile=str(profile),
        distance_m=float(distance_m),
        detour_pct=float(detour_pct),
        risk_reduction_pct=float(risk_reduction_pct),
        high_risk_share_pct=high_risk_share_pct,
        deterministic=RiskExplanation(
            risk_level=level,
            explanation=deterministic_text,
            factors=factors,
        ),
    )

    return {
        "risk_level": level,
        "explanation": explanation_result.explanation,
        "factors": explanation_result.factors,
        "channels": {
            "crime": round(crime_avg * 100.0, 1),
            "lighting": round(lighting_avg * 100.0, 1),
            "live": round(live_avg * 100.0, 1),
            "total": round(total_avg * 100.0, 1),
        },
        "total_risk": round(total_avg, 4),
        "crime_risk": round(crime_avg, 4),
        "lighting_risk": round(lighting_avg, 4),
        "live_risk": round(live_avg, 4),
        "route_risk": round(float(route_risk), 4),
        "high_risk_share_pct": round(high_risk_share_pct, 1),
        "data_coverage_pct": round(coverage_pct, 1),
        "sampled_cell_count": len(samples),
        "data_available": True,
        "observed_risk_level": observed_level,
        "risk_snapshot_at": snapshot_at,
        "explanation_method": explanation_method,
        "disclaimer": DISCLAIMER,
    }


def _weighted_total(crime: float, lighting: float, live: float) -> float:
    return max(
        0.0,
        min(
            1.0,
            CRIME_WEIGHT * crime + LIGHTING_WEIGHT * lighting + LIVE_WEIGHT * live,
        ),
    )


def _sample_route_cells(
    coordinates: list[list[float]],
    resolution: int,
) -> list[tuple[str, float]]:
    """Rota parçalarını H3 hücrelerine indirger ve uzunluk ağırlığı üretir.

    Ağırlık, ilgili hücrede yürünen yaklaşık metre uzunluğudur; böylece uzun
    caddeler kısa ara sokaklardan daha fazla etkiler.
    """
    if not coordinates or len(coordinates) < 2:
        if coordinates:
            lng, lat = float(coordinates[0][0]), float(coordinates[0][1])
            return [(h3.latlng_to_cell(lat, lng, resolution), 1.0)]
        return []

    step = max(1, math.ceil((len(coordinates) - 1) / MAX_SAMPLE_POINTS))
    weights: dict[str, float] = {}

    for index in range(0, len(coordinates) - 1, step):
        start = coordinates[index]
        end = coordinates[min(index + step, len(coordinates) - 1)]
        segment_m = _planar_meters(start, end)
        if segment_m <= 0.0:
            segment_m = 1.0
        mid_lat = (float(start[1]) + float(end[1])) / 2.0
        mid_lng = (float(start[0]) + float(end[0])) / 2.0
        cell = h3.latlng_to_cell(mid_lat, mid_lng, resolution)
        weights[cell] = weights.get(cell, 0.0) + segment_m

    return list(weights.items())


def _planar_meters(start: list[float], end: list[float]) -> float:
    lat_ref = math.radians((float(start[1]) + float(end[1])) / 2.0)
    dx = (float(end[0]) - float(start[0])) * 111320.0 * math.cos(lat_ref)
    dy = (float(end[1]) - float(start[1])) * 110574.0
    return math.hypot(dx, dy)


def _classify(
    total_risk: float,
    *,
    profile: str,
    high_risk_share_pct: float,
    risk_reduction_pct: float,
) -> tuple[str, str, str]:
    if total_risk < 0.20:
        level = "low"
        observed = "Düşük Gözlemlenen Risk"
        base = "Rota boyunca gözlemlenen risk verileri düşük seviyededir."
    elif total_risk < 0.40:
        level = "low_medium"
        observed = "Düşük-Orta Gözlemlenen Risk"
        base = "Rota boyunca düşük-orta seviyede risk kaydedilmiştir."
    elif total_risk < 0.60:
        level = "medium"
        observed = "Orta Gözlemlenen Risk"
        base = "Rota boyunca orta seviyede risk kaydedilmiştir."
    elif total_risk < 0.80:
        level = "high"
        observed = "Yüksek Gözlemlenen Risk"
        base = (
            "Rota boyunca yüksek suç yoğunluğu veya aydınlatma yetersizliği "
            "sinyali gözlemlenmiştir."
        )
    else:
        level = "very_high"
        observed = "Çok Yüksek Gözlemlenen Risk"
        base = "Rota boyunca çok yüksek gözlemlenen risk sinyali vardır."

    details: list[str] = []
    if risk_reduction_pct >= 1.0:
        details.append(
            f"En kısa rotaya göre tahmini risk %{risk_reduction_pct:.0f} daha düşüktür"
        )
    if high_risk_share_pct >= 5.0:
        details.append(
            f"Rotanın yaklaşık %{high_risk_share_pct:.0f}'i daha riskli hücrelerden geçiyor"
        )
    if str(profile) == "shortest":
        details.append("En kısa rota tercih edildiği için risk azaltımı uygulanmadı")

    suffix = ". ".join(details)
    text = f"{base} {suffix}." if suffix else base
    return level, observed, text.strip()


def _build_factors(
    *,
    crime: float,
    lighting: float,
    live: float,
    high_risk_share_pct: float,
    risk_reduction_pct: float,
) -> list[str]:
    factors: list[str] = []
    if crime > 0.4:
        factors.append("Rota boyunca tarihsel suç yoğunluğu yüksek")
    elif crime > 0.1:
        factors.append("Rota boyunca kısmi suç geçmişi kaydedilmiş")
    if lighting > 0.3:
        factors.append("Güzergâhta sokak aydınlatma arızaları mevcut")
    if live > 0.05:
        factors.append("Güzergâhta yakın zamanlı canlı ihbar var")
    if high_risk_share_pct >= 20.0:
        factors.append("Rotanın belirgin bir bölümü daha riskli hücrelerden geçiyor")
    elif risk_reduction_pct >= 5.0:
        factors.append("Daha düşük tahmini riskli alternatif güzergâh seçildi")
    if not factors:
        factors = ["Gözlemlenen genel çevre analizi"]
    return factors[:3]


def _no_data_response(
    *,
    snapshot_at,
    route_risk: float,
    sampled_cell_count: int,
) -> dict:
    return {
        "risk_level": "no_data",
        "explanation": "Bu güzergâh için yeterli risk verisi bulunmuyor.",
        "factors": ["Tarihsel suç verisi yok", "Aydınlatma arıza bildirimi yok"],
        "channels": {"crime": 0.0, "lighting": 0.0, "live": 0.0, "total": 0.0},
        "total_risk": None,
        "crime_risk": 0.0,
        "lighting_risk": 0.0,
        "live_risk": 0.0,
        "route_risk": round(float(route_risk), 4),
        "high_risk_share_pct": 0.0,
        "data_coverage_pct": 0.0,
        "sampled_cell_count": sampled_cell_count,
        "data_available": False,
        "observed_risk_level": "Veri Yok / Belirsiz",
        "risk_snapshot_at": snapshot_at,
        "explanation_method": "deterministic_rules",
        "disclaimer": DISCLAIMER,
    }
