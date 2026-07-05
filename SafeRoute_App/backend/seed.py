# backend/seed.py
import asyncio
import csv
from datetime import datetime, timezone  # Saat dilimi dönüşümleri için
import h3  # Dinamik H3 indeksi üretimi (v4+ uyumlu)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

from config import settings
from models import Base, H3HeatmapModel

# Asenkron veritabanı motoru yapılandırması
engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def seed_data():
    print("Veri aktarımı (Seeding) başlatılıyor...")
    
    # 1. CSV Dosyasının konumu (Data Science klasöründen temiz veriyi okur)
    csv_path = "../data-science/chicago_clean_data.csv" 
    
    async with AsyncSessionLocal() as session:
        async with engine.begin() as conn:
            # Sütun veya tablo yapısı uyumsuzluklarını engellemek için önce eski tabloları güvenle uçuruyoruz
            print("Eski tablolar temizleniyor (Drop)...")
            await conn.run_sync(Base.metadata.drop_all)
            
            # Güncel modellerle tabloları sıfırdan tertemiz oluşturuyoruz
            print("Güncel tablolar yeniden oluşturuluyor...")
            await conn.run_sync(Base.metadata.create_all)
            
        with open(csv_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            bulk_records = []
            for row in reader:
                # WKT formatındaki LINESTRING yapısından koordinat çiftini ayıklama
                raw_geom = row['geometry'].replace("LINESTRING (", "").replace(")", "")
                first_coord = raw_geom.split(",")[0].strip().split(" ")
                lng = float(first_coord[0])
                lat = float(first_coord[1])
                
                # PostGIS (GeoAlchemy2) için coğrafi nokta geometrisi üretimi
                point_geom = from_shape(Point(lng, lat), srid=4326)
                
                # H3 v4+ standardına uygun olarak dinamik hücre indeksi üretimi
                computed_h3 = h3.latlng_to_cell(lat, lng, 9)
                
                # domestic verisini string'den boolean tipe dönüştürme
                is_domestic = row.get('domestic', 'False').lower() in ['true', '1', 't']
                
                # asyncpg uyuşmazlığını çözmek için tzinfo içermeyen (naive) UTC zaman damgası üretiyoruz
                naive_utc_datetime = datetime.now(timezone.utc).replace(tzinfo=None)
                
                bulk_records.append(
                    H3HeatmapModel(
                        h3_index=computed_h3,
                        lat=lat,
                        lng=lng,
                        location=point_geom,
                        risk_weight=float(row['anlik_risk']),
                        domestic=is_domestic,
                        location_description=row['name'],
                        date=naive_utc_datetime  # Hata çıkaran timezone uyuşmazlığı düzeltildi!
                    )
                )
                
            if bulk_records:
                print(f"{len(bulk_records)} adet kayıt veritabanına yazılmak üzere hazırlanıyor...")
                session.add_all(bulk_records)
                await session.commit()
                print(f"Başarıyla {len(bulk_records)} adet suç verisi dinamik H3 indeksleriyle veritabanına aktarıldı!")

if __name__ == "__main__":
    asyncio.run(seed_data())