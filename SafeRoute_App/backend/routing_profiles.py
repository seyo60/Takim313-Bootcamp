"""Sapma bütçeli çok-adaylı rota seçimi için saf politika katmanı.

Bu modül graf motorundan bağımsızdır. NetworkX ve Compact CSR motorları farklı
risk şiddetleriyle aday yollar üretir; burada ise adaylar:

1. Aynı düğüm dizisine sahip tekrarlar elenerek,
2. Profilin fiziksel mesafe bütçesine göre süzülerek,
3. Gerçek uzunluk-ağırlıklı ``route_risk`` değerine göre

seçilir. Maliyet fonksiyonu yalnızca aday üretir; nihai karar maliyetin yapay
"metre eşdeğeri" üzerinden verilmez.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal, Sequence


RouteProfile = Literal["shortest", "balanced", "safer"]
SUPPORTED_ROUTE_PROFILES: tuple[RouteProfile, ...] = (
    "shortest",
    "balanced",
    "safer",
)
DEFAULT_CANDIDATE_ALPHAS: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 16.0)


@dataclass(frozen=True)
class RouteCandidate:
    """Bir graf motorunun ürettiği, fiziksel metrikleri hesaplanmış aday rota."""

    coordinates: list[list[float]]
    distance_m: float
    safety_score: float
    route_risk: float
    risk_coverage: float
    alpha: float | None
    path_signature: tuple[str, ...]
    edge_signature: tuple[str, ...] = ()
    street_names: tuple[str | None, ...] = ()
    way_types: tuple[str | None, ...] = ()

    def legacy_tuple(self) -> tuple[list[list[float]], float, float, float, float]:
        """Mevcut motorların beş alanlı dönüş sözleşmesini korur."""
        return (
            self.coordinates,
            self.distance_m,
            self.safety_score,
            self.route_risk,
            self.risk_coverage,
        )


@dataclass(frozen=True)
class RouteSelectionResult:
    """Profil politikasından çıkan seçili ve referans en kısa rota."""

    selected: RouteCandidate
    shortest: RouteCandidate
    requested_profile: RouteProfile
    max_detour_pct: float
    candidate_count: int
    eligible_candidate_count: int
    meaningful_safer_alternative: bool
    risk_reduction_pct: float
    decision_reason: str
    distinct_from_balanced: bool = True


def parse_candidate_alphas(
    raw_value: str | Sequence[float] | None,
    *,
    required_alpha: float | None = None,
) -> tuple[float, ...]:
    """Environment veya Python dizisinden güvenli, sıralı alpha listesi üretir."""
    if raw_value is None:
        values = list(DEFAULT_CANDIDATE_ALPHAS)
    elif isinstance(raw_value, str):
        values = [
            float(item.strip())
            for item in raw_value.split(",")
            if item.strip()
        ]
    else:
        values = [float(item) for item in raw_value]

    if required_alpha is not None:
        values.append(float(required_alpha))

    cleaned: set[float] = set()
    for value in values:
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(
                "Rota aday alpha değerleri sonlu ve sıfırdan büyük olmalıdır."
            )
        cleaned.add(round(float(value), 8))

    if not cleaned:
        raise ValueError("En az bir pozitif rota aday alpha değeri gereklidir.")
    return tuple(sorted(cleaned))


def normalize_route_profile(profile: str | None) -> RouteProfile:
    value = str(profile or "balanced").strip().lower()
    if value not in SUPPORTED_ROUTE_PROFILES:
        raise ValueError(
            f"Geçersiz rota profili {profile!r}; "
            f"desteklenenler: {', '.join(SUPPORTED_ROUTE_PROFILES)}."
        )
    return value  # type: ignore[return-value]


def select_route_candidate(
    *,
    shortest: RouteCandidate,
    candidates: Sequence[RouteCandidate],
    profile: str,
    balanced_max_detour_pct: float = 15.0,
    safer_max_detour_pct: float = 25.0,
    min_meaningful_risk_reduction_pct: float = 5.0,
    balanced_marginal_gain_floor: float = 0.0,
    balanced_detour_penalty: float = 2.0,
) -> RouteSelectionResult:
    """Adaylar arasından profil bütçesine uyan en düşük riskli rotayı seçer."""
    normalized_profile = normalize_route_profile(profile)
    _validate_policy_percent(
        balanced_max_detour_pct,
        "balanced_max_detour_pct",
    )
    _validate_policy_percent(safer_max_detour_pct, "safer_max_detour_pct")
    _validate_policy_percent(
        min_meaningful_risk_reduction_pct,
        "min_meaningful_risk_reduction_pct",
    )
    if safer_max_detour_pct < balanced_max_detour_pct:
        raise ValueError("Daha güvenli profil bütçesi dengeli profilden küçük olamaz.")

    unique_by_path: dict[tuple[str, ...], RouteCandidate] = {
        shortest.path_signature: shortest
    }
    for candidate in candidates:
        existing = unique_by_path.get(candidate.path_signature)
        if existing is None or (
            candidate.route_risk,
            candidate.distance_m,
        ) < (
            existing.route_risk,
            existing.distance_m,
        ):
            unique_by_path[candidate.path_signature] = candidate

    unique_candidates = list(unique_by_path.values())
    if normalized_profile == "shortest":
        return RouteSelectionResult(
            selected=shortest,
            shortest=shortest,
            requested_profile=normalized_profile,
            max_detour_pct=0.0,
            candidate_count=len(unique_candidates),
            eligible_candidate_count=1,
            meaningful_safer_alternative=False,
            risk_reduction_pct=0.0,
            decision_reason="shortest_profile_requested",
        )

    max_detour_pct = (
        float(balanced_max_detour_pct)
        if normalized_profile == "balanced"
        else float(safer_max_detour_pct)
    )
    max_distance_m = shortest.distance_m * (1.0 + max_detour_pct / 100.0)
    tolerance_m = max(0.01, shortest.distance_m * 1e-9)
    eligible = [
        candidate
        for candidate in unique_candidates
        if candidate.distance_m <= max_distance_m + tolerance_m
    ]
    if not eligible:
        eligible = [shortest]

    if normalized_profile == "safer":
        balanced_max_distance_m = shortest.distance_m * (
            1.0 + float(balanced_max_detour_pct) / 100.0
        )
        within_balanced = [
            candidate
            for candidate in eligible
            if candidate.distance_m <= balanced_max_distance_m + tolerance_m
        ]
        balanced_best = _select_balanced_best(
            within_balanced or eligible,
            shortest=shortest,
            marginal_gain_floor=balanced_marginal_gain_floor,
            detour_penalty=balanced_detour_penalty,
        )
        beyond_balanced = [
            candidate
            for candidate in eligible
            if candidate.distance_m > balanced_max_distance_m + tolerance_m
        ]
        if beyond_balanced:
            safer_only = min(
                beyond_balanced,
                key=lambda item: (
                    item.route_risk,
                    -item.distance_m,
                    float("inf") if item.alpha is None else item.alpha,
                ),
            )
            if safer_only.route_risk + 1e-9 < balanced_best.route_risk:
                best = safer_only
            else:
                same_or_better = [
                    candidate
                    for candidate in eligible
                    if candidate.route_risk <= balanced_best.route_risk + 1e-9
                ]
                best = max(
                    same_or_better,
                    key=lambda item: (
                        item.distance_m,
                        -item.route_risk,
                        float("-inf") if item.alpha is None else -item.alpha,
                    ),
                )
        else:
            same_or_better = [
                candidate
                for candidate in eligible
                if candidate.route_risk <= balanced_best.route_risk + 1e-9
            ]
            best = max(
                same_or_better,
                key=lambda item: (
                    item.distance_m,
                    -item.route_risk,
                    float("-inf") if item.alpha is None else -item.alpha,
                ),
            )
        distinct_from_balanced = (
            best.path_signature != balanced_best.path_signature
        )
    else:
        distinct_from_balanced = True
        best = _select_balanced_best(
            eligible,
            shortest=shortest,
            marginal_gain_floor=balanced_marginal_gain_floor,
            detour_penalty=balanced_detour_penalty,
        )
    risk_reduction_pct = _risk_reduction_pct(
        shortest.route_risk,
        best.route_risk,
    )
    meaningful = (
        best.path_signature != shortest.path_signature
        and risk_reduction_pct + 1e-9
        >= float(min_meaningful_risk_reduction_pct)
    )

    if not meaningful:
        return RouteSelectionResult(
            selected=shortest,
            shortest=shortest,
            requested_profile=normalized_profile,
            max_detour_pct=max_detour_pct,
            candidate_count=len(unique_candidates),
            eligible_candidate_count=len(eligible),
            meaningful_safer_alternative=False,
            risk_reduction_pct=0.0,
            decision_reason="no_meaningful_safer_alternative",
        )

    return RouteSelectionResult(
        selected=best,
        shortest=shortest,
        requested_profile=normalized_profile,
        max_detour_pct=max_detour_pct,
        candidate_count=len(unique_candidates),
        eligible_candidate_count=len(eligible),
        meaningful_safer_alternative=True,
        risk_reduction_pct=round(risk_reduction_pct, 4),
        decision_reason="lower_risk_within_detour_budget",
        distinct_from_balanced=distinct_from_balanced,
    )


def _select_balanced_best(
    eligible: Sequence[RouteCandidate],
    *,
    shortest: RouteCandidate,
    marginal_gain_floor: float,
    detour_penalty: float = 2.0,
) -> RouteCandidate:
    """Dengeli profil için mesafe–risk ödünleşimini (orta yol) seçer.

    Kullanıcı beklentisi: dengeli rota "en güvenli" değil, yolu çok uzatmadan
    kabul edilebilir risk düşüşü sağlayan ortadır. Bütçe içindeki en düşük
    riskli aday çoğu zaman safer ile çöker; bu yüzden verimli sınır üzerinde

        skor = risk_düşüşü_% − ceza × sapma_%

    maksimize edilir. ``detour_penalty`` / ``marginal_gain_floor`` sıfırsa eski
    davranış (bütçe içinde en düşük risk) korunur.
    """
    lowest_risk = min(
        eligible,
        key=lambda item: (
            item.route_risk,
            item.distance_m,
            float("inf") if item.alpha is None else item.alpha,
        ),
    )
    floor = float(marginal_gain_floor)
    penalty = float(detour_penalty)
    if shortest.distance_m <= 0.0 or shortest.route_risk <= 0.0:
        return lowest_risk
    if penalty <= 0.0 and floor <= 0.0:
        return lowest_risk

    frontier = _efficient_frontier(eligible)
    if not frontier:
        return lowest_risk

    if penalty > 0.0:
        best = frontier[0]
        best_score = float("-inf")
        for candidate in frontier:
            detour_pct = max(
                0.0,
                (candidate.distance_m / shortest.distance_m - 1.0) * 100.0,
            )
            risk_drop = _risk_reduction_pct(
                shortest.route_risk, candidate.route_risk
            )
            score = risk_drop - penalty * detour_pct
            if score > best_score + 1e-9 or (
                abs(score - best_score) <= 1e-9
                and candidate.distance_m < best.distance_m
            ):
                best = candidate
                best_score = score
        return best

    if len(frontier) < 2:
        return lowest_risk

    selected = frontier[0]
    for previous, candidate in zip(frontier, frontier[1:]):
        extra_detour_pct = (
            (candidate.distance_m - previous.distance_m)
            / shortest.distance_m
            * 100.0
        )
        if extra_detour_pct <= 1e-9:
            selected = candidate
            continue
        risk_gain_pct = (
            (previous.route_risk - candidate.route_risk)
            / shortest.route_risk
            * 100.0
        )
        if risk_gain_pct / extra_detour_pct + 1e-9 < floor:
            break
        selected = candidate
    return selected


def _efficient_frontier(
    eligible: Sequence[RouteCandidate],
) -> list[RouteCandidate]:
    """Adaylardan (mesafe, risk) düzleminde alt konveks zarfı çıkarır.

    İki aşamalıdır: önce Pareto zinciri (mesafe artarken risk kesin azalan
    adaylar), sonra bu zincirin alt konveks zarfı. Zarf, "biraz daha uzun ama
    riski neredeyse aynı" ara adayları eleyerek marjinal verim ölçümünün bu tür
    gürültüde erken durmasını engeller.
    """
    ordered = sorted(
        eligible,
        key=lambda item: (item.distance_m, item.route_risk),
    )
    chain: list[RouteCandidate] = []
    for candidate in ordered:
        if chain and candidate.route_risk >= chain[-1].route_risk - 1e-12:
            continue
        chain.append(candidate)
    if len(chain) < 3:
        return chain

    def _slope(left: RouteCandidate, right: RouteCandidate) -> float:
        span = right.distance_m - left.distance_m
        if span <= 0.0:
            return float("-inf")
        return (right.route_risk - left.route_risk) / span

    hull: list[RouteCandidate] = []
    for candidate in chain:
        while len(hull) >= 2 and _slope(hull[-2], hull[-1]) >= _slope(
            hull[-2], candidate
        ):
            hull.pop()
        hull.append(candidate)
    return hull


def _risk_reduction_pct(shortest_risk: float, candidate_risk: float) -> float:
    shortest_value = max(0.0, min(1.0, float(shortest_risk)))
    candidate_value = max(0.0, min(1.0, float(candidate_risk)))
    if shortest_value <= 0.0 or candidate_value >= shortest_value:
        return 0.0
    return (shortest_value - candidate_value) / shortest_value * 100.0


def _validate_policy_percent(value: float, field_name: str) -> None:
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 100.0:
        raise ValueError(f"{field_name} 0–100 arasında sonlu bir değer olmalıdır.")
