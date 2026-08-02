"""Belirli bir OD için tüm aday rotaları listeler."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from routing_engine import get_routing_engine
from routing_profiles import RouteCandidate, select_route_candidate


async def dump_candidates(name: str, start_lng: float, start_lat: float, end_lng: float, end_lat: float):
    engine = get_routing_engine()
    result = engine.compute_profiled_route(
        start_lat=start_lat,
        start_lng=start_lng,
        end_lat=end_lat,
        end_lng=end_lng,
        profile="safer",
    )
    # compute_profiled_route returns tuple - need to check signature
    print(f"=== {name} ===")
    print(f"  start=({start_lng},{start_lat}) end=({end_lng},{end_lat})")
    if hasattr(result, "selected"):
        sel = result
        print(f"  selected: {sel.selected.distance_m:.0f}m risk={sel.selected.route_risk:.3f}")
        print(f"  shortest: {sel.shortest.distance_m:.0f}m risk={sel.shortest.route_risk:.3f}")
        print(f"  candidates={sel.candidate_count} eligible={sel.eligible_candidate_count}")
        print(f"  decision={sel.decision_reason} risk_red={sel.risk_reduction_pct:.1f}%")
    else:
        coords, dist, safety, risk, coverage = result[:5]
        print(f"  dist={dist:.0f}m risk={risk:.3f} safety={safety}")


def main():
    scenarios = [
        ("Gorsel2-yakin", -87.631, 41.865, -87.624, 41.875),
        ("Gorsel1-arama-A", -87.6325, 41.862, -87.6255, 41.877),
        ("Gorsel1-arama-B", -87.6335, 41.8605, -87.626, 41.8765),
        ("Gorsel1-arama-C", -87.634, 41.8615, -87.6245, 41.8785),
    ]
    for name, slng, slat, elng, elat in scenarios:
        try:
            engine = get_routing_engine()
            selection = engine.compute_profiled_route(
                start_lat=slat,
                start_lng=slng,
                end_lat=elat,
                end_lng=elng,
                profile="safer",
            )
            # Might return RouteSelectionResult or legacy tuple
            if isinstance(selection, tuple):
                print(f"{name}: legacy tuple dist={selection[1]:.0f}")
                continue
            s = selection
            extra = (s.selected.distance_m / s.shortest.distance_m - 1) * 100
            print(
                f"{name}: short={s.shortest.distance_m:.0f}m/{s.shortest.route_risk:.3f} "
                f"safer={s.selected.distance_m:.0f}m/{s.selected.route_risk:.3f} "
                f"extra={extra:.1f}% cand={s.candidate_count} "
                f"risk_red={s.risk_reduction_pct:.1f}%"
            )
        except Exception as exc:
            print(f"{name}: ERROR {exc}")


if __name__ == "__main__":
    main()
