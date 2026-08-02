"""Bütçe bandında eksik alpha adaylarını ikili arama ile doldurur.

Lagrange/dualite boşluğunda sabit alpha ızgarası %5–%25 aralığına aday
üretemeyebilir. Hedef sapma yüzdesine en yakın rotayı bulmak için alpha
üzerinde ikili arama yapılır (Adım 4 / LARAC öncesi pratik adım).
"""

from __future__ import annotations

import numpy as np

from routing_cost import risk_adjusted_lengths
from routing_profiles import RouteCandidate


def bracket_alpha_candidates(
    *,
    start_idx: int,
    end_idx: int,
    shortest_distance_m: float,
    edge_length: np.ndarray,
    edge_risk: np.ndarray,
    red_threshold: float,
    red_penalty: float,
    target_detour_pcts: tuple[float, ...],
    build_csr_pair,
    path_for_matrices,
    candidate_from_path,
    alpha_lo: float = 1.0,
    alpha_hi: float = 64.0,
    max_steps: int = 6,
) -> list[RouteCandidate]:
    """Hedef sapma yüzdelerine yakın rotalar için alpha ikili araması.

    Arama sırasında ziyaret edilen her bütçe uyumlu aday da havuza eklenir;
    bunlar zaten hesaplandığı için ek maliyet getirmez ve profil seçimine
    daha geniş bir geometri kümesi sunar.
    """
    if shortest_distance_m <= 0.0 or not target_detour_pcts:
        return []

    candidates: list[RouteCandidate] = []
    seen: set[tuple[str, ...]] = set()

    for target_pct in target_detour_pcts:
        if target_pct <= 0.0:
            continue
        target_distance_m = shortest_distance_m * (1.0 + float(target_pct) / 100.0)
        lo = float(alpha_lo)
        hi = float(alpha_hi)

        for _ in range(max(1, int(max_steps))):
            mid = (lo + hi) / 2.0
            costs = risk_adjusted_lengths(
                edge_length,
                edge_risk,
                alpha=mid,
                red_threshold=red_threshold,
                red_penalty=red_penalty,
            )
            matrix_f, matrix_b = build_csr_pair(costs)
            try:
                path_nodes = path_for_matrices(start_idx, end_idx, matrix_f, matrix_b)
            except ValueError:
                hi = mid
                continue
            candidate = candidate_from_path(path_nodes, alpha=mid, edge_costs=None)

            if candidate.distance_m <= target_distance_m + 0.01:
                if candidate.path_signature not in seen:
                    seen.add(candidate.path_signature)
                    candidates.append(candidate)
                lo = mid
            else:
                hi = mid

    return candidates
