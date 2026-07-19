# llm-integration/schemas/types.py
"""
LLM modülünün veri tipleri.
Bunlar Pydantic modelleridir — veritabanı modelleri DEĞİLDİR.
Backend'deki models.py'ye dokunulmaz; DB tabloları hazır olunca
bu tipler repository katmanı üzerinden DB verisine dönüştürülür.
"""
from datetime import datetime
from pydantic import BaseModel, Field


class StreetRiskData(BaseModel):
    """Bir sokağın risk verisi — şimdilik mock JSON'dan, sonra h3_heatmap'ten gelecek."""
    h3_index: str
    lat: float
    lng: float
    risk_historical: float = 0.0
    risk_live: float = 0.0
    risk_social: float = 0.0
    total_risk: float = 0.0
    location_description: str | None = None


class StreetExplanation(BaseModel):
    """Görev 1 çıktısı: Sokak neden güvensiz?"""
    h3_index: str
    summary: str = Field(..., description="Kullanıcıya gösterilecek kısa açıklama (max ~2 cümle)")
    risk_level: str = Field(..., description="low | medium | high | critical")
    factors: list[str] = Field(default_factory=list, description="Risk faktörleri listesi")


class UserReport(BaseModel):
    """Görev 2 girişi: Kullanıcının anlık ihbarı."""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    text: str = Field(..., min_length=1)
    user_score: float | None = Field(None, ge=0, le=100, description="Kullanıcının verdiği suç puanı (opsiyonel)")


class ReportAnalysisResult(BaseModel):
    """Görev 2 çıktısı: LLM'in ihbar analizi."""
    risk_score: float = Field(..., ge=0, le=100)
    summary: str = Field(..., description="İhbarın kısa özeti")
    category: str = Field(..., description="violent | theft | harassment | suspicious | environmental | other")
    severity: str = Field(..., description="low | medium | high | critical")
    h3_index: str | None = None


class NearbyUser(BaseModel):
    """Bildirim gönderilecek yakın kullanıcı — şimdilik mock, sonra users/device_tokens tablosundan."""
    user_id: str
    device_token: str | None = None
    latitude: float
    longitude: float
    distance_meters: float = 0.0


class AlertMessage(BaseModel):
    """Yakın kullanıcıya gidecek uyarı mesajı."""
    alert_id: str
    target_user_id: str
    title: str
    body: str
    latitude: float
    longitude: float
    risk_score: float
    category: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="pending", description="pending | sent | failed")
