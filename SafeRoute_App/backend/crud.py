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