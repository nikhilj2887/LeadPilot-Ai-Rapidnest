"""Add immutable proposal document exports."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0012"
down_revision: str | None = "20260731_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "proposal_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("proposal_version_id", sa.Integer()),
        sa.Column("document_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("storage_provider", sa.String(30), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("file_name", sa.String(200), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size_bytes", sa.Integer()),
        sa.Column("sha256_checksum", sa.String(64)),
        sa.Column("source_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("source_snapshot_json", sa.Text(), nullable=False),
        sa.Column("branding_snapshot_json", sa.Text(), nullable=False),
        sa.Column("page_count", sa.Integer()),
        sa.Column("generated_by_user_id", sa.Integer()),
        sa.Column("error_code", sa.String(100)),
        sa.Column("safe_error_message", sa.String(500)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "file_size_bytes IS NULL OR file_size_bytes >= 0",
            name="ck_proposal_documents_file_size",
        ),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count >= 1",
            name="ck_proposal_documents_page_count",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["proposal_version_id"], ["proposal_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["generated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("storage_key", name="uq_proposal_documents_storage_key"),
    )
    for name in (
        "organization_id",
        "proposal_id",
        "proposal_version_id",
        "status",
        "document_type",
        "created_at",
        "source_snapshot_hash",
    ):
        op.create_index(f"ix_proposal_documents_{name}", "proposal_documents", [name])


def downgrade() -> None:
    op.drop_table("proposal_documents")
