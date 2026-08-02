"""Mesafe bütçeli çok-adaylı rota seçimi regresyon testleri."""

import numpy as np
import pytest

from routing_engine import CompactCSREngine, _build_deduplicated_csr
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


def test_balanced_selects_lowest_risk_candidate_within_15_percent():
    shortest = _candidate("S-E", distance=100.0, risk=0.80, alpha=None)
    result = select_route_candidate(
        shortest=shortest,
        candidates=[
            _candidate("S-A-E", distance=112.0, risk=0.50, alpha=2.0),
            _candidate("S-B-E", distance=124.0, risk=0.20, alpha=8.0),
        ],
        profile="balanced",
    )

    assert result.selected.path_signature == ("S", "A", "E")
    assert result.max_detour_pct == 15.0
    assert result.meaningful_safer_alternative is True
    assert result.decision_reason == "lower_risk_within_detour_budget"


def test_small_risk_improvement_does_not_create_misleading_detour():
    shortest = _candidate("S-E", distance=100.0, risk=0.70, alpha=None)
    result = select_route_candidate(
        shortest=shortest,
        candidates=[
            _candidate("S-A-E", distance=110.0, risk=0.68, alpha=4.0),
        ],
        profile="balanced",
    )

    assert result.selected is shortest
    assert result.meaningful_safer_alternative is False
    assert result.risk_reduction_pct == 0.0
    assert result.decision_reason == "no_meaningful_safer_alternative"


def test_safer_accepts_25_percent_detour_that_balanced_rejects():
    shortest = _candidate("S-E", distance=100.0, risk=0.90, alpha=None)
    candidates = [
        _candidate("S-A-E", distance=112.0, risk=0.40, alpha=2.0),
        _candidate("S-B-E", distance=125.0, risk=0.10, alpha=8.0),
    ]

    balanced = select_route_candidate(
        shortest=shortest,
        candidates=candidates,
        profile="balanced",
    )
    safer = select_route_candidate(
        shortest=shortest,
        candidates=candidates,
        profile="safer",
    )

    assert balanced.selected.path_signature == ("S", "A", "E")
    assert safer.selected.path_signature == ("S", "B", "E")
    assert safer.selected.route_risk < balanced.selected.route_risk


def test_shortest_profile_always_returns_physical_shortest():
    shortest = _candidate("S-E", distance=100.0, risk=0.90, alpha=None)
    result = select_route_candidate(
        shortest=shortest,
        candidates=[
            _candidate("S-A-E", distance=105.0, risk=0.05, alpha=16.0),
        ],
        profile="shortest",
    )

    assert result.selected is shortest
    assert result.max_detour_pct == 0.0
    assert result.decision_reason == "shortest_profile_requested"


def test_duplicate_candidate_paths_are_counted_once():
    shortest = _candidate("S-E", distance=100.0, risk=0.80, alpha=None)
    same_path_a = _candidate("S-A-E", distance=110.0, risk=0.40, alpha=2.0)
    same_path_b = _candidate("S-A-E", distance=110.0, risk=0.40, alpha=4.0)
    result = select_route_candidate(
        shortest=shortest,
        candidates=[same_path_a, same_path_b],
        profile="balanced",
    )

    assert result.candidate_count == 2
    assert result.eligible_candidate_count == 2


def test_safer_prefers_longer_route_when_risk_is_near_optimal():
    shortest = _candidate("S-E", distance=100.0, risk=0.90, alpha=None)
    candidates = [
        _candidate("S-A-E", distance=115.0, risk=0.20, alpha=2.0),
        _candidate("S-B-E", distance=135.0, risk=0.18, alpha=8.0),
    ]

    balanced = select_route_candidate(
        shortest=shortest,
        candidates=candidates,
        profile="balanced",
        balanced_max_detour_pct=20.0,
        safer_max_detour_pct=40.0,
    )
    safer = select_route_candidate(
        shortest=shortest,
        candidates=candidates,
        profile="safer",
        balanced_max_detour_pct=20.0,
        safer_max_detour_pct=40.0,
    )

    assert balanced.selected.path_signature == ("S", "A", "E")
    assert safer.selected.path_signature == ("S", "B", "E")
    assert safer.selected.distance_m > balanced.selected.distance_m
    assert safer.selected.route_risk <= balanced.selected.route_risk


def test_safer_never_worse_risk_than_balanced():
    shortest = _candidate("S-E", distance=100.0, risk=0.90, alpha=None)
    candidates = [
        _candidate("S-A-E", distance=112.0, risk=0.24, alpha=2.0),
        _candidate("S-B-E", distance=130.0, risk=0.26, alpha=8.0),
    ]

    balanced = select_route_candidate(
        shortest=shortest,
        candidates=candidates,
        profile="balanced",
        balanced_max_detour_pct=20.0,
        safer_max_detour_pct=40.0,
    )
    safer = select_route_candidate(
        shortest=shortest,
        candidates=candidates,
        profile="safer",
        balanced_max_detour_pct=20.0,
        safer_max_detour_pct=40.0,
    )

    assert safer.selected.route_risk <= balanced.selected.route_risk


def test_compact_engine_profiles_choose_distinct_detour_budgets(monkeypatch):
    """Gerçek CSR aday üretimi, profil bütçesi ve fiziksel metrik birlikte doğrulanır."""
    from config import settings

    monkeypatch.setattr(settings, "routing_candidate_alphas", "1,2,4,8,16")
    monkeypatch.setattr(settings, "routing_balanced_max_detour_pct", 15.0)
    monkeypatch.setattr(settings, "routing_safer_max_detour_pct", 25.0)
    monkeypatch.setattr(
        settings,
        "routing_min_meaningful_risk_reduction_pct",
        5.0,
    )

    engine = CompactCSREngine()
    # S=0, E=1, A=2 (105 m / risk .30), B=3 (125 m / risk .15)
    engine.node_x = np.array([0.0, 1.0, 0.4, 0.6], dtype=np.float64)
    engine.node_y = np.array([0.0, 0.0, 0.2, -0.2], dtype=np.float64)
    engine.edge_src = np.array([0, 0, 2, 0, 3], dtype=np.int32)
    engine.edge_dst = np.array([1, 2, 1, 3, 1], dtype=np.int32)
    engine.edge_length = np.array(
        [100.0, 52.5, 52.5, 62.5, 62.5],
        dtype=np.float64,
    )
    engine.N = 4
    engine.M = 5
    engine.edge_risk = np.zeros(engine.M, dtype=np.float32)
    engine.edge_has_data = np.zeros(engine.M, dtype=np.bool_)
    engine.h3_keys_map = {
        "red": np.array([0], dtype=np.int32),
        "balanced": np.array([1, 2], dtype=np.int32),
        "green": np.array([3, 4], dtype=np.int32),
    }
    engine.csr_shortest = _build_deduplicated_csr(
        engine.N,
        engine.edge_src,
        engine.edge_dst,
        engine.edge_length,
    )
    engine.csr_shortest_b = _build_deduplicated_csr(
        engine.N,
        engine.edge_dst,
        engine.edge_src,
        engine.edge_length,
    )
    engine.find_nearest_node = lambda lat, lng: (
        (0 if lng < 0.5 else 1),
        0.0,
    )
    engine.apply_risk_weights(
        {"red": 0.90, "balanced": 0.30, "green": 0.15}
    )

    balanced = engine.compute_profiled_route(
        0.0,
        0.0,
        0.0,
        1.0,
        profile="balanced",
    )
    safer = engine.compute_profiled_route(
        0.0,
        0.0,
        0.0,
        1.0,
        profile="safer",
    )

    assert balanced.selected.distance_m == pytest.approx(105.0)
    assert balanced.selected.route_risk == pytest.approx(0.30)
    assert safer.selected.distance_m == pytest.approx(125.0)
    assert safer.selected.route_risk == pytest.approx(0.15)
    assert balanced.selected.distance_m <= balanced.shortest.distance_m * 1.15
    assert safer.selected.distance_m <= safer.shortest.distance_m * 1.25
