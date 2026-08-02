"""Add emergency alert device/confirmation tables.

Revision ID: a8b9c0d1e2f3
Revises: f6a7b8c9d0e1
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geography


revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("expo_push_token", sa.String(length=255), nullable=False),
        sa.Column("last_lat", sa.Float(), nullable=True),
        sa.Column("last_lng", sa.Float(), nullable=True),
        sa.Column(
            "location",
            Geography(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_devices_user_id", "user_devices", ["user_id"])
    op.create_index(
        "ix_user_devices_expo_push_token",
        "user_devices",
        ["expo_push_token"],
        unique=True,
    )
    op.create_index("ix_user_devices_updated_at", "user_devices", ["updated_at"])

    op.create_table(
        "emergency_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid_id", sa.String(length=36), nullable=False),
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("report_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("report_uuid", sa.String(length=36), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.String(length=280), nullable=False),
        sa.Column(
            "llm_method",
            sa.String(length=64),
            nullable=False,
            server_default="deterministic_fallback",
        ),
        sa.Column("confirm_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deny_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "push_target_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("broadcast_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "phase IN ('witness_request', 'broadcast')",
            name="chk_emergency_alerts_phase",
        ),
    )
    op.create_index(
        "ix_emergency_alerts_uuid_id", "emergency_alerts", ["uuid_id"], unique=True
    )
    op.create_index("ix_emergency_alerts_event_id", "emergency_alerts", ["event_id"])
    op.create_index(
        "ix_emergency_alerts_report_uuid", "emergency_alerts", ["report_uuid"]
    )
    op.create_index("ix_emergency_alerts_phase", "emergency_alerts", ["phase"])
    op.create_index(
        "ix_emergency_alerts_created_at", "emergency_alerts", ["created_at"]
    )

    op.create_table(
        "alert_confirmations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("report_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "alert_id",
            sa.Integer(),
            sa.ForeignKey("emergency_alerts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("response", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "event_id", "user_id", name="uq_alert_confirmations_event_user"
        ),
        sa.CheckConstraint(
            "response IN ('confirm', 'deny')",
            name="chk_alert_confirmations_response",
        ),
    )
    op.create_index(
        "ix_alert_confirmations_event_id", "alert_confirmations", ["event_id"]
    )
    op.create_index(
        "ix_alert_confirmations_alert_id", "alert_confirmations", ["alert_id"]
    )
    op.create_index(
        "ix_alert_confirmations_user_id", "alert_confirmations", ["user_id"]
    )


def downgrade() -> None:
    op.drop_table("alert_confirmations")
    op.drop_table("emergency_alerts")
    op.drop_table("user_devices")
