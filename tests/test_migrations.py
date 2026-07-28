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
