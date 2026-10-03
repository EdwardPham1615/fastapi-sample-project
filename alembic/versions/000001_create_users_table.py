"""create users table

Revision ID: 000001
Revises:
Create Date: 2026-09-25 22:48:04.714697

Generated with --autogenerate, then tidied by hand: columns in the order of the
original table spec, and the SQLite JSON variant of logged_in_methods dropped —
migrations only ever run against Postgres.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "000001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("oidc_provider_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("middle_name", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("dial_code", sa.String(length=8), nullable=True),
        sa.Column("gender", sa.SmallInteger(), nullable=False),
        sa.Column("birth_date", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.SmallInteger(), nullable=False),
        sa.Column("lang", sa.String(length=10), nullable=False),
        sa.Column("logged_in_methods", postgresql.ARRAY(sa.SmallInteger()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("oidc_provider_id", name=op.f("uq_users_oidc_provider_id")),
    )
    op.create_index("ix_users_created_at_id", "users", ["created_at", "id"], unique=False)
    op.create_index(op.f("ix_users_status"), "users", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_status"), table_name="users")
    op.drop_index("ix_users_created_at_id", table_name="users")
    op.drop_table("users")
