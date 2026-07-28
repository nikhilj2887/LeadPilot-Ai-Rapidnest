from __future__ import annotations

from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError

from leadpilot.application.ai_evidence import (
    build_snapshot,
    evidence_references,
    snapshot_hash,
)
from leadpilot.application.ai_prompt import PROMPT_VERSION, build_prompt
from leadpilot.application.ai_provider import (
    AIProviderDisabled,
    AIRequest,
    DisabledAIProvider,
)
from leadpilot.application.ai_schema import AIIntelligenceOutput
from leadpilot.application.discovery import DiscoveryScan
from leadpilot.application.discovery_ai import calculate_cost
from leadpilot.infrastructure.ai_providers import FakeAIProvider
from leadpilot.infrastructure.database.ai_analysis_repository import (
    AIAnalysisRepository,
)
from leadpilot.infrastructure.database.company_repository import CompanyRepository
from leadpilot.infrastructure.database.discovery_repository import DiscoveryRepository
from leadpilot.infrastructure.database.engine import create_database_engine
from leadpilot.infrastructure.database.session import create_session_factory


def _repositories(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'ai.db'}"
    monkeypatch.setenv("LEADPILOT_DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "head")
    factory = create_session_factory(create_database_engine(url))
    return (
        CompanyRepository(factory),
        DiscoveryRepository(factory),
        AIAnalysisRepository(factory),
    )


def test_fake_provider_returns_schema_valid_output_and_tokens() -> None:
    response = FakeAIProvider().generate(
        AIRequest("system", "evidence", "fake", 0.2, 6000)
    )
    assert isinstance(response.output, AIIntelligenceOutput)
    assert response.total_tokens == 1100
    assert evidence_references(response.output) == {"website.https"}


def test_disabled_and_fake_failure_modes() -> None:
    request = AIRequest("system", "evidence", "fake", 0.2, 6000)
    with pytest.raises(AIProviderDisabled):
        DisabledAIProvider().generate(request)
    with pytest.raises(Exception, match="timed out"):
        FakeAIProvider("timeout").generate(request)


def test_schema_rejects_invalid_labels() -> None:
    valid = (
        FakeAIProvider()
        .generate(AIRequest("s", "e", "fake", 0.2, 10))
        .output.model_dump()
    )
    valid["quick_wins"][0]["priority"] = "Urgent"
    with pytest.raises(ValidationError):
        AIIntelligenceOutput.model_validate(valid)


def test_snapshot_is_stable_and_prompt_excludes_secrets_and_html() -> None:
    scan = DiscoveryScan(
        1,
        2,
        "https://example.com",
        "Completed",
        None,
        None,
        None,
        {
            "is_https": True,
            "response_time_ms": 100,
            "detected_technologies": [],
            "website_health_score": 80,
            "digital_maturity_score": 60,
            "ai_readiness_score": 50,
            "automation_potential_score": 70,
            "lead_priority_score": 72,
            "score_details": {},
            "findings": [],
            "recommendations": [],
        },
        SimpleNamespace(),
        SimpleNamespace(),
    )
    company = SimpleNamespace(
        name="Acme",
        website=scan.website_url,
        industry=None,
        country=None,
        city=None,
        company_size=None,
    )
    snapshot = build_snapshot(company, scan)
    assert snapshot_hash(snapshot) == snapshot_hash(snapshot)
    system, evidence = build_prompt(snapshot)
    assert PROMPT_VERSION == "leadpilot-ai-v2"
    assert "untrusted" in system
    assert "<html" not in evidence.lower()
    assert "api_key" not in evidence.lower()


def test_repository_history_review_completion_and_cascade(
    tmp_path, monkeypatch
) -> None:
    companies, scans, analyses = _repositories(tmp_path, monkeypatch)
    company = companies.create(
        {
            "name": "AI Acme",
            "website": "https://example.com",
            "industry": None,
            "country": None,
            "city": None,
            "company_size": None,
            "status": "New",
            "source": None,
            "notes": None,
        }
    )
    scan = scans.create(company.id, company.website or "")
    first = analyses.create(
        discovery_scan_id=scan.id,
        company_id=company.id,
        provider="fake",
        model="fake",
        prompt_version="v1",
        schema_version="1",
        input_snapshot_hash="a" * 64,
    )
    analyses.update_status(first.id, "Running")
    output = (
        FakeAIProvider()
        .generate(AIRequest("s", "e", "fake", 0.2, 10))
        .output.model_dump()
    )
    completed = analyses.save_completed(
        first.id, **output, evidence_references=["website.https"]
    )
    assert completed.status == "Completed"
    assert analyses.get_latest_by_scan(scan.id).id == first.id
    assert (
        analyses.update_review(first.id, "Reviewed", "Checked").review_status
        == "Reviewed"
    )
    second = analyses.create(
        discovery_scan_id=scan.id,
        company_id=company.id,
        provider="fake",
        model="fake",
        prompt_version="v1",
        schema_version="1",
        input_snapshot_hash="b" * 64,
    )
    assert [item.id for item in analyses.list_by_scan(scan.id)] == [second.id, first.id]
    assert companies.delete(company.id)
    assert analyses.count() == 0


def test_cost_requires_explicit_rates() -> None:
    assert calculate_cost(1000, 2000, None, None) is None
    assert calculate_cost(1_000_000, 500_000, 2.0, 4.0) == 4.0
