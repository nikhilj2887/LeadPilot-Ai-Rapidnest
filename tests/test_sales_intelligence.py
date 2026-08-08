from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from leadpilot.application.crm import CrmService
from leadpilot.application.sales_intelligence import (
    SalesIntelligenceError,
    SalesIntelligenceService,
    health_band,
    lead_priority_score,
    opportunity_health_score,
    priority_band,
    snapshot_hash,
)
from leadpilot.infrastructure.database.base import Base
from leadpilot.infrastructure.database.crm_repository import SqlAlchemyCrmRepository
from leadpilot.infrastructure.database.models import CompanyModel, OrganizationModel
from leadpilot.infrastructure.database.sales_intelligence_repository import (
    SqlAlchemySalesIntelligenceRepository,
)


@pytest.fixture
def intelligence_services():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False, class_=Session)
    with factory.begin() as session:
        first = OrganizationModel(slug="intel-one", display_name="Intel One")
        second = OrganizationModel(slug="intel-two", display_name="Intel Two")
        session.add_all((first, second))
        session.flush()
        first_company = CompanyModel(organization_id=first.id, name="Synthetic One")
        second_company = CompanyModel(organization_id=second.id, name="Synthetic Two")
        session.add_all((first_company, second_company))
        session.flush()
        ids = first.id, second.id, first_company.id, second_company.id

    def build(organization_id: int) -> SalesIntelligenceService:
        crm = CrmService(SqlAlchemyCrmRepository(factory, organization_id), None)
        return SalesIntelligenceService(
            SqlAlchemySalesIntelligenceRepository(factory, organization_id), crm
        )

    return build(ids[0]), build(ids[1]), ids[2], ids[3], factory


def test_config_defaults_update_and_validation(intelligence_services) -> None:
    service, _, _, _, _ = intelligence_services
    assert service.get_config()["stale_lead_days"] == 14
    assert service.update_config(stale_lead_days=30).stale_lead_days == 30
    with pytest.raises(SalesIntelligenceError):
        service.update_config(stale_lead_days=-1)
    with pytest.raises(SalesIntelligenceError):
        service.update_config(forecast_commit_threshold=101)


@pytest.mark.parametrize(
    "score,band",
    [(0, "LOW"), (40, "MEDIUM"), (60, "HIGH"), (80, "URGENT"), (100, "URGENT")],
)
def test_priority_bands(score: int, band: str) -> None:
    assert priority_band(score) == band


@pytest.mark.parametrize(
    "score,band",
    [
        (0, "CRITICAL"),
        (40, "AT_RISK"),
        (60, "WATCH"),
        (80, "HEALTHY"),
        (100, "HEALTHY"),
    ],
)
def test_health_bands(score: int, band: str) -> None:
    assert health_band(score) == band


def test_deterministic_lead_priority_is_bounded_and_explainable() -> None:
    score, breakdown, flags = lead_priority_score(
        {
            "score": 100,
            "source": "DISCOVERY",
            "estimated_value": Decimal(1000),
            "email": "safe@example.test",
            "owner_user_id": 1,
            "last_activity_at": datetime.now(UTC),
            "next_follow_up_at": datetime.now(UTC) + timedelta(days=1),
            "discovery_completed": True,
            "proposal_engagement": 15,
        }
    )
    assert 0 <= score <= 100 and sum(breakdown.values()) == score and not flags
    stale_score, _, stale_flags = lead_priority_score({"score": 0, "source": "OTHER"})
    assert stale_score < score and {"STALE", "UNASSIGNED", "NO_CONTACT"} <= set(
        stale_flags
    )


def test_opportunity_health_detects_close_and_task_risks() -> None:
    score, breakdown, flags = opportunity_health_score(
        {
            "amount": Decimal(10),
            "probability_percentage": 20,
            "expected_close_date": datetime.now(UTC).date() - timedelta(days=1),
            "overdue_tasks": 2,
        }
    )
    assert 0 <= score <= 100 and sum(breakdown.values()) == score
    assert {
        "STALE",
        "OVERDUE_TASKS",
        "CLOSE_DATE_PASSED",
        "NO_PRIMARY_CONTACT",
        "NO_NEXT_STEP",
        "UNASSIGNED",
    } <= set(flags)


def test_score_hash_is_stable_and_sensitive() -> None:
    assert snapshot_hash({"b": 2, "a": 1}) == snapshot_hash({"a": 1, "b": 2})
    assert snapshot_hash({"a": 1}) != snapshot_hash({"a": 2})


def test_lead_priority_history_and_tenant_isolation(intelligence_services) -> None:
    first, second, company, _, _ = intelligence_services
    lead = first.crm.create_lead(
        "Synthetic lead",
        company_id=company,
        email="buyer@example.test",
        estimated_value=Decimal(5000),
    )
    initial = first.calculate_lead_priority(lead.id)
    later = first.calculate_lead_priority(lead.id)
    assert (
        initial.lead_id == lead.id
        and len(first.get_score_history("lead", lead.id)) == 2
    )
    assert first.get_latest_score("lead", lead.id).id == later.id
    with pytest.raises(SalesIntelligenceError):
        second.calculate_lead_priority(lead.id)


def test_opportunity_health_history_and_no_live_mutation(intelligence_services) -> None:
    first, _, company, _, _ = intelligence_services
    opportunity = first.crm.create_opportunity(
        company, "Synthetic deal", Decimal(1200), probability_percentage=40
    )
    before = first.crm.repo.get("opportunity", opportunity.id)
    result = first.calculate_health(opportunity.id)
    after = first.crm.repo.get("opportunity", opportunity.id)
    assert (
        result.opportunity_id == opportunity.id
        and len(first.get_score_history("opportunity", opportunity.id)) == 1
    )
    assert (
        before.stage_id,
        before.owner_user_id,
        before.amount,
        before.probability_percentage,
        before.expected_close_date,
    ) == (
        after.stage_id,
        after.owner_user_id,
        after.amount,
        after.probability_percentage,
        after.expected_close_date,
    )


def test_recommendation_requires_review_and_creates_task_only(
    intelligence_services,
) -> None:
    first, _, company, _, _ = intelligence_services
    lead = first.crm.create_lead("Needs follow-up", company_id=company)
    recommendations = first.generate_recommendations("lead", lead.id)
    assert recommendations and all(
        x.status == "PENDING_REVIEW" for x in recommendations
    )
    with pytest.raises(SalesIntelligenceError):
        first.apply_recommendation(recommendations[0].id)
    approved = first.approve_recommendation(recommendations[0].id)
    applied = first.apply_recommendation(approved.id)
    assert applied.status == "APPLIED" and applied.applied_task_id
    assert first.crm.repo.get("lead", lead.id).status == "NEW"


def test_recommendation_reject_duplicate_and_cross_tenant(
    intelligence_services,
) -> None:
    first, second, company, _, _ = intelligence_services
    lead = first.crm.create_lead("Duplicate candidate", company_id=company)
    first_batch = first.generate_recommendations("LEAD", lead.id)
    second_batch = first.generate_recommendations("LEAD", lead.id)
    assert [x.id for x in first_batch] == [x.id for x in second_batch]
    assert first.reject_recommendation(first_batch[0].id).status == "REJECTED"
    with pytest.raises(SalesIntelligenceError):
        second.repo.get_recommendation(first_batch[0].id)


def test_structured_ai_recommendations_are_validated_and_remain_pending(
    intelligence_services,
) -> None:
    first, _, company, _, _ = intelligence_services
    lead = first.crm.create_lead("AI evidence", company_id=company)
    payload = {
        "recommendations": [
            {
                "recommendation_type": "FOLLOW_UP",
                "priority": "HIGH",
                "title": "Review the lead",
                "description": "Confirm the next step using the supplied evidence.",
                "reasoning": ["No recent activity"],
                "source_references": [
                    {"source_type": "LEAD", "source_id": lead.lead_number}
                ],
            }
        ]
    }
    result = first.record_ai_recommendations("lead", lead.id, payload, ai_run_id=1)
    assert result[0].status == "PENDING_REVIEW"
    assert first.crm.repo.get("lead", lead.id).status == "NEW"


@pytest.mark.parametrize(
    "mutation",
    [
        {"recommendation_type": "UNKNOWN", "priority": "HIGH"},
        {
            "recommendation_type": "FOLLOW_UP",
            "priority": "HIGH",
            "stage_id": 99,
        },
        {"recommendation_type": "FOLLOW_UP", "priority": "INVALID"},
    ],
)
def test_ai_recommendations_reject_unknown_types_and_mutations(
    intelligence_services, mutation: dict[str, object]
) -> None:
    first, _, company, _, _ = intelligence_services
    lead = first.crm.create_lead("Unsafe AI output", company_id=company)
    mutation.update(
        title="Unsafe suggestion",
        description="Do not apply automatically.",
        source_references=[{"source_type": "LEAD", "source_id": lead.lead_number}],
    )
    with pytest.raises(SalesIntelligenceError):
        first.record_ai_recommendations(
            "lead", lead.id, {"recommendations": [mutation]}, ai_run_id=1
        )


def test_forecast_decimal_currency_scenario_snapshots_and_no_mutation(
    intelligence_services,
) -> None:
    first, _, company, _, _ = intelligence_services
    usd = first.crm.create_opportunity(
        company,
        "USD deal",
        Decimal("100.01"),
        currency="USD",
        probability_percentage=50,
    )
    eur = first.crm.create_opportunity(
        company,
        "EUR deal",
        Decimal("200.00"),
        currency="EUR",
        probability_percentage=80,
    )
    before = first.crm.repo.get("opportunity", usd.id)
    forecasts = first.generate_forecast(
        datetime.now(UTC).date(),
        datetime.now(UTC).date() + timedelta(days=90),
        "SCENARIO",
        {"probability_adjustment": 10},
    )
    assert {x.currency for x in forecasts} == {"USD", "EUR"}
    assert next(
        x for x in forecasts if x.currency == "USD"
    ).weighted_pipeline_amount == Decimal("60.01")
    assert len(first.repo.list_forecasts()) == 2
    after = first.crm.repo.get("opportunity", usd.id)
    assert (before.amount, before.probability_percentage, before.stage_id) == (
        after.amount,
        after.probability_percentage,
        after.stage_id,
    )
    assert eur.currency == "EUR"


def test_pipeline_risk_and_formula_safe_export(intelligence_services) -> None:
    first, _, company, _, _ = intelligence_services
    first.crm.create_opportunity(
        company, "Concentrated", Decimal(1000), probability_percentage=10
    )
    risks = first.pipeline_risks()
    assert any(x["risk_type"] == "OPPORTUNITY_CONCENTRATION" for x in risks)
    exported = first.export_csv(
        ({"title": "=unsafe", "entity_id": 99, "notes": "secret", "amount": 10},)
    ).decode()
    assert (
        "'=unsafe" in exported
        and "entity_id" not in exported
        and "secret" not in exported
    )


def test_team_metrics_include_unassigned_and_insufficient_data(
    intelligence_services,
) -> None:
    first, _, company, _, _ = intelligence_services
    first.crm.create_lead("Unassigned", company_id=company)
    metrics = first.team_metrics()
    assert any(x["owner"] == "Unassigned" and x["leads"] == 1 for x in metrics)


def test_win_loss_requires_closed_tenant_opportunity(intelligence_services) -> None:
    first, second, company, _, _ = intelligence_services
    opportunity = first.crm.create_opportunity(company, "Open", Decimal(500))
    with pytest.raises(SalesIntelligenceError):
        first.analyze_opportunity(opportunity.id, "Not closed")
    stages = first.crm.list("stage", page_size=20).items
    won = next(x for x in stages if x.code == "WON")
    first.crm.move_opportunity(opportunity.id, won.id, "Confirmed win")
    analysis = first.analyze_opportunity(opportunity.id, "Strong product fit")
    assert analysis.outcome == "WON" and analysis.primary_reason == "Strong product fit"
    with pytest.raises(SalesIntelligenceError):
        second.analyze_opportunity(opportunity.id, "No access")


def test_authorization_boundaries(intelligence_services) -> None:
    first, _, company, _, _ = intelligence_services
    lead = first.crm.create_lead("Authorization", company_id=company)
    denied = lambda: (_ for _ in ()).throw(PermissionError("denied"))
    viewer = SalesIntelligenceService(
        first.repo,
        first.crm,
        authorize_calculate=denied,
        authorize_manage=denied,
        authorize_admin=denied,
    )
    assert viewer.get_config()
    with pytest.raises(PermissionError):
        viewer.calculate_lead_priority(lead.id)
    with pytest.raises(PermissionError):
        viewer.generate_forecast(datetime.now(UTC).date(), datetime.now(UTC).date())
    with pytest.raises(PermissionError):
        viewer.update_config(stale_lead_days=10)
