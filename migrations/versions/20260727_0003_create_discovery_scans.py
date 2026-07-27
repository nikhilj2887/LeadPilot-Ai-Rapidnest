"""Create discovery scans for Milestone 4.

Discovery scans are owned by a company and are deleted by the database when that
company is deleted. This prevents orphaned website intelligence records.

Revision ID: 20260727_0003
Revises: 20260725_0002
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_0003"
down_revision: str | None = "20260725_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BOOLEAN_FIELDS = (
    "is_https",
    "ssl_valid",
    "mobile_viewport_present",
    "robots_txt_present",
    "sitemap_present",
    "contact_page_present",
    "about_page_present",
    "careers_page_present",
    "blog_present",
    "privacy_policy_present",
    "terms_page_present",
    "contact_form_present",
    "newsletter_present",
    "booking_system_present",
    "ecommerce_present",
    "live_chat_present",
    "chatbot_present",
    "whatsapp_present",
    "phone_present",
    "email_present",
    "social_links_present",
    "linkedin_present",
    "facebook_present",
    "instagram_present",
    "x_present",
)


def upgrade() -> None:
    columns = [
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("website_url", sa.String(length=2048), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="Pending", nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.Column("http_status_code", sa.Integer()),
        sa.Column("final_url", sa.String(length=2048)),
        sa.Column("page_title", sa.String(length=500)),
        sa.Column("meta_description", sa.Text()),
        sa.Column("response_time_ms", sa.Integer()),
        *(
            sa.Column(name, sa.Boolean(), server_default=sa.false(), nullable=False)
            for name in BOOLEAN_FIELDS
        ),
        sa.Column(
            "detected_technologies", sa.Text(), server_default="[]", nullable=False
        ),
        sa.Column("detected_emails", sa.Text(), server_default="[]", nullable=False),
        sa.Column(
            "detected_phone_numbers", sa.Text(), server_default="[]", nullable=False
        ),
        sa.Column(
            "detected_social_links", sa.Text(), server_default="[]", nullable=False
        ),
        sa.Column(
            "website_health_score", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "digital_maturity_score", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "ai_readiness_score", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "automation_potential_score",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "lead_priority_score", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("score_details", sa.Text(), server_default="{}", nullable=False),
        sa.Column("findings", sa.Text(), server_default="[]", nullable=False),
        sa.Column("recommendations", sa.Text(), server_default="[]", nullable=False),
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
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    ]
    op.create_table("discovery_scans", *columns)
    op.create_index("ix_discovery_scans_company_id", "discovery_scans", ["company_id"])
    op.create_index("ix_discovery_scans_status", "discovery_scans", ["status"])
    op.create_index("ix_discovery_scans_created_at", "discovery_scans", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_discovery_scans_created_at", table_name="discovery_scans")
    op.drop_index("ix_discovery_scans_status", table_name="discovery_scans")
    op.drop_index("ix_discovery_scans_company_id", table_name="discovery_scans")
    op.drop_table("discovery_scans")
