"""Rota hesaplama darboğazlarını cProfile ile ölçer (Adım 4 gecikme çalışması).

Kullanım:
  cd SafeRoute_App/backend
  Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
  .\.venv\Scripts\python.exe scripts/profile_route_compute.py
"""

from __future__ import annotations

import asyncio
import cProfile
import io
import pstats
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import crud  # noqa: E402
import routing  # noqa: E402
from config import settings  # noqa: E402
from h3_policy import LEGACY_H3_RESOLUTION, validate_h3_resolution  # noqa: E402
from routing_engine import get_routing_engine  # noqa: E402

_db_engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(
    _db_engine, class_=AsyncSession, expire_on_commit=False
)


CASES = [
    ("Loop->SouthLoop", 41.8800, -87.6300, 41.8750, -87.6200),
    ("LincolnPark->Loop", 41.9200, -87.6500, 41.8850, -87.6250),
]


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
    cell_count = asyncio.run(_load_risk(engine))
    print(f"Risk hücresi: {cell_count}")
    print(f"Alt graf ayarı: enabled={settings.routing_subgraph_enabled}")

    for name, s_lat, s_lng, e_lat, e_lng in CASES:
        # Alt graf boyutunu raporla.
        start_idx, _ = engine.find_nearest_node(s_lat, s_lng)
        end_idx, _ = engine.find_nearest_node(e_lat, e_lng)
        shortest_nodes = engine._path_for_matrices(
            start_idx, end_idx, engine.csr_shortest, engine.csr_shortest_b
        )
        shortest = engine._candidate_from_path(
            shortest_nodes, alpha=None, edge_costs=None, with_navigation=False
        )
        budget = shortest.distance_m * (
            1.0 + float(settings.routing_safer_max_detour_pct) / 100.0
        )
        from routing_subgraph import build_budget_subgraph

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
        if subgraph is None:
            print(f"\n{name}: alt graf kullanılmıyor (kırpma anlamsız)")
        else:
            print(
                f"\n{name}: shortest={shortest.distance_m:.0f}m "
                f"alt graf düğüm={subgraph.node_count}/{subgraph.total_nodes} "
                f"({subgraph.node_ratio * 100:.1f}%) kenar={subgraph.edge_count}"
            )

        t0 = time.time()
        profiler = cProfile.Profile()
        profiler.enable()
        engine.compute_profiled_route(
            start_lat=s_lat,
            start_lng=s_lng,
            end_lat=e_lat,
            end_lng=e_lng,
            profile="safer",
        )
        profiler.disable()
        elapsed = time.time() - t0

        stream = io.StringIO()
        pstats.Stats(profiler, stream=stream).sort_stats("cumulative").print_stats(14)
        print(f"Toplam: {elapsed:.2f} s")
        print(stream.getvalue().split("Ordered by:")[-1][:2200])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
