from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

EXPECTED_COLUMNS = {
    "id",
    "organization_id",
    "name",
    "website",
    "industry",
    "country",
    "city",
    "company_size",
    "status",
    "source",
    "notes",
    "created_at",
    "updated_at",
}


def test_fresh_migrations_create_exact_company_schema_and_indexes(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "migration.db"
    monkeypatch.setenv("LEADPILOT_DATABASE_URL", f"sqlite:///{database}")
    config = Config("alembic.ini")
    command.upgrade(config, "head")

    inspector = inspect(create_engine(f"sqlite:///{database}"))
    assert "companies" in inspector.get_table_names()
    assert {
        column["name"] for column in inspector.get_columns("companies")
    } == EXPECTED_COLUMNS
    indexes = {index["name"]: index for index in inspector.get_indexes("companies")}
    assert set(indexes) == {
        "ix_companies_organization_id",
        "ix_companies_name",
        "ix_companies_website",
        "ix_companies_status",
        "ix_companies_country",
    }
    assert indexes["ix_companies_name"]["unique"] == 0

    command.downgrade(config, "base")
    assert (
        "companies"
        not in inspect(create_engine(f"sqlite:///{database}")).get_table_names()
    )


def test_alembic_accepts_url_encoded_postgresql_password() -> None:
    database_url = (
        "postgresql+psycopg://postgres:password%40with%25encoding"
        "@db.example.test:5432/postgres"
    )
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    assert config.get_main_option("sqlalchemy.url") == database_url
    migration_environment = Path("migrations/env.py").read_text()
    assert 'database_url.replace("%", "%%")' in migration_environment


def test_proposal_migration_creates_tenant_aware_schema(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "proposal-migration.db"
    monkeypatch.setenv("LEADPILOT_DATABASE_URL", f"sqlite:///{database}")
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    inspector = inspect(create_engine(f"sqlite:///{database}"))

    expected = {
        "proposals",
        "proposal_items",
        "proposal_sections",
        "proposal_versions",
        "proposal_activities",
    }
    assert expected <= set(inspector.get_table_names())
    for table in expected:
        assert "organization_id" in {
            column["name"] for column in inspector.get_columns(table)
        }
    assert {
        "uq_proposals_org_number",
    } <= {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("proposals")
    }
    assert {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("proposal_items")
    } >= {"proposals", "organizations", "organization_services"}


def test_ai_foundation_migration_creates_expected_schema(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "ai-foundation.db"
    monkeypatch.setenv("LEADPILOT_DATABASE_URL", f"sqlite:///{database}")
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    inspector = inspect(create_engine(f"sqlite:///{database}"))
    assert {"ai_provider_configs", "prompt_templates", "ai_runs"} <= set(
        inspector.get_table_names()
    )
    assert {"uq_ai_runs_org_idempotency"} <= {
        item["name"] for item in inspector.get_unique_constraints("ai_runs")
    }
    assert {"uq_prompt_templates_org_key_version"} <= {
        item["name"] for item in inspector.get_unique_constraints("prompt_templates")
    }


def test_offering_recommendation_migration(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "recommendations.db"
    monkeypatch.setenv("LEADPILOT_DATABASE_URL", f"sqlite:///{database}")
    command.upgrade(Config("alembic.ini"), "head")
    inspector = inspect(create_engine(f"sqlite:///{database}"))
    assert "proposal_recommendations" in inspector.get_table_names()
    assert {
        "ck_recommendation_match_score",
        "ck_recommendation_deterministic_score",
    } <= {
        item["name"]
        for item in inspector.get_check_constraints("proposal_recommendations")
    }


def test_proposal_generation_migration(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "proposal-generation.db"
    monkeypatch.setenv("LEADPILOT_DATABASE_URL", f"sqlite:///{database}")
    command.upgrade(Config("alembic.ini"), "head")
    inspector = inspect(create_engine(f"sqlite:///{database}"))
    assert "proposal_generation_drafts" in inspector.get_table_names()
    section_columns = {
        column["name"] for column in inspector.get_columns("proposal_sections")
    }
    assert {
        "content_source",
        "last_ai_run_id",
        "manually_edited",
        "generated_at",
    } <= section_columns
