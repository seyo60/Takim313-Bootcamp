"""Dengeli profil orta-yol (mesafe–risk ödünleşimi) testleri.

Dengeli profil bütçe içindeki en düşük riski değil; risk düşüşü ile sapma
arasındaki dengeyi maksimize eden adayı seçer. En düşük riskli aday safer'a kalır.
"""

from routing_profiles import RouteCandidate, select_route_candidate


def _candidate(
    signature: str,
    *,
    distance: float,
    risk: float,
    alpha: float | None,
) -> RouteCandidate:
    return RouteCandidate(
        coordinates=[[0.0, 0.0], [1.0, 1.0]],
        distance_m=distance,
        safety_score=(1.0 - risk) * 100.0,
        route_risk=risk,
        risk_coverage=100.0,
        alpha=alpha,
        path_signature=tuple(signature.split("-")),
    )


def _hyde_park_case() -> tuple[RouteCandidate, list[RouteCandidate]]:
    shortest = _candidate("S-E", distance=4669.0, risk=0.2849, alpha=None)
    candidates = [
        _candidate("S-A-E", distance=4816.0, risk=0.1762, alpha=1.0),
        _candidate("S-B-E", distance=4852.0, risk=0.1708, alpha=2.0),
        _candidate("S-C-E", distance=4965.0, risk=0.1629, alpha=8.0),
        _candidate("S-D-E", distance=5139.0, risk=0.1564, alpha=64.0),
    ]
    return shortest, candidates


def test_balanced_prefers_compromise_not_lowest_risk():
    shortest, candidates = _hyde_park_case()
    result = select_route_candidate(
        shortest=shortest,
        candidates=candidates,
        profile="balanced",
        balanced_max_detour_pct=20.0,
        safer_max_detour_pct=40.0,
        balanced_detour_penalty=2.0,
    )

    # Ceza=2 ile 4852m adayı (kısa sapma, güçlü risk düşüşü) 5139m'den yüksek skor alır.
    assert result.selected.path_signature == ("S", "B", "E")
    assert result.meaningful_safer_alternative is True


def test_safer_takes_lowest_risk_and_stays_distinct():
    shortest, candidates = _hyde_park_case()
    result = select_route_candidate(
        shortest=shortest,
        candidates=candidates,
        profile="safer",
        balanced_max_detour_pct=20.0,
        safer_max_detour_pct=40.0,
        balanced_detour_penalty=2.0,
    )

    assert result.selected.path_signature == ("S", "D", "E")
    assert result.distinct_from_balanced is True


def test_safer_risk_never_exceeds_balanced_risk():
    shortest, candidates = _hyde_park_case()
    kwargs = dict(
        shortest=shortest,
        candidates=candidates,
        balanced_max_detour_pct=20.0,
        safer_max_detour_pct=40.0,
        balanced_detour_penalty=2.0,
    )
    balanced = select_route_candidate(profile="balanced", **kwargs)
    safer = select_route_candidate(profile="safer", **kwargs)

    assert safer.selected.route_risk <= balanced.selected.route_risk + 1e-9
    assert safer.selected.distance_m >= balanced.selected.distance_m


def test_penalty_zero_preserves_legacy_lowest_risk_behaviour():
    shortest, candidates = _hyde_park_case()
    result = select_route_candidate(
        shortest=shortest,
        candidates=candidates,
        profile="balanced",
        balanced_max_detour_pct=20.0,
        safer_max_detour_pct=40.0,
        balanced_detour_penalty=0.0,
        balanced_marginal_gain_floor=0.0,
    )

    assert result.selected.path_signature == ("S", "D", "E")


def test_screenshot_like_corridor_diverges():
    """Ekran görüntüsündeki gibi ~%12 sapmada dengeli ve safer ayrışmalı."""
    shortest = _candidate("S-E", distance=2650.0, risk=0.496, alpha=None)
    candidates = [
        _candidate("S-MID-E", distance=2800.0, risk=0.380, alpha=2.0),
        _candidate("S-BAL-E", distance=2960.0, risk=0.310, alpha=8.0),
        _candidate("S-SAFE-E", distance=3000.0, risk=0.304, alpha=16.0),
    ]
    balanced = select_route_candidate(
        shortest=shortest,
        candidates=candidates,
        profile="balanced",
        balanced_max_detour_pct=20.0,
        safer_max_detour_pct=40.0,
        balanced_detour_penalty=2.0,
    )
    safer = select_route_candidate(
        shortest=shortest,
        candidates=candidates,
        profile="safer",
        balanced_max_detour_pct=20.0,
        safer_max_detour_pct=40.0,
        balanced_detour_penalty=2.0,
    )

    assert balanced.selected.path_signature != safer.selected.path_signature
    assert balanced.selected.distance_m < safer.selected.distance_m
    assert balanced.selected.route_risk > safer.selected.route_risk


def test_single_candidate_below_meaningful_threshold_falls_back():
    shortest = _candidate("S-E", distance=598.0, risk=0.5332, alpha=None)
    result = select_route_candidate(
        shortest=shortest,
        candidates=[_candidate("S-A-E", distance=600.0, risk=0.5110, alpha=1.0)],
        profile="balanced",
        balanced_max_detour_pct=20.0,
        safer_max_detour_pct=40.0,
        balanced_detour_penalty=2.0,
    )

    assert result.selected is shortest
    assert result.decision_reason == "no_meaningful_safer_alternative"
