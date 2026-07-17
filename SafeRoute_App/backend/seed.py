# backend/seed.py
"""
Bu script SADECE veri yukler, sema (schema) olusturmaz/silmez.
Tablolarin var oldugundan emin olmak icin once 'alembic upgrade head'
calistirilmis olmali.
"""
import asyncio
import csv
from datetime import datetime, timezone
import h3
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import delete
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

from config import settings
from models import H3HeatmapModel
# Agirliklar TEK yerden (crud.py) import edilir - kopya sabit tutulmaz.
# 2 kanalli yapi: HISTORICAL_WEIGHT=0.5, LIVE_WEIGHT=0.5, SOCIAL_WEIGHT=0.0
from crud import HISTORICAL_WEIGHT, LIVE_WEIGHT, SOCIAL_WEIGHT  # noqa: F401

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def seed_data():
    print("Veri aktarımı (Seeding) başlatılıyor...")

    csv_path = "../data-science/chicago_clean_data.csv"

    async with AsyncSessionLocal() as session:
        # Sadece VERIYI temizliyoruz (DELETE), tabloyu DROP etmiyoruz.
        # Sema yonetimi tamamen Alembic'in sorumlulugunda.
        print("Mevcut h3_heatmap satırları temizleniyor (tablo yapısına dokunulmuyor)...")
        await session.execute(delete(H3HeatmapModel))
        await session.commit()

        with open(csv_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            bulk_records = []
            for row in reader:
                raw_geom = row['geometry'].replace("LINESTRING (", "").replace(")", "")
                first_coord = raw_geom.split(",")[0].strip().split(" ")
                lng = float(first_coord[0])
                lat = float(first_coord[1])

                point_geom = from_shape(Point(lng, lat), srid=4326)
                computed_h3 = h3.latlng_to_cell(lat, lng, 9)
                is_domestic = row.get('domestic', 'False').lower() in ['true', '1', 't']
                naive_utc_datetime = datetime.now(timezone.utc).replace(tzinfo=None)

                historical_risk = float(row['anlik_risk'])

                # ONEMLI: crud.py'deki update_h3_live_risk / update_h3_social_risk
                # fonksiyonlarindaki AYNI agirlikli formulu burada da uyguluyoruz.
                # Boylece bir bolgeye ilk canli ihbar geldiginde total_risk
                # beklenmedik sekilde dusmuyor - zaten ayni formulle hesaplanmis oluyor.
                # risk_live ve risk_social henuz 0 oldugu icin sadece historical katkisi var.
                total_risk = historical_risk * HISTORICAL_WEIGHT

                bulk_records.append(
                    H3HeatmapModel(
                        h3_index=computed_h3,
                        lat=lat,
                        lng=lng,
                        location=point_geom,
                        risk_historical=historical_risk,
                        risk_live=0.0,
                        risk_social=0.0,
                        total_risk=total_risk,
                        domestic=is_domestic,
                        location_description=row['name'],
                        date=naive_utc_datetime
                    )
                )

            if bulk_records:
                print(f"{len(bulk_records)} adet kayıt veritabanına yazılmak üzere hazırlanıyor...")
                session.add_all(bulk_records)
                await session.commit()
                print(f"Başarıyla {len(bulk_records)} adet suç verisi dinamik H3 indeksleriyle veritabanına aktarıldı!")


if __name__ == "__main__":
    asyncio.run(seed_data())