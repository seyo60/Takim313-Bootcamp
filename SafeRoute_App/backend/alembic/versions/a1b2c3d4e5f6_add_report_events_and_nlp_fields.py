"""add report events and nlp fields

Revision ID: a1b2c3d4e5f6
Revises: 9d0e1f2a3b4c
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '9d0e1f2a3b4c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # Precondition check: If report_events unexpectedly exists in DB, verify or stop
    if 'report_events' in existing_tables:
        print("[Alembic Precondition] Table 'report_events' already exists.")
    else:
        # 1. Create report_events table with strict constraints
        op.create_table(
            'report_events',
            sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
            sa.Column('uuid_id', sa.String(length=36), nullable=False, unique=True),
            sa.Column('h3_index', sa.String(length=15), nullable=False),
            sa.Column('normalized_category', sa.String(length=50), nullable=False, server_default='general_safety'),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
            sa.Column('unique_reporter_count', sa.Integer(), nullable=True, server_default='1'),
            sa.Column('mean_similarity', sa.Float(), nullable=True, server_default='1.0'),
            sa.Column('mean_user_reliability', sa.Float(), nullable=True, server_default='0.5'),
            sa.Column('mean_model_confidence', sa.Float(), nullable=True, server_default='0.5'),
            sa.Column('validation_score', sa.Float(), nullable=True, server_default='0.0'),
            sa.Column('severity_weight', sa.Float(), nullable=True, server_default='0.35'),
            sa.Column('analysis_method', sa.String(length=50), nullable=True, server_default='deterministic_fallback'),
            sa.Column('first_seen_at', sa.DateTime(), nullable=True),
            sa.Column('last_seen_at', sa.DateTime(), nullable=True),
            sa.Column('accepted_at', sa.DateTime(), nullable=True),
            sa.Column('expires_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.CheckConstraint("status IN ('pending', 'processing', 'accepted', 'rejected', 'expired')", name="chk_report_events_status"),
            sa.CheckConstraint("mean_similarity >= 0.0 AND mean_similarity <= 1.0", name="chk_report_events_mean_similarity"),
            sa.CheckConstraint("mean_user_reliability >= 0.0 AND mean_user_reliability <= 1.0", name="chk_report_events_mean_user_reliability"),
            sa.CheckConstraint("mean_model_confidence >= 0.0 AND mean_model_confidence <= 1.0", name="chk_report_events_mean_model_confidence"),
            sa.CheckConstraint("validation_score >= 0.0 AND validation_score <= 1.0", name="chk_report_events_validation_score"),
            sa.CheckConstraint("severity_weight >= 0.0 AND severity_weight <= 1.0", name="chk_report_events_severity_weight")
        )

        op.create_index('ix_report_events_id', 'report_events', ['id'])
        op.create_index('ix_report_events_uuid_id', 'report_events', ['uuid_id'], unique=True)
        op.create_index('ix_report_events_h3_index', 'report_events', ['h3_index'])
        op.create_index('ix_report_events_status', 'report_events', ['status'])
        op.create_index('ix_report_events_first_seen_at', 'report_events', ['first_seen_at'])
        op.create_index('ix_report_events_last_seen_at', 'report_events', ['last_seen_at'])
        op.create_index('ix_report_events_expires_at', 'report_events', ['expires_at'])
        op.create_index('idx_report_events_h3_status_last_seen', 'report_events', ['h3_index', 'status', 'last_seen_at'])

    # 2. Add new columns to reports table as nullable first
    reports_cols = [c['name'] for c in inspector.get_columns('reports')]

    if 'event_id' not in reports_cols:
        op.add_column('reports', sa.Column('event_id', sa.Integer(), nullable=True))

    if 'reporter_hash' not in reports_cols:
        op.add_column('reports', sa.Column('reporter_hash', sa.String(length=64), nullable=True))

    if 'normalized_category' not in reports_cols:
        op.add_column('reports', sa.Column('normalized_category', sa.String(length=50), nullable=True))

    if 'severity_weight' not in reports_cols:
        op.add_column('reports', sa.Column('severity_weight', sa.Float(), nullable=True))

    if 'model_confidence' not in reports_cols:
        op.add_column('reports', sa.Column('model_confidence', sa.Float(), nullable=True))

    if 'analysis_method' not in reports_cols:
        op.add_column('reports', sa.Column('analysis_method', sa.String(length=50), nullable=True))

    # 3. SAFE BACKFILL STEP: Unique per-row UUID, Token, Status determination, and NLP metadata
    legacy_rows = bind.execute(
        sa.text("SELECT id, category, created_at FROM reports WHERE uuid_id IS NULL OR tracking_token IS NULL OR normalized_category IS NULL")
    ).fetchall()

    for row in legacy_rows:
        r_id, r_cat, r_created_at = row[0], row[1], row[2]
        r_uuid = str(uuid.uuid4())
        r_token = secrets.token_urlsafe(32)

        # Time-based status evaluation: older than 1 hour -> expired, else -> pending. Never accepted.
        is_expired = True
        if r_created_at is not None:
            if r_created_at.tzinfo is None:
                now_cmp = datetime.now(timezone.utc).replace(tzinfo=None)
            else:
                now_cmp = datetime.now(timezone.utc)
            if (now_cmp - r_created_at) < timedelta(hours=1):
                is_expired = False

        status_val = 'expired' if is_expired else 'pending'
        norm_cat = r_cat if r_cat else 'general_safety'

        bind.execute(
            sa.text("""
                UPDATE reports
                SET uuid_id = COALESCE(uuid_id, :u_id),
                    tracking_token = COALESCE(tracking_token, :t_tok),
                    status = :st,
                    category = COALESCE(category, 'general'),
                    normalized_category = COALESCE(normalized_category, :n_cat),
                    severity_weight = COALESCE(severity_weight, 0.35),
                    model_confidence = COALESCE(model_confidence, 0.5),
                    analysis_method = COALESCE(analysis_method, 'legacy_migration'),
                    event_id = NULL
                WHERE id = :r_id
            """),
            {
                "u_id": r_uuid,
                "t_tok": r_token,
                "st": status_val,
                "n_cat": norm_cat,
                "r_id": r_id
            }
        )

    # 4. Add FK and CHECK constraints after backfill is complete
    existing_constraints = [c['name'] for c in inspector.get_check_constraints('reports')] if hasattr(inspector, 'get_check_constraints') else []
    existing_fks = [fk['name'] for fk in inspector.get_foreign_keys('reports')] if hasattr(inspector, 'get_foreign_keys') else []

    if 'fk_reports_event_id_report_events' not in existing_fks:
        try:
            op.create_foreign_key(
                'fk_reports_event_id_report_events',
                'reports',
                'report_events',
                ['event_id'],
                ['id'],
                ondelete='SET NULL'
            )
            op.create_index('ix_reports_event_id', 'reports', ['event_id'])
        except Exception:
            pass

    if 'ix_reports_reporter_hash' not in [idx['name'] for idx in inspector.get_indexes('reports')]:
        try:
            op.create_index('ix_reports_reporter_hash', 'reports', ['reporter_hash'])
        except Exception:
            pass

    if 'chk_reports_severity_weight' not in existing_constraints:
        try:
            op.create_check_constraint('chk_reports_severity_weight', 'reports', 'severity_weight >= 0.0 AND severity_weight <= 1.0')
        except Exception:
            pass

    if 'chk_reports_model_confidence' not in existing_constraints:
        try:
            op.create_check_constraint('chk_reports_model_confidence', 'reports', 'model_confidence >= 0.0 AND model_confidence <= 1.0')
        except Exception:
            pass


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    reports_cols = [c['name'] for c in inspector.get_columns('reports')]

    if 'analysis_method' in reports_cols:
        op.drop_column('reports', 'analysis_method')

    if 'model_confidence' in reports_cols:
        try:
            op.drop_constraint('chk_reports_model_confidence', 'reports', type_='check')
        except Exception:
            pass
        op.drop_column('reports', 'model_confidence')

    if 'severity_weight' in reports_cols:
        try:
            op.drop_constraint('chk_reports_severity_weight', 'reports', type_='check')
        except Exception:
            pass
        op.drop_column('reports', 'severity_weight')

    if 'normalized_category' in reports_cols:
        op.drop_column('reports', 'normalized_category')

    if 'reporter_hash' in reports_cols:
        try:
            op.drop_index('ix_reports_reporter_hash', table_name='reports')
        except Exception:
            pass
        op.drop_column('reports', 'reporter_hash')

    if 'event_id' in reports_cols:
        try:
            op.drop_constraint('fk_reports_event_id_report_events', 'reports', type_='foreignkey')
            op.drop_index('ix_reports_event_id', table_name='reports')
        except Exception:
            pass
        op.drop_column('reports', 'event_id')

    existing_tables = inspector.get_table_names()
    if 'report_events' in existing_tables:
        for idx in ['idx_report_events_h3_status_last_seen', 'ix_report_events_expires_at', 'ix_report_events_last_seen_at', 'ix_report_events_first_seen_at', 'ix_report_events_status', 'ix_report_events_h3_index', 'ix_report_events_uuid_id', 'ix_report_events_id']:
            try:
                op.drop_index(idx, table_name='report_events')
            except Exception:
                pass
        op.drop_table('report_events')
