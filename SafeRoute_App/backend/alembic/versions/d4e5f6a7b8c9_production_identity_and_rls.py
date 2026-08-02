"""production identity, ownership, composite H3 identity, and UTC timestamps

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UTC_COLUMNS = {
    "h3_heatmap": ("date",),
    "reports": ("created_at",),
    "report_events": (
        "first_seen_at",
        "last_seen_at",
        "accepted_at",
        "expires_at",
        "created_at",
        "updated_at",
    ),
    "etl_runs": ("last_successful_run",),
}


def _to_utc_timestamps() -> None:
    for table, columns in UTC_COLUMNS.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                type_=sa.DateTime(timezone=True),
                postgresql_using=f'"{column}" AT TIME ZONE \'UTC\'',
                existing_nullable=column not in {"last_successful_run"},
            )


def _to_naive_timestamps() -> None:
    for table, columns in UTC_COLUMNS.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                type_=sa.DateTime(timezone=False),
                postgresql_using=f'"{column}" AT TIME ZONE \'UTC\'',
                existing_nullable=column not in {"last_successful_run"},
            )


def upgrade() -> None:
    bind = op.get_bind()

    duplicate_tokens = bind.execute(
        sa.text(
            """
            SELECT tracking_token
            FROM reports
            WHERE tracking_token IS NOT NULL
            GROUP BY tracking_token
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate_tokens:
        raise RuntimeError("reports contains duplicate tracking tokens; resolve before migration")

    null_identity_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM reports WHERE uuid_id IS NULL OR tracking_token IS NULL"
        )
    ).scalar_one()
    if null_identity_count:
        raise RuntimeError("reports contains missing UUID/tracking identities; backfill before migration")

    op.drop_constraint("uq_h3_heatmap_h3_index", "h3_heatmap", type_="unique")
    op.create_unique_constraint(
        "uq_h3_heatmap_resolution_index",
        "h3_heatmap",
        ["h3_resolution", "h3_index"],
    )

    op.create_unique_constraint(
        "uq_reports_tracking_token",
        "reports",
        ["tracking_token"],
    )
    op.alter_column("reports", "uuid_id", existing_type=sa.String(36), nullable=False)
    op.alter_column("reports", "tracking_token", existing_type=sa.String(64), nullable=False)

    op.create_table(
        "user_profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=True),
        sa.Column("role", sa.String(length=20), server_default="user", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('user', 'moderator', 'admin')", name="chk_user_profiles_role"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.add_column(
        "reports",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_reports_user_id", "reports", ["user_id"], unique=False)

    # The FK/trigger is installed only on Supabase, where auth.users exists.
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('auth.users') IS NOT NULL THEN
            ALTER TABLE public.user_profiles
              ADD CONSTRAINT fk_user_profiles_auth_user
              FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
            ALTER TABLE public.reports
              ADD CONSTRAINT fk_reports_auth_user
              FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE SET NULL;

            CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
            RETURNS trigger
            LANGUAGE plpgsql
            SECURITY DEFINER SET search_path = public
            AS $fn$
            BEGIN
              INSERT INTO public.user_profiles (user_id, role)
              VALUES (NEW.id, 'user')
              ON CONFLICT (user_id) DO NOTHING;
              RETURN NEW;
            END;
            $fn$;

            DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
            CREATE TRIGGER on_auth_user_created
              AFTER INSERT ON auth.users
              FOR EACH ROW EXECUTE FUNCTION public.handle_new_auth_user();
          END IF;
        END
        $$;
        """
    )

    _to_utc_timestamps()

    op.execute("ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regprocedure('auth.uid()') IS NOT NULL THEN
            DROP POLICY IF EXISTS user_profiles_select_own ON public.user_profiles;
            DROP POLICY IF EXISTS user_profiles_update_own ON public.user_profiles;
            DROP POLICY IF EXISTS reports_select_own ON public.reports;
            DROP POLICY IF EXISTS reports_insert_own ON public.reports;

            CREATE POLICY user_profiles_select_own ON public.user_profiles
              FOR SELECT TO authenticated USING (auth.uid() = user_id);
            CREATE POLICY user_profiles_update_own ON public.user_profiles
              FOR UPDATE TO authenticated
              USING (auth.uid() = user_id)
              WITH CHECK (auth.uid() = user_id AND role = 'user');
            CREATE POLICY reports_select_own ON public.reports
              FOR SELECT TO authenticated USING (auth.uid() = user_id);
            CREATE POLICY reports_insert_own ON public.reports
              FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS reports_insert_own ON public.reports")
    op.execute("DROP POLICY IF EXISTS reports_select_own ON public.reports")
    op.execute("DROP POLICY IF EXISTS user_profiles_update_own ON public.user_profiles")
    op.execute("DROP POLICY IF EXISTS user_profiles_select_own ON public.user_profiles")
    op.execute("ALTER TABLE public.reports DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.user_profiles DISABLE ROW LEVEL SECURITY")
    _to_naive_timestamps()

    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('auth.users') IS NOT NULL THEN
            DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
          END IF;
        END
        $$;
        """
    )
    op.execute("DROP FUNCTION IF EXISTS public.handle_new_auth_user()")
    op.execute("ALTER TABLE public.reports DROP CONSTRAINT IF EXISTS fk_reports_auth_user")
    op.execute("ALTER TABLE public.user_profiles DROP CONSTRAINT IF EXISTS fk_user_profiles_auth_user")

    op.drop_index("ix_reports_user_id", table_name="reports")
    op.drop_column("reports", "user_id")
    op.drop_table("user_profiles")

    op.alter_column("reports", "tracking_token", existing_type=sa.String(64), nullable=True)
    op.alter_column("reports", "uuid_id", existing_type=sa.String(36), nullable=True)
    op.drop_constraint("uq_reports_tracking_token", "reports", type_="unique")

    op.drop_constraint("uq_h3_heatmap_resolution_index", "h3_heatmap", type_="unique")
    op.create_unique_constraint(
        "uq_h3_heatmap_h3_index",
        "h3_heatmap",
        ["h3_index"],
    )
