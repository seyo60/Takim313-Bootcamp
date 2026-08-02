# backend/chicago_311_lighting_etl.py
"""
Chicago 311 Sokak Lambası Arızaları ETL Boru Hattı (Socrata API -> H3 Resolution 9/10).

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
import os
import argparse
import asyncio
from datetime import datetime, timezone, timedelta
import math
import time
import random
import json
import uuid
from typing import Any
from pathlib import Path
import requests
import h3

from config import settings
from h3_policy import (
    LEGACY_H3_RESOLUTION,
    calibrated_child_risk,
    validate_h3_resolution,
)

REQUESTS_311_API_URL = getattr(settings, "chicago_311_api_url", "https://data.cityofchicago.org/resource/v6vf-nfxy.json")
MAX_LIGHTING_PAGE_SIZE = 1000

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

CHECKPOINT_DIR = Path(__file__).parent / ".etl_checkpoints"
CHECKPOINT_FILE = CHECKPOINT_DIR / "lighting_etl_checkpoint.json"
RECORDS_CACHE_FILE = CHECKPOINT_DIR / "lighting_records_cache.json"


class ETLFetchError(Exception):
    """Socrata API çekim hatası."""
    pass


class ETLCheckpointManager:
    """Güvenli, hassas veri barındırmayan ETL checkpoint yöneticisi."""

    def __init__(
        self,
        checkpoint_file: Path = None,
        cache_file: Path = None,
        checkpoint_dir: Path = None
    ):
        if checkpoint_dir is not None:
            cp_dir = Path(checkpoint_dir).resolve()
        elif checkpoint_file is not None:
            cp_dir = Path(checkpoint_file).parent.resolve()
        else:
            cp_dir = CHECKPOINT_DIR.resolve()

        # KRİTİK GÜVENLİK KONTROLÜ: pytest ortamında varsayılan production checkpoint dizinini kullanmak kesinlikle yasaktır!
        if "PYTEST_CURRENT_TEST" in os.environ:
            real_prod_dir = CHECKPOINT_DIR.resolve()
            if cp_dir == real_prod_dir or real_prod_dir in cp_dir.parents:
                raise RuntimeError(
                    f"[ETL SAFETY GUARD ABORT] Test suite varsayılan production checkpoint dizinine erişmeye çalıştı: {cp_dir}. "
                    "Tüm testlerde `tmp_path` ile oluşturulmuş ayrı bir checkpoint_dir kullanılmalıdır!"
                )

        if checkpoint_dir is not None:
            self.checkpoint_dir = Path(checkpoint_dir)
            self.checkpoint_file = self.checkpoint_dir / "lighting_etl_checkpoint.json"
            self.cache_file = self.checkpoint_dir / "lighting_records_cache.json"
        else:
            self.checkpoint_file = checkpoint_file if checkpoint_file else CHECKPOINT_FILE
            self.cache_file = cache_file if cache_file else RECORDS_CACHE_FILE
            self.checkpoint_dir = self.checkpoint_file.parent

        self.lock_file = self.checkpoint_dir / ".etl_instance.lock"
        self._lock_fh = None

    def ensure_dir(self):
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def acquire_lock(self):
        self.ensure_dir()
        if self._lock_fh is not None:
            return
        try:
            self._lock_fh = open(self.lock_file, "a+", encoding="utf-8")
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_fh.seek(0)
            self._lock_fh.truncate()
            self._lock_fh.write(f"PID: {os.getpid()} - {datetime.now(timezone.utc).isoformat()}\n")
            self._lock_fh.flush()
        except (OSError, IOError) as e:
            if self._lock_fh:
                try:
                    self._lock_fh.close()
                except Exception:
                    pass
                self._lock_fh = None
            raise RuntimeError(
                f"[ETL SINGLE-INSTANCE LOCK ERROR] Başka bir ETL süreci bu checkpoint dizinini kullanıyor ({self.checkpoint_dir}): {e}"
            )

    def release_lock(self):
        if self._lock_fh:
            try:
                if os.name == "nt":
                    import msvcrt
                    try:
                        self._lock_fh.seek(0)
                        msvcrt.locking(self._lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
                    except Exception:
                        pass
                else:
                    import fcntl
                    try:
                        fcntl.flock(self._lock_fh.fileno(), fcntl.LOCK_UN)
                    except Exception:
                        pass
                self._lock_fh.close()
            except Exception:
                pass
            finally:
                self._lock_fh = None

    def load(self, resume: bool = False, reset: bool = False) -> dict | None:
        if reset:
            self.clear()
            return None

        if not self.checkpoint_file.exists():
            if resume:
                raise ETLFetchError(f"Resume seçeneği aktif fakat checkpoint dosyası bulunamadı: {self.checkpoint_file}")
            return None

        try:
            with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise ETLFetchError(f"Bozuk/okunamayan checkpoint dosyası algılandı: {e}")

        # Şema ve bütünlük doğrulaması
        if not isinstance(data, dict):
            raise ETLFetchError("Checkpoint veri yapısı bir sözlük (dict) olmalıdır.")

        required_keys = {"version", "etl_name", "status"}
        if not required_keys.issubset(data.keys()):
            raise ETLFetchError("Checkpoint dosyasında zorunlu alanlar eksik.")

        if data.get("etl_name") != "lighting_etl":
            raise ETLFetchError(f"Uyumsuz ETL checkpoint dosyası: '{data.get('etl_name')}' != 'lighting_etl'")

        # Hassas veri kontrolü (DATABASE_URL, parola, token vb. olmamalı)
        sensitive_keywords = ["database_url", "password", "token", "secret"]
        for key in data.keys():
            if any(s in key.lower() for s in sensitive_keywords):
                raise ETLFetchError("Checkpoint dosyasında güvenlik riski oluşturabilecek hassas anahtar tespit edildi.")

        if not resume and data.get("status") == "in_progress":
            print(f"[311 Lighting ETL Checkpoint] Mevcut yarım kalmış checkpoint algılandı: {self.checkpoint_file}")

        return data

    def load_cached_records(self) -> list[dict]:
        if not self.cache_file.exists():
            return []
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[311 Lighting ETL Checkpoint] Uyarı: Önbellek dosyası okunamadı ({e}).")
            return []

    def _atomic_write_file(self, target_path: Path, data_obj: Any):
        """
        Veriyi geçici bir dosyaya yazar, flush + fsync yapar ve hedef dosyaya atomik olarak taşır.
        Windows PermissionError durumunda katlanarak artan gecikme (backoff) ile 10 kez retry yapar.
        """
        self.ensure_dir()
        unique_id = uuid.uuid4().hex[:8]
        temp_path = target_path.with_name(f"{target_path.stem}_{unique_id}.tmp")

        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data_obj, f, indent=2 if "checkpoint" in target_path.name else None, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
        except Exception as err:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            raise err

        max_retries = 10
        for attempt in range(max_retries):
            try:
                os.replace(temp_path, target_path)
                return
            except PermissionError as pe:
                if attempt == max_retries - 1:
                    if temp_path.exists():
                        try:
                            temp_path.unlink()
                        except Exception:
                            pass
                    raise PermissionError(f"Atomic file replace failed after {max_retries} retries for {target_path}: {pe}")
                time.sleep(0.05 * (1.5 ** attempt))
            except Exception as ex:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass
                raise ex

    def save(self, data: dict, records: list[dict] = None):
        self.ensure_dir()
        data["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Hassas bilgileri ayıkla
        sensitive_keywords = ["database_url", "password", "token", "secret"]
        clean_data = {k: v for k, v in data.items() if not any(s in k.lower() for s in sensitive_keywords)}

        # 1. Önce cache dosyasını atomik olarak yaz ve değiştir!
        if records is not None:
            self._atomic_write_file(self.cache_file, records)

        # 2. Cache yazımı BAŞARILI OLDUKTAN SONRA checkpoint metadata dosyasını kaydet!
        self._atomic_write_file(self.checkpoint_file, clean_data)

    def mark_completed(self):
        data = self.load(resume=False, reset=False) or {}
        data["status"] = "completed"
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.save(data)

    def clear(self):
        if self.checkpoint_file.exists():
            try:
                self.checkpoint_file.unlink()
            except Exception:
                pass
        if self.cache_file.exists():
            try:
                self.cache_file.unlink()
            except Exception:
                pass
        print("[311 Lighting ETL Checkpoint] Checkpoint ve önbellek dosyaları silindi.")


def build_date_windows(
    start_date_str: str = "2023-01-01T00:00:00.000",
    end_date_str: str = None,
    end_date_dt: datetime = None,
    window_days: int = 7
) -> list[tuple[str, str]]:
    """
    start_date_str ile end_date arasındaki zaman aralığını en yeni tarihten eskiye doğru
    window_days günlük çakışmasız pencerelere böler.
    Returns: list of (window_start_iso, window_end_iso) tuples.
    """
    if end_date_dt is None:
        if end_date_str:
            end_clean = end_date_str.replace("Z", "+00:00")
            try:
                end_date_dt = datetime.fromisoformat(end_clean)
                if end_date_dt.tzinfo is None:
                    end_date_dt = end_date_dt.replace(tzinfo=timezone.utc)
            except Exception:
                end_date_dt = datetime.now(timezone.utc)
        else:
            end_date_dt = datetime.now(timezone.utc)

    start_clean = start_date_str.replace("Z", "+00:00")
    try:
        start_dt = datetime.fromisoformat(start_clean)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
    except Exception:
        start_dt = datetime(2023, 1, 1, tzinfo=timezone.utc)

    windows = []
    curr_end = end_date_dt

    while curr_end > start_dt:
        curr_start = max(start_dt, curr_end - timedelta(days=window_days))
        w_start_str = curr_start.strftime("%Y-%m-%dT%H:%M:%S.000")
        w_end_str = curr_end.strftime("%Y-%m-%dT%H:%M:%S.000")
        windows.append((w_start_str, w_end_str))
        curr_end = curr_start

    return windows


def _make_api_request_with_retry(
    url: str,
    params: dict,
    headers: dict,
    timeout: tuple[int, int] | int = (15, 180),
    max_retries: int = 6
) -> list[dict]:
    """
    Connect timeout (15s) ve Read timeout (180s) ayrımı, en az 6 deneme,
    exponential backoff + jitter ve Retry-After desteği ile Socrata API isteği yapar.
    Sadece 429, 500, 502, 503, 504 ve ağ zaman aşımı hatalarında yeniden dener.
    """
    attempt = 0
    base_backoff = 1.0

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
                    jitter = random.uniform(0.1, 0.5)
                    delay = base_backoff + jitter
                    base_backoff *= 2.0

                print(f"[311 Lighting ETL Retry] HTTP {resp.status_code} alındı. {delay:.1f}s sonra tekrar deneniyor ({attempt}/{max_retries})...")
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

            jitter = random.uniform(0.1, 0.5)
            delay = base_backoff + jitter
            base_backoff *= 2.0
            print(f"[311 Lighting ETL Retry] Ağ/Timeout hatası ({e}). {delay:.1f}s sonra tekrar deneniyor ({attempt}/{max_retries})...")
            time.sleep(delay)

    raise ETLFetchError(f"API isteği {max_retries} deneme sonrasında başarısız oldu.")


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
        return 0.0, 0.0, 0.0

    status_factor = 1.0
    days_open = max(0.0, (reference_dt - created_dt).total_seconds() / 86400.0)

    time_decay = math.exp(-days_open / 180.0)
    time_factor = max(0.6, time_decay)

    ticket_risk = severity * status_factor * time_factor
    return ticket_risk, status_factor, time_factor


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


PAGE_SIZE_LEVELS = [1000, 500, 250, 100]


def fetch_chicago_311_lighting(
    start_date: str = "2023-01-01T00:00:00.000",
    end_date: str = None,
    limit: int = 1000,
    max_records: int = None,
    app_token: str = None,
    resume: bool = False,
    reset_checkpoint: bool = False,
    page_size: int = None,
    window_days: int = 7,
    checkpoint_mgr: ETLCheckpointManager = None,
) -> list[dict]:
    """
    Tarih pencereli (date-windowed) ve Keyset (Cursor) sayfalama ile 311 sokak lambası şikayetlerini çeker.
    Adaptif sayfa küçültme (1000 -> 500 -> 250 -> 100) ve checkpoint resume dayanıklılığı sunar.
    """
    if checkpoint_mgr is None:
        checkpoint_mgr = ETLCheckpointManager()

    checkpoint_mgr.acquire_lock()
    try:
        if resume:
            cp_data = checkpoint_mgr.load(resume=True, reset=False)
        elif reset_checkpoint:
            checkpoint_mgr.clear()
            cp_data = None
        else:
            checkpoint_mgr.clear()
            cp_data = None

        records = []
        windows = build_date_windows(start_date_str=start_date, end_date_str=end_date, window_days=window_days)
        current_window_idx = 0
        last_created_date = None
        last_sr_number = None

        if cp_data and cp_data.get("status") == "in_progress":
            current_window_idx = cp_data.get("current_window_index", 0)
            last_created_date = cp_data.get("last_created_date")
            last_sr_number = cp_data.get("last_sr_number")
            cached = checkpoint_mgr.load_cached_records()
            if cached:
                records = cached
                print(f"[311 Lighting ETL Resume] Checkpoint'ten {len(records)} kayıt yüklendi. Pencere {current_window_idx+1}/{len(windows)} üzerinden devam ediliyor...")

        headers = {}
        token = app_token or getattr(settings, "chicago_data_app_token", "")
        if token:
            headers["X-App-Token"] = token

        initial_size = page_size if page_size is not None else limit
        target_page_size = min(initial_size, MAX_LIGHTING_PAGE_SIZE)
        current_page_size = target_page_size
        consecutive_successes = 0

        sr_filter_query = (
            "sr_type LIKE '%Street Light%' OR "
            "sr_type LIKE '%Alley Light%' OR "
            "sr_type LIKE '%Viaduct Light%' OR "
            "sr_type LIKE '%Traffic Signal%'"
        )

        print(f"[311 Lighting ETL] Tarih pencereli Keyset API çekimi başlatılıyor ({len(windows)} pencere)...")

        while current_window_idx < len(windows):
            w_start, w_end = windows[current_window_idx]
            base_where = f"({sr_filter_query}) AND created_date >= '{w_start}' AND created_date < '{w_end}' AND latitude IS NOT NULL AND longitude IS NOT NULL"

            window_completed = False

            while not window_completed:
                if max_records is not None:
                    remaining = max_records - len(records)
                    if remaining <= 0:
                        break
                    fetch_limit = min(current_page_size, remaining)
                else:
                    fetch_limit = current_page_size

                if last_created_date is not None and last_sr_number is not None:
                    clean_date = str(last_created_date).replace("'", "''")
                    clean_sr = str(last_sr_number).replace("'", "''")
                    cursor_cond = f"(created_date < '{clean_date}' OR (created_date = '{clean_date}' AND sr_number > '{clean_sr}'))"
                    where_clause = f"({base_where}) AND ({cursor_cond})"
                else:
                    where_clause = base_where

                params = {
                    "$where": where_clause,
                    "$order": "created_date DESC, sr_number ASC",
                    "$limit": fetch_limit,
                }

                # Adaptif sayfa boyutu ile API isteği
                batch = None
                fetch_attempt = 0
                max_fetch_attempts = len(PAGE_SIZE_LEVELS)

                while fetch_attempt < max_fetch_attempts:
                    try:
                        params["$limit"] = fetch_limit
                        batch = _make_api_request_with_retry(REQUESTS_311_API_URL, params=params, headers=headers, timeout=(15, 180), max_retries=6)
                        break
                    except ETLFetchError as err:
                        fetch_attempt += 1
                        if current_page_size in PAGE_SIZE_LEVELS:
                            current_idx = PAGE_SIZE_LEVELS.index(current_page_size)
                            if current_idx < len(PAGE_SIZE_LEVELS) - 1:
                                new_size = PAGE_SIZE_LEVELS[current_idx + 1]
                                print(f"[311 Lighting ETL Adaptif] API hatası/timeout alındı. Sayfa boyutu {current_page_size}'den {new_size}'ye düşürüldü.")
                                current_page_size = new_size
                                fetch_limit = min(current_page_size, fetch_limit)
                                consecutive_successes = 0
                                continue

                        raise err

                if batch is None or len(batch) == 0:
                    window_completed = True
                    break

                records.extend(batch)
                consecutive_successes += 1

                # Başarılı işlemler sonrası sayfa boyutunu kademeli büyüt
                if consecutive_successes >= 3 and current_page_size < target_page_size:
                    current_idx = PAGE_SIZE_LEVELS.index(current_page_size)
                    new_size = PAGE_SIZE_LEVELS[current_idx - 1]
                    print(f"[311 Lighting ETL Adaptif] 3 başarılı sayfa sonrası sayfa boyutu {current_page_size}'den {new_size}'ye yükseltildi.")
                    current_page_size = new_size
                    consecutive_successes = 0

                last_item = batch[-1]
                last_created_date = last_item.get("created_date")
                last_sr_number = last_item.get("sr_number") or ""

                # Checkpoint güncelle
                checkpoint_data = {
                    "version": "1.0",
                    "etl_name": "lighting_etl",
                    "status": "in_progress",
                    "start_date": start_date,
                    "window_days": window_days,
                    "current_window_index": current_window_idx,
                    "total_windows": len(windows),
                    "current_window_start": w_start,
                    "current_window_end": w_end,
                    "last_created_date": last_created_date,
                    "last_sr_number": last_sr_number,
                    "records_count": len(records),
                }
                checkpoint_mgr.save(checkpoint_data, records=records)

                if len(batch) < fetch_limit:
                    window_completed = True

                if max_records and len(records) >= max_records:
                    records = records[:max_records]
                    break

            if max_records and len(records) >= max_records:
                break

            # Pencere tamamlandı, sonraki pencereye geç
            current_window_idx += 1
            last_created_date = None
            last_sr_number = None

            checkpoint_mgr.save(checkpoint_data, records=records)

            print(f"[311 Lighting ETL] Pencere {current_window_idx}/{len(windows)} tamamlandı (Toplam: {len(records)} kayıt)...")

        checkpoint_mgr.mark_completed()
        print(f"[311 Lighting ETL] Toplam {len(records)} geçerli aydınlatma şikayet kaydı başarıyla çekildi.")
        return records
    finally:
        checkpoint_mgr.release_lock()


def process_lighting_records(
    records: list[dict],
    reference_date: datetime = None,
    h3_resolution: int = LEGACY_H3_RESOLUTION,
    parent_resolution: int = LEGACY_H3_RESOLUTION,
) -> tuple[dict[str, dict], dict]:
    """
    311 kayıtlarını seçilen H3 çözünürlüğüne dönüştürür ve risk_lighting skorlarını hesaplar.
    Mükerrer (duplicate) kayıtlar tekleştirilir.
    Returns: (h3_heatmap_data, meta_summary)
    """
    if reference_date is None:
        reference_date = datetime.now(timezone.utc)
    h3_resolution = validate_h3_resolution(h3_resolution)
    parent_resolution = validate_h3_resolution(parent_resolution)
    if parent_resolution > h3_resolution:
        raise ValueError("parent_resolution, h3_resolution değerinden büyük olamaz.")

    cell_stats = {}
    parent_active_risks: dict[str, float] = {}
    seen_sr_numbers = set()
    duplicate_count = 0
    open_records_count = 0
    closed_records_count = 0

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

        h3_idx = h3.latlng_to_cell(lat, lng, h3_resolution)

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

        if status_factor > 0.0:
            open_records_count += 1
        else:
            closed_records_count += 1

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
            if h3_resolution > parent_resolution:
                parent_idx = h3.cell_to_parent(h3_idx, parent_resolution)
                parent_active_risks[parent_idx] = (
                    parent_active_risks.get(parent_idx, 0.0) + ticket_risk
                )
        else:
            cell["completed_count"] += 1

    print(f"[311 Lighting ETL] {duplicate_count} adet mükerrer (duplicate) kayıt süzüldü.")

    h3_heatmap_data = {}
    for h3_idx, stats in cell_stats.items():
        avg_lat, avg_lng = h3.cell_to_latlng(h3_idx)

        # 3 ve üzeri aktif ağır arıza 1.0 azami risk verir
        raw_score = stats["total_active_risk"]
        if h3_resolution > parent_resolution:
            parent_idx = h3.cell_to_parent(h3_idx, parent_resolution)
            (
                risk_lighting,
                local_density_risk,
                parent_risk,
                evidence_weight,
            ) = calibrated_child_risk(
                local_raw_score=raw_score,
                parent_raw_score=parent_active_risks.get(parent_idx, 0.0),
                base_saturation_score=3.0,
                evidence=raw_score,
                child_resolution=h3_resolution,
                parent_resolution=parent_resolution,
                shrinkage_strength=float(
                    getattr(settings, "lighting_h3_shrinkage_strength", 1.0)
                ),
            )
        else:
            parent_idx = h3_idx
            risk_lighting = max(0.0, min(1.0, raw_score / 3.0))
            local_density_risk = risk_lighting
            parent_risk = risk_lighting
            evidence_weight = 1.0

        h3_heatmap_data[h3_idx] = {
            "h3_resolution": h3_resolution,
            "parent_h3_index": parent_idx,
            "lat": avg_lat,
            "lng": avg_lng,
            "open_311_lighting_count": stats["open_count"],
            "completed_311_lighting_count": stats["completed_count"],
            "risk_lighting": round(risk_lighting, 4),
            "local_density_risk_lighting": round(local_density_risk, 4),
            "parent_risk_lighting": round(parent_risk, 4),
            "evidence_weight": round(evidence_weight, 4),
        }

    meta_summary = {
        "duplicate_count": duplicate_count,
        "open_records_count": open_records_count,
        "closed_records_count": closed_records_count,
    }

    return h3_heatmap_data, meta_summary


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


async def run_lighting_etl(
    max_records: int = None,
    dry_run: bool = False,
    resume: bool = False,
    reset_checkpoint: bool = False,
    page_size: int = 1000,
    window_days: int = 7,
    batch_size: int = DEFAULT_ETL_BATCH_SIZE,
    checkpoint_mgr: ETLCheckpointManager = None,
    h3_resolution: int | None = None,
    mode: str = "incremental",
    lookback_days: int = 180,
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
    if checkpoint_mgr is None:
        checkpoint_mgr = ETLCheckpointManager()

    start_date = (
        "2023-01-01T00:00:00.000"
        if mode == "bootstrap"
        else (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime(
            "%Y-%m-%dT%H:%M:%S.000"
        )
    )

    records = fetch_chicago_311_lighting(
        start_date=start_date,
        max_records=max_records,
        resume=resume,
        reset_checkpoint=reset_checkpoint,
        page_size=page_size,
        window_days=window_days,
        checkpoint_mgr=checkpoint_mgr,
    )

    if len(records) == 0 and not dry_run:
        raise ETLFetchError("API üretken (production) modda 0 kayıt döndürdü. Veritabanının silinmesini/boşaltılmasını önlemek için işlem durduruldu.")

    if not dry_run and max_records is None and len(records) < 500:
        raise ETLFetchError(f"API anormal derecede düşük sayıda ({len(records)}) kayıt döndürdü. Veritabanının silinmesini/boşaltılmasını önlemek için işlem durduruldu.")

    print(f"[311 Lighting ETL] İşleniyor ({len(records)} kayıt)...")
    aggregated_h3, meta = process_lighting_records(
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
        f"[311 Lighting ETL] Toplam {total_cells} farklı H3 Res "
        f"{selected_resolution} hücresi hesaplandı."
    )

    # Tüm risk_lighting değerlerinin 0–1 aralığında kaldığını doğrula
    risk_vals = [c["risk_lighting"] for c in aggregated_h3.values()]
    assert all(0.0 <= r <= 1.0 for r in risk_vals), "Kanatsız risk_lighting değeri 0 ile 1 aralığı dışında tespit edildi!"

    valid_dates = [r.get("created_date") for r in records if r.get("created_date")]
    min_date = min(valid_dates) if valid_dates else "Bilinmiyor"
    max_date = max(valid_dates) if valid_dates else "Bilinmiyor"

    positive_risk_count = sum(1 for r in risk_vals if r > 0.0)
    stats = compute_stats_percentiles(risk_vals)

    print("\n=======================================================")
    print("         311 LIGHTING ETL DOĞRULAMA İSTATİSTİKLERİ     ")
    print("=======================================================")
    print(f"  En Eski Created Date  : {min_date}")
    print(f"  En Yeni Created Date  : {max_date}")
    print(f"  Toplam İşlenen Kayıt  : {len(records)}")
    print(f"  Duplicate Kayıt Sayısı: {meta['duplicate_count']}")
    print(f"  Açık Kayıt Sayısı     : {meta['open_records_count']}")
    print(f"  Kapalı Kayıt Sayısı   : {meta['closed_records_count']}")
    print(f"  Toplam H3 Hücresi     : {len(aggregated_h3)}")
    print(f"  risk_lighting > 0     : {positive_risk_count}")
    print(f"  risk_lighting Min     : {stats['min']}")
    print(f"  risk_lighting Median  : {stats['p50']}")
    print(f"  risk_lighting P95     : {stats['p95']}")
    print(f"  risk_lighting Max     : {stats['max']}")
    print("=======================================================\n")

    if dry_run:
        print("[311 Lighting ETL Dry-Run] Dry-run aktif. Veritabanına yazma yapılmadı.")
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
            "open_311_lighting_count": data["open_311_lighting_count"],
            "completed_311_lighting_count": data["completed_311_lighting_count"],
            "risk_lighting": data["risk_lighting"],
            "local_density_risk_lighting": data["local_density_risk_lighting"],
            "parent_risk_lighting": data["parent_risk_lighting"],
            "evidence_weight": data["evidence_weight"],
        }
        items.append({
            "h3_index": h3_idx,
            "h3_resolution": selected_resolution,
            "lat": data["lat"],
            "lng": data["lng"],
            "risk_lighting": data["risk_lighting"],
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
                    await crud.bulk_upsert_lighting_data(session, current_batch)
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
                    print(f"[311 Lighting ETL DB Retry] Batch {batch_num}/{total_batches} ({start_idx+1}-{end_idx}) geçici DB hatası ({e}). {backoff_delay:.1f}s sonra tekrar deneniyor ({attempt}/{max_retries})...")
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
            "lighting_etl"
            if selected_resolution == LEGACY_H3_RESOLUTION
            else f"lighting_etl_r{selected_resolution}"
        )
        await crud.record_etl_run(session, etl_name, records_processed=processed_count)
    print(f"[311 Lighting ETL] Toplam {processed_count} H3 hücresi başarıyla kaydedildi/güncellendi ve etl_runs güncellendi.")

    return aggregated_h3


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chicago 311 Sokak Lambası ETL Boru Hattı")
    parser.add_argument("--max-records", type=int, default=None, help="Çekilecek maks kayıt sayısı")
    parser.add_argument("--dry-run", action="store_true", help="DB'ye yazmadan sadece istatistik üret")
    parser.add_argument("--resume", action="store_true", help="Mevcut checkpoint'ten devam et")
    parser.add_argument("--reset-checkpoint", action="store_true", help="Mevcut checkpoint'i sil ve sıfırdan başla")
    parser.add_argument(
        "--mode",
        choices=("incremental", "bootstrap"),
        default="incremental",
        help="incremental: rolling lookback, bootstrap: 2023'ten tam yükleme",
    )
    parser.add_argument("--lookback-days", type=int, default=180)
    parser.add_argument("--page-size", type=int, default=1000, help="Başlangıç sayfa boyutu (varsayılan: 1000)")
    parser.add_argument("--window-days", type=int, default=7, help="Tarih penceresi büyüklüğü gün sayısı (varsayılan: 7)")
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
            run_lighting_etl(
                max_records=args.max_records,
                dry_run=args.dry_run,
                resume=args.resume,
                reset_checkpoint=args.reset_checkpoint,
                page_size=args.page_size,
                window_days=args.window_days,
                h3_resolution=args.h3_resolution,
                mode=args.mode,
                lookback_days=args.lookback_days,
            )
        )
    except (ETLFetchError, ETLWriteError) as err:
        print(f"[311 Lighting ETL HATA] Boru hattı başarısız: {err}", file=sys.stderr)
        sys.exit(1)
    except Exception as err:
        print(f"[311 Lighting ETL Beklenmeyen Hata]: {err}", file=sys.stderr)
        sys.exit(1)
