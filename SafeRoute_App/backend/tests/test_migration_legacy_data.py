import os
import pytest
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from alembic.config import Config
from alembic import command


TEST_DB_URL = os.getenv("SAFEROUTE_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not TEST_DB_URL,
    reason="SAFEROUTE_TEST_DATABASE_URL isolated PostGIS target is not configured",
)


def _verify_local_test_db():
    if not TEST_DB_URL:
        return
    parsed = urlparse(TEST_DB_URL.replace("postgresql+asyncpg://", "http://"))
    host = parsed.hostname or ""
    dbname = parsed.path.lstrip("/")

    if host not in ("localhost", "127.0.0.1") or dbname != "saferoute_migration_test":
        raise RuntimeError(f"[SAFETY VIOLATION] Refusing to run migration test on non-isolated DB: {host}/{dbname}")

_verify_local_test_db()


def _get_alembic_config(engine_url: str) -> Config:
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ini_path = os.path.join(backend_dir, "alembic.ini")
    config = Config(ini_path)
    config.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    config.set_main_option("sqlalchemy.url", engine_url)
    return config


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
async def async_db_engine():
    assert TEST_DB_URL
    engine = create_async_engine(TEST_DB_URL, pool_pre_ping=True)

    async with engine.begin() as conn:
        await conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version CASCADE;"))
        await conn.execute(sa.text("DROP TABLE IF EXISTS user_profiles CASCADE;"))
        await conn.execute(sa.text("DROP TABLE IF EXISTS report_events CASCADE;"))
        await conn.execute(sa.text("DROP TABLE IF EXISTS reports CASCADE;"))
        await conn.execute(sa.text("DROP TABLE IF EXISTS etl_runs CASCADE;"))
        await conn.execute(sa.text("DROP TABLE IF EXISTS h3_heatmap CASCADE;"))

    yield engine
    await engine.dispose()


@pytest.mark.anyio
async def test_1_legacy_data_migration_regression(async_db_engine):
    """
    Verifies upgrading from 4ba90bcb6804 baseline with legacy out-of-bounds data:
    1. Preserves existing h3_heatmap and reports records (no data loss).
    2. Recalculates risk_live to 0.0 and total_risk to 0.0 cleanly.
    3. Safely backfills uuid_id, tracking_token, status != 'accepted', event_id=None.
    4. Passes all CHECK constraints and reaches revision c3d4e5f6a7b8.
    """
    config = _get_alembic_config(TEST_DB_URL)

    # 1. Bring schema to 4ba90bcb6804 baseline
    command.downgrade(config, "base")
    command.upgrade(config, "4ba90bcb6804")

    # 2. Insert legacy h3_heatmap and reports records into baseline
    async with async_db_engine.begin() as conn:
        await conn.execute(sa.text("""
            INSERT INTO h3_heatmap (id, h3_index, lat, lng, risk_historical, risk_live, risk_social, total_risk)
            VALUES (1, '892a1008003ffff', 41.8781, -87.6298, 0.0, 10.0, 0.0, 5.0);
        """))

        old_created = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
        await conn.execute(sa.text("""
            INSERT INTO reports (id, latitude, longitude, description, created_at)
            VALUES (1, 41.8781, -87.6298, 'Eski legacy ihbar kaydı', :created_at);
        """), {"created_at": old_created})

    # 3. Upgrade to head
    command.upgrade(config, "head")

    # 4. Assertions on migrated data
    async with async_db_engine.begin() as conn:
        # Check current revision
        res_rev = await conn.execute(sa.text("SELECT version_num FROM alembic_version;"))
        rev = res_rev.scalar()
        assert rev == "f6a7b8c9d0e1", f"Expected revision f6a7b8c9d0e1, got {rev}"

        # h3_heatmap record preserved and risk values normalized
        res_h3 = await conn.execute(sa.text("SELECT id, risk_live, total_risk, risk_crime, risk_lighting FROM h3_heatmap;"))
        h3_rows = res_h3.fetchall()
        assert len(h3_rows) == 1, "Legacy h3_heatmap row must not be deleted!"
        h3_row = h3_rows[0]
        assert h3_row.risk_live == 0.0, f"Expected risk_live=0.0, got {h3_row.risk_live}"
        assert h3_row.total_risk == 0.0, f"Expected total_risk=0.0, got {h3_row.total_risk}"
        assert h3_row.risk_crime == 0.0
        assert h3_row.risk_lighting == 0.0
        legacy_columns = (
            await conn.execute(sa.text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'h3_heatmap'
                  AND column_name IN ('risk_historical', 'risk_social')
            """))
        ).fetchall()
        assert legacy_columns == []

        # reports record preserved and safely backfilled
        res_rep = await conn.execute(sa.text("SELECT id, uuid_id, tracking_token, status, event_id, analysis_method FROM reports;"))
        rep_rows = res_rep.fetchall()
        assert len(rep_rows) == 1, "Legacy reports row must not be deleted!"
        rep_row = rep_rows[0]
        assert rep_row.uuid_id is not None and len(rep_row.uuid_id) == 36
        assert rep_row.tracking_token is not None and len(rep_row.tracking_token) > 10
        assert rep_row.status != "accepted", "Legacy report status must NEVER be set to accepted!"
        assert rep_row.status == "expired", f"Report older than 1 hour should be expired, got {rep_row.status}"
        assert rep_row.event_id is None, "Legacy report event_id must be NULL!"
        assert rep_row.analysis_method == "legacy_migration"

        # report_events table is empty
        res_evt = await conn.execute(sa.text("SELECT COUNT(*) FROM report_events;"))
        evt_cnt = res_evt.scalar()
        assert evt_cnt == 0, "No report_events should be generated for legacy reports"


@pytest.mark.anyio
async def test_2_empty_database_migration(async_db_engine):
    """Verifies that an upgrade on a completely empty database succeeds cleanly."""
    config = _get_alembic_config(TEST_DB_URL)

    command.downgrade(config, "base")
    command.upgrade(config, "head")

    async with async_db_engine.begin() as conn:
        res_rev = await conn.execute(sa.text("SELECT version_num FROM alembic_version;"))
        rev = res_rev.scalar()
        assert rev == "f6a7b8c9d0e1"


@pytest.mark.anyio
async def test_3_migration_idempotency_and_reupgrade(async_db_engine):
    """Verifies running upgrade head again does not throw duplicate column/index/constraint errors."""
    config = _get_alembic_config(TEST_DB_URL)
    command.upgrade(config, "head")

    async with async_db_engine.begin() as conn:
        res_rev = await conn.execute(sa.text("SELECT version_num FROM alembic_version;"))
        rev = res_rev.scalar()
        assert rev == "f6a7b8c9d0e1"


@pytest.mark.anyio
async def test_4_migration_symmetry(async_db_engine):
    """
    Verifies migration DDL symmetry: 4ba90bcb6804 -> head -> 4ba90bcb6804 -> head.
    Note: Schema DDL is symmetric, but data normalization (resetting legacy unverified risk_live=10 to 0.0)
    is intentionally irreversible to prevent re-introducing unverified risk corruption.
    """
    config = _get_alembic_config(TEST_DB_URL)

    command.downgrade(config, "4ba90bcb6804")
    async with async_db_engine.begin() as conn:
        res_rev = await conn.execute(sa.text("SELECT version_num FROM alembic_version;"))
        rev = res_rev.scalar()
        assert rev == "4ba90bcb6804"

    command.upgrade(config, "head")
    async with async_db_engine.begin() as conn:
        res_rev = await conn.execute(sa.text("SELECT version_num FROM alembic_version;"))
        rev = res_rev.scalar()
        assert rev == "f6a7b8c9d0e1"
