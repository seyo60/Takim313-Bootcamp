"""SafeRoute H3 çözünürlük ve çok-hücreli kenar örnekleme politikası.

Üretim verisi bugün H3 resolution 9'dadır. Resolution 10 geçişi, yalnızca
indeksi 10 yapmakla kalmaz:

* Daha küçük hücrelerde veri seyrekleştiği için yerel skor ebeveyn (res-9)
  skoru ile kanıt miktarına göre yumuşatılır.
* Bir yol kenarı tek orta noktaya değil, geometrisi boyunca birden fazla
  resolution-10 hücresine bağlanır.
* Resolution-10 hücresinde veri yoksa resolution-9 ebeveyn riski kontrollü
  geri dönüş olarak kullanılabilir.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

import h3


LEGACY_H3_RESOLUTION = 9
TARGET_H3_RESOLUTION = 10
MIN_SUPPORTED_H3_RESOLUTION = 9
MAX_SUPPORTED_H3_RESOLUTION = 10
DEFAULT_EDGE_SAMPLE_SPACING_M = 30.0

METERS_PER_DEG_LAT = 110_540.0
METERS_PER_DEG_LNG_CHICAGO = 82_900.0


def validate_h3_resolution(resolution: int) -> int:
    """SafeRoute'un kontrollü geçişte desteklediği çözünürlüğü doğrular."""
    value = int(resolution)
    if not MIN_SUPPORTED_H3_RESOLUTION <= value <= MAX_SUPPORTED_H3_RESOLUTION:
        raise ValueError(
            "SafeRoute H3 çözünürlüğü yalnızca 9 veya 10 olabilir; "
            f"alınan değer: {resolution!r}."
        )
    return value


def infer_h3_resolution(h3_index: str, default: int = LEGACY_H3_RESOLUTION) -> int:
    """Geçerli bir H3 indeksinden çözünürlüğü çıkarır; legacy veride güvenli varsayılanı kullanır."""
    try:
        return int(h3.get_resolution(str(h3_index)))
    except Exception:
        return validate_h3_resolution(default)


def parent_cell(h3_index: str, parent_resolution: int = LEGACY_H3_RESOLUTION) -> str:
    """Hücreyi istenen üst çözünürlükteki ebeveynine çevirir."""
    parent_resolution = validate_h3_resolution(parent_resolution)
    current_resolution = infer_h3_resolution(h3_index)
    if current_resolution <= parent_resolution:
        return str(h3_index)
    return str(h3.cell_to_parent(str(h3_index), parent_resolution))


def resolve_hierarchical_risk(
    h3_index: str,
    risk_lookup: dict[str, float],
    *,
    parent_resolution: int = LEGACY_H3_RESOLUTION,
    unknown_risk: float,
) -> tuple[float, bool, str | None]:
    """Önce tam hücreyi, yoksa res-9 ebeveyni, o da yoksa belirsizlik riskini döndürür."""
    key = str(h3_index)
    if key in risk_lookup:
        return _clamp01(risk_lookup[key]), True, key

    parent = parent_cell(key, parent_resolution)
    if parent != key and parent in risk_lookup:
        return _clamp01(risk_lookup[parent]), True, parent

    return _clamp01(unknown_risk), False, None


def calibrated_child_risk(
    *,
    local_raw_score: float,
    parent_raw_score: float,
    base_saturation_score: float,
    evidence: float,
    child_resolution: int,
    parent_resolution: int = LEGACY_H3_RESOLUTION,
    shrinkage_strength: float = 2.0,
) -> tuple[float, float, float, float]:
    """Resolution-10 yerel yoğunluğunu res-9 ebeveyn öncülüyle yumuşatır.

    Resolution her arttığında ortalama hücre alanı yaklaşık yediye bölünür.
    Yerel ham skor bu alan oranıyla yoğunluk eşdeğerine çevrilir. Az kanıtlı
    hücrelerin aşırı kırmızı/yeşil görünmesini engellemek için sonuç ebeveyn
    skoruna doğru ``evidence / (evidence + shrinkage_strength)`` katsayısıyla
    küçültülür.

    Dönüş: ``(nihai_risk, local_density_risk, parent_risk, evidence_weight)``.
    """
    child_resolution = validate_h3_resolution(child_resolution)
    parent_resolution = validate_h3_resolution(parent_resolution)
    if child_resolution < parent_resolution:
        raise ValueError("Çocuk çözünürlük ebeveyn çözünürlükten küçük olamaz.")
    if base_saturation_score <= 0:
        raise ValueError("base_saturation_score sıfırdan büyük olmalıdır.")
    if shrinkage_strength < 0:
        raise ValueError("shrinkage_strength negatif olamaz.")

    resolution_delta = child_resolution - parent_resolution
    area_ratio = 7.0 ** resolution_delta
    local_density_risk = _clamp01(
        float(local_raw_score) * area_ratio / float(base_saturation_score)
    )
    parent_risk = _clamp01(
        float(parent_raw_score) / float(base_saturation_score)
    )

    evidence = max(0.0, float(evidence))
    if resolution_delta == 0:
        evidence_weight = 1.0
        final_risk = local_density_risk
    elif shrinkage_strength == 0:
        evidence_weight = 1.0
        final_risk = local_density_risk
    else:
        evidence_weight = evidence / (evidence + float(shrinkage_strength))
        final_risk = (
            evidence_weight * local_density_risk
            + (1.0 - evidence_weight) * parent_risk
        )

    return (
        _clamp01(final_risk),
        local_density_risk,
        parent_risk,
        _clamp01(evidence_weight),
    )


def polyline_sample_points(
    lat_lng_points: Sequence[tuple[float, float]],
    *,
    spacing_m: float = DEFAULT_EDGE_SAMPLE_SPACING_M,
) -> list[tuple[float, float]]:
    """Bir çizgiyi Chicago için metrik aralıklarla örnekler; ilk ve son noktayı da içerir."""
    if spacing_m <= 0:
        raise ValueError("spacing_m sıfırdan büyük olmalıdır.")

    cleaned: list[tuple[float, float]] = []
    for lat, lng in lat_lng_points:
        point = (float(lat), float(lng))
        if not cleaned or point != cleaned[-1]:
            cleaned.append(point)

    if not cleaned:
        return []
    if len(cleaned) == 1:
        return cleaned

    sampled: list[tuple[float, float]] = [cleaned[0]]
    for start, end in zip(cleaned, cleaned[1:]):
        segment_m = _segment_distance_m(start, end)
        steps = max(1, int(math.ceil(segment_m / float(spacing_m))))
        for step in range(1, steps + 1):
            fraction = step / steps
            sampled.append(
                (
                    start[0] + (end[0] - start[0]) * fraction,
                    start[1] + (end[1] - start[1]) * fraction,
                )
            )
    return sampled


def polyline_h3_cells(
    lat_lng_points: Sequence[tuple[float, float]],
    *,
    resolution: int,
    spacing_m: float = DEFAULT_EDGE_SAMPLE_SPACING_M,
) -> list[str]:
    """Çizginin geçtiği H3 hücrelerini ilk görülme sırasıyla, tekrarsız döndürür."""
    resolution = validate_h3_resolution(resolution)
    ordered_cells: list[str] = []
    seen: set[str] = set()
    for lat, lng in polyline_sample_points(lat_lng_points, spacing_m=spacing_m):
        cell = str(h3.latlng_to_cell(lat, lng, resolution))
        if cell not in seen:
            seen.add(cell)
            ordered_cells.append(cell)
    return ordered_cells


def edge_lat_lng_points(graph, u, v, edge_data: dict) -> list[tuple[float, float]]:
    """NetworkX/OSMnx kenar geometrisini ``[(lat, lng), ...]`` biçiminde çıkarır."""
    geometry = edge_data.get("geometry")
    if geometry is not None and hasattr(geometry, "coords"):
        try:
            coords = [(float(lat), float(lng)) for lng, lat in geometry.coords]
            if len(coords) >= 2:
                return coords
        except Exception:
            pass

    return [
        (float(graph.nodes[u]["y"]), float(graph.nodes[u]["x"])),
        (float(graph.nodes[v]["y"]), float(graph.nodes[v]["x"])),
    ]


def aggregate_edge_cell_risks(
    risks: Iterable[float],
    *,
    max_weight: float = 0.65,
) -> float:
    """Birden çok hücreye yayılan kenar için güvenlik ağırlıklı max/ortalama birleşimi."""
    values = [_clamp01(v) for v in risks]
    if not values:
        raise ValueError("En az bir risk değeri gereklidir.")
    max_weight = _clamp01(max_weight)
    return _clamp01(
        max_weight * max(values)
        + (1.0 - max_weight) * (sum(values) / len(values))
    )


def _segment_distance_m(
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dy = (end[0] - start[0]) * METERS_PER_DEG_LAT
    dx = (end[1] - start[1]) * METERS_PER_DEG_LNG_CHICAGO
    return math.hypot(dx, dy)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
