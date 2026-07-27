"""add indexes for map reports query

Revision ID: 9d0e1f2a3b4c
Revises: 8c9d0e1f2a3b
Create Date: 2026-07-27 02:10:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d0e1f2a3b4c'
down_revision: Union[str, Sequence[str], None] = '8c9d0e1f2a3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('idx_reports_status_created_at', 'reports', ['status', 'created_at'])
    op.create_index('idx_reports_category', 'reports', ['category'])


def downgrade() -> None:
    op.drop_index('idx_reports_category', table_name='reports')
    op.drop_index('idx_reports_status_created_at', table_name='reports')
