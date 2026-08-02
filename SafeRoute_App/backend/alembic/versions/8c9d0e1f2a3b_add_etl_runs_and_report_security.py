"""add etl_runs table and security columns to reports

Revision ID: 8c9d0e1f2a3b
Revises: 7a8b9c0d1e2f
Create Date: 2026-07-26 20:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c9d0e1f2a3b'
down_revision: Union[str, Sequence[str], None] = '7a8b9c0d1e2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. etl_runs tablosunun oluşturulması
    op.create_table(
        'etl_runs',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('etl_name', sa.String(length=50), nullable=False),
        sa.Column('last_successful_run', sa.DateTime(), nullable=False),
        sa.Column('records_processed', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='success')
    )
    op.create_index('idx_etl_runs_etl_name', 'etl_runs', ['etl_name'], unique=True)

    # 2. reports tablosuna güvenlik ve takip sütunlarının eklenmesi
    op.add_column('reports', sa.Column('uuid_id', sa.String(length=36), nullable=True))
    op.add_column('reports', sa.Column('tracking_token', sa.String(length=64), nullable=True))
    op.add_column('reports', sa.Column('category', sa.String(length=50), nullable=False, server_default='general'))
    op.add_column('reports', sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'))
    op.add_column('reports', sa.Column('ip_address', sa.String(length=45), nullable=True))

    op.create_index('idx_reports_uuid_id', 'reports', ['uuid_id'], unique=True)
    op.create_index('idx_reports_tracking_token', 'reports', ['tracking_token'])


def downgrade() -> None:
    op.drop_index('idx_reports_tracking_token', table_name='reports')
    op.drop_index('idx_reports_uuid_id', table_name='reports')
    op.drop_column('reports', 'ip_address')
    op.drop_column('reports', 'status')
    op.drop_column('reports', 'category')
    op.drop_column('reports', 'tracking_token')
    op.drop_column('reports', 'uuid_id')

    op.drop_index('idx_etl_runs_etl_name', table_name='etl_runs')
    op.drop_table('etl_runs')
