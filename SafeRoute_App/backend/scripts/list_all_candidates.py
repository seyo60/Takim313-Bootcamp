"""OD icin tum benzersiz aday rotalari listeler (DB risk yuklemeli)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from main import AsyncSessionLocal
from h3_policy import LEGACY_H3_RESOLUTION, validate_h3_resolution
import crud
import routing
from routing_cost import risk_adjusted_lengths
from routing_engine import get_routing_engine
from routing_profiles import select_route_candidate


async def bootstrap_engine():
    engine = get_routing_engine(settings.routing_engine)
    if settings.routing_engine == "compact":
        engine.load_graph(settings.compact_graph_path)
    else:
        engine.load_graph(settings.graph_path)
    async with AsyncSessionLocal() as session:
        routing_resolution = validate_h3_resolution(
            getattr(settings, "routing_h3_resolution", LEGACY_H3_RESOLUTION)
        )
        parent_resolution = validate_h3_resolution(
            getattr(settings, "h3_parent_resolution", LEGACY_H3_RESOLUTION)
        )
        heatmap_points = await crud.get_all_heatmap_points(
            session, h3_resolution=routing_resolution
        )
        if parent_resolution != routing_resolution:
            heatmap_points.extend(
                await crud.get_all_heatmap_points(
                    session, h3_resolution=parent_resolution
                )
            )
        risk_lookup = routing.build_risk_lookup(heatmap_points)
    engine.apply_risk_weights(risk_lookup, alpha=settings.routing_risk_alpha)
    return engine


def all_candidates(engine, start_lat, start_lng, end_lat, end_lng):
    start_idx, _ = engine.find_nearest_node(start_lat, start_lng)
    end_idx, _ = engine.find_nearest_node(end_lat, end_lng)

    shortest_nodes = engine._path_for_matrices(
        start_idx, end_idx, engine.csr_shortest, engine.csr_shortest_b
    )
    shortest = engine._candidate_from_path(shortest_nodes, alpha=None, edge_costs=None)

    candidates = []
    for alpha, (matrix_f, matrix_b) in sorted(engine._candidate_route_cache.items()):
        path_nodes = engine._path_for_matrices(start_idx, end_idx, matrix_f, matrix_b)
        candidates.append(engine._candidate_from_path(path_nodes, alpha=alpha, edge_costs=None))

    max_dist = shortest.distance_m * (1 + settings.routing_safer_max_detour_pct / 100)
    candidates.extend(
        engine._diversified_path_candidates(
            start_idx, end_idx,
            engine.edge_length.astype(float, copy=False),
            alpha=None,
            max_distance_m=max_dist,
        )
    )
    if engine._candidate_route_cache:
        max_alpha = max(engine._candidate_route_cache.keys())
        max_costs = risk_adjusted_lengths(
            engine.edge_length, engine.edge_risk,
            alpha=max_alpha,
            red_threshold=engine._red_threshold,
            red_penalty=engine._red_penalty,
        )
        candidates.extend(
            engine._diversified_path_candidates(
                start_idx, end_idx, max_costs, alpha=max_alpha,
                max_distance_m=max_dist,
                max_iterations=min(3, settings.routing_diversify_iterations),
            )
        )

    unique = {shortest.path_signature: shortest}
    for c in candidates:
        ex = unique.get(c.path_signature)
        if ex is None or (c.route_risk, c.distance_m) < (ex.route_risk, ex.distance_m):
            unique[c.path_signature] = c
    return shortest, list(unique.values())


def report(engine, name, slng, slat, elng, elat):
    shortest, uniq = all_candidates(engine, slat, slng, elat, elng)
    max_dist = shortest.distance_m * (1 + settings.routing_safer_max_detour_pct / 100)

    print(f"\n=== {name} ===")
    print(f"start=({slng},{slat}) end=({elng},{elat})")
    print(f"shortest: {shortest.distance_m:.0f}m risk_score={shortest.route_risk*100:.0f}")
    print(f"safer butce: max {max_dist:.0f}m (+{settings.routing_safer_max_detour_pct}%)")
    print(f"benzersiz aday: {len(uniq)}")
    print("  mesafe  risk%  ek%    butce  alpha")

    for c in sorted(uniq, key=lambda x: (x.route_risk, x.distance_m)):
        extra = (c.distance_m / shortest.distance_m - 1) * 100
        in_b = c.distance_m <= max_dist + 0.01
        print(
            f"  {c.distance_m:6.0f}  {c.route_risk*100:5.0f}  {extra:5.1f}  "
            f"{'evet' if in_b else 'hayir':5s}  {c.alpha}"
        )

    for profile in ("balanced", "safer"):
        sel = select_route_candidate(
            shortest=shortest,
            candidates=[c for c in uniq if c.path_signature != shortest.path_signature],
            profile=profile,
            balanced_max_detour_pct=settings.routing_balanced_max_detour_pct,
            safer_max_detour_pct=settings.routing_safer_max_detour_pct,
        )
        extra = (sel.selected.distance_m / shortest.distance_m - 1) * 100
        red = sel.risk_reduction_pct
        same_as = ""
        print(
            f"  SECIM {profile}: {sel.selected.distance_m:.0f}m risk%={sel.selected.route_risk*100:.0f} "
            f"ek={extra:.1f}% risk_dusus={red:.1f}% karar={sel.decision_reason}{same_as}"
        )


async def main():
    engine = await bootstrap_engine()
    report(engine, "Gorsel2-benzer (~1.9km)", -87.631, 41.865, -87.624, 41.875)
    report(engine, "Gorsel1-arama-A", -87.6325, 41.862, -87.6255, 41.877)
    report(engine, "Gorsel1-arama-B", -87.6338, 41.8608, -87.6262, 41.8768)
    report(engine, "Gorsel1-arama-C", -87.6345, 41.8612, -87.6248, 41.8782)


if __name__ == "__main__":
    asyncio.run(main())
