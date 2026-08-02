"""test1 için pending alert listesini sunucu fonksiyonuyla simüle eder."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from services.emergency_alert_service import list_nearby_pending_alerts_for_user

_engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        row = await db.execute(
            text(
                "SELECT id::text FROM auth.users WHERE email = 'test1@saferoute.local' LIMIT 1"
            )
        )
        uid = row.scalar()
        if not uid:
            raise SystemExit("test1 missing")
        items = await list_nearby_pending_alerts_for_user(
            db, user_id=uid, lat=41.8826, lng=-87.6226
        )
        print(f"test1_pending_count={len(items)}")
        for item in items:
            print(
                f"  phase={item.get('phase')} dist={item.get('distance_m')} "
                f"title={item.get('title')[:48]!r} alert={str(item.get('alert_id'))[:8]}"
            )
    await _engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
