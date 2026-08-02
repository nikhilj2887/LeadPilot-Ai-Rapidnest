"""Add immutable client proposal acceptance evidence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0015"
down_revision: str | None = "20260802_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "proposal_acceptances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("proposal_portal_link_id", sa.Integer(), nullable=False),
        sa.Column("proposal_document_id", sa.Integer(), nullable=False),
        sa.Column("signed_document_id", sa.Integer()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("accepted_by_name", sa.String(200)),
        sa.Column("accepted_by_email", sa.String(320)),
        sa.Column("accepted_by_company", sa.String(200)),
        sa.Column("accepted_by_title", sa.String(200)),
        sa.Column("signature_type", sa.String(20)),
        sa.Column("typed_signature", sa.String(200)),
        sa.Column("signature_image_path", sa.String(500)),
        sa.Column("comments", sa.Text()),
        sa.Column("client_ip_hash", sa.String(64)),
        sa.Column("client_user_agent_hash", sa.String(64)),
        sa.Column("client_session_hash", sa.String(64)),
        sa.Column("evidence_hash", sa.String(64)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("rejected_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'REJECTED')",
            name="ck_proposal_acceptances_status",
        ),
        sa.CheckConstraint(
            "signature_type IS NULL OR signature_type IN ('TYPED', 'HANDWRITTEN')",
            name="ck_proposal_acceptances_signature_type",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["proposal_portal_link_id"],
            ["proposal_portal_links.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["proposal_document_id"], ["proposal_documents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["signed_document_id"], ["proposal_documents.id"], ondelete="RESTRICT"
        ),
    )
    for column in (
        "organization_id",
        "proposal_id",
        "proposal_portal_link_id",
        "proposal_document_id",
        "signed_document_id",
        "status",
        "evidence_hash",
        "created_at",
    ):
        op.create_index(
            f"ix_proposal_acceptances_{column}", "proposal_acceptances", [column]
        )
    op.create_index(
        "ix_proposal_acceptances_history",
        "proposal_acceptances",
        ["organization_id", "proposal_id", "created_at"],
    )
    op.create_index(
        "uq_proposal_acceptances_one_accepted",
        "proposal_acceptances",
        ["proposal_id"],
        unique=True,
        sqlite_where=sa.text("status = 'ACCEPTED'"),
        postgresql_where=sa.text("status = 'ACCEPTED'"),
    )


def downgrade() -> None:
    op.drop_table("proposal_acceptances")
