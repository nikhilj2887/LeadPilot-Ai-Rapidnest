from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from leadpilot.application.companies import (
    COMPANY_SIZES,
    COMPANY_STATUSES,
    Company,
    CompanyNotFoundError,
    CompanyService,
    CompanyValidationError,
)
from leadpilot.infrastructure.database.base import Base
from leadpilot.infrastructure.database.company_repository import CompanyRepository
from leadpilot.presentation.streamlit.pages.companies import (
    PAGE_SIZE,
    filter_companies,
    paginate,
)


@pytest.fixture
def repository() -> CompanyRepository:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    return CompanyRepository(factory)


@pytest.fixture
def service(repository: CompanyRepository) -> CompanyService:
    return CompanyService(repository)


def company_values(name: str, **overrides: str) -> dict[str, str]:
    values = {
        "website": f"https://{name.lower()}.example",
        "industry": "Technology",
        "country": "Canada",
        "city": "Toronto",
        "company_size": "11-50",
        "status": "New",
        "source": "Referral",
        "notes": "Follow up",
    }
    values.update(overrides)
    return {"name": name, **values}


def test_repository_supports_crud_and_lookup(repository: CompanyRepository) -> None:
    created = repository.create(company_values("RapidNest"))
    assert repository.count() == 1
    assert repository.get_by_id(created.id).name == "RapidNest"  # type: ignore[union-attr]
    assert repository.get_by_name("rapidnest").id == created.id  # type: ignore[union-attr]
    assert [item.name for item in repository.list_all()] == ["RapidNest"]

    updated = repository.update(created.id, {"status": "Qualified", "city": "Ottawa"})
    assert updated is not None and updated.status == "Qualified"
    assert repository.delete(created.id)
    assert repository.get_by_id(created.id) is None
    assert repository.delete(created.id) is False


@pytest.mark.parametrize(
    "query", ["rapid", "RAPIDNEST.EXAMPLE", "tech", "CANADA", "toron"]
)
def test_repository_searches_all_required_fields_case_insensitively(
    repository: CompanyRepository, query: str
) -> None:
    repository.create(company_values("RapidNest"))
    assert [company.name for company in repository.search(query)] == ["RapidNest"]


def test_repository_aggregates_and_lists_recent(repository: CompanyRepository) -> None:
    repository.create(company_values("Alpha", status="Qualified"))
    repository.create(
        company_values("Beta", status="Qualified", country="USA", industry="Finance")
    )
    repository.create(company_values("Gamma", status="Contacted"))

    assert repository.count_by_status() == {"Contacted": 1, "Qualified": 2}
    assert repository.count_by_country() == {"Canada": 2, "USA": 1}
    assert repository.count_by_industry() == {"Finance": 1, "Technology": 2}
    assert [company.name for company in repository.list_recent(2)] == ["Gamma", "Beta"]


def test_company_service_crud_fields_metrics_and_normalization(
    service: CompanyService,
) -> None:
    created = service.create_company(
        name="RapidNest",
        website="rapidnest.example/path",
        industry="Real Estate",
        country="Canada",
        city="Toronto",
        company_size="11-50",
        status="New",
        source="Referral",
        notes="Priority lead",
    )
    assert created.website == "https://rapidnest.example/path"
    assert created.country == "Canada"
    assert created.company_size == "11-50"
    assert created.source == "Referral"

    updated = service.update_company(
        created.id,
        name="RapidNest AI",
        website="http://rapidnest.example",
        industry="Technology",
        country="United States",
        city="Austin",
        company_size="51-200",
        status="Qualified",
        source="Conference",
        notes=None,
    )
    assert updated.status == "Qualified"
    service.create_company(name="New Lead", status="New")
    service.create_company(name="Contacted Lead", status="Contacted")
    service.create_company(name="Proposal Lead", status="Proposal")
    metrics = service.metrics()
    assert (metrics.total, metrics.new, metrics.qualified) == (4, 1, 1)
    assert (metrics.contacted, metrics.proposal) == (1, 1)
    assert set(metrics.by_status) == set(COMPANY_STATUSES)
    assert service.search_companies("united STATES") == [updated]
    assert service.recent_companies(1)[0].name == "Proposal Lead"
    assert service.counts_by_country() == {"United States": 1}
    assert service.counts_by_industry() == {"Technology": 1}

    service.delete_company(created.id)
    with pytest.raises(CompanyNotFoundError):
        service.get_company(created.id)


def test_required_company_values_are_exact() -> None:
    assert COMPANY_SIZES == (
        "Solo",
        "2-10",
        "11-50",
        "51-200",
        "201-500",
        "501-1000",
        "1000+",
    )
    assert COMPANY_STATUSES == (
        "New",
        "Researching",
        "Qualified",
        "Contacted",
        "Proposal",
        "Won",
        "Lost",
    )


@pytest.mark.parametrize("company_size", COMPANY_SIZES)
def test_all_company_sizes_are_accepted(
    service: CompanyService, company_size: str
) -> None:
    created = service.create_company(
        name=f"Company {company_size}", company_size=company_size
    )
    assert created.company_size == company_size


@pytest.mark.parametrize("status", COMPANY_STATUSES)
def test_all_statuses_are_accepted(service: CompanyService, status: str) -> None:
    created = service.create_company(name=f"Company {status}", status=status)
    assert created.status == status


@pytest.mark.parametrize(
    ("website", "expected"),
    [
        ("example.com", "https://example.com"),
        ("https://example.com", "https://example.com"),
        ("http://example.com/path", "http://example.com/path"),
        (None, None),
    ],
)
def test_website_normalization(website: str | None, expected: str | None) -> None:
    assert CompanyService.normalize_website(website) == expected


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"name": " "}, "name is required"),
        ({"name": "Acme", "website": "not-a-domain"}, "valid domain"),
        ({"name": "Acme", "company_size": "Large"}, "size is invalid"),
        ({"name": "Acme", "status": "prospect"}, "status is invalid"),
    ],
)
def test_company_validation(
    service: CompanyService, values: dict[str, str], message: str
) -> None:
    with pytest.raises(CompanyValidationError, match=message):
        service.create_company(**values)


def test_company_names_are_unique_case_insensitively(service: CompanyService) -> None:
    service.create_company(name="Acme")
    with pytest.raises(CompanyValidationError, match="already exists"):
        service.create_company(name="acme")


def sample_company(number: int, **overrides: str) -> Company:
    values = {
        "name": f"Company {number}",
        "website": f"https://company{number}.example",
        "industry": "Technology",
        "country": "Canada",
        "city": "Toronto",
        "company_size": "2-10",
        "status": "New",
        "source": None,
        "notes": None,
    }
    values.update(overrides)
    now = datetime.now(UTC)
    return Company(id=number, created_at=now, updated_at=now, **values)


def test_ui_filtering_covers_search_and_all_filters() -> None:
    companies = [
        sample_company(1),
        sample_company(2, industry="Finance", country="USA", status="Won"),
    ]
    assert filter_companies(companies, query="COMPANY1.EXAMPLE") == [companies[0]]
    assert filter_companies(companies, status="Won") == [companies[1]]
    assert filter_companies(companies, industry="Finance") == [companies[1]]
    assert filter_companies(companies, country="USA") == [companies[1]]


def test_ui_pagination_uses_ten_items_per_page() -> None:
    companies = [sample_company(number) for number in range(1, 13)]
    assert PAGE_SIZE == 10
    assert paginate(companies, 1) == companies[:10]
    assert paginate(companies, 2) == companies[10:]


def test_ui_and_dashboard_expose_required_controls_and_sections() -> None:
    root = Path(__file__).parents[1]
    companies_page = (
        root / "src/leadpilot/presentation/streamlit/pages/companies.py"
    ).read_text()
    dashboard = (
        root / "src/leadpilot/presentation/streamlit/pages/dashboard.py"
    ).read_text()
    for label in (
        "Add Company",
        "Edit",
        "View",
        "Delete",
        "Search",
        "Status",
        "Industry",
        "Country",
        "Clear Filters",
        "Page",
        "I confirm",
        "selected_company",
    ):
        assert label in companies_page
    for label in (
        "Total Companies",
        "New Leads",
        "Qualified Leads",
        "Contacted Leads",
        "Proposal Stage",
        "Recent Companies",
        "Companies by Status",
    ):
        assert label in dashboard


def test_only_one_navigation_menu_is_defined() -> None:
    root = Path(__file__).parents[1]
    streamlit_source = "".join(
        path.read_text()
        for path in (root / "src/leadpilot/presentation/streamlit").rglob("*.py")
    )
    assert streamlit_source.count("st.sidebar.radio(") == 1
