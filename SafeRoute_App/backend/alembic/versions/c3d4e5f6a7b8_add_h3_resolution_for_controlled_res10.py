"""add explicit H3 resolution for controlled res-10 rollout

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Mevcut 5.336 satır res-9'dur; server_default güvenli ve deterministik backfill sağlar.
    op.add_column(
        "h3_heatmap",
        sa.Column(
            "h3_resolution",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("9"),
        ),
    )
    op.create_check_constraint(
        "chk_h3_heatmap_h3_resolution",
        "h3_heatmap",
        "h3_resolution IN (9, 10)",
    )
    op.create_index(
        "idx_h3_heatmap_resolution",
        "h3_heatmap",
        ["h3_resolution"],
        unique=False,
    )

    op.add_column(
        "report_events",
        sa.Column(
            "h3_resolution",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("9"),
        ),
    )
    op.create_check_constraint(
        "chk_report_events_h3_resolution",
        "report_events",
        "h3_resolution IN (9, 10)",
    )
    op.create_index(
        "idx_report_events_resolution_h3",
        "report_events",
        ["h3_resolution", "h3_index"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_report_events_resolution_h3", table_name="report_events")
    op.drop_constraint(
        "chk_report_events_h3_resolution",
        "report_events",
        type_="check",
    )
    op.drop_column("report_events", "h3_resolution")

    op.drop_index("idx_h3_heatmap_resolution", table_name="h3_heatmap")
    op.drop_constraint(
        "chk_h3_heatmap_h3_resolution",
        "h3_heatmap",
        type_="check",
    )
    op.drop_column("h3_heatmap", "h3_resolution")
