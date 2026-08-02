"""Şema uygunluk kontrolü — PII yazdırmaz."""

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


async def main() -> None:
    async with AsyncSessionLocal() as db:
        for table in (
            "user_devices",
            "emergency_alerts",
            "alert_confirmations",
            "report_events",
            "reports",
        ):
            exists = await db.execute(
                text("SELECT to_regclass(:name)"),
                {"name": f"public.{table}"},
            )
            if not exists.scalar():
                print(f"{table}: MISSING")
                continue
            count = await db.execute(text(f"SELECT COUNT(*) FROM {table}"))
            print(f"{table}: ok count={count.scalar()}")

        ver = await db.execute(text("SELECT version_num FROM alembic_version"))
        print(f"alembic: {ver.scalar()}")

        cols = await db.execute(
            text(
                """
                SELECT column_name, udt_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'user_devices'
                ORDER BY ordinal_position
                """
            )
        )
        print("user_devices cols:", [(r[0], r[1]) for r in cols.fetchall()])

        alert_cols = await db.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'emergency_alerts'
                ORDER BY ordinal_position
                """
            )
        )
        print("emergency_alerts cols:", [r[0] for r in alert_cols.fetchall()])

        with_loc = await db.execute(
            text("SELECT COUNT(*) FROM user_devices WHERE location IS NOT NULL")
        )
        print(f"devices_with_location: {with_loc.scalar()}")

        test_accounts = await db.execute(
            text(
                "SELECT COUNT(*) FROM auth.users WHERE email LIKE '%@saferoute.local'"
            )
        )
        print(f"test_accounts: {test_accounts.scalar()}")

    await _engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
