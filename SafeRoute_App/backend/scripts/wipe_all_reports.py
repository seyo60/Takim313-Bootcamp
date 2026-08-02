"""Tüm ihbar / olay / acil bildirim kayıtlarını siler; risk_live sıfırlar."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings


async def main() -> None:
    engine = create_async_engine(settings.database_url)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db:
        steps = [
            "DELETE FROM alert_confirmations",
            "DELETE FROM emergency_alerts",
            "UPDATE reports SET event_id = NULL",
            "DELETE FROM reports",
            "DELETE FROM report_events",
            """
            UPDATE h3_heatmap SET
              risk_live = 0,
              total_risk = LEAST(
                1.0,
                GREATEST(
                  0.0,
                  0.60 * COALESCE(risk_crime, 0)
                  + 0.25 * COALESCE(risk_lighting, 0)
                )
              )
            WHERE COALESCE(risk_live, 0) > 0
            """,
        ]
        for sql in steps:
            result = await db.execute(text(sql))
            print("OK", " ".join(sql.split()[:3]), "rowcount=", result.rowcount)
        await db.commit()

        for table in (
            "reports",
            "report_events",
            "emergency_alerts",
            "alert_confirmations",
        ):
            count = (
                await db.execute(text(f"SELECT COUNT(*) FROM {table}"))
            ).scalar()
            print("count", table, count)

        live = (
            await db.execute(
                text(
                    "SELECT COUNT(*) FROM h3_heatmap WHERE COALESCE(risk_live, 0) > 0"
                )
            )
        ).scalar()
        print("h3_heatmap risk_live>0", live)

    await engine.dispose()
    print("DONE")


if __name__ == "__main__":
    asyncio.run(main())
