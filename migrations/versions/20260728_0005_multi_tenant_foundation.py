"""Build the multi-tenant organization foundation.

The downgrade removes organization metadata after returning owned records to the
legacy schema. That necessarily discards organization separation and should only
be used for local rollback.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0005"
down_revision: str | None = "20260728_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SERVICES = (
    "AI Chatbots and Conversational Automation",
    "Business Process Automation",
    "Websites and Web Applications",
    "Mobile Applications",
    "Custom CRM and ERP Solutions",
    "Cloud and Digital Transformation",
)


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("legal_name", sa.String(200)),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column(
            "default_currency", sa.String(3), server_default="INR", nullable=False
        ),
        sa.Column(
            "timezone", sa.String(80), server_default="Asia/Kolkata", nullable=False
        ),
        sa.Column("website", sa.String(500)),
        sa.Column("contact_email", sa.String(320)),
        sa.Column("contact_phone", sa.String(50)),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)
    op.create_index("ix_organizations_status", "organizations", ["status"])
    op.create_table(
        "organization_branding",
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("brand_name", sa.String(200), nullable=False),
        sa.Column("logo_reference", sa.String(500)),
        sa.Column(
            "primary_color", sa.String(7), server_default="#2563EB", nullable=False
        ),
        sa.Column(
            "secondary_color", sa.String(7), server_default="#0F172A", nullable=False
        ),
        sa.Column(
            "accent_color", sa.String(7), server_default="#14B8A6", nullable=False
        ),
        sa.Column("proposal_footer", sa.Text()),
        sa.Column("email_signature", sa.Text()),
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
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("organization_id"),
    )
    op.create_table(
        "organization_services",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("short_description", sa.String(500)),
        sa.Column("full_description", sa.Text()),
        sa.Column("category", sa.String(120)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
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
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_org_services_name"),
    )
    op.create_index(
        "ix_organization_services_organization_id",
        "organization_services",
        ["organization_id"],
    )
    op.create_index(
        "ix_organization_services_is_active", "organization_services", ["is_active"]
    )

    organization = sa.table(
        "organizations",
        sa.column("id", sa.Integer),
        sa.column("slug", sa.String),
        sa.column("legal_name", sa.String),
        sa.column("display_name", sa.String),
        sa.column("status", sa.String),
        sa.column("default_currency", sa.String),
        sa.column("timezone", sa.String),
        sa.column("website", sa.String),
        sa.column("contact_email", sa.String),
        sa.column("contact_phone", sa.String),
    )
    op.bulk_insert(
        organization,
        [
            {
                "id": 1,
                "slug": "rapidnest",
                "legal_name": "RapidNest Software Solutions",
                "display_name": "RapidNest Software Solutions",
                "status": "active",
                "default_currency": "INR",
                "timezone": "Asia/Kolkata",
                "website": "www.therapidnest.com",
                "contact_email": "contact@therapidnest.com",
                "contact_phone": "+91 63006 75410",
            }
        ],
    )
    branding = sa.table(
        "organization_branding",
        sa.column("organization_id", sa.Integer),
        sa.column("brand_name", sa.String),
        sa.column("logo_reference", sa.String),
        sa.column("primary_color", sa.String),
        sa.column("secondary_color", sa.String),
        sa.column("accent_color", sa.String),
        sa.column("proposal_footer", sa.Text),
        sa.column("email_signature", sa.Text),
    )
    op.bulk_insert(
        branding,
        [
            {
                "organization_id": 1,
                "brand_name": "RapidNest Software Solutions",
                "logo_reference": "assets/leadpilot-logo.png",
                "primary_color": "#2563EB",
                "secondary_color": "#0F172A",
                "accent_color": "#14B8A6",
                "proposal_footer": "RapidNest Software Solutions · www.therapidnest.com",
                "email_signature": "RapidNest Software Solutions",
            }
        ],
    )
    service_table = sa.table(
        "organization_services",
        sa.column("organization_id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("short_description", sa.String),
        sa.column("category", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("display_order", sa.Integer),
    )
    op.bulk_insert(
        service_table,
        [
            {
                "organization_id": 1,
                "name": name,
                "short_description": name,
                "category": "Digital Solutions",
                "is_active": True,
                "display_order": order,
            }
            for order, name in enumerate(SERVICES, 1)
        ],
    )

    op.drop_index("ix_companies_name", table_name="companies")
    for table in ("companies", "discovery_scans", "discovery_ai_analyses"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET organization_id = 1"))
        with op.batch_alter_table(table) as batch:
            batch.alter_column("organization_id", nullable=False)
            batch.create_foreign_key(
                f"fk_{table}_organization_id",
                "organizations",
                ["organization_id"],
                ["id"],
                ondelete="RESTRICT",
            )
            batch.create_index(f"ix_{table}_organization_id", ["organization_id"])
    op.create_index("ix_companies_name", "companies", ["name"])
    with op.batch_alter_table("companies") as batch:
        batch.create_unique_constraint(
            "uq_companies_org_name", ["organization_id", "name"]
        )
        batch.create_unique_constraint(
            "uq_companies_org_website", ["organization_id", "website"]
        )


def downgrade() -> None:
    with op.batch_alter_table("companies") as batch:
        batch.drop_constraint("uq_companies_org_website", type_="unique")
        batch.drop_constraint("uq_companies_org_name", type_="unique")
    op.drop_index("ix_companies_name", table_name="companies")
    for table in ("discovery_ai_analyses", "discovery_scans", "companies"):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_organization_id")
            batch.drop_constraint(f"fk_{table}_organization_id", type_="foreignkey")
            batch.drop_column("organization_id")
    op.create_index("ix_companies_name", "companies", ["name"], unique=True)
    op.drop_table("organization_services")
    op.drop_table("organization_branding")
    op.drop_index("ix_organizations_status", table_name="organizations")
    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_table("organizations")
