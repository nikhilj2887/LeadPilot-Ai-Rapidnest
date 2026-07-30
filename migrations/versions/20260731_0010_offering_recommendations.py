"""Add tenant proposal offering recommendations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260730_0010"
down_revision: str | None = "20260730_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "proposal_recommendations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("service_catalog_id", sa.Integer(), nullable=False),
        sa.Column("ai_run_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("match_score", sa.Integer(), nullable=False),
        sa.Column("deterministic_score", sa.Integer()),
        sa.Column("priority", sa.String(10), nullable=False),
        sa.Column("recommendation_reason", sa.Text(), nullable=False),
        sa.Column(
            "matched_findings_json", sa.Text(), server_default="[]", nullable=False
        ),
        sa.Column(
            "expected_benefits_json", sa.Text(), server_default="[]", nullable=False
        ),
        sa.Column("suggested_scope", sa.Text(), nullable=False),
        sa.Column("suggested_timeline", sa.String(200)),
        sa.Column("warnings_json", sa.Text(), server_default="[]", nullable=False),
        sa.Column("reviewed_by_user_id", sa.Integer()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("added_proposal_item_id", sa.Integer()),
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
        sa.CheckConstraint(
            "match_score BETWEEN 0 AND 100", name="ck_recommendation_match_score"
        ),
        sa.CheckConstraint(
            "deterministic_score IS NULL OR deterministic_score BETWEEN 0 AND 100",
            name="ck_recommendation_deterministic_score",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["service_catalog_id"], ["organization_services.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["ai_run_id"], ["ai_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["added_proposal_item_id"], ["proposal_items.id"], ondelete="SET NULL"
        ),
    )
    for name in (
        "organization_id",
        "proposal_id",
        "company_id",
        "service_catalog_id",
        "ai_run_id",
        "status",
        "priority",
        "created_at",
    ):
        op.create_index(
            f"ix_proposal_recommendations_{name}", "proposal_recommendations", [name]
        )


def downgrade() -> None:
    op.drop_table("proposal_recommendations")
