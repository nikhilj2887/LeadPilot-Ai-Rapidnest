from __future__ import annotations

from alembic import command
from alembic.config import Config

from leadpilot.infrastructure.database.company_repository import CompanyRepository
from leadpilot.infrastructure.database.discovery_repository import DiscoveryRepository
from leadpilot.infrastructure.database.engine import create_database_engine
from leadpilot.infrastructure.database.session import create_session_factory


def repositories(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'discovery.db'}"
    monkeypatch.setenv("LEADPILOT_DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    factory = create_session_factory(create_database_engine(url))
    return CompanyRepository(factory), DiscoveryRepository(factory)


def test_repository_lifecycle_and_summary(tmp_path, monkeypatch) -> None:
    companies, scans = repositories(tmp_path, monkeypatch)
    company = companies.create(
        {
            "name": "Acme",
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
    assert scan.status == "Pending"
    scans.update_status(scan.id, "Running")
    completed = scans.save_completed_result(
        scan.id,
        {
            "website_health_score": 80,
            "digital_maturity_score": 60,
            "ai_readiness_score": 50,
            "automation_potential_score": 70,
            "lead_priority_score": 72,
            "detected_emails": ["hi@example.com"],
        },
    )
    assert completed.status == "Completed"
    assert completed.detected_emails == ["hi@example.com"]
    assert scans.get_latest_by_company(company.id).id == scan.id
    assert scans.list_by_status("Completed")[0].id == scan.id
    assert scans.summary().high_priority == 1


def test_company_delete_cascades_scans(tmp_path, monkeypatch) -> None:
    companies, scans = repositories(tmp_path, monkeypatch)
    company = companies.create(
        {
            "name": "Delete Me",
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
    scans.create(company.id, company.website or "")
    assert companies.delete(company.id) is True
    assert scans.count() == 0
