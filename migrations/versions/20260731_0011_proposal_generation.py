"""Add proposal generation drafts and section provenance."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0011"
down_revision: str | None = "20260730_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("proposal_sections") as batch:
        batch.add_column(
            sa.Column(
                "content_source", sa.String(30), server_default="EMPTY", nullable=False
            )
        )
        batch.add_column(sa.Column("last_ai_run_id", sa.Integer()))
        batch.add_column(
            sa.Column(
                "manually_edited",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch.add_column(sa.Column("generated_at", sa.DateTime(timezone=True)))
        batch.create_foreign_key(
            "fk_proposal_sections_last_ai_run",
            "ai_runs",
            ["last_ai_run_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_table(
        "proposal_generation_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("ai_run_id", sa.Integer(), nullable=False),
        sa.Column("generation_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("tone", sa.String(20), nullable=False),
        sa.Column("instructions", sa.Text()),
        sa.Column("requested_section_keys_json", sa.Text(), nullable=False),
        sa.Column("generated_sections_json", sa.Text(), nullable=False),
        sa.Column("source_references_json", sa.Text()),
        sa.Column("warnings_json", sa.Text()),
        sa.Column("applied_section_keys_json", sa.Text()),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("applied_by_user_id", sa.Integer()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("rejected_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_run_id"], ["ai_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["applied_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
    )
    for name in (
        "organization_id",
        "proposal_id",
        "ai_run_id",
        "status",
        "generation_type",
        "created_at",
        "input_hash",
    ):
        op.create_index(
            f"ix_proposal_generation_drafts_{name}",
            "proposal_generation_drafts",
            [name],
        )


def downgrade() -> None:
    op.drop_table("proposal_generation_drafts")
    with op.batch_alter_table("proposal_sections") as batch:
        batch.drop_constraint("fk_proposal_sections_last_ai_run", type_="foreignkey")
        batch.drop_column("generated_at")
        batch.drop_column("manually_edited")
        batch.drop_column("last_ai_run_id")
        batch.drop_column("content_source")
