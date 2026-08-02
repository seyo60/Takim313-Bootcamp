"""Dearborn Park civarına anlık tanık (onay) bildirimi ekler — test3 görmeli."""

from __future__ import annotations

import asyncio
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import h3
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from models import EmergencyAlertModel, ReportEventModel, ReportModel, UserDeviceModel

_engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

# Dearborn Park / Printer's Row (Chicago South Loop)
LAT = 41.8715
LNG = -87.6289
TITLE = "Dearborn Park: acil durum bildirildi"
BODY = "Dearborn Park civarında acil bir durum bildirildi. Gördünüz mü? Uygulamadan onaylayın veya reddedin."


def _h3_cell(lat: float, lng: float, res: int) -> str:
    if hasattr(h3, "latlng_to_cell"):
        return h3.latlng_to_cell(lat, lng, res)
    return h3.geo_to_h3(lat, lng, res)


async def main() -> None:
    now = datetime.now(timezone.utc)
    h3_index = _h3_cell(LAT, LNG, 9)
    event_uuid = str(uuid.uuid4())
    report_uuid = str(uuid.uuid4())
    alert_uuid = str(uuid.uuid4())

    async with AsyncSessionLocal() as db:
        emails = await db.execute(
            text(
                """
                SELECT id::text, split_part(email, '@', 1)
                FROM auth.users
                WHERE email LIKE '%@saferoute.local'
                """
            )
        )
        by_local = {str(local): uid for uid, local in emails.fetchall()}
        if "test2" not in by_local:
            raise SystemExit("test2@saferoute.local bulunamadı")
        reporter_id = uuid.UUID(by_local["test2"])
        witness_ids = [uid for key, uid in by_local.items() if key != "test2"]

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
            mean_model_confidence=0.7,
            validation_score=0.4,
            severity_weight=0.7,
            analysis_method="seed_dearborn_park",
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
            user_id=reporter_id,
            latitude=LAT,
            longitude=LNG,
            description="TEST: Dearborn Park civarında acil durum (manuel seed)",
            category="crime",
            priority="urgent",
            status="pending",
            created_at=now,
            event_id=event.id,
            reporter_hash=secrets.token_hex(16),
            normalized_category="crime_related",
            severity_weight=0.7,
            model_confidence=0.7,
            analysis_method="seed_dearborn_park",
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
            {"lng": LNG, "lat": LAT, "uuid": report_uuid},
        )

        alert = EmergencyAlertModel(
            uuid_id=alert_uuid,
            event_id=event.id,
            report_uuid=report_uuid,
            latitude=LAT,
            longitude=LNG,
            phase="witness_request",
            title=TITLE,
            body=BODY,
            llm_method="seed_dearborn",
            confirm_count=0,
            deny_count=0,
            push_target_count=0,
            created_at=now,
        )
        db.add(alert)

        devices_updated = 0
        for uid in witness_ids:
            token = f"ExponentPushToken[local-test-{uid[:8]}]"
            existing = await db.execute(
                select(UserDeviceModel).where(UserDeviceModel.user_id == uuid.UUID(uid))
            )
            device = existing.scalars().first()
            if device is None:
                db.add(
                    UserDeviceModel(
                        user_id=uuid.UUID(uid),
                        expo_push_token=token,
                        last_lat=LAT,
                        last_lng=LNG,
                        created_at=now,
                        updated_at=now,
                    )
                )
                await db.flush()
            else:
                device.last_lat = LAT
                device.last_lng = LNG
                device.updated_at = now

            await db.execute(
                text(
                    """
                    UPDATE user_devices
                    SET location = ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                        last_lat = :lat,
                        last_lng = :lng,
                        updated_at = :ts
                    WHERE user_id = CAST(:uid AS uuid)
                    """
                ),
                {"lng": LNG, "lat": LAT, "ts": now, "uid": uid},
            )
            devices_updated += 1

        alert.push_target_count = devices_updated
        await db.commit()

        print("OK Dearborn Park witness alert seeded")
        print(f"event_id={event_uuid}")
        print(f"alert_id={alert_uuid}")
        print(f"lat={LAT} lng={LNG}")
        print(f"witness_devices={devices_updated}")
        print("test1 veya test3 ile giris yap -> onay modal / bildirim gelmeli")


if __name__ == "__main__":
    async def _run() -> None:
        try:
            await main()
        finally:
            await _engine.dispose()

    asyncio.run(_run())
