"""South Loop / Loop güzergâh profil analizi."""
import httpx

BASE = "http://127.0.0.1:8002"

# South Loop -> Loop / Financial District yaklaşık OD adayları
SCENARIOS = [
    ("SLoop-Loop-A", [-87.6330, 41.8610], [-87.6250, 41.8780]),
    ("SLoop-Loop-B", [-87.6350, 41.8580], [-87.6200, 41.8820]),
    ("SLoop-Loop-C", [-87.6310, 41.8650], [-87.6240, 41.8750]),
    ("SLoop-Loop-D", [-87.6370, 41.8600], [-87.6180, 41.8850]),
    ("SLoop-Loop-E", [-87.6290, 41.8630], [-87.6220, 41.8800]),
]

with httpx.Client(timeout=120.0) as client:
    for name, start, end in SCENARIOS:
        results = {}
        for profile in ("shortest", "balanced", "safer"):
            r = client.post(
                f"{BASE}/api/v1/route",
                json={"start": start, "end": end, "profile": profile},
            )
            d = r.json()
            c = d.get("comparison") or {}
            results[profile] = {
                "dist": d.get("distance_m"),
                "risk": d.get("route_risk"),
                "safety": d.get("safety_score"),
                "extra_pct": c.get("extra_distance_pct"),
                "risk_red": c.get("risk_reduction_pct"),
                "meaningful": c.get("meaningful_safer_alternative"),
                "candidates": c.get("candidate_count"),
                "decision": c.get("decision_reason"),
            }

        s, b, f = results["shortest"], results["balanced"], results["safer"]
        same_geom = (
            abs(s["dist"] - b["dist"]) < 5
            and abs(b["dist"] - f["dist"]) < 5
        )
        marker = ""
        if 1100 <= s["dist"] <= 1300:
            marker = " [~1.2km ekran]"
        if 1700 <= s["dist"] <= 2000:
            marker = " [~1.9km ekran]"

        print(f"=== {name}{marker} ===")
        print(f"  start={start} end={end}")
        for p in ("shortest", "balanced", "safer"):
            x = results[p]
            print(
                f"  {p:8s} {x['dist']:7.0f}m risk={x['risk']:.3f} "
                f"(guvenlik {x['safety']:.0f}) extra={x['extra_pct']}% "
                f"risk_red={x['risk_red']}% cand={x['candidates']} "
                f"meaningful={x['meaningful']} decision={x['decision']}"
            )
        print(f"  3 profil ayni geometri: {same_geom}")
        print()
