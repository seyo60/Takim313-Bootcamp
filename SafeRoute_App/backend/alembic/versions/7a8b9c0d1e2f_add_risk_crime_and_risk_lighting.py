"""Add crime and lighting risk columns with an H3 unique constraint.

Revision ID: 7a8b9c0d1e2f
Revises: 4ba90bcb6804
Create Date: 2026-07-26 03:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Alembic revision identifiers.
revision: str = "7a8b9c0d1e2f"
down_revision: Union[str, Sequence[str], None] = "4ba90bcb6804"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add source-specific risk columns and the H3 uniqueness constraint."""

    op.add_column(
        "h3_heatmap",
        sa.Column(
            "risk_crime",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.0"),
        ),
    )

    op.add_column(
        "h3_heatmap",
        sa.Column(
            "risk_lighting",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.0"),
        ),
    )

    # Required for safe INSERT ... ON CONFLICT upsert operations.
    op.create_unique_constraint(
        "uq_h3_heatmap_h3_index",
        "h3_heatmap",
        ["h3_index"],
    )


def downgrade() -> None:
    """Remove only the schema objects owned by this migration."""

    op.drop_constraint(
        "uq_h3_heatmap_h3_index",
        table_name="h3_heatmap",
        type_="unique",
    )

    op.drop_column("h3_heatmap", "risk_lighting")
    op.drop_column("h3_heatmap", "risk_crime")