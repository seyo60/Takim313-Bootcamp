"""Add an explicit freshness timestamp to heatmap cells.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "h3_heatmap",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_h3_heatmap_updated_at",
        "h3_heatmap",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_h3_heatmap_updated_at", table_name="h3_heatmap")
    op.drop_column("h3_heatmap", "updated_at")
