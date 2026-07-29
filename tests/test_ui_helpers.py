from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from leadpilot.application.companies import COMPANY_STATUSES, Company, CompanyMetrics
from leadpilot.presentation.streamlit.app import (
    organization_selector_required,
    render_page_safely,
)
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
from leadpilot.presentation.streamlit.discovery_report import (
    executive_summary,
    finding_rows,
    opportunity_rows,
    score_cards,
    signal_rows,
    social_link_rows,
    website_health_rows,
)
from leadpilot.presentation.streamlit.state import (
    open_company_mode,
    reset_company_filters,
    return_to_company_list,
    switch_organization,
    sync_filter_page,
)
from leadpilot.presentation.streamlit.views.dashboard import (
    discovery_metric_values,
    kpi_values,
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


def test_sidebar_navigation_has_accessible_active_and_focus_states() -> None:
    root = Path(__file__).parents[1]
    theme = (root / "src/leadpilot/presentation/streamlit/theme.py").read_text()
    assert '[role="radiogroup"] label:has(input:checked)' in theme
    assert "box-shadow:inset 4px 0 0 #7c6cff" in theme
    assert "background:#29265f" in theme
    assert "width:100%" in theme
    assert "white-space:nowrap" in theme
    assert "input:focus-visible" in theme
    assert "label:not(:has(input:checked)):hover" in theme
    assert "border:1.5px solid rgba(235,235,245,.62)" in theme


def test_sidebar_css_preserves_native_collapse_and_expand_controls() -> None:
    root = Path(__file__).parents[1]
    theme = (root / "src/leadpilot/presentation/streamlit/theme.py").read_text()
    compact = "".join(theme.casefold().split())
    assert '[data-testid="sttoolbar"]' not in compact
    assert '[data-testid="stsidebarcollapsedcontrol"]' not in compact
    assert '[data-testid="collapsedcontrol"]' not in compact
    sidebar_rules = [
        rule for rule in compact.split("}") if '[data-testid="stsidebar"]' in rule
    ]
    assert all("display:none" not in rule for rule in sidebar_rules)
    assert all("visibility:hidden" not in rule for rule in sidebar_rules)
    assert all("pointer-events:none" not in rule for rule in sidebar_rules)


def test_authentication_ui_is_responsive_and_preserves_streamlit_controls() -> None:
    root = Path(__file__).parents[1] / "src/leadpilot/presentation/streamlit"
    auth_source = (root / "auth_ui.py").read_text()
    compact = "".join(auth_source.casefold().split())
    assert "lp-auth-brand" in auth_source
    assert "lp-auth-card" in auth_source
    assert "@media(max-width:850px)" in compact
    assert "if an account exists for this email" in auth_source.casefold()
    assert '[data-testid="sttoolbar"]{opacity:.55' in compact
    assert "stsidebarcollapsedcontrol" not in compact
    assert "visibility:hidden" not in compact


def test_organization_context_and_selector_rules_are_explicit() -> None:
    root = Path(__file__).parents[1]
    app_source = (root / "src/leadpilot/presentation/streamlit/app.py").read_text()
    assert "lp-organization-label" in app_source
    assert ">Organization</div>" in app_source
    assert "current_name" in app_source
    assert not organization_selector_required(1)
    assert organization_selector_required(2)
    assert '"Switch organization"' in app_source


def test_organization_switch_clears_owned_state_but_keeps_preferences() -> None:
    state: dict[str, object] = {
        "organization_id": 1,
        "navigation": "Discovery",
        "selected_company": 9,
        "company_mode": "view",
        "company_search": "keep this preference",
        "discovery_scan_id": 21,
        "discovery_company_id": 9,
        "discovery_mode": "report",
        "ai_analysis_id": 33,
        "selected_ai_report": 33,
        "theme_preference": "dark",
    }
    assert switch_organization(state, 2, {1, 2})
    assert state["organization_id"] == 2
    assert state["navigation"] == "Dashboard"
    assert state["company_search"] == "keep this preference"
    assert state["theme_preference"] == "dark"
    for key in (
        "selected_company",
        "company_mode",
        "discovery_scan_id",
        "discovery_company_id",
        "discovery_mode",
        "ai_analysis_id",
        "selected_ai_report",
    ):
        assert key not in state


def test_ui_sources_include_milestone_sections_and_controls() -> None:
    streamlit_root = Path(__file__).parents[1] / "src/leadpilot/presentation/streamlit"
    root = streamlit_root / "views"
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


def discovery_scan(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "website_url": "https://acme.example",
        "final_url": "https://acme.example/",
        "is_https": True,
        "ssl_valid": True,
        "http_status_code": 200,
        "response_time_ms": 420,
        "page_title": "Acme",
        "meta_description": "Acme services",
        "mobile_viewport_present": True,
        "robots_txt_present": True,
        "sitemap_present": False,
        "website_health_score": 80,
        "digital_maturity_score": 65,
        "ai_readiness_score": 55,
        "automation_potential_score": 75,
        "lead_priority_score": 72,
        "contact_page_present": True,
        "about_page_present": True,
        "careers_page_present": False,
        "blog_present": True,
        "booking_system_present": False,
        "ecommerce_present": False,
        "contact_form_present": True,
        "newsletter_present": False,
        "whatsapp_present": True,
        "phone_present": True,
        "email_present": True,
        "chatbot_present": False,
        "detected_social_links": [
            "https://linkedin.com/company/acme/",
            "https://linkedin.com/company/acme",
            "https://x.com/acme",
        ],
        "score_details": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_business_readable_discovery_report_mappings() -> None:
    scan = discovery_scan()
    health = website_health_rows(scan)  # type: ignore[arg-type]
    assert health[0] == {
        "Check": "HTTPS",
        "Result": "Pass — Yes",
        "Details": "https://acme.example/",
    }
    assert all(set(row) == {"Check", "Result", "Details"} for row in health)
    assert [item.label for item in score_cards(scan)] == [  # type: ignore[arg-type]
        "Website Health",
        "Digital Maturity",
        "AI Readiness",
        "Automation Potential",
        "Lead Priority",
    ]
    assert signal_rows(scan)[0]["Status"] == "Detected"  # type: ignore[arg-type]
    assert "observable" not in executive_summary("Acme", scan).casefold()  # type: ignore[arg-type]


def test_finding_opportunity_and_social_mappings() -> None:
    findings = finding_rows(
        [
            {
                "severity": "Attention",
                "title": "Metadata gap",
                "evidence": "No description",
                "explanation": "Public signal",
            }
        ]
    )
    assert findings[0]["Severity"] == "Improvement"
    opportunities = opportunity_rows(
        [
            {
                "service_category": "CRM",
                "opportunity": "Centralize enquiries",
                "evidence": "Contact form",
                "suggested_outcome": "Faster follow-up",
            }
        ]
    )
    assert opportunities[0]["RapidNest Service"] == "CRM Integration"
    assert opportunities[0]["Priority"] == "High"
    links = social_link_rows(discovery_scan())  # type: ignore[arg-type]
    assert len(links) == 2
    assert links[0]["Platform"] == "LinkedIn"
    assert links[0]["Status"] == "Profile link"


def test_dashboard_discovery_metrics_and_page_error_isolation() -> None:
    summary = SimpleNamespace(
        completed=4,
        high_priority=2,
        average_automation_potential=71.5,
        average_ai_readiness=58.0,
    )
    assert [value for _, value, _ in discovery_metric_values(summary)] == [
        4,
        2,
        71.5,
        58.0,
    ]
    errors: list[str] = []

    def broken(_container: object) -> None:
        raise RuntimeError("dashboard section failed")

    assert not render_page_safely(broken, object(), on_error=errors.append)  # type: ignore[arg-type]
    assert errors and "saved data" in errors[0]
    assert "could not start" not in errors[0].casefold()


def test_theme_is_responsive_without_css_scaling() -> None:
    root = Path(__file__).parents[1] / "src/leadpilot/presentation/streamlit"
    theme = (root / "theme.py").read_text().casefold()
    discovery = (root / "views/discovery.py").read_text()
    assert "max-width:1560px" in theme
    assert "@media (max-width: 900px)" in theme
    assert "zoom:" not in theme
    assert "transform:scale" not in theme.replace(" ", "")
    assert "st.json(" not in discovery
    assert '"◈"' not in discovery


def test_application_uses_supplied_logo_assets() -> None:
    root = Path(__file__).parents[1] / "src/leadpilot/presentation/streamlit"
    app_source = (root / "app.py").read_text()
    logo = root / "assets/leadpilot-logo.png"
    icon = root / "assets/leadpilot-icon.png"
    assert logo.is_file() and logo.stat().st_size > 10_000
    assert icon.is_file() and icon.stat().st_size > 1_000
    assert "st.logo(" not in app_source
    assert "page_icon=str(ICON_PATH)" in app_source
    assert "st.sidebar.image(str(LOGO_PATH)" in app_source
    theme = (root / "theme.py").read_text()
    assert "padding:.25rem 1rem 1.7rem" in theme
    assert '[data-testid="stSidebarHeader"]' in theme
    assert "position:absolute" in theme
    assert "margin:-1rem auto 1rem" in theme
    assert "Lead Intelligence Workspace" in app_source
    assert "Built by RapidNest" in app_source
