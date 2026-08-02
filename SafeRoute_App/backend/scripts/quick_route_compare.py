"""Quick route profile comparison script."""
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8002"
ROUTES = [
    ("Near North", [-87.6368, 41.8990], [-87.6205, 41.8940]),
    ("Loop kisa", [-87.6297, 41.8795], [-87.6268, 41.8812]),
    ("Lakeview", [-87.6600, 41.9400], [-87.6400, 41.9300]),
    ("Englewood", [-87.6500, 41.7800], [-87.6400, 41.7700]),
]

with httpx.Client(timeout=120.0) as client:
    for name, start, end in ROUTES:
        print(f"=== {name} ===")
        for profile in ("shortest", "balanced", "safer"):
            t0 = time.perf_counter()
            response = client.post(
                f"{BASE.rstrip('/')}/api/v1/route",
                json={"start": start, "end": end, "profile": profile},
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            payload = response.json()
            comparison = payload.get("comparison") or {}
            print(
                f"  {profile:8s} "
                f"{payload.get('distance_m', 0):7.0f}m "
                f"risk={payload.get('route_risk', 0):.3f} "
                f"extra={comparison.get('extra_distance_pct')}% "
                f"meaningful={comparison.get('meaningful_safer_alternative')} "
                f"cand={comparison.get('candidate_count')} "
                f"{elapsed_ms:.0f}ms"
            )
        print()
