"""Ayrışmayan güzergâhlarda yüksek alpha adaylarını inceler.

Balanced ve safer profilin aynı rotayı seçtiği güzergâhlarda, daha yüksek risk
ağırlığının bütçe içinde daha düşük riskli bir alternatif üretip üretmediğini
ölçer (Adım 4 kalite çalışması).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import crud  # noqa: E402
import routing  # noqa: E402
from config import settings  # noqa: E402
from h3_policy import LEGACY_H3_RESOLUTION, validate_h3_resolution  # noqa: E402
from routing_cost import risk_adjusted_lengths  # noqa: E402
from routing_engine import get_routing_engine  # noqa: E402
from routing_subgraph import build_budget_subgraph  # noqa: E402

_db_engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(
    _db_engine, class_=AsyncSession, expire_on_commit=False
)

CASES = [
    ("Englewood kisa", 41.7800, -87.6500, 41.7790, -87.6440),
    ("Hyde Park -> Bronzeville", 41.7900, -87.6000, 41.8200, -87.6200),
    ("Pilsen -> Chinatown", 41.8570, -87.6560, 41.8510, -87.6330),
]

ALPHAS = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0]


async def _load_risk(engine) -> int:
    routing_resolution = validate_h3_resolution(
        getattr(settings, "routing_h3_resolution", LEGACY_H3_RESOLUTION)
    )
    parent_resolution = validate_h3_resolution(
        getattr(settings, "h3_parent_resolution", LEGACY_H3_RESOLUTION)
    )
    async with AsyncSessionLocal() as session:
        points = await crud.get_all_heatmap_points(
            session, h3_resolution=routing_resolution
        )
        if parent_resolution != routing_resolution:
            points.extend(
                await crud.get_all_heatmap_points(
                    session, h3_resolution=parent_resolution
                )
            )
    risk_lookup = routing.build_risk_lookup(points)
    engine.apply_risk_weights(risk_lookup, alpha=settings.routing_risk_alpha)
    return len(risk_lookup)


def main() -> int:
    engine = get_routing_engine("compact")
    engine.load_graph(settings.compact_graph_path)
    print(f"Risk hücresi: {asyncio.run(_load_risk(engine))}\n")

    safer_pct = float(settings.routing_safer_max_detour_pct)

    for name, s_lat, s_lng, e_lat, e_lng in CASES:
        start_idx, _ = engine.find_nearest_node(s_lat, s_lng)
        end_idx, _ = engine.find_nearest_node(e_lat, e_lng)
        shortest_nodes = engine._path_for_matrices(
            start_idx, end_idx, engine.csr_shortest, engine.csr_shortest_b
        )
        shortest = engine._candidate_from_path(
            shortest_nodes, alpha=None, edge_costs=None, with_navigation=False
        )
        budget = shortest.distance_m * (1.0 + safer_pct / 100.0)
        print(
            f"=== {name} === shortest={shortest.distance_m:.0f}m "
            f"risk={shortest.route_risk:.4f} bütçe={budget:.0f}m"
        )

        subgraph = build_budget_subgraph(
            node_x=engine.node_x,
            node_y=engine.node_y,
            edge_src=engine.edge_src,
            edge_dst=engine.edge_dst,
            start_idx=start_idx,
            end_idx=end_idx,
            max_distance_m=budget,
            margin=float(settings.routing_subgraph_margin),
            max_node_ratio=float(settings.routing_subgraph_max_node_ratio),
        )
        build_csr = (
            subgraph.build_csr if subgraph is not None else engine._build_csr_pair
        )
        path_finder = (
            subgraph.path_finder
            if subgraph is not None
            else engine._path_for_matrices
        )

        seen: set[tuple[str, ...]] = set()
        for alpha in ALPHAS:
            costs = risk_adjusted_lengths(
                engine.edge_length,
                engine.edge_risk,
                alpha=alpha,
                red_threshold=engine._red_threshold,
                red_penalty=engine._red_penalty,
            )
            matrix_f, matrix_b = build_csr(costs)
            try:
                nodes = path_finder(start_idx, end_idx, matrix_f, matrix_b)
            except ValueError:
                print(f"  alpha={alpha:6.1f}  rota yok")
                continue
            candidate = engine._candidate_from_path(
                nodes, alpha=alpha, edge_costs=None, with_navigation=False
            )
            detour = (
                (candidate.distance_m / shortest.distance_m - 1.0) * 100.0
                if shortest.distance_m > 0
                else 0.0
            )
            fits = "BÜTÇE-İÇİ" if candidate.distance_m <= budget else "bütçe-dışı"
            fresh = "" if candidate.path_signature in seen else "  <-- yeni geometri"
            seen.add(candidate.path_signature)
            print(
                f"  alpha={alpha:6.1f}  dist={candidate.distance_m:7.0f}m "
                f"(%{detour:5.1f})  risk={candidate.route_risk:.4f}  {fits}{fresh}"
            )
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
