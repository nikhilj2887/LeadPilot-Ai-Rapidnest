from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from leadpilot.application.organizations import (
    OrganizationContext,
    OrganizationCreate,
    OrganizationValidationError,
    validate_color,
    validate_logo_reference,
)
from leadpilot.infrastructure.database.base import Base
from leadpilot.infrastructure.database.company_repository import CompanyRepository
from leadpilot.infrastructure.database.models import OrganizationModel
from leadpilot.infrastructure.database.organization_repository import (
    OrganizationRepository,
)
from leadpilot.presentation.streamlit.state import switch_organization


def organization_values(slug: str, name: str) -> OrganizationCreate:
    return OrganizationCreate(
        slug=slug,
        display_name=name,
        contact_email=f"hello@{slug}.example",
        default_currency="USD",
        timezone="UTC",
    )


@pytest.fixture
def repositories():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    organizations = OrganizationRepository(factory)
    first = organizations.create(
        organization_values("organization-a", "Organization A")
    )
    second = organizations.create(
        organization_values("organization-b", "Organization B")
    )
    return (
        organizations,
        CompanyRepository(factory, first.id),
        CompanyRepository(factory, second.id),
    )


def test_organization_validation_and_safe_branding() -> None:
    assert organization_values("valid-slug", "Valid").slug == "valid-slug"
    for values in (
        {"slug": "Not Safe", "display_name": "Invalid"},
        {"slug": "valid", "display_name": "Invalid", "contact_email": "bad"},
        {"slug": "valid", "display_name": "Invalid", "status": "unknown"},
    ):
        with pytest.raises(ValidationError):
            OrganizationCreate(**values)
    assert validate_color("#12abEF") == "#12ABEF"
    with pytest.raises(OrganizationValidationError):
        validate_color("red")
    assert validate_logo_reference("assets/logo.png") == "assets/logo.png"
    with pytest.raises(OrganizationValidationError):
        validate_logo_reference("../secret")


def test_duplicate_slug_is_rejected(repositories) -> None:
    organizations, _, _ = repositories
    with pytest.raises(ValueError, match="already exists"):
        organizations.create(organization_values("organization-a", "Duplicate"))


def test_company_repositories_are_isolated(repositories) -> None:
    _, first, second = repositories
    company = first.create({"name": "Private Lead", "status": "New"})
    assert first.get_by_id(company.id) is not None
    assert second.get_by_id(company.id) is None
    assert second.list_all() == []
    assert second.update(company.id, {"status": "Won"}) is None
    assert second.delete(company.id) is False
    assert first.count() == 1 and second.count() == 0


def test_context_rejects_inactive_and_switch_resets_state(repositories) -> None:
    organizations, first, _ = repositories
    context = OrganizationContext.resolve(organizations, first.organization_id)
    assert context.organization_id == first.organization_id
    with first._session_factory() as session, session.begin():
        model = session.get(OrganizationModel, first.organization_id)
        model.status = "suspended"
    with pytest.raises(OrganizationValidationError):
        OrganizationContext.resolve(organizations, first.organization_id)
    state = {"organization_id": 2, "selected_company": 42, "navigation": "Companies"}
    assert switch_organization(state, 1, {1, 2})
    assert state["navigation"] == "Dashboard"
    assert "selected_company" not in state
    assert not switch_organization(state, 999, {1, 2})


def test_migration_seeds_and_backfills_existing_data(
    tmp_path: Path, monkeypatch
) -> None:
    url = f"sqlite:///{tmp_path / 'backfill.db'}"
    monkeypatch.setenv("LEADPILOT_DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "20260728_0004")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO companies (name, status) VALUES ('Existing Lead', 'New')"
        )
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT organization_id FROM companies WHERE name='Existing Lead'"
            ).scalar_one()
            == 1
        )
        assert (
            connection.exec_driver_sql(
                "SELECT contact_email FROM organizations WHERE slug='rapidnest'"
            ).scalar_one()
            == "contact@therapidnest.com"
        )
        assert (
            connection.exec_driver_sql(
                "SELECT count(*) FROM organization_services WHERE organization_id=1"
            ).scalar_one()
            == 6
        )
