"""Allow unsure response on alert_confirmations.

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-08-01
"""

from alembic import op

revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE alert_confirmations DROP CONSTRAINT IF EXISTS chk_alert_confirmations_response"
    )
    op.execute(
        """
        ALTER TABLE alert_confirmations
        ADD CONSTRAINT chk_alert_confirmations_response
        CHECK (response IN ('confirm', 'deny', 'unsure'))
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE alert_confirmations DROP CONSTRAINT IF EXISTS chk_alert_confirmations_response"
    )
    op.execute(
        """
        ALTER TABLE alert_confirmations
        ADD CONSTRAINT chk_alert_confirmations_response
        CHECK (response IN ('confirm', 'deny'))
        """
    )
