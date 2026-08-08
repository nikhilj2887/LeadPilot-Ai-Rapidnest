"""Add tenant-aware sales automation and revenue intelligence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0018"
down_revision: str | None = "20260802_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tenant_id() -> sa.Column:
    return sa.Column(
        "organization_id",
        sa.Integer(),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )


def _created() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def upgrade() -> None:
    op.create_table(
        "sales_intelligence_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        _tenant_id(),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "default_forecast_method",
            sa.String(30),
            nullable=False,
            server_default="STAGE_WEIGHTED",
        ),
        sa.Column("stale_lead_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column(
            "stale_opportunity_days", sa.Integer(), nullable=False, server_default="21"
        ),
        sa.Column("weights_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "lead_priority_threshold", sa.Integer(), nullable=False, server_default="60"
        ),
        sa.Column(
            "opportunity_risk_threshold",
            sa.Integer(),
            nullable=False,
            server_default="40",
        ),
        sa.Column(
            "high_health_threshold", sa.Integer(), nullable=False, server_default="80"
        ),
        sa.Column(
            "medium_health_threshold", sa.Integer(), nullable=False, server_default="60"
        ),
        sa.Column(
            "low_health_threshold", sa.Integer(), nullable=False, server_default="40"
        ),
        sa.Column(
            "forecast_commit_threshold",
            sa.Integer(),
            nullable=False,
            server_default="75",
        ),
        sa.Column(
            "forecast_best_case_threshold",
            sa.Integer(),
            nullable=False,
            server_default="50",
        ),
        sa.Column(
            "default_forecast_horizon_days",
            sa.Integer(),
            nullable=False,
            server_default="90",
        ),
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
        _created(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("lead_priority_threshold BETWEEN 0 AND 100"),
        sa.CheckConstraint("opportunity_risk_threshold BETWEEN 0 AND 100"),
        sa.UniqueConstraint("organization_id", name="uq_sales_intelligence_config_org"),
    )
    op.create_table(
        "lead_intelligence_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        _tenant_id(),
        sa.Column(
            "lead_id",
            sa.Integer(),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("priority_band", sa.String(20), nullable=False),
        sa.Column("score_breakdown_json", sa.Text(), nullable=False),
        sa.Column("risk_flags_json", sa.Text(), nullable=False),
        sa.Column("recommended_follow_up_at", sa.DateTime(timezone=True)),
        sa.Column("source_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "calculated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        _created(),
        sa.CheckConstraint("score BETWEEN 0 AND 100"),
    )
    op.create_table(
        "opportunity_health_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        _tenant_id(),
        sa.Column(
            "opportunity_id",
            sa.Integer(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("health_score", sa.Integer(), nullable=False),
        sa.Column("health_band", sa.String(20), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("score_breakdown_json", sa.Text(), nullable=False),
        sa.Column("risk_flags_json", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.String(500)),
        sa.Column("source_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "calculated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        _created(),
        sa.CheckConstraint("health_score BETWEEN 0 AND 100"),
    )
    op.create_table(
        "revenue_forecasts",
        sa.Column("id", sa.Integer(), primary_key=True),
        _tenant_id(),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("forecast_method", sa.String(30), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        *[
            sa.Column(name, sa.Numeric(18, 2), nullable=False)
            for name in (
                "open_pipeline_amount",
                "weighted_pipeline_amount",
                "commit_amount",
                "best_case_amount",
                "worst_case_amount",
                "won_amount",
                "lost_amount",
            )
        ],
        sa.Column("scenario_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("source_snapshot_hash", sa.String(64), nullable=False),
        sa.Column(
            "generated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        _created(),
        sa.CheckConstraint("period_start <= period_end"),
    )
    op.create_table(
        "opportunity_forecast_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        _tenant_id(),
        sa.Column(
            "revenue_forecast_id",
            sa.Integer(),
            sa.ForeignKey("revenue_forecasts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "opportunity_id",
            sa.Integer(),
            sa.ForeignKey("opportunities.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "stage_id",
            sa.Integer(),
            sa.ForeignKey("pipeline_stages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("probability_percentage", sa.Integer(), nullable=False),
        sa.Column("weighted_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("expected_close_date", sa.Date()),
        sa.Column("forecast_category", sa.String(20), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("included_in_commit", sa.Boolean(), nullable=False),
        sa.Column("included_in_best_case", sa.Boolean(), nullable=False),
        sa.Column("included_in_worst_case", sa.Boolean(), nullable=False),
        _created(),
    )
    op.create_table(
        "sales_recommendations",
        sa.Column("id", sa.Integer(), primary_key=True),
        _tenant_id(),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("recommendation_type", sa.String(40), nullable=False),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="PENDING_REVIEW"
        ),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reasoning_json", sa.Text(), nullable=False),
        sa.Column("source_references_json", sa.Text(), nullable=False),
        sa.Column("suggested_due_at", sa.DateTime(timezone=True)),
        sa.Column(
            "suggested_owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "ai_run_id", sa.Integer(), sa.ForeignKey("ai_runs.id", ondelete="SET NULL")
        ),
        sa.Column("source_snapshot_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "reviewed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "applied_task_id",
            sa.Integer(),
            sa.ForeignKey("crm_tasks.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "applied_activity_id",
            sa.Integer(),
            sa.ForeignKey("crm_activities.id", ondelete="SET NULL"),
        ),
        _created(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "organization_id",
            "entity_type",
            "entity_id",
            "recommendation_type",
            "source_snapshot_hash",
            name="uq_sales_recommendation_source",
        ),
    )
    op.create_table(
        "win_loss_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        _tenant_id(),
        sa.Column(
            "opportunity_id",
            sa.Integer(),
            sa.ForeignKey("opportunities.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("outcome", sa.String(10), nullable=False),
        sa.Column("primary_reason", sa.String(300), nullable=False),
        sa.Column(
            "secondary_reasons_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column("competitor", sa.String(200)),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("sales_cycle_days", sa.Integer()),
        sa.Column("proposal_count", sa.Integer(), nullable=False),
        sa.Column("activity_count", sa.Integer(), nullable=False),
        sa.Column(
            "engagement_summary_json", sa.Text(), nullable=False, server_default="{}"
        ),
        sa.Column("notes", sa.Text()),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "analyzed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        _created(),
    )
    op.create_table(
        "sales_intelligence_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        _tenant_id(),
        sa.Column("run_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("entity_type", sa.String(20)),
        sa.Column("entity_id", sa.Integer()),
        sa.Column("source_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("result_summary_json", sa.Text()),
        sa.Column(
            "ai_run_id", sa.Integer(), sa.ForeignKey("ai_runs.id", ondelete="SET NULL")
        ),
        sa.Column("error_code", sa.String(80)),
        sa.Column("safe_error_message", sa.String(500)),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        _created(),
    )
    for table, columns in {
        "lead_intelligence_scores": (
            "lead_id",
            "score",
            "priority_band",
            "calculated_at",
        ),
        "opportunity_health_scores": (
            "opportunity_id",
            "health_score",
            "health_band",
            "risk_level",
            "calculated_at",
        ),
        "sales_recommendations": (
            "entity_type",
            "entity_id",
            "status",
            "priority",
            "recommendation_type",
            "created_at",
        ),
        "revenue_forecasts": (
            "forecast_date",
            "period_start",
            "period_end",
            "forecast_method",
            "currency",
        ),
        "opportunity_forecast_snapshots": (
            "revenue_forecast_id",
            "opportunity_id",
            "forecast_category",
            "risk_level",
        ),
        "win_loss_analyses": ("opportunity_id", "outcome", "analyzed_at"),
        "sales_intelligence_runs": (
            "run_type",
            "status",
            "entity_type",
            "entity_id",
            "created_at",
        ),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table in (
        "sales_intelligence_runs",
        "win_loss_analyses",
        "sales_recommendations",
        "opportunity_forecast_snapshots",
        "revenue_forecasts",
        "opportunity_health_scores",
        "lead_intelligence_scores",
        "sales_intelligence_configs",
    ):
        op.drop_table(table)
