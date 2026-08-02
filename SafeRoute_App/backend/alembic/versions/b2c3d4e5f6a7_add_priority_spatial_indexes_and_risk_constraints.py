"""add priority, spatial indexes, and risk check constraints

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-28 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Add priority column and CHECK constraints to reports and report_events
    reports_cols = [c['name'] for c in inspector.get_columns('reports')]
    if 'priority' not in reports_cols:
        op.add_column('reports', sa.Column('priority', sa.String(length=20), server_default='normal', nullable=False))
        op.create_check_constraint('chk_reports_priority', 'reports', "priority IN ('normal', 'urgent')")

    existing_tables = inspector.get_table_names()
    if 'report_events' in existing_tables:
        events_cols = [c['name'] for c in inspector.get_columns('report_events')]
        if 'priority' not in events_cols:
            op.add_column('report_events', sa.Column('priority', sa.String(length=20), server_default='normal', nullable=False))
            op.create_check_constraint('chk_report_events_priority', 'report_events', "priority IN ('normal', 'urgent')")

    # 2. PostGIS GIST spatial indexes (idempotent)
    op.execute("CREATE INDEX IF NOT EXISTS idx_h3_heatmap_location ON h3_heatmap USING gist (location);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_reports_location ON reports USING gist (location);")

    # 3. CORRUPTION GUARD & PRECONDITION CHECK (Mandates 5, 6, 7)
    # 3a. Check for corrupted values (< 0.0 or > 100.0)
    corrupted = bind.execute(sa.text("""
        SELECT id, h3_index, risk_live, total_risk, risk_crime, risk_lighting
        FROM h3_heatmap
        WHERE (risk_live IS NOT NULL AND (risk_live < 0.0 OR risk_live > 100.0))
           OR (total_risk IS NOT NULL AND (total_risk < 0.0 OR total_risk > 100.0))
           OR (risk_crime IS NOT NULL AND (risk_crime < 0.0 OR risk_crime > 100.0))
           OR (risk_lighting IS NOT NULL AND (risk_lighting < 0.0 OR risk_lighting > 100.0));
    """)).fetchall()

    if corrupted:
        raise ValueError(f"[Corruption Guard] Out-of-bounds (<0.0 or >100.0) risk values detected in h3_heatmap: {corrupted}")

    # 3b. Check report_events precondition
    if 'report_events' in existing_tables:
        evt_count = bind.execute(sa.text("SELECT COUNT(*) FROM report_events")).scalar() or 0
        if evt_count > 0:
            raise RuntimeError(f"[Precondition Error] Unexpected records found in report_events table during migration (count={evt_count}). Migration expects empty report_events for legacy risk cleanup.")

    # 3c. Clean legacy risk_live and recalculate total_risk using canonical formula before adding CHECK constraints
    # Formula: total_risk = 0.65 * risk_crime + 0.20 * risk_lighting + 0.15 * risk_live
    # Legacy risk_live (unverified) is reset to 0.0.
    bind.execute(sa.text("""
        UPDATE h3_heatmap
        SET risk_live = 0.0,
            total_risk = LEAST(1.0, GREATEST(0.0, 
                0.65 * COALESCE(risk_crime, 0.0) 
              + 0.20 * COALESCE(risk_lighting, 0.0) 
              + 0.15 * 0.0
            ));
    """))

    # 4. CHECK constraints on h3_heatmap for canonical 0.0 - 1.0 risk range
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_h3_heatmap_risk_crime') THEN
                ALTER TABLE h3_heatmap ADD CONSTRAINT chk_h3_heatmap_risk_crime CHECK (risk_crime >= 0 AND risk_crime <= 1);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_h3_heatmap_risk_lighting') THEN
                ALTER TABLE h3_heatmap ADD CONSTRAINT chk_h3_heatmap_risk_lighting CHECK (risk_lighting >= 0 AND risk_lighting <= 1);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_h3_heatmap_risk_live') THEN
                ALTER TABLE h3_heatmap ADD CONSTRAINT chk_h3_heatmap_risk_live CHECK (risk_live >= 0 AND risk_live <= 1);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_h3_heatmap_total_risk') THEN
                ALTER TABLE h3_heatmap ADD CONSTRAINT chk_h3_heatmap_total_risk CHECK (total_risk >= 0 AND total_risk <= 1);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Note: Downgrade provides DDL schema symmetry by removing constraints and indexes.
    # However, data normalization (resetting legacy unverified risk_live=10 to 0.0) is
    # irreversible by design and does not attempt to guess or recreate legacy unverified values.

    # 1. Drop CHECK constraints on h3_heatmap
    op.execute("ALTER TABLE h3_heatmap DROP CONSTRAINT IF EXISTS chk_h3_heatmap_total_risk;")
    op.execute("ALTER TABLE h3_heatmap DROP CONSTRAINT IF EXISTS chk_h3_heatmap_risk_live;")
    op.execute("ALTER TABLE h3_heatmap DROP CONSTRAINT IF EXISTS chk_h3_heatmap_risk_lighting;")
    op.execute("ALTER TABLE h3_heatmap DROP CONSTRAINT IF EXISTS chk_h3_heatmap_risk_crime;")

    # 2. Drop spatial indexes safely
    op.execute("DROP INDEX IF EXISTS idx_reports_location;")
    op.execute("DROP INDEX IF EXISTS idx_h3_heatmap_location;")

    # 3. Drop priority columns and constraints
    existing_tables = inspector.get_table_names()
    if 'report_events' in existing_tables:
        events_cols = [c['name'] for c in inspector.get_columns('report_events')]
        if 'priority' in events_cols:
            try:
                op.drop_constraint('chk_report_events_priority', 'report_events', type_='check')
            except Exception:
                pass
            op.drop_column('report_events', 'priority')

    reports_cols = [c['name'] for c in inspector.get_columns('reports')]
    if 'priority' in reports_cols:
        try:
            op.drop_constraint('chk_reports_priority', 'reports', type_='check')
        except Exception:
            pass
        op.drop_column('reports', 'priority')

