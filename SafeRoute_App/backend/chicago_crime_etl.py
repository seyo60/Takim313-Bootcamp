# backend/chicago_crime_etl.py
"""
Chicago Police Suç Verileri ETL Boru Hattı (Socrata API -> H3 Resolution 9/10).

Socrata API: https://data.cityofchicago.org/resource/ijzp-q8t2.json
Tarih Aralığı: 2023-01-01 -> Günümüz

İşlem Adımları:
1. Socrata API'den suç kayıtları keyset cursor ile çekilir.
2. Geçerli koordinatlar seçilen H3 Res 9/10 hücresine dönüştürülür.
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
import time
import requests
import h3

from config import settings
from h3_policy import (
    LEGACY_H3_RESOLUTION,
    calibrated_child_risk,
    validate_h3_resolution,
)

CRIME_API_URL = getattr(settings, "chicago_crime_api_url", "https://data.cityofchicago.org/resource/ijzp-q8t2.json")
MAX_CRIME_PAGE_SIZE = 5000

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


class ETLFetchError(Exception):
    """Socrata API çekim hatası."""
    pass


def _make_api_request_with_retry(url: str, params: dict, headers: dict, timeout: int = 60, max_retries: int = 3) -> list[dict]:
    """
    Exponential backoff ve Retry-After başlığı desteği ile Socrata API isteği yapar.
    Sadece 429, 500, 502, 503, 504 ve ağ zaman aşımı hatalarında yeniden dener.
    """
    attempt = 0
    backoff_delay = 1.0

    while attempt <= max_retries:
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)

            if resp.status_code in (429, 500, 502, 503, 504):
                attempt += 1
                if attempt > max_retries:
                    raise ETLFetchError(f"API isteği HTTP {resp.status_code} hatası ile {max_retries} deneme sonrasında başarısız oldu.")

                retry_after = resp.headers.get("Retry-After")
                delay = None
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        pass
                if delay is None:
                    delay = backoff_delay
                    backoff_delay *= 2.0

                print(f"[Crime ETL Retry] HTTP {resp.status_code} alındı. {delay:.1f} saniye sonra tekrar deneniyor ({attempt}/{max_retries})...")
                time.sleep(delay)
                continue

            resp.raise_for_status()
            return resp.json()

        except requests.HTTPError as e:
            raise ETLFetchError(f"API HTTP Hatası: {e}")
        except (requests.Timeout, requests.ConnectionError, requests.RequestException) as e:
            attempt += 1
            if attempt > max_retries:
                raise ETLFetchError(f"API bağlantı hatası {max_retries} deneme sonrasında başarısız oldu: {e}")

            delay = backoff_delay
            backoff_delay *= 2.0
            print(f"[Crime ETL Retry] Ağ/Timeout hatası ({e}). {delay:.1f} saniye sonra tekrar deneniyor ({attempt}/{max_retries})...")
            time.sleep(delay)

    raise ETLFetchError(f"API isteği {max_retries} deneme sonrasında başarısız oldu.")


def get_crime_severity(primary_type: str) -> float:
    """Suç birincil türüne göre ciddiyet katsayısı döner (0.3 - 1.0)."""
    pt_upper = (primary_type or "").upper().strip()
    if pt_upper in VIOLENT_CRIMES:
        return 1.0
    elif pt_upper in PROPERTY_CRIMES:
        return 0.6
    return 0.3


def compute_stats_percentiles(values: list[float]) -> dict:
    """Listesindeki risk değerleri için min, median (p50), p95 ve max istatistiklerini hesaplar."""
    if not values:
        return {"min": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    min_val = round(sorted_vals[0], 4)
    max_val = round(sorted_vals[-1], 4)
    p50_val = round(sorted_vals[int(n * 0.50)], 4) if n > 1 else min_val
    p95_val = round(sorted_vals[min(n - 1, int(math.ceil(n * 0.95) - 1))], 4)
    return {
        "min": min_val,
        "p50": p50_val,
        "p95": p95_val,
        "max": max_val
    }


def fetch_chicago_crimes(
    start_date: str = "2023-01-01T00:00:00.000",
    limit: int = 5000,
    max_records: int = None,
    app_token: str = None
) -> list[dict]:
    """
    Socrata API üzerinden keyset pagination ile en yeni kayıtlar önde olacak
    şekilde ($order: date DESC, id ASC) suç verilerini çeker. Yüksek offset
    kullanılmadığı için API maliyeti veri büyüdükçe doğrusal biçimde bozulmaz.
    Sayfa boyutu en fazla MAX_CRIME_PAGE_SIZE (5000) olabilir.
    """
    records = []
    page_num = 0
    cursor_date = None
    cursor_id = None

    headers = {}
    token = app_token or getattr(settings, "chicago_data_app_token", "")
    if token:
        headers["X-App-Token"] = token

    effective_limit = min(limit, MAX_CRIME_PAGE_SIZE)

    print(f"[Crime ETL] API isteği başlatılıyor ({CRIME_API_URL})...")
    while True:
        if max_records is not None:
            remaining = max_records - len(records)
            if remaining <= 0:
                break
            current_batch_size = min(effective_limit, remaining)
        else:
            current_batch_size = effective_limit

        base_where = (
            f"date >= '{start_date}' AND latitude IS NOT NULL "
            "AND longitude IS NOT NULL"
        )
        if cursor_date is not None and cursor_id is not None:
            safe_date = str(cursor_date).replace("'", "''")
            safe_id = str(cursor_id).replace("'", "''")
            cursor_where = (
                f"(date < '{safe_date}' OR "
                f"(date = '{safe_date}' AND id > '{safe_id}'))"
            )
            where_clause = f"({base_where}) AND ({cursor_where})"
        else:
            where_clause = base_where

        params = {
            "$select": (
                "id,case_number,date,updated_on,primary_type,description,"
                "location_description,domestic,arrest,latitude,longitude"
            ),
            "$where": where_clause,
            "$order": "date DESC, id ASC",
            "$limit": current_batch_size,
        }

        batch = _make_api_request_with_retry(CRIME_API_URL, params=params, headers=headers, timeout=60)

        if not batch:
            break

        records.extend(batch)
        page_num += 1
        print(f"[Crime ETL] Sayfa {page_num}: {len(batch)} kayıt çekildi (Toplam: {len(records)} kayıt)...")

        last_item = batch[-1]
        next_cursor_date = last_item.get("date")
        next_cursor_id = last_item.get("id")
        if not next_cursor_date or next_cursor_id is None:
            raise ETLFetchError("Crime API response is missing date/id cursor fields")
        if (next_cursor_date, str(next_cursor_id)) == (cursor_date, cursor_id):
            raise ETLFetchError("Crime API cursor did not advance")
        cursor_date = next_cursor_date
        cursor_id = str(next_cursor_id)
        if len(batch) < current_batch_size:
            break
        if max_records and len(records) >= max_records:
            records = records[:max_records]
            break

    print(f"[Crime ETL] Toplam {len(records)} geçerli suç kaydı çekildi.")
    return records


def process_crime_records(
    records: list[dict],
    reference_date: datetime = None,
    h3_resolution: int = LEGACY_H3_RESOLUTION,
    parent_resolution: int = LEGACY_H3_RESOLUTION,
) -> dict[str, dict]:
    """
    Suç kayıtlarını seçilen H3 çözünürlüğüne dönüştürür ve agregasyonları hesaplar.

    Resolution 10'da hücre alanı yaklaşık yedi kat küçüldüğü için yerel yoğunluk
    res-9 ebeveyn öncülüyle kanıt miktarına göre yumuşatılır. Resolution 9
    varsayılan davranışı ve skorları geriye dönük uyumludur.
    Returns:
        { h3_index: { "lat": float, "lng": float, "crime_7d": int, ..., "risk_crime": float } }
    """
    if reference_date is None:
        reference_date = datetime.now(timezone.utc)
    h3_resolution = validate_h3_resolution(h3_resolution)
    parent_resolution = validate_h3_resolution(parent_resolution)
    if parent_resolution > h3_resolution:
        raise ValueError("parent_resolution, h3_resolution değerinden büyük olamaz.")

    # h3_index -> cell data
    cell_stats = {}
    parent_weighted_scores: dict[str, float] = {}

    for rec in records:
        try:
            lat = float(rec["latitude"])
            lng = float(rec["longitude"])
        except (KeyError, ValueError, TypeError):
            continue

        h3_idx = h3.latlng_to_cell(lat, lng, h3_resolution)

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
        time_decay = math.exp(-max(0.0, days_diff) / 45.0)  # 45 gün yarı ömürlü sönümlenme
        evidence_score = severity * time_decay
        cell["weighted_score"] += evidence_score

        if h3_resolution > parent_resolution:
            parent_idx = h3.cell_to_parent(h3_idx, parent_resolution)
            parent_weighted_scores[parent_idx] = (
                parent_weighted_scores.get(parent_idx, 0.0) + evidence_score
            )

    # Hücre merkezlerini ve nihai 0-1 risk_crime skorlarını hesapla
    h3_heatmap_data = {}
    for h3_idx, stats in cell_stats.items():
        avg_lat, avg_lng = h3.cell_to_latlng(h3_idx)

        # Sigmoid / Min-Max benzeri 0.0 - 1.0 normalizasyon
        # 10 ve üzeri ağırlıklı puan 1.0 risk kabul edilir
        raw_score = stats["weighted_score"]
        if h3_resolution > parent_resolution:
            parent_idx = h3.cell_to_parent(h3_idx, parent_resolution)
            (
                risk_crime,
                local_density_risk,
                parent_risk,
                evidence_weight,
            ) = calibrated_child_risk(
                local_raw_score=raw_score,
                parent_raw_score=parent_weighted_scores.get(parent_idx, 0.0),
                base_saturation_score=10.0,
                evidence=raw_score,
                child_resolution=h3_resolution,
                parent_resolution=parent_resolution,
                shrinkage_strength=float(
                    getattr(settings, "crime_h3_shrinkage_strength", 2.0)
                ),
            )
        else:
            parent_idx = h3_idx
            risk_crime = max(0.0, min(1.0, raw_score / 10.0))
            local_density_risk = risk_crime
            parent_risk = risk_crime
            evidence_weight = 1.0

        h3_heatmap_data[h3_idx] = {
            "h3_resolution": h3_resolution,
            "parent_h3_index": parent_idx,
            "lat": avg_lat,
            "lng": avg_lng,
            "crime_7d": stats["crime_7d"],
            "crime_30d": stats["crime_30d"],
            "crime_90d": stats["crime_90d"],
            "violent_crime_30d": stats["violent_crime_30d"],
            "night_crime_30d": stats["night_crime_30d"],
            "risk_crime": round(risk_crime, 4),
            "local_density_risk_crime": round(local_density_risk, 4),
            "parent_risk_crime": round(parent_risk, 4),
            "evidence_weight": round(evidence_weight, 4),
        }

    return h3_heatmap_data


DEFAULT_ETL_BATCH_SIZE = 250


class ETLWriteError(Exception):
    """ETL Veritabanı yazma hatası."""
    pass


def _is_transient_db_error(e: Exception) -> bool:
    """Geçici veritabanı/bağlantı hatalarını tespit eder."""
    err_str = str(e).lower()
    err_type = type(e).__name__.lower()
    if "connection" in err_type or "connection" in err_str:
        return True
    if "closed" in err_str or "reset" in err_str or "pooler" in err_str or "doesnotexist" in err_str or "invalidated" in err_str:
        return True
    if "operationalerror" in err_type or "dbapierror" in err_type:
        return True
    return False


async def run_crime_etl(
    max_records: int = None,
    dry_run: bool = False,
    batch_size: int = DEFAULT_ETL_BATCH_SIZE,
    h3_resolution: int | None = None,
    mode: str = "incremental",
    lookback_days: int = 90,
):
    """Run a bounded rolling refresh or an explicit historical bootstrap."""
    if mode not in {"incremental", "bootstrap"}:
        raise ETLFetchError("mode must be incremental or bootstrap")
    if lookback_days < 90 or lookback_days > 3650:
        raise ETLFetchError("lookback_days must be between 90 and 3650")
    selected_resolution = validate_h3_resolution(
        h3_resolution
        if h3_resolution is not None
        else getattr(settings, "etl_h3_resolution", LEGACY_H3_RESOLUTION)
    )
    start_date = (
        "2023-01-01T00:00:00.000"
        if mode == "bootstrap"
        else (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime(
            "%Y-%m-%dT%H:%M:%S.000"
        )
    )
    records = fetch_chicago_crimes(
        start_date=start_date,
        max_records=max_records,
    )

    if len(records) == 0 and not dry_run:
        raise ETLFetchError("API üretken (production) modda 0 kayıt döndürdü. Veritabanının silinmesini/boşaltılmasını önlemek için işlem durduruldu.")

    print(f"[Crime ETL] İşleniyor ({len(records)} kayıt)...")
    aggregated_h3 = process_crime_records(
        records,
        h3_resolution=selected_resolution,
        parent_resolution=getattr(
            settings,
            "h3_parent_resolution",
            LEGACY_H3_RESOLUTION,
        ),
    )
    total_cells = len(aggregated_h3)
    print(
        f"[Crime ETL] Toplam {total_cells} farklı H3 Res "
        f"{selected_resolution} hücresi oluşturuldu/hesaplandı."
    )

    # Tarih aralığını belirle
    valid_dates = []
    for r in records:
        d_str = r.get("date")
        if d_str:
            valid_dates.append(d_str)

    min_event_date = min(valid_dates) if valid_dates else "Bilinmiyor"
    max_event_date = max(valid_dates) if valid_dates else "Bilinmiyor"

    risk_vals = [c["risk_crime"] for c in aggregated_h3.values()]
    positive_risk_count = sum(1 for r in risk_vals if r > 0.0)
    total_7d = sum(c["crime_7d"] for c in aggregated_h3.values())
    total_30d = sum(c["crime_30d"] for c in aggregated_h3.values())
    total_90d = sum(c["crime_90d"] for c in aggregated_h3.values())
    stats = compute_stats_percentiles(risk_vals)

    print("\n=======================================================")
    print("             CRIME ETL DOĞRULAMA İSTATİSTİKLERİ        ")
    print("=======================================================")
    print(f"  En Eski Olay Tarihi   : {min_event_date}")
    print(f"  En Yeni Olay Tarihi   : {max_event_date}")
    print(f"  Toplam İşlenen Kayıt  : {len(records)}")
    print(f"  Toplam H3 Hücresi     : {len(aggregated_h3)}")
    print(f"  risk_crime > 0 Hücre  : {positive_risk_count}")
    print(f"  Toplam Sayaçlar (7d/30d/90d): 7d={total_7d}, 30d={total_30d}, 90d={total_90d}")
    print(f"  risk_crime Min        : {stats['min']}")
    print(f"  risk_crime Median(p50): {stats['p50']}")
    print(f"  risk_crime P95        : {stats['p95']}")
    print(f"  risk_crime Max        : {stats['max']}")
    print("=======================================================\n")

    if dry_run:
        print("[Crime ETL Dry-Run] Dry-run aktif. Veritabanına yazma yapılmadı.")
        return aggregated_h3

    configured_write_resolution = validate_h3_resolution(
        getattr(settings, "etl_h3_resolution", LEGACY_H3_RESOLUTION)
    )
    if selected_resolution != configured_write_resolution:
        raise ETLWriteError(
            "H3 çözünürlük yazma koruması: seçilen çözünürlük "
            f"{selected_resolution}, ETL_H3_RESOLUTION={configured_write_resolution} "
            "ile aynı değil. Dry-run dışında örtük çözünürlük geçişine izin verilmez."
        )

    # Veritabanına toplu (bulk) batch yazma
    from main import AsyncSessionLocal
    import crud

    items = []
    for h3_idx, data in aggregated_h3.items():
        extra_features = {
            "h3_resolution": selected_resolution,
            "parent_h3_index": data["parent_h3_index"],
            "crime_7d": data["crime_7d"],
            "crime_30d": data["crime_30d"],
            "crime_90d": data["crime_90d"],
            "violent_crime_30d": data["violent_crime_30d"],
            "night_crime_30d": data["night_crime_30d"],
            "risk_crime": data["risk_crime"],
            "local_density_risk_crime": data["local_density_risk_crime"],
            "parent_risk_crime": data["parent_risk_crime"],
            "evidence_weight": data["evidence_weight"],
        }
        items.append({
            "h3_index": h3_idx,
            "h3_resolution": selected_resolution,
            "lat": data["lat"],
            "lng": data["lng"],
            "risk_crime": data["risk_crime"],
            "extra_features": extra_features
        })

    total_batches = math.ceil(len(items) / batch_size) if items else 0
    processed_count = 0

    for i in range(total_batches):
        batch_num = i + 1
        start_idx = i * batch_size
        end_idx = min(len(items), (i + 1) * batch_size)
        current_batch = items[start_idx:end_idx]

        attempt = 0
        max_retries = 3
        backoff_delay = 1.0
        batch_success = False

        while attempt <= max_retries:
            session = AsyncSessionLocal()
            try:
                async with session.begin():
                    await crud.bulk_upsert_crime_data(session, current_batch)
                batch_success = True
                await session.close()
                break
            except Exception as e:
                attempt += 1
                transient = _is_transient_db_error(e)
                if transient:
                    try:
                        await session.invalidate()
                    except Exception:
                        pass
                else:
                    try:
                        await session.rollback()
                    except Exception:
                        pass
                    try:
                        await session.close()
                    except Exception:
                        pass

                if transient and attempt <= max_retries:
                    print(f"[Crime ETL DB Retry] Batch {batch_num}/{total_batches} ({start_idx+1}-{end_idx}) geçici DB hatası ({e}). {backoff_delay:.1f}s sonra tekrar deneniyor ({attempt}/{max_retries})...")
                    await asyncio.sleep(backoff_delay)
                    backoff_delay *= 2.0
                else:
                    raise ETLWriteError(f"Batch {batch_num}/{total_batches} ({start_idx+1}-{end_idx}) {attempt} deneme sonrasında kalıcı veritabanı hatası aldı: {e}")

        if not batch_success:
            raise ETLWriteError(f"Batch {batch_num}/{total_batches} işlenemedi.")

        processed_count += len(current_batch)
        print(f"Batch {batch_num}/{total_batches} tamamlandı — {processed_count}/{total_cells} hücre")

    # Tüm batch'ler 100% başarıyla tamamlandıktan sonra etl_runs kaydı oluştur/güncelle
    async with AsyncSessionLocal() as session:
        etl_name = (
            "crime_etl"
            if selected_resolution == LEGACY_H3_RESOLUTION
            else f"crime_etl_r{selected_resolution}"
        )
        await crud.record_etl_run(session, etl_name, records_processed=processed_count)
    print(f"[Crime ETL] Toplam {processed_count} H3 hücresi başarıyla kaydedildi/güncellendi ve etl_runs güncellendi.")

    return aggregated_h3


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chicago Suç Verisi ETL Boru Hattı")
    parser.add_argument("--max-records", type=int, default=None, help="Çekilecek maks kayıt sayısı")
    parser.add_argument("--dry-run", action="store_true", help="DB'ye yazmadan sadece istatistik üret")
    parser.add_argument(
        "--mode",
        choices=("incremental", "bootstrap"),
        default="incremental",
        help="incremental: rolling lookback, bootstrap: 2023'ten tam yükleme",
    )
    parser.add_argument("--lookback-days", type=int, default=90)
    parser.add_argument(
        "--h3-resolution",
        type=int,
        choices=(9, 10),
        default=None,
        help="H3 çözünürlüğü (varsayılan: ETL_H3_RESOLUTION, güvenli değer 9)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(
            run_crime_etl(
                max_records=args.max_records,
                dry_run=args.dry_run,
                h3_resolution=args.h3_resolution,
                mode=args.mode,
                lookback_days=args.lookback_days,
            )
        )
    except (ETLFetchError, ETLWriteError) as err:
        print(f"[Crime ETL HATA] Boru hattı başarısız: {err}", file=sys.stderr)
        sys.exit(1)
    except Exception as err:
        print(f"[Crime ETL Beklenmeyen Hata]: {err}", file=sys.stderr)
        sys.exit(1)
