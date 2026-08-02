"""Financial District / lakefront güzergâh profil testi."""
import httpx

BASE = "http://127.0.0.1:8002"

PAIRS = [
    ([-87.628, 41.861], [-87.635, 41.878], "Central->Financial"),
    ([-87.630, 41.862], [-87.633, 41.877], "SLoop->Loop"),
    ([-87.625, 41.860], [-87.632, 41.879], "Harbor->Financial"),
    ([-87.627, 41.863], [-87.634, 41.876], "Dearborn->Financial"),
    ([-87.629, 41.864], [-87.636, 41.881], "SLoopE->Financial"),
]

with httpx.Client(timeout=120.0) as client:
    for start, end, name in PAIRS:
        print(f"=== {name} ===")
        rows = {}
        for profile in ("shortest", "balanced", "safer"):
            r = client.post(
                f"{BASE}/api/v1/route",
                json={"start": start, "end": end, "profile": profile},
            )
            d = r.json()
            comp = d.get("comparison") or {}
            sr = d.get("shortest_route") or {}
            rows[profile] = {
                "dist": d.get("distance_m"),
                "risk": d.get("risk_score"),
                "short_dist": sr.get("distance_m", d.get("distance_m")),
                "short_risk": sr.get("risk_score"),
                "extra": comp.get("extra_distance_pct"),
                "red": comp.get("risk_reduction_pct"),
                "cand": comp.get("candidate_count"),
            }
        s, b, f = rows["shortest"], rows["balanced"], rows["safer"]
        marker = ""
        if 2300 <= s["dist"] <= 2500 and b["dist"] and abs(b["dist"] - s["dist"]) / s["dist"] < 0.06:
            marker = " [EKRAN BENZER]"
        print(f"  start={start} end={end}{marker}")
        for p in ("shortest", "balanced", "safer"):
            x = rows[p]
            print(
                f"  {p:8s} {x['dist']:7.0f}m risk={x['risk']:4.0f} "
                f"extra={x['extra']}% red={x['red']}% cand={x['cand']}"
            )
        same_bs = abs(b["dist"] - f["dist"]) < 5
        same_sb = abs(s["dist"] - b["dist"]) < 5
        print(f"  shortest==balanced: {same_sb}  balanced==safer: {same_bs}")
        print()
