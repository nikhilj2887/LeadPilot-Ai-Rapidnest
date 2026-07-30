"""Add provider-agnostic AI configuration, templates, and run tracking."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260730_0009"
down_revision: str | None = "20260730_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    timestamps = (
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
    )
    op.create_table(
        "ai_provider_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer()),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "is_default", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "temperature", sa.Numeric(4, 3), server_default="0.1", nullable=False
        ),
        sa.Column(
            "max_output_tokens", sa.Integer(), server_default="2048", nullable=False
        ),
        sa.Column(
            "request_timeout_seconds", sa.Integer(), server_default="60", nullable=False
        ),
        sa.Column("max_retries", sa.Integer(), server_default="2", nullable=False),
        sa.Column("monthly_token_limit", sa.Integer()),
        sa.Column("monthly_cost_limit", sa.Numeric(14, 4)),
        sa.Column("credentials_reference", sa.String(200)),
        *timestamps,
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
    )
    for name in ("organization_id", "provider", "is_active", "is_default"):
        op.create_index(f"ix_ai_provider_configs_{name}", "ai_provider_configs", [name])

    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer()),
        sa.Column("template_key", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("system_template", sa.Text(), nullable=False),
        sa.Column("user_template", sa.Text(), nullable=False),
        sa.Column("response_schema_version", sa.String(50), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.false(), nullable=False),
        *timestamps,
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "template_key",
            "version",
            name="uq_prompt_templates_org_key_version",
        ),
    )
    for name in ("organization_id", "template_key", "is_active"):
        op.create_index(f"ix_prompt_templates_{name}", "prompt_templates", [name])

    op.create_table(
        "ai_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer()),
        sa.Column("proposal_id", sa.Integer()),
        sa.Column("company_id", sa.Integer()),
        sa.Column("discovery_scan_id", sa.Integer()),
        sa.Column("run_type", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("prompt_template_key", sa.String(100)),
        sa.Column("prompt_template_version", sa.Integer()),
        sa.Column("idempotency_key", sa.String(200)),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("input_snapshot_json", sa.Text(), nullable=False),
        sa.Column("output_json", sa.Text()),
        sa.Column("raw_output_reference", sa.String(500)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.String(500)),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("total_tokens", sa.Integer()),
        sa.Column("estimated_cost", sa.Numeric(14, 6)),
        sa.Column("provider_request_id", sa.String(200)),
        sa.Column("finish_reason", sa.String(100)),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["discovery_scan_id"], ["discovery_scans.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_ai_runs_org_idempotency"
        ),
    )
    for name in (
        "organization_id",
        "status",
        "run_type",
        "provider",
        "proposal_id",
        "company_id",
        "created_at",
    ):
        op.create_index(f"ix_ai_runs_{name}", "ai_runs", [name])


def downgrade() -> None:
    op.drop_table("ai_runs")
    op.drop_table("prompt_templates")
    op.drop_table("ai_provider_configs")
