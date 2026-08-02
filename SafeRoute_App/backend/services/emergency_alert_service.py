"""Acil ihbar: 1 km tanık isteği → onay → herkese yayın."""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import (
    AlertConfirmationModel,
    EmergencyAlertModel,
    ReportEventModel,
    ReportModel,
    UserDeviceModel,
)
from services.emergency_alert_llm import compose_emergency_alert_copy
from services.expo_push import build_expo_message, send_expo_push_messages

logger = logging.getLogger("saferoute.emergency_alert")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


async def upsert_user_device(
    db: AsyncSession,
    *,
    user_id: UUID | str,
    expo_push_token: str,
    lat: float | None = None,
    lng: float | None = None,
) -> UserDeviceModel:
    token = expo_push_token.strip()
    uid = UUID(str(user_id))
    now = _now()
    result = await db.execute(
        select(UserDeviceModel).where(UserDeviceModel.expo_push_token == token)
    )
    device = result.scalars().first()
    if device is None:
        device = UserDeviceModel(
            user_id=uid,
            expo_push_token=token,
            last_lat=float(lat) if lat is not None else None,
            last_lng=float(lng) if lng is not None else None,
            created_at=now,
            updated_at=now,
        )
        db.add(device)
        await db.flush()
    else:
        device.user_id = uid
        device.updated_at = now
        if lat is not None and lng is not None:
            device.last_lat = float(lat)
            device.last_lng = float(lng)

    if lat is not None and lng is not None:
        await db.execute(
            text(
                """
                UPDATE user_devices
                SET location = ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                    last_lat = :lat,
                    last_lng = :lng,
                    updated_at = :ts
                WHERE expo_push_token = :token
                """
            ),
            {"lng": float(lng), "lat": float(lat), "token": token, "ts": now},
        )
    await db.commit()
    result = await db.execute(
        select(UserDeviceModel).where(UserDeviceModel.expo_push_token == token)
    )
    return result.scalars().one()


async def update_user_location(
    db: AsyncSession,
    *,
    user_id: UUID | str,
    lat: float,
    lng: float,
) -> int:
    """Kullanıcının tüm cihazlarındaki son konumu günceller."""
    now = _now()
    result = await db.execute(
        text(
            """
            UPDATE user_devices
            SET location = ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                last_lat = :lat,
                last_lng = :lng,
                updated_at = :ts
            WHERE user_id = :uid
            """
        ),
        {
            "lng": float(lng),
            "lat": float(lat),
            "ts": now,
            "uid": str(user_id),
        },
    )
    await db.commit()
    return int(result.rowcount or 0)


async def ensure_user_device_for_location(
    db: AsyncSession,
    *,
    user_id: UUID | str,
    lat: float,
    lng: float,
) -> UserDeviceModel:
    """Push token yokken bile konum kaydı için placeholder cihaz oluşturur."""
    uid = UUID(str(user_id))
    token = f"ExponentPushToken[local-loc-{str(uid)[:8]}]"
    return await upsert_user_device(
        db,
        user_id=uid,
        expo_push_token=token,
        lat=lat,
        lng=lng,
    )


def _dedupe_devices_by_user(devices: list[UserDeviceModel]) -> list[UserDeviceModel]:
    """Aynı kullanıcıya birden fazla cihaz satırı varsa en güncelini bırak (çoklu push engeli)."""
    best: dict[str, UserDeviceModel] = {}
    for device in devices:
        key = str(device.user_id)
        prev = best.get(key)
        if prev is None:
            best[key] = device
            continue
        prev_ts = getattr(prev, "updated_at", None)
        cur_ts = getattr(device, "updated_at", None)
        if cur_ts is not None and (prev_ts is None or cur_ts >= prev_ts):
            best[key] = device
    return list(best.values())


async def find_nearby_devices(
    db: AsyncSession,
    *,
    lat: float,
    lng: float,
    radius_m: float,
    exclude_user_id: UUID | str | None = None,
) -> list[UserDeviceModel]:
    """PostGIS ST_DWithin; yoksa haversine ile bellek içi süzme."""
    params: dict[str, Any] = {
        "lng": float(lng),
        "lat": float(lat),
        "radius": float(radius_m),
    }
    sql = """
        SELECT id FROM user_devices
        WHERE location IS NOT NULL
          AND ST_DWithin(
              location,
              ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
              :radius
          )
    """
    if exclude_user_id is not None:
        sql += " AND user_id <> CAST(:exclude AS uuid)"
        params["exclude"] = str(exclude_user_id)
    try:
        rows = await db.execute(text(sql), params)
        ids = [row[0] for row in rows.fetchall()]
        if not ids:
            return []
        result = await db.execute(
            select(UserDeviceModel).where(UserDeviceModel.id.in_(ids))
        )
        return _dedupe_devices_by_user(list(result.scalars().all()))
    except Exception:
        logger.exception("nearby_devices_postgis_failed_falling_back")
        await db.rollback()
        result = await db.execute(select(UserDeviceModel))
        devices = list(result.scalars().all())
        nearby: list[UserDeviceModel] = []
        exclude = str(exclude_user_id) if exclude_user_id else None
        for device in devices:
            if device.last_lat is None or device.last_lng is None:
                continue
            if exclude and str(device.user_id) == exclude:
                continue
            if (
                _haversine_m(lat, lng, float(device.last_lat), float(device.last_lng))
                <= radius_m
            ):
                nearby.append(device)
        return _dedupe_devices_by_user(nearby)


async def dispatch_witness_request(
    db: AsyncSession,
    *,
    event: ReportEventModel,
    report: ReportModel,
    app_state: Any | None = None,
) -> EmergencyAlertModel | None:
    """Geçerli ihbar sonrası 1 km içine 'Gördünüz mü?' tanık bildirimi."""
    # Aynı olay için ikinci tanık isteği gönderme.
    existing = await db.execute(
        select(EmergencyAlertModel).where(
            EmergencyAlertModel.event_id == event.id,
            EmergencyAlertModel.phase == "witness_request",
        )
    )
    if existing.scalars().first() is not None:
        return None

    category = (
        getattr(report, "normalized_category", None)
        or getattr(report, "category", None)
        or "general"
    )
    copy, method = await compose_emergency_alert_copy(
        phase="witness_request",
        category=str(category),
        description=str(report.description or ""),
        priority=str(report.priority or "urgent"),
    )

    exclude_user = getattr(report, "user_id", None)
    devices = await find_nearby_devices(
        db,
        lat=float(report.latitude),
        lng=float(report.longitude),
        radius_m=float(settings.alert_radius_meters),
        exclude_user_id=exclude_user,
    )

    alert = EmergencyAlertModel(
        uuid_id=str(uuid.uuid4()),
        event_id=event.id,
        report_uuid=str(report.uuid_id),
        latitude=float(report.latitude),
        longitude=float(report.longitude),
        phase="witness_request",
        title=copy.title,
        body=copy.body,
        llm_method=method,
        confirm_count=0,
        deny_count=0,
        push_target_count=len(devices),
        created_at=_now(),
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)

    messages = [
        build_expo_message(
            to=device.expo_push_token,
            title=copy.title,
            body=copy.body,
            data={
                "type": "witness_request",
                "event_id": str(event.uuid_id),
                "alert_id": alert.uuid_id,
                "lat": float(report.latitude),
                "lng": float(report.longitude),
            },
        )
        for device in devices
        if device.expo_push_token
    ]
    if messages:
        await send_expo_push_messages(messages)

    logger.info(
        "witness_request_dispatched",
        extra={
            "event_id": event.uuid_id,
            "targets": len(messages),
            "llm_method": method,
        },
    )
    return alert


async def dispatch_verified_community_alert(
    db: AsyncSession,
    *,
    event: ReportEventModel,
    report: ReportModel,
) -> EmergencyAlertModel | None:
    """Solo/normal doğrulanmış ihbarı 1 km içindeki kullanıcılara duyurur."""
    if str(getattr(event, "status", "")).lower() != "accepted":
        return None

    existing = await db.execute(
        select(EmergencyAlertModel).where(
            EmergencyAlertModel.event_id == event.id,
            EmergencyAlertModel.phase == "broadcast",
        )
    )
    if existing.scalars().first() is not None:
        return None

    category = (
        getattr(report, "normalized_category", None)
        or getattr(report, "category", None)
        or "general"
    )
    copy, method = await compose_emergency_alert_copy(
        phase="broadcast",
        category=str(category),
        description=str(report.description or "Doğrulanmış güvenlik ihbarı"),
        priority=str(getattr(report, "priority", None) or "normal"),
    )

    exclude_user = getattr(report, "user_id", None)
    devices = await find_nearby_devices(
        db,
        lat=float(report.latitude),
        lng=float(report.longitude),
        radius_m=float(settings.alert_radius_meters),
        exclude_user_id=exclude_user,
    )

    alert = EmergencyAlertModel(
        uuid_id=str(uuid.uuid4()),
        event_id=event.id,
        report_uuid=str(report.uuid_id),
        latitude=float(report.latitude),
        longitude=float(report.longitude),
        phase="broadcast",
        title=copy.title,
        body=copy.body,
        llm_method=method,
        confirm_count=0,
        deny_count=0,
        push_target_count=len(devices),
        created_at=_now(),
        broadcast_sent_at=_now(),
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)

    messages = [
        build_expo_message(
            to=device.expo_push_token,
            title=copy.title,
            body=copy.body,
            data={
                "type": "emergency_broadcast",
                "event_id": str(event.uuid_id),
                "alert_id": alert.uuid_id,
                "lat": float(report.latitude),
                "lng": float(report.longitude),
            },
        )
        for device in devices
        if device.expo_push_token
    ]
    if messages:
        await send_expo_push_messages(messages)

    logger.info(
        "verified_community_alert_dispatched",
        extra={
            "event_id": event.uuid_id,
            "targets": len(messages),
            "llm_method": method,
        },
    )
    return alert


async def respond_to_alert(
    db: AsyncSession,
    *,
    event_uuid: str,
    user_id: UUID | str,
    response: str,
    app_state: Any | None = None,
) -> dict[str, Any]:
    """Tanık yanıtı. İlk 'confirm' (Gördüm) sonrası herkese yayın + risk_live."""
    raw = str(response or "").strip().lower()
    if raw in {"confirm", "seen", "gördüm", "gordum"}:
        response_norm = "confirm"
    elif raw in {"unsure", "maybe", "emin_degil", "emin değilim"}:
        response_norm = "unsure"
    else:
        response_norm = "deny"
    uid = UUID(str(user_id))

    event_res = await db.execute(
        select(ReportEventModel).where(ReportEventModel.uuid_id == event_uuid)
    )
    event = event_res.scalars().first()
    if event is None:
        raise LookupError("event_not_found")

    # İhbarı yapan kişi kendi olayını onaylayamaz.
    reporter_res = await db.execute(
        select(ReportModel).where(
            ReportModel.event_id == event.id,
            ReportModel.user_id == uid,
        )
    )
    if reporter_res.scalars().first() is not None:
        raise PermissionError("reporter_cannot_confirm_own_alert")

    alert_res = await db.execute(
        select(EmergencyAlertModel)
        .where(
            EmergencyAlertModel.event_id == event.id,
            EmergencyAlertModel.phase == "witness_request",
        )
        .order_by(EmergencyAlertModel.created_at.asc())
    )
    alert = alert_res.scalars().first()
    if alert is None:
        raise LookupError("alert_not_found")

    existing = await db.execute(
        select(AlertConfirmationModel).where(
            AlertConfirmationModel.event_id == event.id,
            AlertConfirmationModel.user_id == uid,
        )
    )
    if existing.scalars().first() is not None:
        raise ValueError("already_responded")

    confirmation = AlertConfirmationModel(
        event_id=event.id,
        alert_id=alert.id,
        user_id=uid,
        response=response_norm,
        created_at=_now(),
    )
    db.add(confirmation)
    if response_norm == "confirm":
        alert.confirm_count = int(alert.confirm_count or 0) + 1
    elif response_norm == "deny":
        alert.deny_count = int(alert.deny_count or 0) + 1
    # unsure: sayaç artmaz; yanıt kaydı tekrar oylamayı engeller
    await db.commit()
    await db.refresh(alert)

    broadcast_alert = None
    live_risk_applied = False
    min_confirm = int(getattr(settings, "alert_min_confirmations", 1))
    if (
        response_norm == "confirm"
        and int(alert.confirm_count) >= min_confirm
        and alert.broadcast_sent_at is None
    ):
        broadcast_alert, live_risk_applied = await _dispatch_broadcast(
            db,
            event=event,
            witness_alert=alert,
            app_state=app_state,
        )

    return {
        "event_id": event.uuid_id,
        "alert_id": alert.uuid_id,
        "response": response_norm,
        "confirm_count": alert.confirm_count,
        "deny_count": alert.deny_count,
        "broadcast_sent": broadcast_alert is not None,
        "broadcast_alert_id": broadcast_alert.uuid_id if broadcast_alert else None,
        "live_risk_applied": live_risk_applied,
    }


async def _dispatch_broadcast(
    db: AsyncSession,
    *,
    event: ReportEventModel,
    witness_alert: EmergencyAlertModel,
    app_state: Any | None,
) -> tuple[EmergencyAlertModel, bool]:
    report_res = await db.execute(
        select(ReportModel)
        .where(ReportModel.event_id == event.id)
        .order_by(ReportModel.created_at.asc())
    )
    reports = list(report_res.scalars().all())
    seed = reports[0] if reports else None
    description = seed.description if seed else "Acil durum ihbarı"
    category = (
        (seed.normalized_category or seed.category)
        if seed
        else event.normalized_category
    )

    copy, method = await compose_emergency_alert_copy(
        phase="broadcast",
        category=str(category or "general"),
        description=str(description),
        priority="urgent",
    )

    # Olayı kabul et; canlı risk uygulaması endpoint/background'da yapılır
    # (main ile döngüsel import olmaması için).
    if event.status != "accepted":
        now = _now()
        event.status = "accepted"
        event.accepted_at = now
        from datetime import timedelta

        event.expires_at = now + timedelta(
            minutes=int(settings.report_event_expiry_minutes)
        )
        for report in reports:
            if getattr(report, "status", None) != "accepted":
                report.status = "accepted"
        await db.commit()
    needs_live_risk = seed is not None

    devices = await find_nearby_devices(
        db,
        lat=float(witness_alert.latitude),
        lng=float(witness_alert.longitude),
        radius_m=float(settings.alert_radius_meters),
        exclude_user_id=None,
    )

    # Jüri demosu işaretini yayında da koru (mesafe filtresi / istemci için).
    witness_method = str(getattr(witness_alert, "llm_method", "") or "")
    broadcast_method = "jury_demo" if witness_method == "jury_demo" else method
    if witness_method == "jury_demo":
        copy_title = "Magnificent Mile: doğrulanmış ihbar"
        copy_body = (
            '"Bir kadının çantası çalındı" ihbarı doğrulandı. '
            "Magnificent Mile civarında dikkatli olun."
        )
    else:
        copy_title = copy.title
        copy_body = copy.body

    broadcast = EmergencyAlertModel(
        uuid_id=str(uuid.uuid4()),
        event_id=event.id,
        report_uuid=witness_alert.report_uuid,
        latitude=float(witness_alert.latitude),
        longitude=float(witness_alert.longitude),
        phase="broadcast",
        title=copy_title,
        body=copy_body,
        llm_method=broadcast_method,
        confirm_count=int(witness_alert.confirm_count or 0),
        deny_count=int(witness_alert.deny_count or 0),
        push_target_count=len(devices),
        created_at=_now(),
        broadcast_sent_at=_now(),
    )
    db.add(broadcast)
    witness_alert.broadcast_sent_at = _now()
    await db.commit()
    await db.refresh(broadcast)

    messages = [
        build_expo_message(
            to=device.expo_push_token,
            title=copy_title,
            body=copy_body,
            data={
                "type": "emergency_broadcast",
                "event_id": str(event.uuid_id),
                "alert_id": broadcast.uuid_id,
                "lat": float(witness_alert.latitude),
                "lng": float(witness_alert.longitude),
            },
        )
        for device in devices
        if device.expo_push_token
    ]
    if messages:
        await send_expo_push_messages(messages)

    logger.info(
        "emergency_broadcast_dispatched",
        extra={"event_id": event.uuid_id, "targets": len(messages)},
    )
    return broadcast, needs_live_risk


# Magnificent Mile (N Michigan Ave) — jüri demosu sabit konumu
JURY_DEMO_LAT = 41.89474
JURY_DEMO_LNG = -87.62437


async def _reset_previous_jury_demos(db: AsyncSession) -> None:
    """Önceki jüri simülasyonlarını temizler; her basışta sıfırdan akış için."""
    from datetime import timedelta

    from sqlalchemy import delete

    cutoff = _now() - timedelta(days=2)
    old = await db.execute(
        select(EmergencyAlertModel).where(
            EmergencyAlertModel.llm_method == "jury_demo",
            EmergencyAlertModel.created_at >= cutoff,
        )
    )
    alerts = list(old.scalars().all())
    if not alerts:
        return
    event_ids = [a.event_id for a in alerts if a.event_id is not None]
    alert_ids = [a.id for a in alerts]
    if alert_ids:
        await db.execute(
            delete(AlertConfirmationModel).where(
                AlertConfirmationModel.alert_id.in_(alert_ids)
            )
        )
        await db.execute(
            delete(EmergencyAlertModel).where(EmergencyAlertModel.id.in_(alert_ids))
        )
    if event_ids:
        await db.execute(
            delete(ReportModel).where(ReportModel.event_id.in_(event_ids))
        )
        await db.execute(
            delete(ReportEventModel).where(ReportEventModel.id.in_(event_ids))
        )
    await db.commit()


async def start_jury_demo_witness_alert(
    db: AsyncSession,
    *,
    user_id: UUID | str,
    lat: float | None = None,
    lng: float | None = None,
) -> dict[str, Any]:
    """
    Jüri / demo: Magnificent Mile civarında tanık onayı akışı.
    Her çağrıda önceki demo temizlenir; yeni bildirim üretilir.
    """
    import secrets
    from datetime import timedelta

    import h3

    uid = UUID(str(user_id))
    # İhbar Magnificent Mile'da; kullanıcı cihaz konumu da oraya alınır (1 km filtre).
    demo_lat = JURY_DEMO_LAT + 0.0009  # ~100 m kuzey
    demo_lng = JURY_DEMO_LNG
    viewer_lat = JURY_DEMO_LAT
    viewer_lng = JURY_DEMO_LNG
    now = _now()

    await _reset_previous_jury_demos(db)
    await ensure_user_device_for_location(
        db, user_id=uid, lat=viewer_lat, lng=viewer_lng
    )

    if hasattr(h3, "latlng_to_cell"):
        h3_index = h3.latlng_to_cell(demo_lat, demo_lng, 9)
    else:
        h3_index = h3.geo_to_h3(demo_lat, demo_lng, 9)

    event_uuid = str(uuid.uuid4())
    report_uuid = str(uuid.uuid4())
    # user_id=None: kendi ihbarını onaylama yasağına takılmaz; FK/auth.users ihlali olmaz.

    event = ReportEventModel(
        uuid_id=event_uuid,
        h3_index=h3_index,
        h3_resolution=9,
        normalized_category="crime_related",
        priority="urgent",
        status="pending",
        unique_reporter_count=1,
        mean_similarity=1.0,
        mean_user_reliability=0.5,
        mean_model_confidence=0.85,
        validation_score=0.5,
        severity_weight=0.75,
        analysis_method="jury_demo",
        first_seen_at=now,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=6),
    )
    db.add(event)
    await db.flush()

    report = ReportModel(
        uuid_id=report_uuid,
        tracking_token=secrets.token_hex(16),
        user_id=None,
        latitude=demo_lat,
        longitude=demo_lng,
        description="Bir kadının çantası çalındı",
        category="crime",
        priority="urgent",
        status="pending",
        created_at=now,
        event_id=event.id,
        reporter_hash=secrets.token_hex(16),
        normalized_category="crime_related",
        severity_weight=0.75,
        model_confidence=0.85,
        analysis_method="jury_demo",
    )
    db.add(report)
    await db.flush()
    await db.execute(
        text(
            """
            UPDATE reports
            SET location = ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
            WHERE uuid_id = :uuid
            """
        ),
        {"lng": demo_lng, "lat": demo_lat, "uuid": report_uuid},
    )

    alert = EmergencyAlertModel(
        uuid_id=str(uuid.uuid4()),
        event_id=event.id,
        report_uuid=report_uuid,
        latitude=demo_lat,
        longitude=demo_lng,
        phase="witness_request",
        title="Magnificent Mile: doğrulama bekleyen ihbar",
        body='"Bir kadının çantası çalındı" — Magnificent Mile civarı. Bölgedeyseniz olayı gördünüz mü?',
        llm_method="jury_demo",
        confirm_count=0,
        deny_count=0,
        push_target_count=1,
        created_at=now,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)

    distance = _haversine_m(viewer_lat, viewer_lng, demo_lat, demo_lng)
    return {
        "alert_id": alert.uuid_id,
        "event_id": event_uuid,
        "phase": "witness_request",
        "title": alert.title,
        "body": alert.body,
        "latitude": demo_lat,
        "longitude": demo_lng,
        "distance_m": round(distance),
        "confirm_count": 0,
        "created_at": now.isoformat(),
        "llm_method": "jury_demo",
        "message": "Jüri simülasyonu Magnificent Mile'da sıfırdan başlatıldı.",
        "viewer_lat": viewer_lat,
        "viewer_lng": viewer_lng,
    }


async def list_nearby_pending_alerts_for_user(
    db: AsyncSession,
    *,
    user_id: UUID | str,
    lat: float | None,
    lng: float | None,
) -> list[dict[str, Any]]:
    """Uygulama içi yedek: push gelmese bile yakındaki tanık / yayın bildirimlerini listeler."""
    from datetime import timedelta

    uid = UUID(str(user_id))
    if lat is None or lng is None:
        device_res = await db.execute(
            select(UserDeviceModel)
            .where(UserDeviceModel.user_id == uid)
            .order_by(UserDeviceModel.updated_at.desc())
        )
        device = device_res.scalars().first()
        if device is None or device.last_lat is None or device.last_lng is None:
            return []
        lat = float(device.last_lat)
        lng = float(device.last_lng)

    radius = float(settings.alert_radius_meters)
    now = _now()
    broadcast_cutoff = now - timedelta(hours=6)

    alerts_res = await db.execute(
        select(EmergencyAlertModel)
        .where(
            EmergencyAlertModel.phase.in_(("witness_request", "broadcast")),
            EmergencyAlertModel.created_at >= broadcast_cutoff,
        )
        .order_by(EmergencyAlertModel.created_at.desc())
        .limit(80)
    )
    alerts = list(alerts_res.scalars().all())
    responded = await db.execute(
        select(AlertConfirmationModel.event_id).where(
            AlertConfirmationModel.user_id == uid
        )
    )
    responded_ids = {row[0] for row in responded.fetchall()}

    # Kullanıcının kendi ihbar ettiği olaylar (yalnızca tanık isteğinden hariç).
    own = await db.execute(
        select(ReportModel.event_id).where(ReportModel.user_id == uid)
    )
    own_event_ids = {row[0] for row in own.fetchall() if row[0] is not None}

    # Olay başına en fazla bir kayıt: yayın varsa tanık isteğini düşür.
    best_by_event: dict[int, EmergencyAlertModel] = {}
    for alert in alerts:
        phase = str(alert.phase)
        if phase == "witness_request":
            if alert.event_id in responded_ids or alert.event_id in own_event_ids:
                continue
            if alert.broadcast_sent_at is not None:
                continue
        prev = best_by_event.get(alert.event_id)
        if prev is None:
            best_by_event[alert.event_id] = alert
            continue
        # broadcast > witness_request
        if phase == "broadcast" and str(prev.phase) != "broadcast":
            best_by_event[alert.event_id] = alert

    pending: list[dict[str, Any]] = []
    for alert in best_by_event.values():
        phase = str(alert.phase)
        distance = _haversine_m(
            float(lat), float(lng), float(alert.latitude), float(alert.longitude)
        )
        is_jury = str(getattr(alert, "llm_method", "") or "") == "jury_demo"
        # Jüri demosu: emülatör GPS uzak olsa bile göster.
        if distance > radius and not is_jury:
            continue
        event_res = await db.execute(
            select(ReportEventModel).where(ReportEventModel.id == alert.event_id)
        )
        event = event_res.scalars().first()
        pending.append(
            {
                "alert_id": alert.uuid_id,
                "event_id": event.uuid_id if event else None,
                "phase": phase,
                "title": alert.title,
                "body": alert.body,
                "latitude": alert.latitude,
                "longitude": alert.longitude,
                "distance_m": round(distance),
                "confirm_count": alert.confirm_count,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
                "llm_method": alert.llm_method,
            }
        )
    # Tanık istekleri önce, sonra yayınlar.
    pending.sort(
        key=lambda item: (
            0 if item.get("phase") == "witness_request" else 1,
            item.get("distance_m") or 0,
        )
    )
    return pending
