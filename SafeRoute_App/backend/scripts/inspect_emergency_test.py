"""Son acil bildirim durumunu PII yazmadan özetler."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings

_engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

TARGET_EVENT = "567cfb42-e7f7-4b44-9026-5024e2cb62dc"


async def main() -> None:
    async with AsyncSessionLocal() as db:
        ev = await db.execute(
            text(
                """
                SELECT e.id, e.uuid_id, e.status, e.priority,
                       (SELECT COUNT(*) FROM reports r WHERE r.event_id = e.id) AS reports
                FROM report_events e
                WHERE e.uuid_id = :eid
                """
            ),
            {"eid": TARGET_EVENT},
        )
        print("event:", ev.fetchone())

        alerts = await db.execute(
            text(
                """
                SELECT a.uuid_id, a.phase, a.confirm_count, a.deny_count,
                       a.push_target_count, a.broadcast_sent_at IS NOT NULL AS broadcasted,
                       a.title
                FROM emergency_alerts a
                JOIN report_events e ON e.id = a.event_id
                WHERE e.uuid_id = :eid
                ORDER BY a.id
                """
            ),
            {"eid": TARGET_EVENT},
        )
        print("alerts:")
        for row in alerts.fetchall():
            print(" ", row)

        conf = await db.execute(
            text(
                """
                SELECT c.response,
                       CASE
                         WHEN u.email LIKE '%@saferoute.local' THEN split_part(u.email, '@', 1)
                         ELSE 'other'
                       END AS who
                FROM alert_confirmations c
                JOIN report_events e ON e.id = c.event_id
                LEFT JOIN auth.users u ON u.id = c.user_id
                WHERE e.uuid_id = :eid
                """
            ),
            {"eid": TARGET_EVENT},
        )
        print("confirmations:", conf.fetchall())

        # Reporter email local-part only
        rep = await db.execute(
            text(
                """
                SELECT split_part(u.email, '@', 1)
                FROM reports r
                JOIN report_events e ON e.id = r.event_id
                LEFT JOIN auth.users u ON u.id = r.user_id
                WHERE e.uuid_id = :eid
                """
            ),
            {"eid": TARGET_EVENT},
        )
        print("reporter_accounts:", [r[0] for r in rep.fetchall()])

        # Devices near Millennium Park (haversine approx via lat/lng)
        devices = await db.execute(
            text(
                """
                SELECT split_part(u.email, '@', 1) AS who,
                       d.last_lat, d.last_lng,
                       d.location IS NOT NULL AS has_geo,
                       left(d.expo_push_token, 28) AS token_prefix,
                       CASE
                         WHEN d.last_lat IS NULL THEN NULL
                         ELSE round(
                           (6371000 * 2 * asin(sqrt(
                             power(sin(radians((d.last_lat - 41.8826)/2)), 2) +
                             cos(radians(41.8826)) * cos(radians(d.last_lat)) *
                             power(sin(radians((d.last_lng - -87.6226)/2)), 2)
                           )))::numeric, 0
                         )
                       END AS dist_m
                FROM user_devices d
                LEFT JOIN auth.users u ON u.id = d.user_id
                WHERE u.email LIKE '%@saferoute.local'
                ORDER BY who
                """
            )
        )
        print("test_devices:")
        for row in devices.fetchall():
            print(" ", row)

        # All recent alerts
        recent = await db.execute(
            text(
                """
                SELECT a.phase, a.confirm_count, a.push_target_count,
                       a.broadcast_sent_at IS NOT NULL, left(a.uuid_id, 8)
                FROM emergency_alerts a
                ORDER BY a.id DESC
                LIMIT 8
                """
            )
        )
        print("recent_alerts:", recent.fetchall())

    await _engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
