"""Create tenant-aware proposal engine foundation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260730_0008"
down_revision: str | None = "20260730_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "proposals",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("discovery_scan_id", sa.Integer()),
        sa.Column("proposal_number", sa.String(30), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("status", sa.String(20), server_default="DRAFT", nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("valid_until", sa.Date()),
        *[
            sa.Column(name, sa.Text())
            for name in (
                "summary",
                "client_requirements",
                "recommended_approach",
                "implementation_plan",
                "commercial_notes",
                "terms_and_conditions",
                "internal_notes",
            )
        ],
        *[
            sa.Column(name, sa.Numeric(14, 2), server_default="0", nullable=False)
            for name in ("subtotal", "discount_amount", "tax_amount", "total_amount")
        ],
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("updated_by_user_id", sa.Integer()),
        sa.Column("approved_by_user_id", sa.Integer()),
        *[
            sa.Column(name, sa.DateTime(timezone=True))
            for name in (
                "approved_at",
                "sent_at",
                "accepted_at",
                "rejected_at",
                "expired_at",
            )
        ],
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["discovery_scan_id"], ["discovery_scans.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "organization_id", "proposal_number", name="uq_proposals_org_number"
        ),
    )
    for name in ("organization_id", "company_id", "status", "created_at"):
        op.create_index(f"ix_proposals_{name}", "proposals", [name])
    op.create_index(
        "ix_proposals_org_status", "proposals", ["organization_id", "status"]
    )
    op.create_index(
        "ix_proposals_org_company", "proposals", ["organization_id", "company_id"]
    )

    op.create_table(
        "proposal_items",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("service_catalog_id", sa.Integer()),
        sa.Column("item_type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "discount_amount", sa.Numeric(14, 2), server_default="0", nullable=False
        ),
        sa.Column("tax_rate", sa.Numeric(7, 4), server_default="0", nullable=False),
        sa.Column("line_subtotal", sa.Numeric(14, 2), nullable=False),
        sa.Column("line_tax", sa.Numeric(14, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("delivery_timeline", sa.String(200)),
        sa.Column("selection_reason", sa.Text()),
        sa.Column(
            "is_optional", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["service_catalog_id"], ["organization_services.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_proposal_items_organization_id", "proposal_items", ["organization_id"]
    )
    op.create_index("ix_proposal_items_proposal_id", "proposal_items", ["proposal_id"])

    op.create_table(
        "proposal_sections",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("section_key", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "proposal_id", "section_key", name="uq_proposal_sections_key"
        ),
    )
    op.create_index(
        "ix_proposal_sections_organization_id", "proposal_sections", ["organization_id"]
    )
    op.create_index(
        "ix_proposal_sections_proposal_id", "proposal_sections", ["proposal_id"]
    )

    op.create_table(
        "proposal_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("change_summary", sa.String(500)),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "proposal_id", "version_number", name="uq_proposal_versions_number"
        ),
    )
    op.create_index(
        "ix_proposal_versions_organization_id", "proposal_versions", ["organization_id"]
    )
    op.create_index(
        "ix_proposal_versions_proposal_id", "proposal_versions", ["proposal_id"]
    )

    op.create_table(
        "proposal_activities",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer()),
        sa.Column("activity_type", sa.String(30), nullable=False),
        sa.Column("details_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    for name in ("organization_id", "proposal_id", "activity_type", "created_at"):
        op.create_index(f"ix_proposal_activities_{name}", "proposal_activities", [name])


def downgrade() -> None:
    for table in (
        "proposal_activities",
        "proposal_versions",
        "proposal_sections",
        "proposal_items",
        "proposals",
    ):
        op.drop_table(table)
