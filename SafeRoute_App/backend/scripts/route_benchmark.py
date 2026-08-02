"""Golden route benchmark — 3 profil farklılaşması ve risk düşüşü metrikleri.

Kullanım:
    .\.venv\Scripts\python.exe scripts/route_benchmark.py
    .\.venv\Scripts\python.exe scripts/route_benchmark.py --base-url http://127.0.0.1:8002
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass

import httpx

DEFAULT_ROUTES = [
    {"name": "Loop -> South Loop", "start": [-87.6300, 41.8800], "end": [-87.6200, 41.8750]},
    {"name": "Lincoln Park -> Loop", "start": [-87.6500, 41.9200], "end": [-87.6250, 41.8850]},
    {"name": "Austin -> Garfield Park", "start": [-87.7700, 41.8900], "end": [-87.7170, 41.8800]},
    {"name": "Englewood kisa", "start": [-87.6500, 41.7800], "end": [-87.6440, 41.7790]},
    {"name": "Rogers Park -> Uptown", "start": [-87.6700, 42.0100], "end": [-87.6550, 41.9660]},
    {"name": "Hyde Park -> Bronzeville", "start": [-87.6000, 41.7900], "end": [-87.6200, 41.8200]},
    {"name": "Wicker Park -> West Loop", "start": [-87.6770, 41.9080], "end": [-87.6500, 41.8820]},
    {"name": "Pilsen -> Chinatown", "start": [-87.6560, 41.8570], "end": [-87.6330, 41.8510]},
    {"name": "Lakeview -> Old Town", "start": [-87.6530, 41.9400], "end": [-87.6370, 41.9100]},
    {"name": "South Shore -> Woodlawn", "start": [-87.5700, 41.7600], "end": [-87.6000, 41.7800]},
]

PROFILES = ("shortest", "balanced", "safer")


@dataclass
class RouteResult:
    name: str
    profile: str
    distance_m: float
    avg_risk: float
    geometry_hash: str


def geometry_hash(geojson: dict | None) -> str:
    if not geojson:
        return "none"
    coords = geojson.get("coordinates") or []
    if not coords:
        return "empty"
    sample = coords[:: max(1, len(coords) // 8)]
    return json.dumps(sample, separators=(",", ":"))[:120]


def fetch_route(client: httpx.Client, base_url: str, start: list[float], end: list[float], profile: str) -> dict:
    response = client.post(
        f"{base_url.rstrip('/')}/api/v1/route",
        json={"start": start, "end": end, "profile": profile},
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="SafeRoute golden route benchmark")
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    args = parser.parse_args()

    results: list[RouteResult] = []
    distinct_count = 0
    balanced_fallback = 0
    safer_worse_than_balanced = 0
    risk_drops: list[float] = []

    with httpx.Client() as client:
        ready = client.get(f"{args.base_url.rstrip('/')}/health/ready", timeout=10.0)
        ready.raise_for_status()

        for route in DEFAULT_ROUTES:
            by_profile: dict[str, RouteResult] = {}
            for profile in PROFILES:
                payload = fetch_route(client, args.base_url, route["start"], route["end"], profile)
                result = RouteResult(
                    name=route["name"],
                    profile=profile,
                    distance_m=float(payload.get("distance_m") or 0.0),
                    avg_risk=float(payload.get("route_risk") or 0.0),
                    geometry_hash=geometry_hash(payload.get("route")),
                )
                by_profile[profile] = result
                results.append(result)

            hashes = {by_profile[p].geometry_hash for p in PROFILES}
            if len(hashes) == 3:
                distinct_count += 1

            shortest_risk = by_profile["shortest"].avg_risk
            safer_risk = by_profile["safer"].avg_risk
            balanced_risk = by_profile["balanced"].avg_risk
            if shortest_risk > 0:
                risk_drops.append(100.0 * (shortest_risk - safer_risk) / shortest_risk)

            if safer_risk > balanced_risk + 1e-6:
                safer_worse_than_balanced += 1

            if by_profile["balanced"].geometry_hash == by_profile["shortest"].geometry_hash and shortest_risk > 0.5:
                balanced_fallback += 1

            print(f"\n{route['name']}")
            for profile in PROFILES:
                item = by_profile[profile]
                print(
                    f"  {profile:8s}  dist={item.distance_m:7.0f}m  "
                    f"risk={item.avg_risk:.3f}  geom={item.geometry_hash[:40]}"
                )

    avg_drop = sum(risk_drops) / len(risk_drops) if risk_drops else 0.0
    print("\n=== ÖZET ===")
    print(f"Güzergâh sayısı: {len(DEFAULT_ROUTES)}")
    print(f"3 farklı geometri: {distinct_count}/{len(DEFAULT_ROUTES)}")
    print(f"Ort. güvenli risk düşüşü: {avg_drop:.1f}%")
    print(f"Dengeli → en kısa düşme (yüksek risk): {balanced_fallback}/{len(DEFAULT_ROUTES)}")
    print(f"Daha güvenli riski > dengeli: {safer_worse_than_balanced}/{len(DEFAULT_ROUTES)}")


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        sys.exit(1)
