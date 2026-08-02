"""Ekran istatistiklerine yakin OD arama: short~2400 risk~26, bal~2600 risk~21."""
import httpx
import itertools

BASE = "http://127.0.0.1:8002"

lons = [-87.632, -87.630, -87.628, -87.626, -87.624]
lats = [41.858, 41.860, 41.862, 41.864, 41.866]
elons = [-87.638, -87.636, -87.634, -87.632]
elats = [41.874, 41.876, 41.878, 41.880, 41.882]

with httpx.Client(timeout=120.0) as client:
    for slng, slat, elng, elat in itertools.product(lons, lats, elons, elats):
        if slat >= elat - 0.005:
            continue
        try:
            rs = client.post(
                f"{BASE}/api/v1/route",
                json={"start": [slng, slat], "end": [elng, elat], "profile": "shortest"},
            ).json()
            sd = float(rs.get("distance_m") or 0)
            sr = float(rs.get("risk_score") or 0)
            if not (2200 <= sd <= 2600 and 20 <= sr <= 35):
                continue
            rb = client.post(
                f"{BASE}/api/v1/route",
                json={"start": [slng, slat], "end": [elng, elat], "profile": "balanced"},
            ).json()
            comp = rb.get("comparison") or {}
            bd = float(rb.get("distance_m") or 0)
            br = float(rb.get("risk_score") or 0)
            extra = float(comp.get("extra_distance_pct") or 0)
            red = float(comp.get("risk_reduction_pct") or 0)
            if 2500 <= bd <= 2700 and 15 <= br <= 28 and 3 <= extra <= 8 and 15 <= red <= 25:
                rf = client.post(
                    f"{BASE}/api/v1/route",
                    json={"start": [slng, slat], "end": [elng, elat], "profile": "safer"},
                ).json()
                print(
                    "MATCH",
                    [slng, slat],
                    [elng, elat],
                    f"short={sd:.0f}/{sr:.0f}",
                    f"bal={bd:.0f}/{br:.0f} extra={extra:.1f}% red={red:.1f}%",
                    f"safer={rf.get('distance_m'):.0f}/{rf.get('risk_score'):.0f}",
                )
        except Exception:
            pass
