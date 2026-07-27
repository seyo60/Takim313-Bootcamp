# backend/chicago_311_lighting_etl.py
"""
Chicago 311 Sokak Lambası Arızaları ETL Boru Hattı (Socrata API -> H3 Resolution 9).

Socrata API: https://data.cityofchicago.org/resource/v6vf-nfxy.json
Tarih Aralığı: 2023-01-01 -> Günümüz

Kategori Ağırlıkları (sr_type):
- Street Light Out Complaint (SFD): 0.25 (Tek lamba) / 0.50 (Çoklu)
- Alley Light Out Complaint: 0.50
- Viaduct Light Out Complaint: 0.85 (Alt geçit aydınlatması)
- Street Light Pole Damage Complaint: 0.50
- Street Light Pole Door Missing Complaint: 0.25
- Traffic Signal Out Complaint: 0.75

Durum ve Zaman Sönümlenmesi:
- Tamamlanmış (Completed/Closed) arıza = Aktif risk 0.0 (Tarihsel kronik analiz için tutulur)
- Açık/İşlemde (Open/In Progress) arıza = Aktif risk 1.0 * time_factor (min 0.6 sönümlenme)
"""

import sys
import argparse
import asyncio
from datetime import datetime, timezone
import math
import requests
import h3

from config import settings

REQUESTS_311_API_URL = getattr(settings, "chicago_311_api_url", "https://data.cityofchicago.org/resource/v6vf-nfxy.json")

# 311 Aydınlatma Kategorileri & Ağırlıkları
LIGHTING_SR_TYPES = {
    "Street Light Out Complaint": 0.35,
    "Street Light - All Out Complaint": 0.80,
    "Street Light - One Out Complaint": 0.25,
    "Alley Light Out Complaint": 0.50,
    "Viaduct Light Out Complaint": 0.85,
    "Street Light Pole Damage Complaint": 0.50,
    "Street Light Pole Door Missing Complaint": 0.25,
    "Traffic Signal Out Complaint": 0.75,
}

OPEN_STATUSES = {"OPEN", "IN PROGRESS", "PENDING", "ASSIGNED", "NEW", "OPEN - DUP"}


def get_lighting_severity(sr_type: str) -> float:
    """Kategoriye göre başlangıç ciddiyet ağırlığını döner."""
    sr_clean = (sr_type or "").strip()
    for key, weight in LIGHTING_SR_TYPES.items():
        if key.lower() in sr_clean.lower():
            return weight
    return 0.35


def compute_lighting_ticket_risk(status: str, created_dt: datetime, reference_dt: datetime, severity: float) -> tuple[float, float, float]:
    """
    StatusFactor ve TimeFactor kullanarak şikayet biletinin aktif risk katkısını hesaplar.
    Returns: (ticket_risk, status_factor, time_factor)
    """
    status_upper = (status or "").upper().strip()

    if status_upper not in OPEN_STATUSES and "OPEN" not in status_upper:
        # Tamamlanan, iptal edilen veya kapalı biletlerin aktif riski 0'dır
        return 0.0, 0.0, 0.0

    status_factor = 1.0
    days_open = max(0.0, (reference_dt - created_dt).total_seconds() / 86400.0)

    # Açık arızalar eskidikçe tamamen sıfırlanmaz, minimum 0.6 katsayı korur
    time_decay = math.exp(-days_open / 180.0)  # 180 günlük yumuşak sönümlenme
    time_factor = max(0.6, time_decay)

    ticket_risk = severity * status_factor * time_factor
    return ticket_risk, status_factor, time_factor


def fetch_chicago_311_lighting(
    start_date: str = "2023-01-01T00:00:00.000",
    limit: int = 50000,
    max_records: int = None,
    app_token: str = None
) -> list[dict]:
    """
    Socrata API üzerinden Chicago 311 sokak lambası şikayetlerini çeker.
    """
    records = []
    offset = 0
    batch_size = min(limit, 50000)

    headers = {}
    token = app_token or getattr(settings, "chicago_data_app_token", "")
    if token:
        headers["X-App-Token"] = token

    sr_filter_query = (
        "sr_type LIKE '%Street Light%' OR "
        "sr_type LIKE '%Alley Light%' OR "
        "sr_type LIKE '%Viaduct Light%' OR "
        "sr_type LIKE '%Traffic Signal%'"
    )

    print(f"[311 Lighting ETL] API isteği başlatılıyor ({REQUESTS_311_API_URL})...")
    while True:
        params = {
            "$where": f"({sr_filter_query}) AND created_date >= '{start_date}' AND latitude IS NOT NULL AND longitude IS NOT NULL",
            "$order": "created_date ASC",
            "$limit": batch_size,
            "$offset": offset,
        }

        try:
            resp = requests.get(REQUESTS_311_API_URL, params=params, headers=headers, timeout=60)
            resp.raise_for_status()
            batch = resp.json()
        except Exception as e:
            print(f"[311 Lighting ETL Hata] API çağrısı hatası: {e}")
            break

        if not batch:
            break

        records.extend(batch)
        print(f"[311 Lighting ETL] {len(records)} kayıt çekildi...")

        offset += len(batch)
        if len(batch) < batch_size:
            break
        if max_records and len(records) >= max_records:
            records = records[:max_records]
            break

    print(f"[311 Lighting ETL] Toplam {len(records)} geçerli aydınlatma şikayet kaydı çekildi.")
    return records


def process_lighting_records(records: list[dict], reference_date: datetime = None) -> dict[str, dict]:
    """
    311 kayıtlarını H3 Resolution 9 hücrelerine dönüştürür ve risk_lighting skorlarını hesaplar.
    Mükerrer (duplicate) kayıtlar tekleştirilir.
    """
    if reference_date is None:
        reference_date = datetime.now(timezone.utc)

    cell_stats = {}
    seen_sr_numbers = set()
    duplicate_count = 0

    for rec in records:
        sr_number = rec.get("sr_number")
        status = rec.get("status", "")

        # Mükerrer / Duplicate kontrolü
        if sr_number and sr_number in seen_sr_numbers:
            duplicate_count += 1
            continue
        if "DUP" in status.upper() or rec.get("duplicate") in ("true", "True", True):
            duplicate_count += 1
            continue

        if sr_number:
            seen_sr_numbers.add(sr_number)

        try:
            lat = float(rec["latitude"])
            lng = float(rec["longitude"])
        except (KeyError, ValueError, TypeError):
            continue

        h3_idx = h3.latlng_to_cell(lat, lng, 9)

        raw_date_str = rec.get("created_date", "")
        try:
            dt = datetime.fromisoformat(raw_date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = reference_date

        sr_type = rec.get("sr_type", "")
        severity = get_lighting_severity(sr_type)

        ticket_risk, status_factor, _ = compute_lighting_ticket_risk(
            status=status,
            created_dt=dt,
            reference_dt=reference_date,
            severity=severity
        )

        if h3_idx not in cell_stats:
            cell_stats[h3_idx] = {
                "lat": lat,
                "lng": lng,
                "lats": [lat],
                "lngs": [lng],
                "open_count": 0,
                "completed_count": 0,
                "total_active_risk": 0.0,
            }

        cell = cell_stats[h3_idx]
        cell["lats"].append(lat)
        cell["lngs"].append(lng)

        if status_factor > 0.0:
            cell["open_count"] += 1
            cell["total_active_risk"] += ticket_risk
        else:
            cell["completed_count"] += 1

    print(f"[311 Lighting ETL] {duplicate_count} adet mükerrer (duplicate) kayıt süzüldü.")

    h3_heatmap_data = {}
    for h3_idx, stats in cell_stats.items():
        avg_lat = sum(stats["lats"]) / len(stats["lats"])
        avg_lng = sum(stats["lngs"]) / len(stats["lngs"])

        # 3 ve üzeri aktif ağır arıza 1.0 azami risk verir
        risk_lighting = min(1.0, stats["total_active_risk"] / 3.0)

        h3_heatmap_data[h3_idx] = {
            "lat": avg_lat,
            "lng": avg_lng,
            "open_311_lighting_count": stats["open_count"],
            "completed_311_lighting_count": stats["completed_count"],
            "risk_lighting": round(risk_lighting, 4),
        }

    return h3_heatmap_data


async def run_lighting_etl(max_records: int = None, dry_run: bool = False):
    """311 Lighting ETL boru hattını çalıştırır."""
    records = fetch_chicago_311_lighting(max_records=max_records)
    print(f"[311 Lighting ETL] İşleniyor ({len(records)} kayıt)...")
    aggregated_h3 = process_lighting_records(records)
    print(f"[311 Lighting ETL] Toplam {len(aggregated_h3)} farklı H3 Res 9 hücresi hesaplandı.")

    if dry_run:
        print("[311 Lighting ETL Dry-Run] Örnek H3 Çıktısı:")
        for idx, (cell_id, data) in enumerate(list(aggregated_h3.items())[:5]):
            print(f"  H3: {cell_id} -> risk_lighting: {data['risk_lighting']}, Open 311: {data['open_311_lighting_count']}")
        return aggregated_h3

    # Veritabanına kaydet
    try:
        from main import AsyncSessionLocal
        import crud

        async with AsyncSessionLocal() as session:
            count = 0
            for h3_idx, data in aggregated_h3.items():
                extra_features = {
                    "open_311_lighting_count": data["open_311_lighting_count"],
                    "completed_311_lighting_count": data["completed_311_lighting_count"],
                    "risk_lighting": data["risk_lighting"],
                }
                await crud.upsert_lighting_data(
                    db=session,
                    h3_index=h3_idx,
                    lat=data["lat"],
                    lng=data["lng"],
                    risk_lighting=data["risk_lighting"],
                    extra_features=extra_features
                )
                count += 1
            await crud.record_etl_run(session, "lighting_etl", records_processed=count)
            print(f"[311 Lighting ETL] Veritabanına {count} H3 hücresi kaydedildi/güncellendi ve etl_runs güncellendi.")
    except Exception as e:
        print(f"[311 Lighting ETL DB Uyarısı] DB kaydı atlandı veya hata oluştu: {e}")

    return aggregated_h3


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chicago 311 Sokak Lambası ETL Boru Hattı")
    parser.add_argument("--max-records", type=int, default=None, help="Çekilecek maks kayıt sayısı")
    parser.add_argument("--dry-run", action="store_true", help="DB'ye yazmadan sadece istatistik üret")
    args = parser.parse_args()

    asyncio.run(run_lighting_etl(max_records=args.max_records, dry_run=args.dry_run))
