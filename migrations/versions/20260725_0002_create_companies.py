"""Create the Milestone 2 companies table.

Revision ID: 20260725_0002
Revises: 20260725_0001
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260725_0002"
down_revision: str | None = "20260725_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("company_size", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="New", nullable=False),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_companies_country"), "companies", ["country"])
    op.create_index(op.f("ix_companies_name"), "companies", ["name"], unique=True)
    op.create_index(op.f("ix_companies_status"), "companies", ["status"])
    op.create_index(op.f("ix_companies_website"), "companies", ["website"])


def downgrade() -> None:
    op.drop_index(op.f("ix_companies_website"), table_name="companies")
    op.drop_index(op.f("ix_companies_status"), table_name="companies")
    op.drop_index(op.f("ix_companies_name"), table_name="companies")
    op.drop_index(op.f("ix_companies_country"), table_name="companies")
    op.drop_table("companies")
