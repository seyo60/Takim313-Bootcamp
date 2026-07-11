# backend/crud.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from datetime import datetime

from models import H3HeatmapModel, ReportModel

async def create_heatmap_point(db: AsyncSession, h3_index: str, lat: float, lng: float, risk: float) -> H3HeatmapModel:
    point_geom = from_shape(Point(lng, lat), srid=4326)
    new_point = H3HeatmapModel(
        h3_index=h3_index, lat=lat, lng=lng, location=point_geom, risk_weight=risk
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

# Osman'ın mobil uygulamadan göndereceği canlı ihbarları kaydeden fonksiyon
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
