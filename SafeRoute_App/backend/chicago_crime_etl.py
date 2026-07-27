# backend/chicago_crime_etl.py
"""
Chicago Police Suç Verileri ETL Boru Hattı (Socrata API -> H3 Resolution 9).

Socrata API: https://data.cityofchicago.org/resource/ijzp-q8t2.json
Tarih Aralığı: 2023-01-01 -> Günümüz

İşlem Adımları:
1. Socrata API'den suç kayıtları çekilir ($select, $where, $limit, $offset).
2. Geçerli latitude & longitude koordinatları H3 Res 9 hücresine dönüştürülür.
3. Kategori ve ciddiyet ağırlıkları hesaplanır (Şiddet suçları: 1.0, Mülkiyet: 0.6, Diğer: 0.3).
4. Zaman penceresi agregasyonları yapılır (7d, 30d, 90d, violent_30d, night_30d).
5. 0.0 - 1.0 arasında normalize edilmiş `risk_crime` üretilir.
6. Veritabanındaki `h3_heatmap` tablosuna yazılır/güncellenir.
"""

import sys
import argparse
import asyncio
from datetime import datetime, timezone, timedelta
import math
import requests
import h3

from config import settings

CRIME_API_URL = getattr(settings, "chicago_crime_api_url", "https://data.cityofchicago.org/resource/ijzp-q8t2.json")

# Suç Türleri Ciddiyet Ağırlıkları
VIOLENT_CRIMES = {
    "HOMICIDE", "BATTERY", "ASSAULT", "ROBBERY",
    "CRIMSEXUAL ASSAULT", "CRIMINAL SEXUAL ASSAULT",
    "KIDNAPPING", "HUMAN TRAFFICKING"
}

PROPERTY_CRIMES = {
    "BURGLARY", "THEFT", "MOTOR VEHICLE THEFT",
    "ARSON", "WEAPONS VIOLATION", "CRIMINAL DAMAGE"
}


def get_crime_severity(primary_type: str) -> float:
    """Suç birincil türüne göre ciddiyet katsayısı döner (0.3 - 1.0)."""
    pt_upper = (primary_type or "").upper().strip()
    if pt_upper in VIOLENT_CRIMES:
        return 1.0
    elif pt_upper in PROPERTY_CRIMES:
        return 0.6
    return 0.3


def fetch_chicago_crimes(
    start_date: str = "2023-01-01T00:00:00.000",
    limit: int = 50000,
    max_records: int = None,
    app_token: str = None
) -> list[dict]:
    """
    Socrata API üzerinden sayfalama (pagination) ile suç verilerini çeker.
    """
    records = []
    offset = 0
    batch_size = min(limit, 50000)

    headers = {}
    token = app_token or getattr(settings, "chicago_data_app_token", "")
    if token:
        headers["X-App-Token"] = token

    print(f"[Crime ETL] API isteği başlatılıyor ({CRIME_API_URL})...");
    while True:
        params = {
            "$select": (
                "id,case_number,date,updated_on,primary_type,description,"
                "location_description,domestic,arrest,latitude,longitude"
            ),
            "$where": f"date >= '{start_date}' AND latitude IS NOT NULL AND longitude IS NOT NULL",
            "$order": "date ASC",
            "$limit": batch_size,
            "$offset": offset,
        }

        try:
            resp = requests.get(CRIME_API_URL, params=params, headers=headers, timeout=60)
            resp.raise_for_status()
            batch = resp.json()
        except Exception as e:
            print(f"[Crime ETL Hata] API çağrısı sırasında hata oluştu: {e}")
            break

        if not batch:
            break

        records.extend(batch)
        print(f"[Crime ETL] {len(records)} kayıt çekildi...")

        offset += len(batch)
        if len(batch) < batch_size:
            break
        if max_records and len(records) >= max_records:
            records = records[:max_records]
            break

    print(f"[Crime ETL] Toplam {len(records)} geçerli suç kaydı çekildi.")
    return records


def process_crime_records(records: list[dict], reference_date: datetime = None) -> dict[str, dict]:
    """
    Suç kayıtlarını H3 Resolution 9 hücrelerine dönüştürür ve agregasyonları hesaplar.
    Returns:
        { h3_index: { "lat": float, "lng": float, "crime_7d": int, ..., "risk_crime": float } }
    """
    if reference_date is None:
        reference_date = datetime.now(timezone.utc)

    # h3_index -> cell data
    cell_stats = {}

    for rec in records:
        try:
            lat = float(rec["latitude"])
            lng = float(rec["longitude"])
        except (KeyError, ValueError, TypeError):
            continue

        h3_idx = h3.latlng_to_cell(lat, lng, 9)

        # Tarih ayrıştırma
        raw_date_str = rec.get("date", "")
        try:
            dt = datetime.fromisoformat(raw_date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = reference_date

        days_diff = (reference_date - dt).total_seconds() / 86400.0
        primary_type = (rec.get("primary_type") or "").upper().strip()
        severity = get_crime_severity(primary_type)
        is_violent = primary_type in VIOLENT_CRIMES
        is_night = (dt.hour >= 22 or dt.hour < 6)

        if h3_idx not in cell_stats:
            cell_stats[h3_idx] = {
                "lat": lat,
                "lng": lng,
                "lats": [lat],
                "lngs": [lng],
                "crime_7d": 0,
                "crime_30d": 0,
                "crime_90d": 0,
                "violent_crime_30d": 0,
                "night_crime_30d": 0,
                "weighted_score": 0.0,
            }

        cell = cell_stats[h3_idx]
        cell["lats"].append(lat)
        cell["lngs"].append(lng)

        # Agregasyon sayaçları
        if days_diff <= 7:
            cell["crime_7d"] += 1
        if days_diff <= 30:
            cell["crime_30d"] += 1
            if is_violent:
                cell["violent_crime_30d"] += 1
            if is_night:
                cell["night_crime_30d"] += 1
        if days_diff <= 90:
            cell["crime_90d"] += 1

        # Zaman sönümlenmeli ciddiyet skoru
        time_decay = math.exp(-days_diff / 45.0)  # 45 gün yarı ömürlü sönümlenme
        cell["weighted_score"] += severity * time_decay

    # Hücre merkezlerini ve nihai 0-1 risk_crime skorlarını hesapla
    h3_heatmap_data = {}
    for h3_idx, stats in cell_stats.items():
        avg_lat = sum(stats["lats"]) / len(stats["lats"])
        avg_lng = sum(stats["lngs"]) / len(stats["lngs"])

        # Sigmoid / Min-Max benzeri 0.0 - 1.0 normalizasyon
        # 10 ve üzeri ağırlıklı puan 1.0 risk kabul edilir
        raw_score = stats["weighted_score"]
        risk_crime = min(1.0, raw_score / 10.0)

        h3_heatmap_data[h3_idx] = {
            "lat": avg_lat,
            "lng": avg_lng,
            "crime_7d": stats["crime_7d"],
            "crime_30d": stats["crime_30d"],
            "crime_90d": stats["crime_90d"],
            "violent_crime_30d": stats["violent_crime_30d"],
            "night_crime_30d": stats["night_crime_30d"],
            "risk_crime": round(risk_crime, 4),
        }

    return h3_heatmap_data


async def run_crime_etl(max_records: int = None, dry_run: bool = False):
    """ETL sürecini yürütür ve DB'ye kaydeder."""
    records = fetch_chicago_crimes(max_records=max_records)
    print(f"[Crime ETL] İşleniyor ({len(records)} kayıt)...")
    aggregated_h3 = process_crime_records(records)
    print(f"[Crime ETL] Toplam {len(aggregated_h3)} farklı H3 Res 9 hücresi oluşturuldu/hesaplandı.")

    if dry_run:
        print("[Crime ETL Dry-Run] Örnek H3 Çıktısı:")
        for idx, (cell_id, data) in enumerate(list(aggregated_h3.items())[:5]):
            print(f"  H3: {cell_id} -> risk_crime: {data['risk_crime']}, 30d crimes: {data['crime_30d']}")
        return aggregated_h3

    # Veritabanına kaydet
    try:
        from main import AsyncSessionLocal
        import crud

        async with AsyncSessionLocal() as session:
            count = 0
            for h3_idx, data in aggregated_h3.items():
                extra_features = {
                    "crime_7d": data["crime_7d"],
                    "crime_30d": data["crime_30d"],
                    "crime_90d": data["crime_90d"],
                    "violent_crime_30d": data["violent_crime_30d"],
                    "night_crime_30d": data["night_crime_30d"],
                    "risk_crime": data["risk_crime"],
                }
                await crud.upsert_crime_data(
                    db=session,
                    h3_index=h3_idx,
                    lat=data["lat"],
                    lng=data["lng"],
                    risk_crime=data["risk_crime"],
                    extra_features=extra_features
                )
                count += 1
            await crud.record_etl_run(session, "crime_etl", records_processed=count)
            print(f"[Crime ETL] Veritabanına {count} H3 hücresi kaydedildi/güncellendi ve etl_runs güncellendi.")
    except Exception as e:
        print(f"[Crime ETL DB Uyarısı] DB kaydı atlandı veya hata oluştu: {e}")

    return aggregated_h3


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chicago Suç Verisi ETL Boru Hattı")
    parser.add_argument("--max-records", type=int, default=None, help="Çekilecek maks kayıt sayısı")
    parser.add_argument("--dry-run", action="store_true", help="DB'ye yazmadan sadece istatistik üret")
    args = parser.parse_args()

    asyncio.run(run_crime_etl(max_records=args.max_records, dry_run=args.dry_run))
