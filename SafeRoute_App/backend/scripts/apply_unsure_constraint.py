import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from config import settings


async def main() -> None:
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "ALTER TABLE alert_confirmations "
                "DROP CONSTRAINT IF EXISTS chk_alert_confirmations_response"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE alert_confirmations "
                "ADD CONSTRAINT chk_alert_confirmations_response "
                "CHECK (response IN ('confirm', 'deny', 'unsure'))"
            )
        )
    await engine.dispose()
    print("constraint ok")


if __name__ == "__main__":
    asyncio.run(main())
