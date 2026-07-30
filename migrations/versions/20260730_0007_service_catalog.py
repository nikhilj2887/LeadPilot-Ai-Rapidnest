"""Expand organization services into a tenant-aware product catalog."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260730_0007"
down_revision: str | None = "20260729_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("organization_services") as batch:
        batch.add_column(sa.Column("detailed_description", sa.Text()))
        for name in (
            "problems_solved",
            "business_benefits",
            "deliverables",
            "target_industries",
            "tags",
        ):
            batch.add_column(
                sa.Column(name, sa.Text(), server_default="[]", nullable=False)
            )
        batch.add_column(
            sa.Column(
                "pricing_model",
                sa.String(20),
                server_default="CUSTOM",
                nullable=False,
            )
        )
        batch.add_column(sa.Column("base_price", sa.Numeric(12, 2)))
        batch.add_column(
            sa.Column("currency", sa.String(3), server_default="INR", nullable=False)
        )
        batch.add_column(sa.Column("estimated_timeline", sa.String(200)))
    op.execute(
        sa.text(
            "UPDATE organization_services "
            "SET detailed_description = full_description "
            "WHERE detailed_description IS NULL"
        )
    )
    op.create_index(
        "ix_org_services_org_category",
        "organization_services",
        ["organization_id", "category"],
    )
    op.create_index(
        "ix_org_services_org_pricing_model",
        "organization_services",
        ["organization_id", "pricing_model"],
    )
    op.create_index(
        "ix_org_services_org_active",
        "organization_services",
        ["organization_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_org_services_org_active", table_name="organization_services")
    op.drop_index(
        "ix_org_services_org_pricing_model", table_name="organization_services"
    )
    op.drop_index("ix_org_services_org_category", table_name="organization_services")
    with op.batch_alter_table("organization_services") as batch:
        for name in (
            "estimated_timeline",
            "currency",
            "base_price",
            "pricing_model",
            "tags",
            "target_industries",
            "deliverables",
            "business_benefits",
            "problems_solved",
            "detailed_description",
        ):
            batch.drop_column(name)
