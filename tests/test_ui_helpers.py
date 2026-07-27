from datetime import UTC, datetime, timedelta
from pathlib import Path

from leadpilot.application.companies import COMPANY_STATUSES, Company, CompanyMetrics
from leadpilot.presentation.streamlit.company_query import (
    PAGE_SIZE,
    build_page,
    filter_companies,
    sort_companies,
)
from leadpilot.presentation.streamlit.components import (
    STATUS_STYLES,
    is_empty,
    status_badge,
    validate_status_styles,
)
from leadpilot.presentation.streamlit.pages.dashboard import kpi_values
from leadpilot.presentation.streamlit.state import (
    open_company_mode,
    reset_company_filters,
    return_to_company_list,
    sync_filter_page,
)


def company(
    company_id: int,
    name: str,
    *,
    status: str = "New",
    industry: str = "Technology",
    country: str = "Canada",
    days_old: int = 0,
) -> Company:
    timestamp = datetime.now(UTC) - timedelta(days=days_old)
    return Company(
        id=company_id,
        name=name,
        website=f"https://{name.casefold()}.example",
        industry=industry,
        country=country,
        city="Toronto",
        company_size="11-50",
        status=status,
        source="Referral",
        notes=None,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_kpi_mapping_uses_dashboard_metric_fields_in_display_order() -> None:
    metrics = CompanyMetrics(
        total=10,
        new=4,
        qualified=3,
        contacted=2,
        proposal=1,
        by_status={status: 0 for status in COMPANY_STATUSES},
    )
    assert [(label, value) for label, value, _ in kpi_values(metrics)] == [
        ("Total Companies", 10),
        ("New Leads", 4),
        ("Qualified Leads", 3),
        ("Contacted Leads", 2),
        ("Proposal Stage", 1),
    ]


def test_filtering_combines_search_and_facets() -> None:
    items = [
        company(1, "Alpha", status="Qualified"),
        company(2, "Beta", status="Won", industry="Finance", country="USA"),
    ]
    assert filter_companies(
        items, query="beta.example", status="Won", industry="Finance", country="USA"
    ) == [items[1]]
    assert filter_companies(items, query="missing") == []


def test_all_sort_options_have_deterministic_behavior() -> None:
    alpha = company(1, "Alpha", status="Won", days_old=2)
    beta = company(2, "Beta", status="New", days_old=1)
    items = [beta, alpha]
    assert sort_companies(items, "Name A-Z") == [alpha, beta]
    assert sort_companies(items, "Name Z-A") == [beta, alpha]
    assert sort_companies(items, "Recently Updated") == [beta, alpha]
    assert sort_companies(items, "Recently Added") == [beta, alpha]
    assert sort_companies(items, "Status") == [beta, alpha]


def test_page_builder_clamps_page_and_uses_ten_rows() -> None:
    items = [company(number, f"Company {number}") for number in range(1, 13)]
    page = build_page(items, 99)
    assert PAGE_SIZE == 10
    assert (page.number, page.count, page.total_items) == (2, 2, 12)
    assert page.items == items[10:]
    empty_page = build_page([], 3)
    assert (empty_page.number, empty_page.count, empty_page.items) == (1, 1, [])


def test_empty_state_and_status_badge_helpers() -> None:
    assert is_empty([])
    assert not is_empty([1])
    assert validate_status_styles()
    assert set(STATUS_STYLES) == set(COMPANY_STATUSES)
    assert "Qualified" in status_badge("Qualified")
    assert "lp-qualified" in status_badge("Qualified")


def test_session_state_helpers_reset_filters_page_and_selection() -> None:
    state: dict[str, object] = {
        "company_search": "Acme",
        "company_status": "Won",
        "company_page": 4,
        "selected_company": 9,
    }
    reset_company_filters(state)
    assert state["company_search"] == ""
    assert state["company_status"] == "All"
    assert state["company_page"] == 1
    sync_filter_page(state, ("", "All"))
    state["company_page"] = 2
    sync_filter_page(state, ("query", "All"))
    assert state["company_page"] == 1
    open_company_mode(state, "view", 12)
    assert state["selected_company"] == 12
    return_to_company_list(state)
    assert state["company_mode"] == "list"
    assert "selected_company" not in state


def test_navigation_is_single_and_no_reserved_pages_directory_exists() -> None:
    root = Path(__file__).parents[1]
    streamlit_root = root / "src/leadpilot/presentation/streamlit"
    source = "".join(path.read_text() for path in streamlit_root.rglob("*.py"))
    assert source.count("st.sidebar.radio(") == 1
    assert not (root / "pages").exists()
    assert not (streamlit_root / "pages.py").exists()


def test_ui_sources_include_milestone_sections_and_controls() -> None:
    streamlit_root = Path(__file__).parents[1] / "src/leadpilot/presentation/streamlit"
    root = streamlit_root / "pages"
    companies_source = "".join(
        path.read_text()
        for path in (root / "companies.py", streamlit_root / "company_query.py")
    )
    detail_labels = (
        "Company Information",
        "Location",
        "Lead Management",
        "Additional Information",
        "Company Overview",
        "Lead Information",
        "Record Metadata",
        "Contacts",
        "Activities",
        "AI Insights",
        "Discovery Audit",
        "Recently Updated",
        "Clear Filters",
        "Previous",
        "Next",
    )
    assert all(label in companies_source for label in detail_labels)
    assert "Website Scan" in (root / "discovery.py").read_text()
    assert "PDF Export" in (root / "proposals.py").read_text()
