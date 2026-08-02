"""Add tenant-scoped proposal engagement analytics events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0016"
down_revision: str | None = "20260802_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "proposal_engagement_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("portal_link_id", sa.Integer(), nullable=False),
        sa.Column("proposal_document_id", sa.Integer()),
        sa.Column("visitor_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("page_number", sa.Integer()),
        sa.Column("section_key", sa.String(100)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("ip_hash", sa.String(64)),
        sa.Column("user_agent_hash", sa.String(64)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "page_number IS NULL OR page_number > 0", name="ck_engagement_page_number"
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR (duration_ms >= 0 AND duration_ms <= 86400000)",
            name="ck_engagement_duration",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["portal_link_id"], ["proposal_portal_links.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["proposal_document_id"], ["proposal_documents.id"], ondelete="SET NULL"
        ),
    )
    for column in (
        "organization_id",
        "proposal_id",
        "portal_link_id",
        "event_type",
        "created_at",
    ):
        op.create_index(
            f"ix_proposal_engagement_events_{column}",
            "proposal_engagement_events",
            [column],
        )
    op.create_index(
        "ix_proposal_engagement_timeline",
        "proposal_engagement_events",
        ["organization_id", "proposal_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("proposal_engagement_events")
