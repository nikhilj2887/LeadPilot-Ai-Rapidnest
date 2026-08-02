"""Add secure tenant proposal portal links and access history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0014"
down_revision: str | None = "20260801_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "proposal_portal_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("proposal_document_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("token_prefix", sa.String(12), nullable=False),
        sa.Column("password_hash", sa.String(500)),
        sa.Column(
            "password_required", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("max_access_count", sa.Integer()),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "allow_pdf_download", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "show_pricing", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "show_internal_branding_details",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("revoked_by_user_id", sa.Integer()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("access_count >= 0", name="ck_portal_links_access_count"),
        sa.CheckConstraint(
            "max_access_count IS NULL OR max_access_count > 0",
            name="ck_portal_links_max_access_count",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["proposal_document_id"], ["proposal_documents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("token_hash", name="uq_proposal_portal_links_token_hash"),
    )
    for column in (
        "organization_id",
        "proposal_id",
        "proposal_document_id",
        "status",
        "token_hash",
        "expires_at",
        "created_at",
    ):
        op.create_index(
            f"ix_proposal_portal_links_{column}", "proposal_portal_links", [column]
        )
    op.create_index(
        "ix_proposal_portal_links_history",
        "proposal_portal_links",
        ["organization_id", "proposal_id", "created_at"],
    )

    op.create_table(
        "proposal_portal_access_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("portal_link_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("access_result", sa.String(20), nullable=False),
        sa.Column("ip_hash", sa.String(64)),
        sa.Column("user_agent_hash", sa.String(64)),
        sa.Column("session_hash", sa.String(64)),
        sa.Column("safe_metadata_json", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["portal_link_id"], ["proposal_portal_links.id"], ondelete="CASCADE"
        ),
    )
    for column in (
        "organization_id",
        "portal_link_id",
        "event_type",
        "access_result",
        "created_at",
    ):
        op.create_index(
            f"ix_proposal_portal_access_events_{column}",
            "proposal_portal_access_events",
            [column],
        )
    op.create_index(
        "ix_proposal_portal_access_events_history",
        "proposal_portal_access_events",
        ["organization_id", "portal_link_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("proposal_portal_access_events")
    op.drop_table("proposal_portal_links")
