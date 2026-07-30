from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from leadpilot.application.proposals import (
    DEFAULT_SECTIONS,
    ProposalFilters,
    ProposalInput,
    ProposalItemInput,
    ProposalService,
    ProposalSort,
    ProposalStatus,
    ProposalValidationError,
)
from leadpilot.infrastructure.database.base import Base
from leadpilot.infrastructure.database.models import (
    CompanyModel,
    OrganizationModel,
    OrganizationServiceModel,
)
from leadpilot.infrastructure.database.proposal_repository import (
    SqlAlchemyProposalRepository,
)


@pytest.fixture
def proposal_services() -> tuple[ProposalService, ProposalService, int, int, int]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    with factory.begin() as session:
        first = OrganizationModel(slug="proposal-a", display_name="Proposal A")
        second = OrganizationModel(slug="proposal-b", display_name="Proposal B")
        session.add_all((first, second))
        session.flush()
        first_company = CompanyModel(organization_id=first.id, name="Acme")
        second_company = CompanyModel(organization_id=second.id, name="Private")
        catalog = OrganizationServiceModel(
            organization_id=first.id,
            name="Automation",
            short_description="Workflow automation",
            pricing_model="FIXED",
            base_price=Decimal(1000),
            currency="USD",
        )
        session.add_all((first_company, second_company, catalog))
        session.flush()
        ids = first_company.id, second_company.id, catalog.id
        organization_ids = first.id, second.id
    return (
        ProposalService(SqlAlchemyProposalRepository(factory, organization_ids[0])),
        ProposalService(SqlAlchemyProposalRepository(factory, organization_ids[1])),
        *ids,
    )


def values(company_id: int, title: str = "Automation Proposal") -> ProposalInput:
    return ProposalInput(company_id=company_id, title=title, currency="usd")


def test_validation_and_decimal_calculation() -> None:
    item = ProposalItemInput(
        title="Platform",
        quantity=Decimal(2),
        unit_price=Decimal("125.55"),
        discount_amount=Decimal("10.10"),
        tax_rate=Decimal(18),
    )
    assert ProposalService.calculate_line(item) == (
        Decimal("251.10"),
        Decimal("43.38"),
        Decimal("284.38"),
    )
    with pytest.raises(ProposalValidationError, match="Discount"):
        ProposalService.calculate_line(
            ProposalItemInput(
                title="Invalid",
                unit_price=Decimal(10),
                discount_amount=Decimal(11),
            )
        )
    with pytest.raises(ValidationError):
        ProposalInput(company_id=1, title="", currency="USD")
    with pytest.raises(ValidationError):
        ProposalItemInput(title="Bad", unit_price=Decimal(-1))


def test_create_defaults_crud_totals_versions_and_activity(proposal_services) -> None:
    first, _, first_company, _, catalog_id = proposal_services
    proposal = first.create_proposal(values(first_company))
    assert proposal.proposal_number.endswith("0001")
    assert proposal.status == ProposalStatus.DRAFT
    assert len(first.list_sections(proposal.id)) == len(DEFAULT_SECTIONS)

    manual = first.add_manual_item(
        proposal.id,
        ProposalItemInput(
            title="Discovery",
            quantity=Decimal(2),
            unit_price=Decimal(100),
            discount_amount=Decimal(20),
            tax_rate=Decimal(10),
        ),
    )
    catalog = first.add_catalog_item(proposal.id, catalog_id)
    assert manual.line_total == Decimal("198.00")
    assert catalog.line_total == Decimal("1000.00")
    assert first.get_proposal(proposal.id).total_amount == Decimal("1198.00")

    first.update_item(
        proposal.id,
        manual.id,
        ProposalItemInput(title="Discovery", unit_price=Decimal(250)),
    )
    assert first.get_proposal(proposal.id).total_amount == Decimal("1250.00")
    version = first.create_version(proposal.id, "Commercial baseline")
    assert version.version_number == 1
    assert version.snapshot["proposal"]["proposal_number"] == proposal.proposal_number
    assert len(first.list_activities(proposal.id)) >= 5
    first.delete_item(proposal.id, catalog.id)
    assert first.get_proposal(proposal.id).total_amount == Decimal("250.00")


def test_status_workflow_immutability_and_permissions(proposal_services) -> None:
    first, _, company_id, _, _ = proposal_services
    proposal = first.create_proposal(values(company_id))
    with pytest.raises(ProposalValidationError, match="Cannot move"):
        first.transition_status(proposal.id, ProposalStatus.SENT)
    first.transition_status(proposal.id, ProposalStatus.IN_REVIEW)
    first.transition_status(proposal.id, ProposalStatus.APPROVED)
    first.transition_status(proposal.id, ProposalStatus.SENT)
    accepted = first.transition_status(proposal.id, ProposalStatus.ACCEPTED)
    assert accepted.status == ProposalStatus.ACCEPTED
    with pytest.raises(ProposalValidationError, match="cannot be edited"):
        first.add_manual_item(
            proposal.id,
            ProposalItemInput(title="Late", unit_price=Decimal(1)),
        )
    with pytest.raises(ProposalValidationError, match="cannot be deleted"):
        first.delete_proposal(proposal.id)

    denied = ProposalService(
        first._repository,
        authorize_write=lambda: (_ for _ in ()).throw(PermissionError("denied")),
    )
    with pytest.raises(PermissionError):
        denied.create_proposal(values(company_id, "Denied"))


def test_tenant_isolation_filters_sorting_pagination_and_numbers(
    proposal_services,
) -> None:
    first, second, first_company, second_company, _ = proposal_services
    alpha = first.create_proposal(values(first_company, "Alpha"))
    beta = first.create_proposal(values(first_company, "Beta"))
    other = second.create_proposal(values(second_company, "Alpha"))
    assert alpha.proposal_number.endswith("0001")
    assert beta.proposal_number.endswith("0002")
    assert other.proposal_number.endswith("0001")
    with pytest.raises(ProposalValidationError, match="Company"):
        first.create_proposal(values(second_company, "Leak"))
    assert second._repository.get(alpha.id) is None
    assert not second._repository.delete(alpha.id)

    page = first.list_proposals(
        ProposalFilters(query="a"),
        page=1,
        page_size=1,
        sort=ProposalSort.TITLE,
        descending=False,
    )
    assert page.total == 2
    assert [item.title for item in page.items] == ["Alpha"]
    assert first.search_proposals("Beta").items[0].id == beta.id


def test_catalog_currency_and_optional_items_are_validated(
    proposal_services,
) -> None:
    first, _, company_id, _, catalog_id = proposal_services
    proposal = first.create_proposal(
        ProposalInput(company_id=company_id, title="INR", currency="INR")
    )
    with pytest.raises(ProposalValidationError, match="currencies"):
        first.add_catalog_item(proposal.id, catalog_id)
    optional = first.add_manual_item(
        proposal.id,
        ProposalItemInput(title="Optional", unit_price=Decimal(100), is_optional=True),
    )
    assert optional.line_total == Decimal("100.00")
    assert first.get_proposal(proposal.id).total_amount == Decimal("0.00")
