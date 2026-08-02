# backend/crud.py
import h3
import hmac
import hashlib
import math
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, delete as sa_delete
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from models import (
    ETLRunModel,
    H3HeatmapModel,
    ReportEventModel,
    ReportModel,
    UserProfileModel,
)
from config import settings
from h3_policy import infer_h3_resolution, validate_h3_resolution
from services.report_nlp import get_nlp_analyzer
from errors import ConfigurationError, PersistenceError


# --- TEK DOĞRULUK KAYNAĞI: Ağırlıklı toplama formülü ---
# YENİ MİMARİ: 3 KANALLI ÇOK ETKENLİ RİSK FORMÜLÜ
# R_total = 0.65 * R_crime + 0.20 * R_lighting + 0.15 * R_live
CRIME_WEIGHT = 0.65       # %65 Suç Verileri (Chicago Police Department)
LIGHTING_WEIGHT = 0.20    # %20 Aydınlatma Arızaları (Chicago 311)
LIVE_WEIGHT = 0.15        # %15 Canlı Kullanıcı İhbarları


def generate_reporter_hash(raw_id: str | None) -> str | None:
    """
    Kullanıcının anonim kurulum UUID'sini sunucu tarafındaki secret ile HMAC-SHA256 kullanarak tek yönlü hash'ler.
    IP adresi veya ham UUID asla saklanmaz/dönülmez.
    """
    if not raw_id:
        return None
    secret_value = getattr(settings, "reporter_hash_secret", "").strip()
    if len(secret_value) < 32:
        raise ConfigurationError("Reporter identity hashing is not configured")
    secret = secret_value.encode("utf-8")
    return hmac.new(secret, raw_id.encode("utf-8"), hashlib.sha256).hexdigest()


async def _raise_persistence_error(
    db: AsyncSession,
    operation: str,
    exc: Exception,
) -> None:
    """Rollback a failed unit of work and hide driver details from callers."""
    await db.rollback()
    raise PersistenceError(f"{operation} failed") from exc


def _h3_identity(h3_index: str):
    return and_(
        H3HeatmapModel.h3_index == h3_index,
        H3HeatmapModel.h3_resolution == infer_h3_resolution(h3_index),
    )


def _compute_total_risk(
    crime: float = 0.0,
    lighting: float = 0.0,
    live: float = 0.0,
) -> float:
    """
    Tüm risk kanallarını tek bir ağırlıklı skora dönüştürür:
    R_total = 0.65*crime + 0.20*lighting + 0.15*live
    """
    return (crime * CRIME_WEIGHT) + (lighting * LIGHTING_WEIGHT) + (live * LIVE_WEIGHT)


async def create_heatmap_point(db: AsyncSession, h3_index: str, lat: float, lng: float, risk: float) -> H3HeatmapModel:
    point_geom = from_shape(Point(lng, lat), srid=4326)
    new_point = H3HeatmapModel(
        h3_index=h3_index,
        h3_resolution=infer_h3_resolution(h3_index),
        lat=lat,
        lng=lng,
        location=point_geom,
        risk_crime=risk,
        risk_lighting=0.0,
        risk_live=0.0,
        total_risk=_compute_total_risk(crime=risk)
    )
    db.add(new_point)
    await db.commit()
    await db.refresh(new_point)
    return new_point


async def get_all_heatmap_points(
    db: AsyncSession,
    h3_resolution: int | None = None,
    bbox_tuple: tuple[float, float, float, float] | None = None,
) -> list[H3HeatmapModel]:
    if db is None:
        return []
    stmt = select(H3HeatmapModel)
    if h3_resolution is not None:
        stmt = stmt.where(
            H3HeatmapModel.h3_resolution == validate_h3_resolution(h3_resolution)
        )
    if bbox_tuple is not None:
        west, south, east, north = bbox_tuple
        stmt = stmt.where(
            H3HeatmapModel.lng.between(west, east),
            H3HeatmapModel.lat.between(south, north),
        )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_heatmap_points_by_indices(
    db: AsyncSession,
    h3_indices: list[str],
    h3_resolution: int | None = None,
) -> dict[str, H3HeatmapModel]:
    """Birden çok H3 hücresini tek sorguda getirir.

    Rota boyunca onlarca hücrenin risk kanalları gerektiğinde hücre başına ayrı
    sorgu açmamak için kullanılır.
    """
    if db is None or not h3_indices:
        return {}
    unique_indices = list({str(index) for index in h3_indices if index})
    if not unique_indices:
        return {}

    stmt = select(H3HeatmapModel).where(H3HeatmapModel.h3_index.in_(unique_indices))
    if h3_resolution is not None:
        stmt = stmt.where(
            H3HeatmapModel.h3_resolution == validate_h3_resolution(h3_resolution)
        )
    result = await db.execute(stmt)
    return {str(point.h3_index): point for point in result.scalars().all()}


async def get_heatmap_point(
    db: AsyncSession,
    h3_index: str,
) -> H3HeatmapModel | None:
    """Fetch exactly one composite H3 identity without scanning the table."""
    if db is None:
        return None
    result = await db.execute(
        select(H3HeatmapModel).where(_h3_identity(h3_index)).limit(1)
    )
    return result.scalars().first()


async def get_nearby_risk_points(
    db: AsyncSession,
    user_lat: float,
    user_lng: float,
    radius_meters: int = 500,
    h3_resolution: int | None = None,
) -> list[H3HeatmapModel]:
    user_point = func.ST_SetSRID(func.ST_MakePoint(user_lng, user_lat), 4326)
    query = select(H3HeatmapModel).where(func.ST_DWithin(H3HeatmapModel.location, user_point, radius_meters))
    if h3_resolution is not None:
        query = query.where(
            H3HeatmapModel.h3_resolution == validate_h3_resolution(h3_resolution)
        )
    result = await db.execute(query)
    return result.scalars().all()


DEFAULT_ETL_BATCH_SIZE = 250


async def bulk_upsert_crime_data(
    db: AsyncSession,
    batch_data: list[dict]
) -> int:
    """
    Crime ETL için hücreleri composite H3 identity ile toplu upsert eder.
    Batch başına TEK BİR SQL ifadesi çalıştırır, ORM refresh/SELECT yapmaz.

    batch_data eleman yapısı:
    {
        "h3_index": str,
        "lat": float,
        "lng": float,
        "risk_crime": float,
        "extra_features": dict
    }
    """
    if not batch_data:
        return 0

    import sqlalchemy as sa
    from sqlalchemy.dialects.postgresql import insert as pg_insert, JSONB

    values_to_insert = []
    for item in batch_data:
        lat = float(item["lat"])
        lng = float(item["lng"])
        norm_risk = max(0.0, min(1.0, float(item["risk_crime"])))
        ewkt_location = f"SRID=4326;POINT({lng} {lat})"

        values_to_insert.append({
            "h3_index": item["h3_index"],
            "h3_resolution": validate_h3_resolution(
                item.get("h3_resolution", infer_h3_resolution(item["h3_index"]))
            ),
            "lat": lat,
            "lng": lng,
            "location": ewkt_location,
            "risk_crime": norm_risk,
            "risk_lighting": 0.0,
            "risk_live": 0.0,
            "total_risk": _compute_total_risk(crime=norm_risk),
            "updated_at": func.now(),
            "extra_features": item.get("extra_features") or {}
        })

    stmt = pg_insert(H3HeatmapModel).values(values_to_insert)
    excluded = stmt.excluded

    total_risk_expr = func.least(
        1.0,
        func.greatest(
            0.0,
            (0.65 * excluded.risk_crime) +
            (0.20 * func.coalesce(H3HeatmapModel.risk_lighting, 0.0)) +
            (0.15 * func.coalesce(H3HeatmapModel.risk_live, 0.0))
        )
    )

    jsonb_empty = sa.cast(sa.literal("{}"), JSONB)
    merged_extra_features = func.coalesce(H3HeatmapModel.extra_features, jsonb_empty).op("||")(excluded.extra_features)

    update_dict = {
        "h3_resolution": excluded.h3_resolution,
        "lat": excluded.lat,
        "lng": excluded.lng,
        "location": excluded.location,
        "risk_crime": excluded.risk_crime,
        "total_risk": total_risk_expr,
        "updated_at": func.now(),
        "extra_features": merged_extra_features
    }

    upsert_stmt = stmt.on_conflict_do_update(
        index_elements=["h3_resolution", "h3_index"],
        set_=update_dict
    )

    await db.execute(upsert_stmt)
    return len(batch_data)


async def bulk_upsert_lighting_data(
    db: AsyncSession,
    batch_data: list[dict]
) -> int:
    """
    311 Lighting ETL için hücreleri composite H3 identity ile toplu upsert eder.
    Batch başına TEK BİR SQL ifadesi çalıştırır, ORM refresh/SELECT yapmaz.

    batch_data eleman yapısı:
    {
        "h3_index": str,
        "lat": float,
        "lng": float,
        "risk_lighting": float,
        "extra_features": dict
    }
    """
    if not batch_data:
        return 0

    import sqlalchemy as sa
    from sqlalchemy.dialects.postgresql import insert as pg_insert, JSONB

    values_to_insert = []
    for item in batch_data:
        lat = float(item["lat"])
        lng = float(item["lng"])
        norm_lighting = max(0.0, min(1.0, float(item["risk_lighting"])))
        ewkt_location = f"SRID=4326;POINT({lng} {lat})"

        values_to_insert.append({
            "h3_index": item["h3_index"],
            "h3_resolution": validate_h3_resolution(
                item.get("h3_resolution", infer_h3_resolution(item["h3_index"]))
            ),
            "lat": lat,
            "lng": lng,
            "location": ewkt_location,
            "risk_crime": 0.0,
            "risk_lighting": norm_lighting,
            "risk_live": 0.0,
            "total_risk": _compute_total_risk(lighting=norm_lighting),
            "updated_at": func.now(),
            "extra_features": item.get("extra_features") or {}
        })

    stmt = pg_insert(H3HeatmapModel).values(values_to_insert)
    excluded = stmt.excluded

    total_risk_expr = func.least(
        1.0,
        func.greatest(
            0.0,
            (0.65 * func.coalesce(H3HeatmapModel.risk_crime, 0.0)) +
            (0.20 * excluded.risk_lighting) +
            (0.15 * func.coalesce(H3HeatmapModel.risk_live, 0.0))
        )
    )

    jsonb_empty = sa.cast(sa.literal("{}"), JSONB)
    merged_extra_features = func.coalesce(H3HeatmapModel.extra_features, jsonb_empty).op("||")(excluded.extra_features)

    update_dict = {
        "h3_resolution": excluded.h3_resolution,
        "lat": excluded.lat,
        "lng": excluded.lng,
        "location": excluded.location,
        "risk_lighting": excluded.risk_lighting,
        "total_risk": total_risk_expr,
        "updated_at": func.now(),
        "extra_features": merged_extra_features
    }

    upsert_stmt = stmt.on_conflict_do_update(
        index_elements=["h3_resolution", "h3_index"],
        set_=update_dict
    )

    await db.execute(upsert_stmt)
    return len(batch_data)


async def upsert_crime_data(
    db: AsyncSession,
    h3_index: str,
    lat: float,
    lng: float,
    risk_crime: float,
    extra_features: dict = None
) -> H3HeatmapModel:
    """
    SADECE Suç ETL verisini günceller. Mevcut risk_lighting ve risk_live değerlerini KORUR,
    total_risk'i diğer kanallarla birlikte yeniden hesaplar.
    """
    query = select(H3HeatmapModel).where(_h3_identity(h3_index))
    result = await db.execute(query)
    cell = result.scalars().first()

    norm_crime = max(0.0, min(1.0, risk_crime))

    if cell:
        cell.risk_crime = norm_crime
        if extra_features:
            merged = dict(cell.extra_features or {})
            merged.update(extra_features)
            cell.extra_features = merged

        cell.total_risk = _compute_total_risk(
            crime=cell.risk_crime,
            lighting=cell.risk_lighting or 0.0,
            live=cell.risk_live or 0.0,
        )
    else:
        point_geom = from_shape(Point(lng, lat), srid=4326)
        cell = H3HeatmapModel(
            h3_index=h3_index,
            h3_resolution=infer_h3_resolution(h3_index),
            lat=lat,
            lng=lng,
            location=point_geom,
            risk_crime=norm_crime,
            risk_lighting=0.0,
            risk_live=0.0,
            total_risk=_compute_total_risk(crime=norm_crime),
            extra_features=extra_features or {}
        )
        db.add(cell)

    await db.commit()
    await db.refresh(cell)
    return cell


async def upsert_lighting_data(
    db: AsyncSession,
    h3_index: str,
    lat: float,
    lng: float,
    risk_lighting: float,
    extra_features: dict = None
) -> H3HeatmapModel:
    """
    SADECE 311 Aydınlatma ETL verisini günceller. Mevcut risk_crime ve risk_live değerlerini KORUR,
    total_risk'i diğer kanallarla birlikte yeniden hesaplar.
    """
    query = select(H3HeatmapModel).where(_h3_identity(h3_index))
    result = await db.execute(query)
    cell = result.scalars().first()

    norm_lighting = max(0.0, min(1.0, risk_lighting))

    if cell:
        cell.risk_lighting = norm_lighting
        if extra_features:
            existing = dict(cell.extra_features or {})
            existing.update(extra_features)
            cell.extra_features = existing
        cell.total_risk = _compute_total_risk(
            crime=cell.risk_crime or 0.0,
            lighting=cell.risk_lighting,
            live=cell.risk_live or 0.0
        )
    else:
        point_geom = from_shape(Point(lng, lat), srid=4326)
        cell = H3HeatmapModel(
            h3_index=h3_index,
            h3_resolution=infer_h3_resolution(h3_index),
            lat=lat,
            lng=lng,
            location=point_geom,
            risk_crime=0.0,
            risk_lighting=norm_lighting,
            risk_live=0.0,
            total_risk=_compute_total_risk(lighting=norm_lighting),
            extra_features=extra_features or {}
        )
        db.add(cell)

    await db.commit()
    await db.refresh(cell)
    return cell


async def record_etl_run(db: AsyncSession, etl_name: str, records_processed: int = 0, status: str = "success") -> ETLRunModel:
    """ETL tamamlandığında çalışma zamanını ve işlenen kayıt sayısını veritabanına kaydeder."""
    query = select(ETLRunModel).where(ETLRunModel.etl_name == etl_name)
    result = await db.execute(query)
    record = result.scalars().first()

    now_utc = datetime.now(timezone.utc)
    if record:
        record.last_successful_run = now_utc
        record.records_processed = records_processed
        record.status = status
    else:
        record = ETLRunModel(
            etl_name=etl_name,
            last_successful_run=now_utc,
            records_processed=records_processed,
            status=status
        )
        db.add(record)

    await db.commit()
    await db.refresh(record)
    return record


async def get_latest_etl_runs(db: AsyncSession) -> dict:
    """Crime ve Lighting ETL işlemlerinin son güncelleme zamanlarını ve nihai risk snapshot tarihini sorgular."""
    now_iso = datetime.now(timezone.utc).isoformat()
    if db is None:
        return {
            "crime_data_updated_at": None,
            "lighting_data_updated_at": None,
            "risk_snapshot_at": now_iso
        }

    query = select(ETLRunModel)
    result = await db.execute(query)
    runs = {r.etl_name: r.last_successful_run for r in result.scalars().all()}

    active_resolution = validate_h3_resolution(
        getattr(settings, "routing_h3_resolution", 10)
    )
    suffix = "" if active_resolution == 9 else f"_r{active_resolution}"
    crime_dt = runs.get(f"crime_etl{suffix}")
    lighting_dt = runs.get(f"lighting_etl{suffix}")

    snapshot_dts = [dt for dt in (crime_dt, lighting_dt) if dt is not None]
    snapshot_dt = max(snapshot_dts) if snapshot_dts else datetime.now(timezone.utc)

    return {
        "crime_data_updated_at": crime_dt.isoformat() if crime_dt else None,
        "lighting_data_updated_at": lighting_dt.isoformat() if lighting_dt else None,
        "risk_snapshot_at": snapshot_dt.isoformat(),
    }


_in_memory_reports: dict[str, ReportModel] = {}
_in_memory_report_events: dict[str, ReportEventModel] = {}


async def check_duplicate_report(
    db: AsyncSession,
    lat: float,
    lng: float,
    time_window_minutes: int = 10,
    radius_meters: float = 50.0,
    reporter_hash: str | None = None,
    user_id: uuid.UUID | None = None,
) -> bool:
    """
    Belirtilen koordinat etrafında (radius_meters) ve zaman penceresinde (time_window_minutes)
    daha önce ihbar girilip girilmediğini kontrol eder (mükerrer ihbar / spam koruması).

    MiniLM metin benzerliği burada kullanılmaz; yalnızca aynı muhabirin
    aynı noktaya kısa sürede tekrar ihbar atmasını engeller.

    Giriş yapmış kullanıcıda ``user_id`` önceliklidir. Aynı emülatörde test1/test2
    gibi hesaplar aynı ``reporter_installation_id`` paylaştığı için hash ile
    filtrelemek ikinci hesabı yanlışlıkla engelliyordu.
    """
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=time_window_minutes)

    if db is None:
        for rep in _in_memory_reports.values():
            if user_id is not None:
                if getattr(rep, "user_id", None) != user_id:
                    continue
            elif reporter_hash is not None:
                if getattr(rep, "reporter_hash", None) != reporter_hash:
                    continue
            if rep.created_at and rep.created_at >= cutoff_time:
                d_lat = (rep.latitude - lat) * 111000.0
                d_lng = (rep.longitude - lng) * 82000.0
                if (d_lat**2 + d_lng**2)**0.5 <= radius_meters:
                    return True
        return False

    try:
        point_geom = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)
        query = select(ReportModel).where(
            ReportModel.created_at >= cutoff_time,
            func.ST_DWithin(ReportModel.location, point_geom, radius_meters)
        )
        if user_id is not None:
            query = query.where(ReportModel.user_id == user_id)
        elif reporter_hash is not None:
            query = query.where(ReportModel.reporter_hash == reporter_hash)
        result = await db.execute(query)
        existing = result.scalars().first()
        return existing is not None
    except Exception as exc:
        await _raise_persistence_error(db, "duplicate report check", exc)


async def create_report(
    db: AsyncSession,
    lat: float,
    lng: float,
    text: str,
    category: str = "general",
    priority: str = "normal",
    ip_address: str = None,
    reporter_installation_id: str = None,
    user_id: uuid.UUID | None = None,
    **kwargs
) -> ReportModel:
    """
    Kriptografik olarak güvenli UUID v4, tracking_token ve HMAC reporter_hash üreterek yeni ihbar kaydeder.
    İlk durumda 'pending' olarak kaydedilir ve NLP analizi uygulanır.
    """
    generated_uuid = str(uuid.uuid4())
    generated_token = secrets.token_urlsafe(32)
    reporter_hash = generate_reporter_hash(reporter_installation_id)
    norm_priority = "urgent" if str(priority).lower() == "urgent" else "normal"

    nlp = get_nlp_analyzer()
    nlp_res = nlp.analyze(text)

    report_fields = dict(
        uuid_id=generated_uuid,
        tracking_token=generated_token,
        user_id=user_id,
        latitude=lat,
        longitude=lng,
        description=text[:250],
        category=category,
        priority=norm_priority,
        status="pending",
        # Raw IP addresses are used only for the process-local rate limiter and
        # are never persisted.
        ip_address=None,
        created_at=datetime.now(timezone.utc),
        reporter_hash=reporter_hash,
        normalized_category=nlp_res.normalized_category,
        severity_weight=nlp_res.severity_weight,
        model_confidence=nlp_res.model_confidence,
        analysis_method=nlp_res.analysis_method,
    )

    if db is None:
        new_report = ReportModel(id=len(_in_memory_reports) + 1, **report_fields)
        _in_memory_reports[generated_uuid] = new_report
        return new_report

    new_report = ReportModel(
        location=from_shape(Point(lng, lat), srid=4326),
        **report_fields,
    )
    try:
        db.add(new_report)
        await db.commit()
        await db.refresh(new_report)
    except Exception as exc:
        await _raise_persistence_error(db, "report create", exc)
    return new_report


async def get_or_create_user_profile(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> UserProfileModel:
    result = await db.execute(
        select(UserProfileModel).where(UserProfileModel.user_id == user_id)
    )
    profile = result.scalars().first()
    if profile is not None:
        return profile

    now_utc = datetime.now(timezone.utc)
    profile = UserProfileModel(
        user_id=user_id,
        role="user",
        created_at=now_utc,
        updated_at=now_utc,
    )
    try:
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    except Exception as exc:
        await _raise_persistence_error(db, "user profile create", exc)
    return profile


async def list_user_reports(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 100,
) -> list[ReportModel]:
    result = await db.execute(
        select(ReportModel)
        .where(ReportModel.user_id == user_id)
        .order_by(ReportModel.created_at.desc())
        .limit(max(1, min(int(limit), 200)))
    )
    return list(result.scalars().all())


async def delete_user_report(
    db: AsyncSession,
    user_id: uuid.UUID,
    report_id: str,
) -> bool:
    """Kullanıcının kendi ihbarını siler (uuid_id veya sayısal id)."""
    report_id = str(report_id or "").strip()
    if not report_id:
        return False
    filters = [ReportModel.user_id == user_id]
    if report_id.isdigit():
        filters.append(
            or_(ReportModel.uuid_id == report_id, ReportModel.id == int(report_id))
        )
    else:
        filters.append(ReportModel.uuid_id == report_id)
    try:
        result = await db.execute(sa_delete(ReportModel).where(*filters))
        await db.commit()
    except Exception as exc:
        await _raise_persistence_error(db, "user report delete", exc)
    return int(result.rowcount or 0) > 0


async def set_account_deletion_request(
    db: AsyncSession,
    user_id: uuid.UUID,
    requested: bool,
) -> UserProfileModel:
    profile = await get_or_create_user_profile(db, user_id)
    profile.deletion_requested_at = datetime.now(timezone.utc) if requested else None
    profile.updated_at = datetime.now(timezone.utc)
    try:
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    except Exception as exc:
        await _raise_persistence_error(db, "account deletion request", exc)
    return profile


async def get_nearby_heatmap_points(
    db: AsyncSession,
    lat: float,
    lng: float,
    radius_meters: float = 1000.0,
    limit: int = 100,
    h3_resolution: int | None = None,
) -> list[H3HeatmapModel]:
    """
    PostGIS ST_DWithin kullanarak verilen koordinat etrafındaki H3 heatmap noktalarını veritabanı seviyesinde spatial index ile çeker.
    Tüm tabloyu Python'a kopyalamaz.
    """
    if db is None:
        return []

    radius_meters = max(10.0, min(10000.0, float(radius_meters)))
    limit = max(1, min(500, int(limit)))

    stmt = (
        select(H3HeatmapModel)
        .where(
            func.ST_DWithin(
                H3HeatmapModel.location,
                func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326),
                radius_meters,
            )
        )
        .order_by(
            func.ST_Distance(
                H3HeatmapModel.location,
                func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326),
            )
        )
        .limit(limit)
    )
    if h3_resolution is not None:
        stmt = stmt.where(
            H3HeatmapModel.h3_resolution == validate_h3_resolution(h3_resolution)
        )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def process_report_and_event_clustering(db: AsyncSession | None, report: ReportModel) -> ReportEventModel:
    """
    Yeni girilen ihbarı H3 hücre ve zaman penceresine (15 dk) göre mevcut olay kümesine (ReportEventModel) bağlar
    veya yeni küme oluşturur. Doğrulama skorunu (V) hesaplar.
    """
    now_utc = datetime.now(timezone.utc)
    cutoff_time = now_utc - timedelta(minutes=getattr(settings, "report_cluster_window_minutes", 15))

    report_h3_resolution = validate_h3_resolution(
        getattr(settings, "report_h3_resolution", 9)
    )
    h3_cell = h3.latlng_to_cell(
        report.latitude,
        report.longitude,
        report_h3_resolution,
    )
    neighbor_cells = set(h3.grid_disk(h3_cell, 1))

    report_cat = report.normalized_category or "general_safety"
    nlp = get_nlp_analyzer()

    candidate_events: list[ReportEventModel] = []

    if db is None:
        for ev in _in_memory_report_events.values():
            if (ev.h3_index in neighbor_cells and
                ev.status in ("pending", "processing", "accepted") and
                ev.normalized_category == report_cat):
                ev_time = ev.last_seen_at or ev.created_at
                if ev_time and ev_time.tzinfo is None:
                    ev_time = ev_time.replace(tzinfo=timezone.utc)
                if ev_time and ev_time >= cutoff_time:
                    candidate_events.append(ev)
    else:
        stmt = select(ReportEventModel).where(
            ReportEventModel.h3_resolution == report_h3_resolution,
            ReportEventModel.h3_index.in_(list(neighbor_cells)),
            ReportEventModel.status.in_(["pending", "processing", "accepted"]),
            ReportEventModel.last_seen_at >= cutoff_time,
            ReportEventModel.normalized_category == report_cat,
        )
        res = await db.execute(stmt)
        candidate_events = list(res.scalars().all())

    matched_event: ReportEventModel | None = None
    best_similarity = -1.0

    sim_thresh = float(getattr(settings, "report_similarity_threshold", 0.80))
    category_match_enabled = bool(
        getattr(settings, "report_cluster_category_match_enabled", True)
    )
    report_reporter_hash = getattr(report, "reporter_hash", None)

    for ev in candidate_events:
        if db is None:
            cluster_reports = [r for r in _in_memory_reports.values() if r.event_id == ev.id]
        else:
            stmt_r = select(ReportModel).where(ReportModel.event_id == ev.id)
            res_r = await db.execute(stmt_r)
            cluster_reports = list(res_r.scalars().all())

        if not cluster_reports:
            sim = 1.0
        else:
            sims = [nlp.similarity(report.description, r.description) for r in cluster_reports]
            sim = max(sims) if sims else 1.0

        matches = sim >= sim_thresh
        if not matches and category_match_enabled and cluster_reports:
            # Aynı olayı gören iki kişi onu farklı kelimelerle anlatır; deterministik
            # metin benzerliği bu durumda eşiği geçemez. Aday olay zaten aynı
            # kategori, aynı/komşu hücre ve zaman penceresinden geçtiği için,
            # kümede henüz bulunmayan bağımsız bir muhabirin ihbarı aynı olaya
            # bağlanır. Aksi halde iki bağımsız destek hiçbir zaman toplanamaz ve
            # hiçbir olay kabul edilemezdi.
            # Bağımsız muhabir: user_id (tercih) veya reporter_hash.
            # Aynı emülatörde test1/test2 aynı installation hash paylaşır.
            def _reporter_key(item: ReportModel) -> str | None:
                uid = getattr(item, "user_id", None)
                if uid is not None:
                    return f"user:{uid}"
                rh = getattr(item, "reporter_hash", None)
                return f"hash:{rh}" if rh else None

            existing_reporters = {
                key
                for existing in cluster_reports
                for key in [_reporter_key(existing)]
                if key is not None
            }
            report_key = _reporter_key(report)
            matches = report_key is not None and report_key not in existing_reporters

        if matches and sim >= best_similarity:
            best_similarity = sim
            matched_event = ev

    if matched_event is not None:
        report.event_id = matched_event.id
        matched_event.last_seen_at = now_utc
    else:
        event_uuid = str(uuid.uuid4())
        expiry_mins = getattr(settings, "report_event_expiry_minutes", 60)
        event_fields = dict(
            uuid_id=event_uuid,
            h3_index=h3_cell,
            h3_resolution=report_h3_resolution,
            normalized_category=report_cat,
            status="pending",
            unique_reporter_count=1,
            mean_similarity=1.0,
            mean_user_reliability=0.50,
            mean_model_confidence=report.model_confidence or 0.50,
            validation_score=0.0,
            severity_weight=report.severity_weight or 0.35,
            analysis_method=report.analysis_method or "deterministic_fallback",
            first_seen_at=now_utc,
            last_seen_at=now_utc,
            expires_at=now_utc + timedelta(minutes=expiry_mins),
            created_at=now_utc,
            updated_at=now_utc
        )

        if db is None:
            new_event = ReportEventModel(
                id=len(_in_memory_report_events) + 1,
                **event_fields,
            )
            _in_memory_report_events[event_uuid] = new_event
        else:
            new_event = ReportEventModel(**event_fields)
            try:
                db.add(new_event)
                await db.flush()
            except Exception as exc:
                await _raise_persistence_error(db, "report event create", exc)

        report.event_id = new_event.id
        matched_event = new_event

    if db is not None:
        try:
            db.add(report)
            await db.commit()
        except Exception as exc:
            await _raise_persistence_error(db, "report event association", exc)

    await evaluate_and_update_event(db, matched_event)
    return matched_event


async def evaluate_and_update_event(db: AsyncSession | None, event: ReportEventModel) -> ReportEventModel:
    """
    Olay kümesindeki bağımsız kullanıcı sayısını (S), metinsel benzerliği (M), model güvenini (C) ve
    bütünsel doğrulama skorunu (V) hesaplar.
    V >= 0.70 ve unique_reporter_count >= 2 ise olayı 'accepted' durumuna geçirir.
    """
    now_utc = datetime.now(timezone.utc)

    if db is None:
        reports = [r for r in _in_memory_reports.values() if r.event_id == event.id]
    else:
        stmt = select(ReportModel).where(ReportModel.event_id == event.id)
        res = await db.execute(stmt)
        reports = list(res.scalars().all())

    if not reports:
        return event

    # Bağımsız muhabir: önce hesap (user_id), yoksa cihaz hash'i.
    # Aynı telefondaki farklı hesaplar aynı installation_id paylaşır; yalnızca
    # hash sayılırsa test1+test2 asla 2 bağımsız destek oluşturamazdı.
    unique_reporters: set[str] = set()
    for r in reports:
        uid = getattr(r, "user_id", None)
        if uid is not None:
            unique_reporters.add(f"user:{uid}")
        elif getattr(r, "reporter_hash", None):
            unique_reporters.add(f"hash:{r.reporter_hash}")
        # Kimlik yoksa bağımsız destek sayılmaz.

    unique_reporter_count = len(unique_reporters)

    nlp = get_nlp_analyzer()
    if len(reports) <= 1:
        mean_similarity = 1.0
    else:
        pair_sims = []
        for i in range(len(reports)):
            for j in range(i + 1, len(reports)):
                pair_sims.append(nlp.similarity(reports[i].description, reports[j].description))
        mean_similarity = sum(pair_sims) / float(len(pair_sims)) if pair_sims else 1.0

        # Deterministik benzerlik kelime/n-gram örtüşmesine dayanır; aynı olayı
        # gören iki kişi onu farklı kelimelerle anlattığında bu ölçüt düşük kalır
        # ve V eşiği hiçbir zaman aşılamazdı. Tüm ihbarlar aynı kategoriye
        # düştüğünde bu, kelimelerden bağımsız bir uyum sinyalidir; bu nedenle bir
        # taban uygulanır. Kabul için asıl kapı olan bağımsız muhabir sayısı
        # (report_min_independent_support) değişmeden kalır.
        same_category = (
            len({(r.normalized_category or "general_safety") for r in reports}) == 1
        )
        if same_category:
            mean_similarity = max(
                mean_similarity,
                float(getattr(settings, "report_category_similarity_floor", 0.75)),
            )

    confidences = [r.model_confidence for r in reports if r.model_confidence is not None]
    mean_confidence = sum(confidences) / float(len(confidences)) if confidences else 0.50

    S = min(unique_reporter_count / 3.0, 1.0)
    M = max(0.0, min(1.0, mean_similarity))
    U = 0.50
    C = max(0.0, min(1.0, mean_confidence))

    validation_score = round((0.35 * S) + (0.25 * M) + (0.20 * U) + (0.20 * C), 4)

    event.unique_reporter_count = unique_reporter_count
    event.mean_similarity = round(M, 4)
    event.mean_model_confidence = round(C, 4)
    event.validation_score = validation_score
    event.updated_at = now_utc

    expiry_mins = getattr(settings, "report_event_expiry_minutes", 60)

    # Kabul kararı otomatik (2. ihbar) ile verilmez.
    # Akış: geçerli ihbar → 1 km tanık → en az bir "Gördüm"
    # (_dispatch_broadcast). Burada yalnızca skorlar güncellenir.
    # REPORT_DEV_SOLO_ACCEPT yalnızca otomatik test kaçış kapısıdır.
    solo_accept = bool(getattr(settings, "report_dev_solo_accept", False))
    if settings.app_environment == "production":
        solo_accept = False

    if solo_accept and unique_reporter_count >= 1 and event.status != "accepted":
        event.status = "accepted"
        event.accepted_at = now_utc
        event.expires_at = now_utc + timedelta(minutes=expiry_mins)
        for r in reports:
            if getattr(r, "status", None) != "accepted":
                r.status = "accepted"

    if db is not None:
        try:
            db.add(event)
            for r in reports:
                db.add(r)
            await db.commit()
            await db.refresh(event)
        except Exception as exc:
            await _raise_persistence_error(db, "report event evaluation", exc)

    return event


async def recalculate_h3_live_risk(db: AsyncSession | None, h3_index: str) -> float:
    r"""
    H3 hücresi ve komşu hücrelerindeki aktif kabul edilmiş (accepted) olayların zamansal sönümlemeli
    etkilerini hesaplar ve bounded accumulation (1 - \prod(1 - I_i)) ile risk_live ve total_risk'i günceller.
    """
    now_utc = datetime.now(timezone.utc)
    neighbor_cells = set(h3.grid_disk(h3_index, 1))

    if db is None:
        active_events = [
            ev for ev in _in_memory_report_events.values()
            if ev.h3_index in neighbor_cells and ev.status == "accepted" and (ev.expires_at is None or ev.expires_at > now_utc)
        ]
    else:
        event_resolution = infer_h3_resolution(h3_index)
        stmt = select(ReportEventModel).where(
            ReportEventModel.h3_resolution == event_resolution,
            ReportEventModel.h3_index.in_(list(neighbor_cells)),
            ReportEventModel.status == "accepted",
            or_(ReportEventModel.expires_at.is_(None), ReportEventModel.expires_at > now_utc),
        )
        res = await db.execute(stmt)
        active_events = list(res.scalars().all())

    if not active_events:
        new_live_risk = 0.0
    else:
        tau = float(getattr(settings, "report_live_risk_tau_minutes", 60.0))
        event_impacts = []

        for ev in active_events:
            acc_time = ev.accepted_at or ev.first_seen_at or now_utc
            if acc_time.tzinfo is None:
                acc_time = acc_time.replace(tzinfo=timezone.utc)

            t_min = max(0.0, (now_utc - acc_time).total_seconds() / 60.0)
            severity = float(ev.severity_weight or 0.35)
            val_score = float(ev.validation_score or 0.70)

            impact_i = severity * val_score * math.exp(-t_min / tau)
            event_impacts.append(max(0.0, min(1.0, impact_i)))

        prod_safe = 1.0
        for imp in event_impacts:
            prod_safe *= (1.0 - imp)

        new_live_risk = max(0.0, min(1.0, 1.0 - prod_safe))

    if db is None:
        new_total_risk = _compute_total_risk(live=new_live_risk)
        return new_total_risk

    try:
        stmt_c = select(H3HeatmapModel).where(_h3_identity(h3_index))
        res_c = await db.execute(stmt_c)
        cell = res_c.scalars().first()

        if cell:
            cell.risk_live = round(new_live_risk, 4)
            cell.total_risk = _compute_total_risk(
                crime=cell.risk_crime or 0.0,
                lighting=cell.risk_lighting or 0.0,
                live=cell.risk_live
            )
            await db.commit()
            return cell.total_risk
        else:
            lat, lng = h3.cell_to_latlng(h3_index)
            point_geom = from_shape(Point(lng, lat), srid=4326)
            new_total = _compute_total_risk(live=new_live_risk)

            new_cell = H3HeatmapModel(
                h3_index=h3_index,
                h3_resolution=infer_h3_resolution(h3_index),
                lat=lat,
                lng=lng,
                location=point_geom,
                risk_crime=0.0,
                risk_lighting=0.0,
                risk_live=round(new_live_risk, 4),
                total_risk=new_total
            )
            db.add(new_cell)
            await db.commit()
            return new_total
    except Exception as exc:
        await _raise_persistence_error(db, "live risk recalculation", exc)


async def project_parent_live_risk_to_child(
    db: AsyncSession,
    *,
    parent_h3_index: str,
    child_h3_index: str,
) -> float:
    """Res-9 olay kümesinin canlı riskini ilgili res-10 rota hücresine yansıtır.

    Suç ve aydınlatma kanalları çocuk hücrede korunur; yalnızca ``risk_live`` ve
    buna bağlı ``total_risk`` güncellenir. Böylece ihbar kümeleme gizliliği
    res-9'da kalırken res-10 rotalama canlı olaydan haberdar olur.
    """
    parent_stmt = select(H3HeatmapModel).where(
        _h3_identity(parent_h3_index)
    )
    parent_result = await db.execute(parent_stmt)
    parent = parent_result.scalars().first()
    live_risk = max(
        0.0,
        min(1.0, float(getattr(parent, "risk_live", 0.0) or 0.0)),
    )

    child_stmt = select(H3HeatmapModel).where(
        _h3_identity(child_h3_index)
    )
    child_result = await db.execute(child_stmt)
    child = child_result.scalars().first()

    if child is None:
        lat, lng = h3.cell_to_latlng(child_h3_index)
        child = H3HeatmapModel(
            h3_index=child_h3_index,
            h3_resolution=infer_h3_resolution(child_h3_index),
            lat=lat,
            lng=lng,
            location=from_shape(Point(lng, lat), srid=4326),
            risk_crime=0.0,
            risk_lighting=0.0,
            risk_live=live_risk,
            total_risk=_compute_total_risk(live=live_risk),
            extra_features={
                "live_risk_parent_h3_index": parent_h3_index,
            },
        )
        db.add(child)
    else:
        child.risk_live = round(live_risk, 4)
        child.total_risk = _compute_total_risk(
            crime=child.risk_crime or 0.0,
            lighting=child.risk_lighting or 0.0,
            live=child.risk_live,
        )
        extra = dict(child.extra_features or {})
        extra["live_risk_parent_h3_index"] = parent_h3_index
        child.extra_features = extra

    await db.commit()
    return float(child.total_risk)


async def get_report_by_uuid_and_token(db: AsyncSession | None, uuid_id: str, token: str) -> ReportModel | None:
    """
    IDOR Saldırılarına karşı korumalı ihbar sorgulama.
    Sadece UUID VE doğrulama jetonu (tracking_token) eşleştiğinde sonucu döner.
    """
    if db is None:
        rep = _in_memory_reports.get(uuid_id)
        if rep and rep.tracking_token == token:
            return rep
        return None

    query = select(ReportModel).where(
        ReportModel.uuid_id == uuid_id,
        ReportModel.tracking_token == token,
    )
    result = await db.execute(query)
    return result.scalars().first()


async def get_report_by_id(db: AsyncSession | None, report_id: int) -> ReportModel | None:
    if db is None:
        for r in _in_memory_reports.values():
            if r.id == report_id:
                return r
        return None
    query = select(ReportModel).where(ReportModel.id == report_id)
    result = await db.execute(query)
    return result.scalars().first()


async def update_h3_live_risk(db: AsyncSession | None, h3_index: str, added_live_risk: float) -> float:
    """
    Geriye dönük uyumluluk: Canlı ihbar güncellemelerinde recalculate_h3_live_risk çağrılır.
    """
    return await recalculate_h3_live_risk(db, h3_index)


def anonymize_location(lat: float, lng: float) -> tuple[float, float]:
    """
    İhbar gizliliği için yapılandırılmış H3 hücresinin merkezine dönüştürür.
    H3 başarısız olursa 3 ondalık yuvarlama yapar (~110m hassasiyet).
    """
    try:
        report_resolution = validate_h3_resolution(
            getattr(settings, "report_h3_resolution", 9)
        )
        cell = h3.latlng_to_cell(lat, lng, report_resolution)
        cell_lat, cell_lng = h3.cell_to_latlng(cell)
        return round(float(cell_lat), 5), round(float(cell_lng), 5)
    except Exception:
        return round(lat, 3), round(lng, 3)


def generate_public_id(uuid_id: str, created_at: datetime) -> str:
    """
    Gerçek uuid_id veya tracking_token'ı ASLA sızdırmayan deterministik anonim id üretir.
    """
    raw = f"public_map_anon_{uuid_id}_{created_at.isoformat()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def parse_bbox(bbox_str: str) -> tuple[float, float, float, float] | None:
    """
    'west,south,east,north' dizesini (min_lng, min_lat, max_lng, max_lat) olarak ayrıştırır.
    """
    try:
        parts = [float(p.strip()) for p in bbox_str.split(",")]
        if len(parts) == 4:
            return parts[0], parts[1], parts[2], parts[3]
    except Exception:
        pass
    return None


async def update_report_status(db: AsyncSession | None, uuid_id: str, new_status: str) -> None:
    """
    Rapor durumunu günceller (ör. background işleme sonrası pending -> accepted).
    """
    if db is None:
        if uuid_id in _in_memory_reports:
            _in_memory_reports[uuid_id].status = new_status
        return
    if db is not None:
        try:
            query = select(ReportModel).where(ReportModel.uuid_id == uuid_id)
            res = await db.execute(query)
            rep = res.scalars().first()
            if rep:
                rep.status = new_status
                await db.commit()
        except Exception as exc:
            await _raise_persistence_error(db, "report status update", exc)


async def get_recent_map_reports(
    db: AsyncSession | None,
    minutes: int = 60,
    bbox: str | None = None,
    category: str | None = None,
    limit: int = 500
) -> dict:
    """
    Son N dakika içinde gönderilen, kabul edilmiş (accepted) ve harita gösterimine uygun
    ihbarları gizlilik kurallarına tam uyumlu (anonimleşmiş) olarak döner.
    Tekil 'pending', 'rejected' veya 'expired' ihbarlar public harita yanıtında gösterilmez.
    """
    now_utc = datetime.now(timezone.utc)
    minutes = max(5, min(60, minutes))
    limit = max(1, min(1000, limit))
    cutoff_time = now_utc - timedelta(minutes=minutes)

    bbox_tuple = parse_bbox(bbox) if bbox else None
    reports_list = []

    if db is None:
        raw_reports = [r for r in _in_memory_reports.values() if getattr(r, "status", "pending") == "accepted"]
    else:
        query = select(ReportModel).where(
            ReportModel.created_at >= cutoff_time,
            ReportModel.status == "accepted",
        )
        if category:
            query = query.where(ReportModel.category == category.lower())

        query = query.order_by(ReportModel.created_at.desc()).limit(limit)
        result = await db.execute(query)
        raw_reports = list(result.scalars().all())

    for r in raw_reports:
        r_created = r.created_at
        if r_created is not None:
            if r_created.tzinfo is None:
                r_created = r_created.replace(tzinfo=timezone.utc)
            if r_created < cutoff_time:
                continue

        r_status = getattr(r, "status", "pending")
        if r_status != "accepted":
            continue

        r_cat = getattr(r, "category", "general")
        if category and r_cat.lower() != category.lower():
            continue

        r_lat = r.latitude
        r_lng = r.longitude
        if bbox_tuple:
            west, south, east, north = bbox_tuple
            if not (west <= r_lng <= east and south <= r_lat <= north):
                continue

        anon_lat, anon_lng = anonymize_location(r_lat, r_lng)
        pub_id = generate_public_id(r.uuid_id or str(r.id), r_created or now_utc)
        min_ago = max(0, int((now_utc - (r_created or now_utc)).total_seconds() / 60))

        reports_list.append({
            "public_id": pub_id,
            "category": r_cat,
            "lat": anon_lat,
            "lng": anon_lng,
            "reported_at": (r_created or now_utc).isoformat(),
            "status": "accepted",
            "verification_label": "community_report",
            "minutes_ago": min_ago
        })

        if len(reports_list) >= limit:
            break

    return {
        "generated_at": now_utc.isoformat(),
        "window_minutes": minutes,
        "count": len(reports_list),
        "reports": reports_list
    }


async def get_heatmap_geojson_map(
    db: AsyncSession | None,
    bbox: str | None = None,
    channel: str = "total",
    include_no_data: bool = True,
    h3_resolution: int | None = None,
) -> dict:
    """
    Chicago H3 hücre risk verilerini seçilen çözünürlükte GeoJSON FeatureCollection olarak döner.
    Poligonlar kapalı halka ([lng, lat] sırası) olarak üretilir.
    """
    now_utc = datetime.now(timezone.utc)
    freshness = await get_latest_etl_runs(db)

    selected_resolution = validate_h3_resolution(
        h3_resolution
        if h3_resolution is not None
        else getattr(settings, "routing_h3_resolution", 9)
    )
    bbox_tuple = parse_bbox(bbox) if bbox else None
    points = await get_all_heatmap_points(
        db,
        h3_resolution=selected_resolution,
        # Unit tests deliberately use db=None and monkeypatch the legacy
        # two-argument reader; production sessions push the viewport filter
        # into SQL so all Chicago rows are never materialized per map move.
        **({"bbox_tuple": bbox_tuple} if db is not None else {}),
    )

    channel_clean = channel.lower() if channel else "total"

    features = []
    data_count = 0

    for p in points:
        p_lat = getattr(p, "lat", 0.0)
        p_lng = getattr(p, "lng", 0.0)
        h3_idx = getattr(p, "h3_index", "") or ""

        if bbox_tuple:
            west, south, east, north = bbox_tuple
            if not (west <= p_lng <= east and south <= p_lat <= north):
                continue

        risk_crime = getattr(p, "risk_crime", 0.0)
        risk_lighting = getattr(p, "risk_lighting", 0.0)
        risk_live = getattr(p, "risk_live", 0.0)
        total_risk = getattr(p, "total_risk", 0.0)
        extra_features = getattr(p, "extra_features", None) or {}
        crime_observed = any(key in extra_features for key in ("crime_7d", "crime_30d", "crime_90d")) or float(risk_crime or 0.0) > 0.0
        lighting_observed = any(key in extra_features for key in ("open_311_lighting_count", "completed_311_lighting_count")) or float(risk_lighting or 0.0) > 0.0
        live_observed = "live_risk_parent_h3_index" in extra_features or float(risk_live or 0.0) > 0.0

        if channel_clean == "crime":
            raw_risk = risk_crime
        elif channel_clean == "lighting":
            raw_risk = risk_lighting
        elif channel_clean == "live":
            raw_risk = risk_live
        else:
            raw_risk = total_risk

        if channel_clean == "crime":
            has_data = crime_observed
        elif channel_clean == "lighting":
            has_data = lighting_observed
        elif channel_clean == "live":
            has_data = live_observed
        else:
            has_data = crime_observed or lighting_observed or live_observed

        if not has_data and not include_no_data:
            continue

        if has_data:
            data_count += 1
            risk_val = round(max(0.0, min(1.0, float(raw_risk or 0.0))), 4)
        else:
            risk_val = None

        try:
            boundary = h3.cell_to_boundary(h3_idx)
            ring = [[round(float(pt[1]), 6), round(float(pt[0]), 6)] for pt in boundary]
            if ring and ring[0] != ring[-1]:
                ring.append(ring[0])
        except Exception:
            d = 0.001
            ring = [
                [round(p_lng - d, 6), round(p_lat - d, 6)],
                [round(p_lng + d, 6), round(p_lat - d, 6)],
                [round(p_lng + d, 6), round(p_lat + d, 6)],
                [round(p_lng - d, 6), round(p_lat - d, 6)],
                [round(p_lng - d, 6), round(p_lat - d, 6)],
            ]

        features.append({
            "type": "Feature",
            "id": h3_idx,
            "geometry": {
                "type": "Polygon",
                "coordinates": [ring]
            },
            "properties": {
                "h3_index": h3_idx,
                "lat": round(float(p_lat), 6),
                "lng": round(float(p_lng), 6),
                "risk": risk_val,
                "risk_crime": round(float(risk_crime or 0.0), 4),
                "risk_lighting": round(float(risk_lighting or 0.0), 4),
                "risk_live": round(float(risk_live or 0.0), 4),
                "total_risk": round(float(total_risk or 0.0), 4),
                "data_available": has_data
            }
        })

    coverage_pct = round((data_count / len(points) * 100.0), 1) if points else 0.0

    return {
        "type": "FeatureCollection",
        "metadata": {
            "generated_at": now_utc.isoformat(),
            "risk_snapshot_at": freshness.get("risk_snapshot_at"),
            "crime_data_updated_at": freshness.get("crime_data_updated_at"),
            "lighting_data_updated_at": freshness.get("lighting_data_updated_at"),
            "h3_resolution": selected_resolution,
            "channel": channel_clean,
            "feature_count": len(features),
            "data_coverage_pct": coverage_pct
        },
        "features": features
    }
