# llm-integration/services/alert_dispatcher.py
"""
Görev 2 (2. kısım): Analiz edilen ihbarı yakındaki kullanıcılara bildirir.

Şimdilik: mock JSON'dan kullanıcı listesi okunur, bildirimler loglanır.
Sonra:    users/device_tokens/notifications tablolarına bağlanır.
"""
import json
import math
import uuid
from pathlib import Path
from datetime import datetime

from config import settings  # backend/config.py (tek Settings kaynagi)
from ..schemas.types import NearbyUser, AlertMessage, ReportAnalysisResult


def _haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """İki koordinat arası mesafe (metre)."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_mock_users() -> list[NearbyUser]:
    """Mock kullanıcı listesini JSON'dan yükler."""
    mocks_path = Path(__file__).parent.parent / settings.mocks_dir / "sample_users.json"
    with open(mocks_path, encoding="utf-8") as f:
        data = json.load(f)
    return [NearbyUser(**user) for user in data]


def find_nearby_users(
    latitude: float,
    longitude: float,
    radius_meters: int | None = None,
    users: list[NearbyUser] | None = None,
) -> list[NearbyUser]:
    """
    Belirli bir konuma yakın kullanıcıları bulur.

    Args:
        latitude: İhbarın enlemi
        longitude: İhbarın boylamı
        radius_meters: Arama yarıçapı (varsayılan: config'den)
        users: Kullanıcı listesi (verilmezse mock JSON'dan yüklenir)

    Returns:
        Yakın kullanıcılar listesi (mesafeye göre sıralı)
    """
    if radius_meters is None:
        radius_meters = settings.alert_radius_meters

    if users is None:
        users = load_mock_users()

    nearby = []
    for user in users:
        dist = _haversine_distance(latitude, longitude, user.latitude, user.longitude)
        if dist <= radius_meters:
            nearby.append(user.model_copy(update={"distance_meters": round(dist, 1)}))

    nearby.sort(key=lambda u: u.distance_meters)
    return nearby


def _build_alert_message(
    analysis: ReportAnalysisResult,
    user: NearbyUser,
    report_lat: float,
    report_lng: float,
) -> AlertMessage:
    """Analiz sonucundan kullanıcıya gidecek bildirim mesajını oluşturur."""
    severity_labels = {
        "critical": "ACİL",
        "high": "Yüksek Risk",
        "medium": "Dikkat",
        "low": "Bilgi",
    }
    label = severity_labels.get(analysis.severity, "Bildirim")

    distance_text = f"{int(user.distance_meters)}m"
    body = (
        f"{distance_text} yakınınızda {analysis.summary} "
        f"(Risk: {analysis.risk_score}/100)"
    )

    return AlertMessage(
        alert_id=f"alert_{uuid.uuid4().hex[:8]}",
        target_user_id=user.user_id,
        title=f"{label}: Yakınınızda tehlike bildirimi",
        body=body,
        latitude=report_lat,
        longitude=report_lng,
        risk_score=analysis.risk_score,
        category=analysis.category,
        created_at=datetime.utcnow(),
        status="pending",
    )


async def dispatch_alerts(
    analysis: ReportAnalysisResult,
    report_lat: float,
    report_lng: float,
    nearby_users: list[NearbyUser] | None = None,
) -> list[AlertMessage]:
    """
    Yakındaki kullanıcılara bildirim gönderir.

    Şimdilik: Bildirimleri konsola loglar (mock).
    Sonra:    Push notification servisi (FCM/APNs) veya WebSocket ile gerçek gönderim.

    Args:
        analysis: LLM analiz sonucu
        report_lat: İhbarın enlemi
        report_lng: İhbarın boylamı
        nearby_users: Hedef kullanıcılar (verilmezse otomatik bulunur)

    Returns:
        Oluşturulan bildirim mesajları listesi
    """
    if nearby_users is None:
        nearby_users = find_nearby_users(report_lat, report_lng)

    if not nearby_users:
        print("[AlertDispatcher] Yakında kullanıcı bulunamadı.")
        return []

    alerts = []
    for user in nearby_users:
        alert = _build_alert_message(analysis, user, report_lat, report_lng)
        await _send_notification(alert, user)
        alerts.append(alert)

    return alerts


async def _send_notification(alert: AlertMessage, user: NearbyUser) -> None:
    """
    Tek bir bildirimi gönderir.
    Şimdilik mock — konsola yazar.
    Sonra: FCM/APNs veya backend notifications tablosuna yazılır.
    """
    alert.status = "sent"
    token_info = user.device_token or "token_yok"
    print(
        f"\n[Bildirim Gönderildi]\n"
        f"  Kullanıcı: {user.user_id}\n"
        f"  Token: {token_info}\n"
        f"  Başlık: {alert.title}\n"
        f"  Mesaj: {alert.body}\n"
        f"  Mesafe: {user.distance_meters}m\n"
        f"  Kategori: {alert.category} | Risk: {alert.risk_score}\n"
    )
