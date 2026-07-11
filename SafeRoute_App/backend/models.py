# backend/models.py
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean
from geoalchemy2 import Geography
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()

# 1. Veri bilimi ekibinden gelecek temiz veriler için analiz tablosu
class H3HeatmapModel(Base):
    __tablename__ = "h3_heatmap"
    id = Column(Integer, primary_key=True, index=True)
    h3_index = Column(String(15), index=True, nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    location = Column(Geography(geometry_type="POINT", srid=4326))
    risk_weight = Column(Float, default=0.0)
    domestic = Column(Boolean, default=False)
    location_description = Column(String(255))
    date = Column(DateTime, index=True)
    extra_features = Column(JSONB, nullable=True, default=dict)  


# 2. Mobil uygulamadan gelecek canlı ihbarlar için tablo
class ReportModel(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    description = Column(String(255), nullable=False)  # Kullanıcının metin açıklaması
    location = Column(Geography(geometry_type="POINT", srid=4326))  # PostGIS canlı nokta sorgusu
    created_at = Column(DateTime, index=True)  # İhbar oluşturulma zamanı

