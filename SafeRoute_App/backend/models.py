# backend/models.py
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean
from geoalchemy2 import Geography
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()

class H3HeatmapModel(Base):
    __tablename__ = "h3_heatmap"
    id = Column(Integer, primary_key=True, index=True)
    h3_index = Column(String(15), index=True, nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    location = Column(Geography(geometry_type="POINT", srid=4326))
    
    # --- YENİ MİMARİ: RİSK KANALLARI ---
    risk_historical = Column(Float, default=0.0)  # 1. Boru hattı: Chicago Data Portal (Statik)
    risk_live = Column(Float, default=0.0)        # 2. Boru hattı: Kullanıcı İhbarları (Anlık)
    risk_social = Column(Float, default=0.0)      # 3. Boru hattı: Twitter/N8N otomasyonları
    
    # Algoritmanın haritada kullanacağı NİHAİ (Ağırlıklı) Skor
    total_risk = Column(Float, default=0.0)       
    # -----------------------------------
    
    domestic = Column(Boolean, default=False)
    location_description = Column(String(255))
    date = Column(DateTime, index=True)
    extra_features = Column(JSONB, nullable=True, default=dict)  

class ReportModel(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    description = Column(String(255), nullable=False)
    location = Column(Geography(geometry_type="POINT", srid=4326))
    created_at = Column(DateTime, index=True)