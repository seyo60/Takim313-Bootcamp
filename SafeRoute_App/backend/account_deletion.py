"""Idempotent account-deletion worker with dry-run as the default.

Running this module never writes unless both ``--execute`` and
``ACCOUNT_DELETION_EXECUTION_ENABLED=true`` are present. Operators must take a
database backup and obtain approval before enabling it against production.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from errors import ConfigurationError, PersistenceError
from main import AsyncSessionLocal
from models import ReportModel, UserProfileModel


async def _delete_supabase_identity(user_id: str) -> None:
    if not settings.supabase_url.startswith("https://"):
        raise ConfigurationError("Supabase URL is required for account deletion")
    if not settings.supabase_service_role_key:
        raise ConfigurationError("Supabase service role key is required for account deletion")
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}"
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=3.0)) as client:
        response = await client.delete(url, headers=headers)
    if response.status_code not in {200, 204, 404}:
        response.raise_for_status()


async def _anonymize_and_remove_profile(db: AsyncSession, user_id) -> None:
    await db.execute(
        update(ReportModel)
        .where(ReportModel.user_id == user_id)
        .values(user_id=None, reporter_hash=None, ip_address=None)
    )
    await db.execute(delete(UserProfileModel).where(UserProfileModel.user_id == user_id))


async def process_due_account_deletions(*, execute: bool, limit: int = 50) -> dict[str, int | bool]:
    if execute and not settings.account_deletion_execution_enabled:
        raise ConfigurationError("Account deletion execution is not enabled")
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.account_deletion_grace_days)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserProfileModel)
            .where(
                UserProfileModel.deletion_requested_at.is_not(None),
                UserProfileModel.deletion_requested_at <= cutoff,
            )
            .order_by(UserProfileModel.deletion_requested_at)
            .limit(max(1, min(limit, 500)))
        )
        due = list(result.scalars().all())
        if not execute:
            return {"dry_run": True, "due": len(due), "processed": 0, "failed": 0}

        processed = 0
        failed = 0
        for profile in due:
            try:
                # A 404 is success, which makes a retry after a partial failure safe.
                await _delete_supabase_identity(str(profile.user_id))
                await _anonymize_and_remove_profile(db, profile.user_id)
                await db.commit()
                processed += 1
            except (httpx.HTTPError, ConfigurationError, PersistenceError, Exception):
                await db.rollback()
                failed += 1
        return {"dry_run": False, "due": len(due), "processed": processed, "failed": failed}


def main() -> int:
    parser = argparse.ArgumentParser(description="Process due SafeRoute account deletions")
    parser.add_argument("--execute", action="store_true", help="Perform destructive deletion; dry-run is default")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    result = asyncio.run(process_due_account_deletions(execute=args.execute, limit=args.limit))
    print(result)
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
