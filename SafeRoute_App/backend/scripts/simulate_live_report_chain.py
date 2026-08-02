"""Canlı ihbar kabul zincirini iki bağımsız cihazla simüle eder.

Kullanım:
  cd SafeRoute_App/backend
  Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
  .\.venv\Scripts\python.exe scripts/simulate_live_report_chain.py

Tek geliştirici testi için .env'e REPORT_DEV_SOLO_ACCEPT=true ekleyin.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid

import httpx


DEFAULT_LAT = 41.8781
DEFAULT_LNG = -87.6298
DEFAULT_TEXT = "Silahlı çatışma var, bu sokaktan geçmeyin lütfen dikkat edin"


def post_report(base_url: str, lat: float, lng: float, text: str, device_id: str) -> dict:
    payload = {
        "text": text,
        "lat": lat,
        "lng": lng,
        "category": "crime",
        "priority": "urgent",
        "reporter_installation_id": device_id,
    }
    resp = httpx.post(f"{base_url.rstrip('/')}/api/v1/report", json=payload, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Canlı ihbar zinciri simülasyonu")
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--lat", type=float, default=DEFAULT_LAT)
    parser.add_argument("--lng", type=float, default=DEFAULT_LNG)
    parser.add_argument("--solo", action="store_true", help="Tek ihbar gönder (REPORT_DEV_SOLO_ACCEPT gerekir)")
    args = parser.parse_args()

    try:
        health = httpx.get(f"{args.base_url.rstrip('/')}/health/ready", timeout=10.0)
        health.raise_for_status()
    except Exception as exc:
        print(f"[HATA] Backend hazır değil: {exc}", file=sys.stderr)
        return 1

    device_a = str(uuid.uuid4())
    result_a = post_report(args.base_url, args.lat, args.lng, DEFAULT_TEXT, device_a)
    print("İhbar 1:", json.dumps(result_a, ensure_ascii=False, indent=2))

    if result_a.get("live_risk_applied"):
        print("\n[OK] Canlı risk uygulandı (solo veya hızlı kabul).")
        return 0

    if args.solo:
        print("\n[UYARI] Solo modda kabul olmadı — REPORT_DEV_SOLO_ACCEPT=true kontrol edin.")
        return 2

    device_b = str(uuid.uuid4())
    result_b = post_report(
        args.base_url,
        args.lat + 0.0001,
        args.lng + 0.0001,
        "Aynı bölgede silahlı çatışma devam ediyor, sokak kapalı",
        device_b,
    )
    print("\nİhbar 2:", json.dumps(result_b, ensure_ascii=False, indent=2))

    if result_b.get("live_risk_applied"):
        print("\n[OK] İki bağımsız ihbar sonrası canlı risk uygulandı.")
        return 0

    print(
        "\n[BEKLİYOR] Olay henüz kabul edilmedi. "
        f"event_status={result_b.get('event_status')}, "
        f"validation_score={result_b.get('validation_score')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
