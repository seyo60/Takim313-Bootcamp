"""
Test acil tanık bildirimi oluşturur (Millennium Park civarı).

PII yazdırmaz; event_id / alert_id verir.
"""

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
from models import (
    EmergencyAlertModel,
    ReportEventModel,
    ReportModel,
    UserDeviceModel,
)

_engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

LAT = 41.8826
LNG = -87.6226
TITLE = "Yakında acil durum bildirildi"
BODY = "Bu noktada acil bir durum bildirildi. Gördünüz mü? Uygulamadan yanıtlayın."


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
        users = await db.execute(
            text(
                """
                SELECT id::text
                FROM auth.users
                WHERE email LIKE '%@saferoute.local'
                ORDER BY email ASC
                LIMIT 5
                """
            )
        )
        user_ids = [row[0] for row in users.fetchall()]
        if not user_ids:
            raise SystemExit("No @saferoute.local test accounts found")
        # test2 reporter olsun; test1/test3 tanık olarak alsın (email sırası).
        by_local = {}
        emails = await db.execute(
            text(
                """
                SELECT id::text, split_part(email, '@', 1)
                FROM auth.users
                WHERE email LIKE '%@saferoute.local'
                """
            )
        )
        for uid, local in emails.fetchall():
            by_local[str(local)] = uid
        reporter_key = "test2" if "test2" in by_local else user_ids[0]
        reporter_id = uuid.UUID(
            by_local.get(reporter_key, user_ids[0])
            if isinstance(reporter_key, str) and reporter_key in by_local
            else user_ids[0]
        )
        # Tanıklar: reporter hariç tüm test hesapları (özellikle test1).
        witness_ids = [uid for uid in user_ids if uid != str(reporter_id)]
        if not witness_ids:
            witness_ids = user_ids
        print(f"reporter_local={reporter_key} witnesses={len(witness_ids)}")

        event = ReportEventModel(
            uuid_id=event_uuid,
            h3_index=h3_index,
            h3_resolution=9,
            normalized_category="general_safety",
            priority="urgent",
            status="pending",
            unique_reporter_count=1,
            mean_similarity=1.0,
            mean_user_reliability=0.5,
            mean_model_confidence=0.7,
            validation_score=0.4,
            severity_weight=0.7,
            analysis_method="seed_test_emergency_alert",
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
            description="TEST: Millennium Park civarında acil durum (otomasyon)",
            category="crime",
            priority="urgent",
            status="pending",
            created_at=now,
            event_id=event.id,
            reporter_hash=secrets.token_hex(16),
            normalized_category="crime_related",
            severity_weight=0.7,
            model_confidence=0.7,
            analysis_method="seed_test_emergency_alert",
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
            llm_method="seed_test",
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

        print("OK seed emergency alert")
        print(f"event_id={event_uuid}")
        print(f"alert_id={alert_uuid}")
        print(f"lat={LAT} lng={LNG}")
        print(f"test_users_located={devices_updated}")
        print(
            "test2/test3 ile giris -> konum Loop civari -> WitnessAlert / pending poll"
        )

    await _engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
