"""
Bu script SADECE yerel geliştirme ve demo verisi yükler, şema oluşturmaz.
ÖNEMLİ NOT: chicago_clean_data.csv dosyası YALNIZCA legacy/demo baseline veri setidir.
Canlı (production) Supabase veritabanı için KESİNLİKLE kullanılmamalıdır.
Production ortamı için veriler chicago_crime_etl.py ve chicago_311_lighting_etl.py ETL boru hatları ile beslenmelidir.
Tabloların var olduğundan emin olmak için önce 'alembic upgrade head' çalıştırılmış olmalıdır.
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
from crud import CRIME_WEIGHT, LIGHTING_WEIGHT, LIVE_WEIGHT, _compute_total_risk  # noqa: F401

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def seed_data():
    print("Veri aktarımı (Seeding) başlatılıyor...")

    csv_path = "../data-science/chicago_clean_data.csv"

    async with AsyncSessionLocal() as session:
        print("Mevcut h3_heatmap satırları temizleniyor...")
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

                raw_risk = float(row['anlik_risk'])
                crime_risk = raw_risk / 100.0 if raw_risk > 1.0 else raw_risk
                if not (0.0 <= crime_risk <= 1.0):
                    raise ValueError(f"Veri yükleme hatası: crime_risk 0.0-1.0 aralığı dışında ({crime_risk})")

                lighting_risk = 0.0
                live_risk = 0.0

                total_risk = _compute_total_risk(crime=crime_risk, lighting=lighting_risk, live=live_risk)
                if not (0.0 <= total_risk <= 1.0):
                    raise ValueError(f"Veri yükleme hatası: total_risk 0.0-1.0 aralığı dışında ({total_risk})")


                bulk_records.append(
                    H3HeatmapModel(
                        h3_index=computed_h3,
                        lat=lat,
                        lng=lng,
                        location=point_geom,
                        risk_crime=crime_risk,
                        risk_lighting=lighting_risk,
                        risk_live=live_risk,
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
