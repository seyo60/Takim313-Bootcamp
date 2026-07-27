<<<<<<< Updated upstream
# backend/crud.py
import h3
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from datetime import datetime

from models import H3HeatmapModel, ReportModel

# --- TEK DOGRULUK KAYNAGI: Agirlikli toplama formulu ---
# Bu katsayilar seed.py'deki katsayilarla AYNI olmali.
HISTORICAL_WEIGHT = 0.4
LIVE_WEIGHT = 0.5
SOCIAL_WEIGHT = 0.1


def _compute_total_risk(historical: float, live: float, social: float) -> float:
    """
    Uc risk kanalini tek bir agirlikli skora indirger.
    Bu fonksiyon, formulun TEK yazildigi yer olmali - baska hicbir dosyada
    (seed.py haric, ki o da ayni sabitleri kullaniyor) bu hesap tekrarlanmamali.
    """
    return (historical * HISTORICAL_WEIGHT) + (live * LIVE_WEIGHT) + (social * SOCIAL_WEIGHT)


async def create_heatmap_point(db: AsyncSession, h3_index: str, lat: float, lng: float, risk: float) -> H3HeatmapModel:
    point_geom = from_shape(Point(lng, lat), srid=4326)
    new_point = H3HeatmapModel(
        h3_index=h3_index,
        lat=lat,
        lng=lng,
        location=point_geom,
        risk_historical=risk,
        total_risk=risk * HISTORICAL_WEIGHT
    )
    db.add(new_point)
    await db.commit()
    await db.refresh(new_point)
    return new_point


async def get_all_heatmap_points(db: AsyncSession) -> list[H3HeatmapModel]:
    result = await db.execute(select(H3HeatmapModel))
    return result.scalars().all()


async def get_nearby_risk_points(db: AsyncSession, user_lat: float, user_lng: float, radius_meters: int = 500) -> list[H3HeatmapModel]:
    user_point = func.ST_SetSRID(func.ST_MakePoint(user_lng, user_lat), 4326)
    query = select(H3HeatmapModel).where(func.ST_DWithin(H3HeatmapModel.location, user_point, radius_meters))
    result = await db.execute(query)
    return result.scalars().all()


async def create_report(db: AsyncSession, lat: float, lng: float, text: str) -> ReportModel:
    report_geom = from_shape(Point(lng, lat), srid=4326)
    new_report = ReportModel(
        latitude=lat,
        longitude=lng,
        description=text,
        location=report_geom,
        created_at=datetime.utcnow()
    )
    db.add(new_report)
    await db.commit()
    await db.refresh(new_report)
    return new_report


async def update_h3_live_risk(db: AsyncSession, h3_index: str, added_live_risk: float) -> float:
    """
    Canli bir ihbar geldiginde risk_live'i gunceller, total_risk'i
    agirlikli formulle yeniden hesaplar.

    ONEMLI: Bu fonksiyon artik hesapladigi YENI total_risk degerini
    GERI DONUYOR (return). main.py bu degeri RAM'deki grafa dogrudan
    YAZACAK (ekleme yapmayacak) - boylece RAM ve DB her zaman ayni
    formulden gelen ayni sayiyi gosterir, aralarinda sapma olusmaz.
    """
    query = select(H3HeatmapModel).where(H3HeatmapModel.h3_index == h3_index)
    result = await db.execute(query)
    cell = result.scalars().first()

    if cell:
        cell.risk_live += added_live_risk
        cell.total_risk = _compute_total_risk(cell.risk_historical, cell.risk_live, cell.risk_social)
        await db.commit()
        return cell.total_risk
    else:
        lat, lng = h3.cell_to_latlng(h3_index)
        point_geom = from_shape(Point(lng, lat), srid=4326)

        new_total_risk = _compute_total_risk(0.0, added_live_risk, 0.0)

        new_cell = H3HeatmapModel(
            h3_index=h3_index,
            lat=lat,
            lng=lng,
            location=point_geom,
            risk_historical=0.0,
            risk_live=added_live_risk,
            risk_social=0.0,
            total_risk=new_total_risk
        )
        db.add(new_cell)
        await db.commit()
        return new_total_risk


async def update_h3_social_risk(db: AsyncSession, h3_index: str, social_risk_score: float) -> float:
    """
    Webhook'tan (n8n vb.) gelen sosyal medya riskini kaydeder, total_risk'i
    agirlikli formulle yeniden hesaplar. Yeni total_risk'i GERI DONER
    (bkz. update_h3_live_risk'teki aciklama - RAM/DB tutarliligi icin).
    """
    query = select(H3HeatmapModel).where(H3HeatmapModel.h3_index == h3_index)
    result = await db.execute(query)
    cell = result.scalars().first()

    if cell:
        # Sosyal medya verisi kumulatif degil, o anki duyarliligi (sentiment) yansitir
        cell.risk_social = social_risk_score
        cell.total_risk = _compute_total_risk(cell.risk_historical, cell.risk_live, cell.risk_social)
        await db.commit()
        return cell.total_risk
    else:
        lat, lng = h3.cell_to_latlng(h3_index)
        point_geom = from_shape(Point(lng, lat), srid=4326)

        new_total_risk = _compute_total_risk(0.0, 0.0, social_risk_score)

        new_cell = H3HeatmapModel(
            h3_index=h3_index,
            lat=lat,
            lng=lng,
            location=point_geom,
            risk_historical=0.0,
            risk_live=0.0,
            risk_social=social_risk_score,
            total_risk=new_total_risk
        )
        db.add(new_cell)
        await db.commit()
        return new_total_risk
=======
# backend/crud.py
import h3
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from models import H3HeatmapModel, ReportModel, ETLRunModel


# --- TEK DOGRULUK KAYNAGI: Agirlikli toplama formulu ---
# YENİ MİMARİ: 3 KANALLI ÇOK ETKENLİ RİSK FORMÜLÜ
# R_total = 0.65 * R_crime + 0.20 * R_lighting + 0.15 * R_live
CRIME_WEIGHT = 0.65       # %65 Suç Verileri (Chicago Police Department)
LIGHTING_WEIGHT = 0.20    # %20 Aydınlatma Arızaları (Chicago 311)
LIVE_WEIGHT = 0.15        # %15 Canlı Kullanıcı İhbarları
SOCIAL_WEIGHT = 0.0       # Devre dışı (Faz 2)

# Geriye dönük uyumluluk sabitleri
HISTORICAL_WEIGHT = CRIME_WEIGHT


def _compute_total_risk(
    crime: float = 0.0,
    lighting: float = 0.0,
    live: float = 0.0,
    social: float = 0.0,
    historical: float = None
) -> float:
    """
    Tüm risk kanallarını tek bir ağırlıklı skora dönüştürür:
    R_total = 0.65*crime + 0.20*lighting + 0.15*live + 0.0*social
    """
    if crime == 0.0 and historical is not None:
        crime = historical

    return (crime * CRIME_WEIGHT) + (lighting * LIGHTING_WEIGHT) + (live * LIVE_WEIGHT) + (social * SOCIAL_WEIGHT)


async def create_heatmap_point(db: AsyncSession, h3_index: str, lat: float, lng: float, risk: float) -> H3HeatmapModel:
    point_geom = from_shape(Point(lng, lat), srid=4326)
    new_point = H3HeatmapModel(
        h3_index=h3_index,
        lat=lat,
        lng=lng,
        location=point_geom,
        risk_crime=risk,
        risk_historical=risk,
        risk_lighting=0.0,
        risk_live=0.0,
        total_risk=_compute_total_risk(crime=risk)
    )
    db.add(new_point)
    await db.commit()
    await db.refresh(new_point)
    return new_point


async def get_all_heatmap_points(db: AsyncSession) -> list[H3HeatmapModel]:
    if db is None:
        return []
    result = await db.execute(select(H3HeatmapModel))
    return list(result.scalars().all())


async def get_nearby_risk_points(db: AsyncSession, user_lat: float, user_lng: float, radius_meters: int = 500) -> list[H3HeatmapModel]:
    user_point = func.ST_SetSRID(func.ST_MakePoint(user_lng, user_lat), 4326)
    query = select(H3HeatmapModel).where(func.ST_DWithin(H3HeatmapModel.location, user_point, radius_meters))
    result = await db.execute(query)
    return result.scalars().all()


async def upsert_crime_data(
    db: AsyncSession,
    h3_index: str,
    lat: float,
    lng: float,
    risk_crime: float,
    extra_features: dict = None
) -> H3HeatmapModel:
    query = select(H3HeatmapModel).where(H3HeatmapModel.h3_index == h3_index)
    result = await db.execute(query)
    cell = result.scalars().first()

    norm_crime = max(0.0, min(1.0, risk_crime))

    if cell:
        cell.risk_crime = norm_crime
        cell.risk_historical = norm_crime
        if extra_features:
            cell.extra_features = extra_features
        cell.total_risk = _compute_total_risk(
            crime=cell.risk_crime,
            lighting=cell.risk_lighting or 0.0,
            live=cell.risk_live or 0.0
        )
    else:
        point_geom = from_shape(Point(lng, lat), srid=4326)
        cell = H3HeatmapModel(
            h3_index=h3_index,
            lat=lat,
            lng=lng,
            location=point_geom,
            risk_crime=norm_crime,
            risk_historical=norm_crime,
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
    query = select(H3HeatmapModel).where(H3HeatmapModel.h3_index == h3_index)
    result = await db.execute(query)
    cell = result.scalars().first()

    norm_lighting = max(0.0, min(1.0, risk_lighting))

    if cell:
        cell.risk_lighting = norm_lighting
        if extra_features:
            existing = cell.extra_features or {}
            existing.update(extra_features)
            cell.extra_features = existing
        cell.total_risk = _compute_total_risk(
            crime=cell.risk_crime or cell.risk_historical or 0.0,
            lighting=cell.risk_lighting,
            live=cell.risk_live or 0.0
        )
    else:
        point_geom = from_shape(Point(lng, lat), srid=4326)
        cell = H3HeatmapModel(
            h3_index=h3_index,
            lat=lat,
            lng=lng,
            location=point_geom,
            risk_crime=0.0,
            risk_historical=0.0,
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

    try:
        query = select(ETLRunModel)
        result = await db.execute(query)
        runs = {r.etl_name: r.last_successful_run for r in result.scalars().all()}

        crime_dt = runs.get("crime_etl")
        lighting_dt = runs.get("lighting_etl")

        # Snapshot zamanı: İki ETL'in en yenisi veya sistem zamanı
        snapshot_dts = [dt for dt in (crime_dt, lighting_dt) if dt is not None]
        snapshot_dt = max(snapshot_dts) if snapshot_dts else datetime.now(timezone.utc)

        return {
            "crime_data_updated_at": crime_dt.isoformat() if crime_dt else None,
            "lighting_data_updated_at": lighting_dt.isoformat() if lighting_dt else None,
            "risk_snapshot_at": snapshot_dt.isoformat()
        }
    except Exception:
        return {
            "crime_data_updated_at": None,
            "lighting_data_updated_at": None,
            "risk_snapshot_at": now_iso
        }


_in_memory_reports: dict[str, ReportModel] = {}


async def check_duplicate_report(
    db: AsyncSession,
    lat: float,
    lng: float,
    time_window_minutes: int = 10,
    radius_meters: float = 50.0
) -> bool:
    """
    Belirtilen koordinat etrafında (radius_meters) ve zaman penceresinde (time_window_minutes)
    daha önce ihbar girilip girilmediğini kontrol eder (mükerrer ihbar koruması).
    """
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=time_window_minutes)

    if db is None:
        for rep in _in_memory_reports.values():
            if rep.created_at and rep.created_at >= cutoff_time:
                # Metrik mesafe yaklaşık hesabı (1 enlem derecesi ~ 111,000m)
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
        result = await db.execute(query)
        existing = result.scalars().first()
        return existing is not None
    except Exception:
        return False


async def create_report(
    db: AsyncSession,
    lat: float,
    lng: float,
    text: str,
    category: str = "general",
    ip_address: str = None
) -> ReportModel:
    """
    Kriptografik olarak güvenli UUID v4 ve tracking_token üreterek yeni ihbar kaydeder.
    """
    generated_uuid = str(uuid.uuid4())
    generated_token = secrets.token_urlsafe(32)

    new_report = ReportModel(
        id=len(_in_memory_reports) + 1,
        uuid_id=generated_uuid,
        tracking_token=generated_token,
        latitude=lat,
        longitude=lng,
        description=text[:250],  # Temizlenmiş ve sınırlanmış metin
        category=category,
        status="pending",
        ip_address=ip_address,
        created_at=datetime.now(timezone.utc)
    )
    _in_memory_reports[generated_uuid] = new_report

    if db is not None:
        try:
            report_geom = from_shape(Point(lng, lat), srid=4326)
            new_report.location = report_geom
            db.add(new_report)
            await db.commit()
            await db.refresh(new_report)
        except Exception:
            pass

    return new_report


async def get_report_by_uuid_and_token(db: AsyncSession, uuid_id: str, token: str) -> ReportModel | None:
    """
    IDOR Saldırılarına karşı korumalı ihbar sorgulama.
    Sadece UUID VE doğrulama jetonu (tracking_token) eşleştiğinde sonucu döner.
    """
    if db is None:
        rep = _in_memory_reports.get(uuid_id)
        if rep and rep.tracking_token == token:
            return rep
        return None

    try:
        query = select(ReportModel).where(
            ReportModel.uuid_id == uuid_id,
            ReportModel.tracking_token == token
        )
        result = await db.execute(query)
        return result.scalars().first()
    except Exception:
        return None


async def get_report_by_id(db: AsyncSession, report_id: int) -> ReportModel | None:
    query = select(ReportModel).where(ReportModel.id == report_id)
    result = await db.execute(query)
    return result.scalars().first()


async def update_h3_live_risk(db: AsyncSession, h3_index: str, added_live_risk: float) -> float:
    """
    Canli bir ihbar geldiginde risk_live'i [0.0, 1.0] araliginda sinirli birikimle (bounded accumulation)
    gunceller: R_live_new = 1 - (1 - R_live_old) * (1 - Impact)
    Boylece kac ihbar gelirse gelsin risk_live asla 1.0'i asmaz. GERI DONER: yeni total_risk.
    """
    query = select(H3HeatmapModel).where(H3HeatmapModel.h3_index == h3_index)
    result = await db.execute(query)
    cell = result.scalars().first()

    # LLM ceza puanini (0-100) 0.0-1.0 arasi etkiye dönüstür
    impact = min(1.0, added_live_risk / 100.0 if added_live_risk > 1.0 else added_live_risk)

    if cell:
        current_live = cell.risk_live or 0.0
        new_live = 1.0 - ((1.0 - current_live) * (1.0 - impact))
        cell.risk_live = max(0.0, min(1.0, new_live))
        cell.total_risk = _compute_total_risk(
            crime=cell.risk_crime or cell.risk_historical or 0.0,
            lighting=cell.risk_lighting or 0.0,
            live=cell.risk_live,
            social=cell.risk_social or 0.0
        )
        await db.commit()
        return cell.total_risk
    else:
        lat, lng = h3.cell_to_latlng(h3_index)
        point_geom = from_shape(Point(lng, lat), srid=4326)
        initial_live = max(0.0, min(1.0, impact))
        new_total_risk = _compute_total_risk(live=initial_live)

        new_cell = H3HeatmapModel(
            h3_index=h3_index,
            lat=lat,
            lng=lng,
            location=point_geom,
            risk_crime=0.0,
            risk_lighting=0.0,
            risk_historical=0.0,
            risk_live=initial_live,
            risk_social=0.0,
            total_risk=new_total_risk
        )
        db.add(new_cell)
        await db.commit()
        return new_total_risk


async def update_h3_social_risk(db: AsyncSession, h3_index: str, social_risk_score: float) -> float:
    query = select(H3HeatmapModel).where(H3HeatmapModel.h3_index == h3_index)
    result = await db.execute(query)
    cell = result.scalars().first()

    normalized_social = max(0.0, min(1.0, social_risk_score))

    if cell:
        cell.risk_social = normalized_social
        cell.total_risk = _compute_total_risk(
            crime=cell.risk_crime or cell.risk_historical or 0.0,
            lighting=cell.risk_lighting or 0.0,
            live=cell.risk_live or 0.0,
            social=cell.risk_social
        )
        await db.commit()
        return cell.total_risk
    else:
        lat, lng = h3.cell_to_latlng(h3_index)
        point_geom = from_shape(Point(lng, lat), srid=4326)
        new_total_risk = _compute_total_risk(social=normalized_social)

        new_cell = H3HeatmapModel(
            h3_index=h3_index,
            lat=lat,
            lng=lng,
            location=point_geom,
            risk_crime=0.0,
            risk_lighting=0.0,
            risk_historical=0.0,
            risk_live=0.0,
            risk_social=normalized_social,
            total_risk=new_total_risk
        )
        db.add(new_cell)
        await db.commit()
        return new_total_risk


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
    query = select(H3HeatmapModel).where(H3HeatmapModel.h3_index == h3_index)
    result = await db.execute(query)
    cell = result.scalars().first()

    norm_crime = max(0.0, min(1.0, risk_crime))

    if cell:
        cell.risk_crime = norm_crime
        cell.risk_historical = norm_crime
        if extra_features:
            merged = dict(cell.extra_features or {})
            merged.update(extra_features)
            cell.extra_features = merged

        cell.total_risk = _compute_total_risk(
            crime=cell.risk_crime,
            lighting=cell.risk_lighting or 0.0,
            live=cell.risk_live or 0.0,
            social=cell.risk_social or 0.0
        )
        await db.commit()
        return cell
    else:
        point_geom = from_shape(Point(lng, lat), srid=4326)
        tot_risk = _compute_total_risk(crime=norm_crime)

        new_cell = H3HeatmapModel(
            h3_index=h3_index,
            lat=lat,
            lng=lng,
            location=point_geom,
            risk_crime=norm_crime,
            risk_historical=norm_crime,
            risk_lighting=0.0,
            risk_live=0.0,
            risk_social=0.0,
            total_risk=tot_risk,
            extra_features=extra_features or {}
        )
        db.add(new_cell)
        await db.commit()
        return new_cell


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
    query = select(H3HeatmapModel).where(H3HeatmapModel.h3_index == h3_index)
    result = await db.execute(query)
    cell = result.scalars().first()

    norm_lighting = max(0.0, min(1.0, risk_lighting))

    if cell:
        cell.risk_lighting = norm_lighting
        if extra_features:
            merged = dict(cell.extra_features or {})
            merged.update(extra_features)
            cell.extra_features = merged

        cell.total_risk = _compute_total_risk(
            crime=cell.risk_crime or cell.risk_historical or 0.0,
            lighting=cell.risk_lighting,
            live=cell.risk_live or 0.0,
            social=cell.risk_social or 0.0
        )
        await db.commit()
        return cell
    else:
        point_geom = from_shape(Point(lng, lat), srid=4326)
        tot_risk = _compute_total_risk(lighting=norm_lighting)

        new_cell = H3HeatmapModel(
            h3_index=h3_index,
            lat=lat,
            lng=lng,
            location=point_geom,
            risk_crime=0.0,
            risk_historical=0.0,
            risk_lighting=norm_lighting,
            risk_live=0.0,
            risk_social=0.0,
            total_risk=tot_risk,
            extra_features=extra_features or {}
        )
        db.add(new_cell)
        await db.commit()
        return new_cell


async def upsert_h3_cell_data(
    db: AsyncSession,
    h3_index: str,
    lat: float,
    lng: float,
    risk_crime: float = None,
    risk_lighting: float = None,
    extra_features: dict = None
) -> H3HeatmapModel:
    """
    Genel H3 hücre güncellemesi. Belirtilen alanları günceller, belirtilmeyen mevcut alanları KORUR.
    """
    query = select(H3HeatmapModel).where(H3HeatmapModel.h3_index == h3_index)
    result = await db.execute(query)
    cell = result.scalars().first()

    if cell:
        if risk_crime is not None:
            norm_crime = max(0.0, min(1.0, risk_crime))
            cell.risk_crime = norm_crime
            cell.risk_historical = norm_crime
        if risk_lighting is not None:
            norm_lighting = max(0.0, min(1.0, risk_lighting))
            cell.risk_lighting = norm_lighting
        if extra_features is not None:
            merged = dict(cell.extra_features or {})
            merged.update(extra_features)
            cell.extra_features = merged

        cell.total_risk = _compute_total_risk(
            crime=cell.risk_crime or 0.0,
            lighting=cell.risk_lighting or 0.0,
            live=cell.risk_live or 0.0,
            social=cell.risk_social or 0.0
        )
        await db.commit()
        return cell
    else:
        point_geom = from_shape(Point(lng, lat), srid=4326)
        c_risk = max(0.0, min(1.0, risk_crime)) if risk_crime is not None else 0.0
        l_risk = max(0.0, min(1.0, risk_lighting)) if risk_lighting is not None else 0.0
        tot_risk = _compute_total_risk(crime=c_risk, lighting=l_risk)

        new_cell = H3HeatmapModel(
            h3_index=h3_index,
            lat=lat,
            lng=lng,
            location=point_geom,
            risk_crime=c_risk,
            risk_historical=c_risk,
            risk_lighting=l_risk,
            risk_live=0.0,
            risk_social=0.0,
            total_risk=tot_risk,
            extra_features=extra_features or {}
        )
        db.add(new_cell)
        await db.commit()
        return new_cell


import hashlib

def anonymize_location(lat: float, lng: float) -> tuple[float, float]:
    """
    H3 Resolution 9 hücresinin merkezine dönüştürür.
    H3 başarısız olursa 3 ondalık yuvarlama yapar (~110m hassasiyet).
    """
    try:
        cell = h3.latlng_to_cell(lat, lng, 9)
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
    if uuid_id in _in_memory_reports:
        _in_memory_reports[uuid_id].status = new_status
    if db is not None:
        try:
            query = select(ReportModel).where(ReportModel.uuid_id == uuid_id)
            res = await db.execute(query)
            rep = res.scalars().first()
            if rep:
                rep.status = new_status
                await db.commit()
        except Exception:
            pass


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
    """
    now_utc = datetime.now(timezone.utc)
    minutes = max(5, min(60, minutes))
    limit = max(1, min(1000, limit))
    cutoff_time = now_utc - timedelta(minutes=minutes)

    bbox_tuple = parse_bbox(bbox) if bbox else None
    reports_list = []

    if db is None:
        raw_reports = list(_in_memory_reports.values())
    else:
        try:
            query = select(ReportModel).where(
                ReportModel.created_at >= cutoff_time
            )
            if category:
                query = query.where(ReportModel.category == category.lower())

            query = query.order_by(ReportModel.created_at.desc()).limit(limit)
            result = await db.execute(query)
            raw_reports = result.scalars().all()
        except Exception:
            raw_reports = list(_in_memory_reports.values())

    for r in raw_reports:
        r_created = r.created_at
        if r_created is not None:
            if r_created.tzinfo is None:
                r_created = r_created.replace(tzinfo=timezone.utc)
            if r_created < cutoff_time:
                continue

        r_status = getattr(r, "status", "accepted")
        if r_status in ("rejected", "expired"):
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
            "status": r_status if r_status != "pending" else "accepted",
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
    include_no_data: bool = True
) -> dict:
    """
    Chicago H3 Resolution 9 hücre risk verilerini harita katmanı için GeoJSON FeatureCollection olarak döner.
    Poligonlar kapalı halka ([lng, lat] sırası) olarak üretilir.
    """
    now_utc = datetime.now(timezone.utc)
    freshness = await get_latest_etl_runs(db)
    
    points = await get_all_heatmap_points(db)

    bbox_tuple = parse_bbox(bbox) if bbox else None
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

        # Target channel risk extraction
        risk_crime = getattr(p, "risk_crime", getattr(p, "risk_historical", 0.0))
        risk_lighting = getattr(p, "risk_lighting", 0.0)
        risk_live = getattr(p, "risk_live", 0.0)
        total_risk = getattr(p, "total_risk", 0.0)

        if channel_clean == "crime":
            raw_risk = risk_crime
        elif channel_clean == "lighting":
            raw_risk = risk_lighting
        elif channel_clean == "live":
            raw_risk = risk_live
        else:
            raw_risk = total_risk

        has_data = raw_risk is not None and (total_risk is not None and total_risk > 0.0 or risk_crime > 0.0 or risk_lighting > 0.0 or risk_live > 0.0)
        
        if not has_data and not include_no_data:
            continue

        if has_data:
            data_count += 1
            risk_val = round(max(0.0, min(1.0, float(raw_risk or 0.0))), 4)
        else:
            risk_val = None

        # Build H3 polygon ring
        try:
            boundary = h3.cell_to_boundary(h3_idx)
            ring = [[round(float(pt[1]), 6), round(float(pt[0]), 6)] for pt in boundary]
            if ring and ring[0] != ring[-1]:
                ring.append(ring[0])
        except Exception:
            # Fallback square around centroid if boundary generation fails
            d = 0.001
            ring = [
                [round(p_lng - d, 6), round(p_lat - d, 6)],
                [round(p_lng + d, 6), round(p_lat - d, 6)],
                [round(p_lng + d, 6), round(p_lat + d, 6)],
                [round(p_lng - d, 6), round(p_lat + d, 6)],
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
            "h3_resolution": 9,
            "channel": channel_clean,
            "feature_count": len(features),
            "data_coverage_pct": coverage_pct
        },
        "features": features
    }

>>>>>>> Stashed changes
