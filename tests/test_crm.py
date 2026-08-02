from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from leadpilot.application.crm import (
    CrmError,
    CrmService,
    neutralize_formula,
    qualification_band,
    score_lead,
)
from leadpilot.infrastructure.database.base import Base
from leadpilot.infrastructure.database.crm_repository import SqlAlchemyCrmRepository
from leadpilot.infrastructure.database.models import CompanyModel, OrganizationModel


@pytest.fixture
def crm_services():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False, class_=Session)
    with factory.begin() as session:
        first = OrganizationModel(slug="crm-one", display_name="CRM One")
        second = OrganizationModel(slug="crm-two", display_name="CRM Two")
        session.add_all((first, second))
        session.flush()
        first_company = CompanyModel(organization_id=first.id, name="Example One")
        second_company = CompanyModel(organization_id=second.id, name="Example Two")
        session.add_all((first_company, second_company))
        session.flush()
        ids = first.id, second.id, first_company.id, second_company.id
    return (
        CrmService(SqlAlchemyCrmRepository(factory, ids[0]), None),
        CrmService(SqlAlchemyCrmRepository(factory, ids[1]), None),
        ids[2],
        ids[3],
        factory,
    )


def test_contact_creation_normalizes_email_and_primary_contact(crm_services) -> None:
    service, _, company, _, _ = crm_services
    first = service.create_contact(
        company, "Alex", "Buyer", email=" ALEX@EXAMPLE.TEST ", is_primary=True
    )
    second = service.create_contact(
        company, "Sam", "Buyer", email="sam@example.test", is_primary=True
    )
    assert first.email == "alex@example.test"
    contacts = service.list("contact").items
    assert sum(item.is_primary for item in contacts) == 1
    assert next(item for item in contacts if item.id == second.id).is_primary


def test_contact_archive_restore_and_tenant_isolation(crm_services) -> None:
    first, second, company, _, _ = crm_services
    contact = first.create_contact(company, "Alex", "Buyer")
    assert first.archive_contact(contact.id).status == "ARCHIVED"
    assert first.restore_contact(contact.id).status == "ACTIVE"
    with pytest.raises(CrmError):
        second.archive_contact(contact.id)


def test_cross_tenant_company_relationship_is_rejected(crm_services) -> None:
    first, _, _, foreign_company, _ = crm_services
    with pytest.raises(CrmError):
        first.create_contact(foreign_company, "No", "Access")
    with pytest.raises(CrmError):
        first.create_lead("No access", company_id=foreign_company)


def test_lead_numbering_scoring_and_breakdown(crm_services) -> None:
    service, _, company, _, _ = crm_services
    first = service.create_lead(
        "Qualified profile",
        company_id=company,
        website="https://example.test",
        industry="Technology",
        country="India",
        email="buyer@example.test",
    )
    second = service.create_lead("Second", company_id=company)
    assert first.lead_number.endswith("0001") and second.lead_number.endswith("0002")
    assert first.score == 60
    assert "website" in first.score_breakdown_json


@pytest.mark.parametrize(
    "score,band",
    [
        (0, "NOT_QUALIFIED"),
        (40, "MARKETING_QUALIFIED"),
        (60, "SALES_QUALIFIED"),
        (100, "SALES_QUALIFIED"),
    ],
)
def test_qualification_bands(score: int, band: str) -> None:
    assert qualification_band(score) == band


def test_deterministic_score_is_bounded() -> None:
    score, breakdown = score_lead(
        {
            "industry": "Tech",
            "country": "IN",
            "website": "https://example.test",
            "contact_id": 1,
            "company_size": "11-50",
            "discovery_completed": True,
            "automation_score": 90,
            "lead_priority_score": 80,
        }
    )
    assert score == 100 and sum(breakdown.values()) == 100


def test_lead_lifecycle_requires_valid_transition_and_disqualification_reason(
    crm_services,
) -> None:
    service, _, company, _, _ = crm_services
    lead = service.create_lead("Lifecycle", company_id=company)
    with pytest.raises(CrmError):
        service.transition_lead(lead.id, "QUALIFIED")
    lead = service.transition_lead(lead.id, "CONTACTED")
    assert service.transition_lead(lead.id, "QUALIFIED").status == "QUALIFIED"
    other = service.create_lead("Other", company_id=company)
    with pytest.raises(CrmError):
        service.transition_lead(other.id, "DISQUALIFIED")


def test_lead_conversion_is_atomic_and_cannot_repeat(crm_services) -> None:
    service, _, company, _, _ = crm_services
    lead = service.create_lead("Convert me", company_id=company)
    service.transition_lead(lead.id, "CONTACTED")
    service.transition_lead(lead.id, "QUALIFIED")
    opportunity = service.convert_lead_to_opportunity(
        lead.id, "Converted opportunity", Decimal(1000), "usd"
    )
    assert opportunity.weighted_amount == Decimal("100.00")
    assert service.list("lead").items[0].status == "CONVERTED"
    with pytest.raises(CrmError):
        service.convert_lead_to_opportunity(lead.id, "Again", Decimal(1))


def test_opportunity_weighting_stage_history_and_close(crm_services) -> None:
    service, _, company, _, factory = crm_services
    opportunity = service.create_opportunity(
        company, "Pipeline", Decimal(500), probability_percentage=40
    )
    assert opportunity.weighted_amount == Decimal("200.00")
    stages = service.list("stage", page_size=20).items
    won = next(stage for stage in stages if stage.code == "WON")
    closed = service.move_opportunity(opportunity.id, won.id, "Won through review")
    assert closed.status == "WON" and closed.weighted_amount == Decimal("500.00")
    with factory() as session:
        assert (
            session.execute(
                __import__("sqlalchemy").select(
                    __import__(
                        "leadpilot.infrastructure.database.models",
                        fromlist=["CrmStageHistoryModel"],
                    ).CrmStageHistoryModel
                )
            )
            .scalars()
            .all()
        )


def test_task_dates_relationships_and_completion(crm_services) -> None:
    service, _, company, _, _ = crm_services
    lead = service.create_lead("Task lead", company_id=company)
    due = datetime.now(UTC) + timedelta(days=1)
    with pytest.raises(CrmError):
        service.create_related(
            "task",
            "Bad",
            {"lead_id": lead.id},
            due_at=due,
            reminder_at=due + timedelta(hours=1),
        )
    task = service.create_related(
        "task", "Follow up", {"lead_id": lead.id}, due_at=due, reminder_at=due
    )
    assert service.complete("task", task.id).status == "COMPLETED"


def test_activity_note_and_timeline(crm_services) -> None:
    service, _, company, _, _ = crm_services
    lead = service.create_lead("Timeline lead", company_id=company)
    service.create_related(
        "activity", "Client call", {"lead_id": lead.id}, activity_type="CALL"
    )
    service.create_related(
        "note", "Important context", {"lead_id": lead.id}, is_pinned=True
    )
    timeline = service.timeline("lead", lead.id)
    assert {item.source for item in timeline} == {"ACTIVITY", "NOTE"}
    with pytest.raises(CrmError):
        service.create_related("note", "<script>bad</script>", {"lead_id": lead.id})


def test_csv_preview_import_limits_and_formula_neutralization(crm_services) -> None:
    service, _, _, _, _ = crm_services
    content = (
        b"title,industry,estimated_value\nSafe,Tech,100\n=FORMULA,Tech,200\n,Tech,300\n"
    )
    preview = service.preview_csv(content)
    assert len(preview.valid_rows) == 2 and len(preview.errors) == 1
    assert preview.valid_rows[1]["title"].startswith("'")
    assert neutralize_formula("+cmd") == "'+cmd"
    service.import_csv(content, dry_run=False)
    assert service.list("lead").total == 2


def test_search_metrics_and_safe_csv_export(crm_services) -> None:
    service, _, company, _, _ = crm_services
    service.create_lead("=Dangerous title", company_id=company)
    assert service.search("Dangerous")["leads"]
    exported = service.export_csv("lead")
    assert b"'=Dangerous title" in exported
    assert service.metrics()["leads"]["NEW"] == 1


def test_authorization_boundaries() -> None:
    class Repo:
        def metrics(self):
            return {}

    denied = CrmService(
        Repo(),
        None,
        lambda: None,
        lambda: (_ for _ in ()).throw(PermissionError("denied")),
    )
    with pytest.raises(PermissionError):
        denied.create_lead("Blocked")
