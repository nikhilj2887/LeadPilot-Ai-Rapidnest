"""Add tenant-aware CRM foundation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0017"
down_revision: str | None = "20260802_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
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
    )


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("job_title", sa.String(150)),
        sa.Column("department", sa.String(150)),
        sa.Column("email", sa.String(320)),
        sa.Column("phone", sa.String(50)),
        sa.Column("mobile", sa.String(50)),
        sa.Column("linkedin_url", sa.String(500)),
        sa.Column(
            "preferred_contact_method",
            sa.String(20),
            nullable=False,
            server_default="NONE",
        ),
        sa.Column(
            "is_primary", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        *_timestamps(),
        sa.UniqueConstraint("company_id", "email", name="uq_contacts_company_email"),
    )
    op.create_table(
        "pipeline_stages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("stage_type", sa.String(20), nullable=False),
        sa.Column("probability_percentage", sa.Integer(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
        sa.Column("is_won", sa.Boolean(), nullable=False),
        sa.Column("is_lost", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "probability_percentage BETWEEN 0 AND 100",
            name="ck_pipeline_stage_probability",
        ),
        sa.UniqueConstraint(
            "organization_id", "code", name="uq_pipeline_stage_org_code"
        ),
    )
    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "contact_id",
            sa.Integer(),
            sa.ForeignKey("contacts.id", ondelete="SET NULL"),
        ),
        sa.Column("lead_number", sa.String(30), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("qualification_status", sa.String(30), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True)),
        sa.Column("industry", sa.String(150)),
        sa.Column("country", sa.String(100)),
        sa.Column("city", sa.String(100)),
        sa.Column("website", sa.String(500)),
        sa.Column("email", sa.String(320)),
        sa.Column("phone", sa.String(50)),
        sa.Column("estimated_value", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("expected_close_date", sa.Date()),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "score_breakdown_json", sa.Text(), nullable=False, server_default="{}"
        ),
        sa.Column("qualification_notes", sa.Text()),
        sa.Column("disqualification_reason", sa.Text()),
        sa.Column("last_contacted_at", sa.DateTime(timezone=True)),
        sa.Column("next_follow_up_at", sa.DateTime(timezone=True)),
        sa.Column("converted_opportunity_id", sa.Integer()),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        *_timestamps(),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="ck_leads_score"),
        sa.UniqueConstraint(
            "organization_id", "lead_number", name="uq_leads_org_number"
        ),
    )
    op.create_table(
        "opportunities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "primary_contact_id",
            sa.Integer(),
            sa.ForeignKey("contacts.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "source_lead_id",
            sa.Integer(),
            sa.ForeignKey("leads.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "stage_id",
            sa.Integer(),
            sa.ForeignKey("pipeline_stages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("opportunity_number", sa.String(30), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("probability_percentage", sa.Integer(), nullable=False),
        sa.Column("weighted_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("expected_close_date", sa.Date()),
        sa.Column("actual_close_date", sa.Date()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("win_reason", sa.Text()),
        sa.Column("loss_reason", sa.Text()),
        sa.Column("competitor", sa.String(200)),
        sa.Column("next_step", sa.Text()),
        sa.Column("last_activity_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "probability_percentage BETWEEN 0 AND 100",
            name="ck_opportunities_probability",
        ),
        sa.UniqueConstraint(
            "organization_id", "opportunity_number", name="uq_opportunities_org_number"
        ),
    )
    with op.batch_alter_table("proposals") as batch:
        batch.add_column(sa.Column("opportunity_id", sa.Integer()))
        batch.create_foreign_key(
            "fk_proposals_opportunity",
            "opportunities",
            ["opportunity_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_proposals_opportunity_id", ["opportunity_id"])
    entity_columns = lambda: [
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "contact_id", sa.Integer(), sa.ForeignKey("contacts.id", ondelete="CASCADE")
        ),
        sa.Column(
            "lead_id", sa.Integer(), sa.ForeignKey("leads.id", ondelete="CASCADE")
        ),
        sa.Column(
            "opportunity_id",
            sa.Integer(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "proposal_id",
            sa.Integer(),
            sa.ForeignKey("proposals.id", ondelete="CASCADE"),
        ),
    ]
    op.create_table(
        "crm_activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("activity_type", sa.String(30), nullable=False),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False),
        *entity_columns(),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "performed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("duration_minutes", sa.Integer()),
        sa.Column("outcome", sa.Text()),
        *_timestamps(),
    )
    op.create_table(
        "crm_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        *entity_columns(),
        sa.Column(
            "assigned_to_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("reminder_at", sa.DateTime(timezone=True)),
        *_timestamps(),
    )
    op.create_table(
        "crm_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        *entity_columns(),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        *_timestamps(),
    )
    op.create_table(
        "crm_stage_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "opportunity_id",
            sa.Integer(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_stage_id",
            sa.Integer(),
            sa.ForeignKey("pipeline_stages.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "to_stage_id",
            sa.Integer(),
            sa.ForeignKey("pipeline_stages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "changed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("change_reason", sa.String(500)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_table(
        "crm_assignment_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column(
            "from_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column(
            "to_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column(
            "assigned_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("assignment_method", sa.String(30), nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    for table, columns in {
        "contacts": ("organization_id", "company_id", "email", "status", "created_at"),
        "leads": (
            "organization_id",
            "company_id",
            "contact_id",
            "owner_user_id",
            "status",
            "qualification_status",
            "priority",
            "source",
            "created_at",
            "next_follow_up_at",
        ),
        "pipeline_stages": ("organization_id", "display_order"),
        "opportunities": (
            "organization_id",
            "company_id",
            "stage_id",
            "owner_user_id",
            "status",
            "expected_close_date",
            "created_at",
        ),
        "crm_activities": (
            "organization_id",
            "activity_type",
            "status",
            "owner_user_id",
            "scheduled_at",
            "completed_at",
            "company_id",
            "lead_id",
            "opportunity_id",
            "proposal_id",
        ),
        "crm_tasks": (
            "organization_id",
            "status",
            "assigned_to_user_id",
            "due_at",
            "lead_id",
            "opportunity_id",
        ),
        "crm_notes": ("organization_id", "lead_id", "opportunity_id"),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    with op.batch_alter_table("proposals") as batch:
        batch.drop_index("ix_proposals_opportunity_id")
        batch.drop_constraint("fk_proposals_opportunity", type_="foreignkey")
        batch.drop_column("opportunity_id")
    for table in (
        "crm_assignment_history",
        "crm_stage_history",
        "crm_notes",
        "crm_tasks",
        "crm_activities",
        "opportunities",
        "leads",
        "pipeline_stages",
        "contacts",
    ):
        op.drop_table(table)
