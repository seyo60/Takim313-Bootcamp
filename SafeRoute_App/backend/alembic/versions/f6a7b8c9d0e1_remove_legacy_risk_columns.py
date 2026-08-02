"""Remove deprecated historical and social risk columns.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Preserve any last legacy-only crime signal before removing the alias.
    op.execute(
        """
        UPDATE h3_heatmap
        SET risk_crime = LEAST(1.0, GREATEST(0.0, COALESCE(risk_historical, 0.0)))
        WHERE COALESCE(risk_crime, 0.0) = 0.0
          AND COALESCE(risk_historical, 0.0) > 0.0
        """
    )
    op.execute(
        """
        UPDATE h3_heatmap
        SET total_risk = LEAST(
            1.0,
            GREATEST(
                0.0,
                0.65 * COALESCE(risk_crime, 0.0)
                + 0.20 * COALESCE(risk_lighting, 0.0)
                + 0.15 * COALESCE(risk_live, 0.0)
            )
        )
        """
    )
    op.drop_column("h3_heatmap", "risk_social")
    op.drop_column("h3_heatmap", "risk_historical")


def downgrade() -> None:
    op.add_column(
        "h3_heatmap",
        sa.Column("risk_historical", sa.Float(), nullable=True, server_default=sa.text("0.0")),
    )
    op.add_column(
        "h3_heatmap",
        sa.Column("risk_social", sa.Float(), nullable=True, server_default=sa.text("0.0")),
    )
    op.execute("UPDATE h3_heatmap SET risk_historical = COALESCE(risk_crime, 0.0)")

