"""create discovery AI analyses"""

import sqlalchemy as sa
from alembic import op

revision = "20260728_0004"
down_revision = "20260727_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_ai_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "discovery_scan_id",
            sa.Integer(),
            sa.ForeignKey("discovery_scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="Pending"),
        sa.Column(
            "review_status", sa.String(20), nullable=False, server_default="Unreviewed"
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("prompt_version", sa.String(30), nullable=False),
        sa.Column("schema_version", sa.String(30), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.Column("executive_summary", sa.Text()),
        sa.Column("business_profile", sa.Text()),
        *[
            sa.Column(name, sa.Text(), nullable=False, server_default="[]")
            for name in (
                "digital_strengths",
                "improvement_areas",
                "business_risks",
                "quick_wins",
                "strategic_opportunities",
                "recommended_services",
                "implementation_roadmap",
                "discovery_questions",
                "outreach_angles",
                "evidence_references",
            )
        ],
        sa.Column("confidence_notes", sa.Text()),
        sa.Column("input_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("input_token_count", sa.Integer()),
        sa.Column("output_token_count", sa.Integer()),
        sa.Column("total_token_count", sa.Integer()),
        sa.Column("estimated_cost", sa.Float()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column(
            "raw_response_metadata", sa.Text(), nullable=False, server_default="{}"
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewer_notes", sa.Text()),
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
    for name in (
        "discovery_scan_id",
        "company_id",
        "status",
        "generated_at",
        "created_at",
        "input_snapshot_hash",
        "review_status",
    ):
        op.create_index(
            f"ix_discovery_ai_analyses_{name}", "discovery_ai_analyses", [name]
        )


def downgrade() -> None:
    op.drop_table("discovery_ai_analyses")
