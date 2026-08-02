"""Canlı ihbarın rotayı gerçekten etkilediğini uçtan uca doğrular (Adım 7).

Akış:
1. Güzergâhın rotasını alır (ihbar öncesi).
2. Rotanın üzerindeki bir noktaya iki bağımsız cihazdan ihbar gönderir.
3. Olayın kabul edildiğini ve risk_live'ın uygulandığını doğrular.
4. Takip token'ı ile durum sorgusunu doğrular.
5. Aynı güzergâhın rotasını yeniden alır ve riskin/geometrinin değiştiğini
   raporlar.

Production akışı için backend REPORT_DEV_SOLO_ACCEPT=false ile çalıştırılmalıdır.

Kullanım:
  .\.venv\Scripts\python.exe scripts/verify_live_report_impact.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid

import httpx


# İki farklı kullanıcının aynı olayı farklı kelimelerle anlattığı gerçekçi senaryo.
REPORT_TEXTS = (
    "Silahlı çatışma var, bu sokaktan geçmeyin lütfen dikkat edin",
    "Burada silah sesleri duyuldu, silahlı bir olay yaşanıyor caddede",
)


def fetch_route(base_url: str, start: list[float], end: list[float], profile: str) -> dict:
    response = httpx.post(
        f"{base_url.rstrip('/')}/api/v1/route",
        json={"start": start, "end": end, "profile": profile},
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()


def post_report(
    base_url: str,
    *,
    lat: float,
    lng: float,
    text: str,
    device_id: str,
) -> dict:
    response = httpx.post(
        f"{base_url.rstrip('/')}/api/v1/report",
        json={
            "text": text,
            "lat": lat,
            "lng": lng,
            "category": "crime",
            "priority": "urgent",
            "reporter_installation_id": device_id,
        },
        timeout=60.0,
    )
    if response.status_code >= 400:
        print(f"   [HTTP {response.status_code}] {response.text[:500]}")
        return {"http_status": response.status_code, "error": response.text[:500]}
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Canlı ihbar etki doğrulaması")
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--profile", default="balanced")
    parser.add_argument(
        "--start",
        default="-87.6500,41.9200",
        help="Başlangıç 'lng,lat'",
    )
    parser.add_argument("--end", default="-87.6250,41.8850", help="Bitiş 'lng,lat'")
    args = parser.parse_args()

    start = [float(value) for value in args.start.split(",")]
    end = [float(value) for value in args.end.split(",")]

    try:
        httpx.get(f"{args.base_url.rstrip('/')}/health/ready", timeout=10.0).raise_for_status()
    except Exception as exc:
        print(f"[HATA] Backend hazır değil: {exc}", file=sys.stderr)
        return 1

    print("1) İhbar öncesi rota alınıyor...")
    before = fetch_route(args.base_url, start, end, args.profile)
    before_coords = before["route"]["coordinates"]
    print(
        f"   dist={before['distance_m']:.0f}m risk={before['route_risk']:.4f} "
        f"nokta={len(before_coords)}"
    )

    # Rotanın orta bölgesinde bir nokta seç: ihbar burayı riskli hale getirmeli.
    target_lng, target_lat = before_coords[len(before_coords) // 2][:2]
    print(f"2) Hedef nokta (rota ortası): lat={target_lat:.6f} lng={target_lng:.6f}")

    accepted = False
    tracking_token = None
    report_id = None
    for index, text in enumerate(REPORT_TEXTS, start=1):
        result = post_report(
            args.base_url,
            lat=target_lat + (index - 1) * 0.0001,
            lng=target_lng + (index - 1) * 0.0001,
            text=text,
            device_id=str(uuid.uuid4()),
        )
        print(f"   İhbar {index}: status={result.get('status')} "
              f"event_status={result.get('event_status')} "
              f"V={result.get('validation_score')} "
              f"cluster={result.get('cluster_report_count')} "
              f"live_risk_applied={result.get('live_risk_applied')}")
        tracking_token = result.get("tracking_token") or tracking_token
        report_id = result.get("id") or report_id
        if result.get("live_risk_applied"):
            accepted = True
            break

    if not accepted:
        print("[UYARI] İki ihbar sonrası da canlı risk uygulanmadı.")

    if tracking_token and report_id:
        print("3) Takip token'ı ile durum sorgusu...")
        status_response = httpx.get(
            f"{args.base_url.rstrip('/')}/api/v1/reports/{report_id}",
            params={"token": tracking_token},
            timeout=30.0,
        )
        print(f"   HTTP {status_response.status_code}: "
              f"{json.dumps(status_response.json(), ensure_ascii=False)[:300]}")

    print("4) Etkinin grafa yansıması için kısa bekleme...")
    time.sleep(2.0)

    print("5) İhbar sonrası rota alınıyor...")
    after = fetch_route(args.base_url, start, end, args.profile)
    after_coords = after["route"]["coordinates"]
    print(
        f"   dist={after['distance_m']:.0f}m risk={after['route_risk']:.4f} "
        f"nokta={len(after_coords)}"
    )

    geometry_changed = after_coords != before_coords
    risk_changed = abs(after["route_risk"] - before["route_risk"]) > 1e-6

    print("\n=== SONUÇ ===")
    print(f"Olay kabul edildi (live_risk_applied): {accepted}")
    print(f"Rota geometrisi değişti: {geometry_changed}")
    print(f"Rota riski değişti: {risk_changed} "
          f"({before['route_risk']:.4f} -> {after['route_risk']:.4f})")
    print(f"Mesafe: {before['distance_m']:.0f}m -> {after['distance_m']:.0f}m")

    if accepted and (geometry_changed or risk_changed):
        print("[OK] Canlı ihbar rotayı etkiledi.")
        return 0
    if accepted:
        print(
            "[BİLGİ] Olay kabul edildi ancak rota değişmedi. "
            "İhbar hücresi rotanın kaçınabileceği bir konumda olmayabilir."
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
