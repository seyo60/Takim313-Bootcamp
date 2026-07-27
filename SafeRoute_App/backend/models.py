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
    risk_crime = Column(Float, default=0.0)       # 1. Boru hattı: Chicago Police Suç Verileri (%65)
    risk_lighting = Column(Float, default=0.0)    # 2. Boru hattı: Chicago 311 Aydınlatma Arızaları (%20)
    risk_historical = Column(Float, default=0.0)  # Geriye dönük uyumluluk (risk_crime ile aynı)
    risk_live = Column(Float, default=0.0)        # 3. Boru hattı: Kullanıcı İhbarları (%15)
    risk_social = Column(Float, default=0.0)      # Faz 2: Sosyal medya / N8N duyarlılığı (opsiyonel)
    
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
    uuid_id = Column(String(36), unique=True, index=True, nullable=True)
    tracking_token = Column(String(64), index=True, nullable=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    description = Column(String(255), nullable=False)
    category = Column(String(50), default="general", nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    ip_address = Column(String(45), nullable=True)
    location = Column(Geography(geometry_type="POINT", srid=4326))
    created_at = Column(DateTime, index=True)


class ETLRunModel(Base):
    __tablename__ = "etl_runs"
    id = Column(Integer, primary_key=True, index=True)
    etl_name = Column(String(50), unique=True, index=True, nullable=False)
    last_successful_run = Column(DateTime, nullable=False)
    records_processed = Column(Integer, default=0)
    status = Column(String(20), default="success", nullable=False)