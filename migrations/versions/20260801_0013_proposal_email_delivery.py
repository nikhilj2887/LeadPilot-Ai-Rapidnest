"""Add tenant-aware proposal email delivery."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0013"
down_revision: str | None = "20260731_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_provider_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer()),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("from_address", sa.String(320), nullable=False),
        sa.Column("from_name", sa.String(200), nullable=False),
        sa.Column("reply_to_address", sa.String(320)),
        sa.Column("credentials_reference", sa.String(300)),
        sa.Column("smtp_host", sa.String(255)),
        sa.Column("smtp_port", sa.Integer()),
        sa.Column(
            "smtp_use_tls", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "smtp_use_ssl", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "request_timeout_seconds", sa.Integer(), nullable=False, server_default="30"
        ),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="2"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "smtp_port IS NULL OR (smtp_port >= 1 AND smtp_port <= 65535)",
            name="ck_email_provider_configs_port",
        ),
        sa.CheckConstraint(
            "NOT (smtp_use_tls AND smtp_use_ssl)",
            name="ck_email_provider_configs_transport",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_email_provider_configs_organization_id",
        "email_provider_configs",
        ["organization_id"],
    )
    op.create_index(
        "ix_email_provider_configs_provider", "email_provider_configs", ["provider"]
    )
    op.create_index(
        "ix_email_provider_configs_is_active", "email_provider_configs", ["is_active"]
    )
    op.create_index(
        "ix_email_provider_configs_is_default", "email_provider_configs", ["is_default"]
    )
    op.create_index(
        "ix_email_provider_configs_resolution",
        "email_provider_configs",
        ["organization_id", "provider", "is_active", "is_default"],
    )

    op.create_table(
        "proposal_email_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("proposal_document_id", sa.Integer(), nullable=False),
        sa.Column("provider_config_id", sa.Integer()),
        sa.Column("original_delivery_id", sa.Integer()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("from_address", sa.String(320), nullable=False),
        sa.Column("from_name", sa.String(200), nullable=False),
        sa.Column("reply_to_address", sa.String(320)),
        sa.Column("to_addresses_json", sa.Text(), nullable=False),
        sa.Column("cc_addresses_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("bcc_addresses_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column("attachment_file_name", sa.String(200), nullable=False),
        sa.Column("attachment_sha256_checksum", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_message_id", sa.String(300)),
        sa.Column("provider_response_json", sa.Text()),
        sa.Column("idempotency_key", sa.String(64)),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("safe_error_code", sa.String(100)),
        sa.Column("safe_error_message", sa.String(500)),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("queued_at", sa.DateTime(timezone=True)),
        sa.Column("sending_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_proposal_email_deliveries_attempt_count"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["proposal_document_id"], ["proposal_documents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["provider_config_id"], ["email_provider_configs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["original_delivery_id"],
            ["proposal_email_deliveries.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_proposal_email_deliveries_idempotency",
        ),
    )
    for column in (
        "organization_id",
        "proposal_id",
        "proposal_document_id",
        "provider_config_id",
        "original_delivery_id",
        "status",
        "provider",
        "created_at",
    ):
        op.create_index(
            f"ix_proposal_email_deliveries_{column}",
            "proposal_email_deliveries",
            [column],
        )
    op.create_index(
        "ix_proposal_email_deliveries_history",
        "proposal_email_deliveries",
        ["organization_id", "proposal_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("proposal_email_deliveries")
    op.drop_table("email_provider_configs")
