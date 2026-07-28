from __future__ import annotations

from collections.abc import Sequence
from html import escape

import streamlit as st

from leadpilot.application.companies import (
    COMPANY_SIZES,
    COMPANY_STATUSES,
    Company,
    CompanyNotFoundError,
    CompanyValidationError,
)
from leadpilot.bootstrap import Container
from leadpilot.presentation.streamlit.company_query import (
    PAGE_SIZE,
    SORT_OPTIONS,
    build_page,
    filter_companies,
    paginate,
    sort_companies,
)
from leadpilot.presentation.streamlit.components import (
    alert_message,
    empty_state,
    form_section,
    kpi_card,
    page_header,
    section_header,
    status_badge,
)
from leadpilot.presentation.streamlit.state import (
    FILTER_DEFAULTS,
    navigate,
    open_company_mode,
    reset_company_filters,
    return_to_company_list,
    sync_filter_page,
)

__all__ = ["PAGE_SIZE", "filter_companies", "paginate", "sort_companies"]


def _go_to(mode: str, company_id: int | None = None) -> None:
    open_company_mode(st.session_state, mode, company_id)
    st.rerun()


def _save_company(container: Container, company: Company | None = None) -> None:
    action = "Save Changes" if company else "Add Company"
    page_header(
        "Edit Company" if company else "Add Company",
        "Update this lead without changing the rules that keep your data clean."
        if company
        else "Create a company record to begin tracking it through your pipeline.",
        eyebrow="Companies",
    )
    with st.form(f"company-form-{company.id if company else 'new'}"):
        form_section(
            "Company Information",
            "Company name is required. Bare website domains are saved as secure URLs.",
        )
        left, right = st.columns(2)
        name = left.text_input(
            "Company Name *",
            value=company.name if company else "",
            help="Required. Company names must be unique.",
            max_chars=200,
        )
        website = right.text_input(
            "Website",
            value=(company.website or "") if company else "",
            placeholder="example.com",
            help="Enter a domain or a complete HTTP(S) URL.",
        )
        industry = left.text_input(
            "Industry",
            value=(company.industry or "") if company else "",
            placeholder="e.g. Software",
        )
        size_options = ("", *COMPANY_SIZES)
        company_size = right.selectbox(
            "Company Size",
            size_options,
            index=size_options.index(company.company_size or "") if company else 0,
            format_func=lambda value: value or "Select a size",
        )

        form_section("Location", "Add the primary location for this company.")
        left, right = st.columns(2)
        country = left.text_input(
            "Country", value=(company.country or "") if company else ""
        )
        city = right.text_input("City", value=(company.city or "") if company else "")

        form_section(
            "Lead Management",
            "Use status and source to keep pipeline reporting useful.",
        )
        left, right = st.columns(2)
        status = left.selectbox(
            "Status",
            COMPANY_STATUSES,
            index=COMPANY_STATUSES.index(company.status) if company else 0,
        )
        source = right.text_input(
            "Source",
            value=(company.source or "") if company else "",
            placeholder="e.g. Referral",
        )

        form_section(
            "Additional Information",
            "Capture context that will help with the next conversation.",
        )
        notes = st.text_area(
            "Notes",
            value=(company.notes or "") if company else "",
            placeholder="Add useful context, priorities, or next steps…",
        )
        cancel, submit, _ = st.columns([1, 1.3, 3])
        cancelled = cancel.form_submit_button("Cancel", use_container_width=True)
        submitted = submit.form_submit_button(
            action, type="primary", use_container_width=True
        )

    if cancelled:
        return_to_company_list(st.session_state)
        st.rerun()
    if not submitted:
        return
    values = {
        "name": name,
        "website": website,
        "industry": industry,
        "country": country,
        "city": city,
        "company_size": company_size,
        "status": status,
        "source": source,
        "notes": notes,
    }
    try:
        saved = (
            container.companies.update_company(company.id, **values)
            if company
            else container.companies.create_company(**values)
        )
    except (CompanyValidationError, CompanyNotFoundError) as exc:
        alert_message(str(exc), kind="error")
    else:
        return_to_company_list(st.session_state)
        st.session_state.company_flash = f"{saved.name} was saved successfully."
        st.rerun()


def _field(label: str, value: str | None) -> None:
    st.markdown(
        f'<div class="lp-label">{escape(label)}</div>'
        f'<div class="lp-value">{escape(value or "Not provided")}</div>',
        unsafe_allow_html=True,
    )


def _detail(container: Container, company: Company) -> None:
    if st.button("← Back to Companies"):
        _go_to("list")
    title, actions = st.columns([5, 2])
    with title:
        page_header(
            company.name,
            "A complete view of this company and its current pipeline context.",
            eyebrow="Company profile",
        )
        st.markdown(status_badge(company.status), unsafe_allow_html=True)
        if company.website:
            st.link_button("↗ Visit Website", company.website)
    edit, remove = actions.columns(2)
    if edit.button("Edit", type="primary", use_container_width=True):
        _go_to("edit", company.id)
    if remove.button("Delete", use_container_width=True):
        _go_to("delete", company.id)

    section_header("Company Overview")
    first = st.columns(3)
    with first[0]:
        _field("Website", company.website)
    with first[1]:
        _field("Industry", company.industry)
    with first[2]:
        _field("Company Size", company.company_size)

    section_header("Location")
    location = st.columns(2)
    with location[0]:
        _field("Country", company.country)
    with location[1]:
        _field("City", company.city)

    section_header("Lead Information")
    lead = st.columns(2)
    with lead[0]:
        _field("Status", company.status)
    with lead[1]:
        _field("Source", company.source)

    section_header("Notes")
    st.markdown(
        f'<div class="lp-panel">{escape(company.notes or "No notes have been added.")}</div>',
        unsafe_allow_html=True,
    )

    section_header("Discovery", "Latest public website intelligence for this company.")
    latest = container.discovery.latest_for_company(company.id)
    if latest:
        st.markdown(status_badge(latest.status), unsafe_allow_html=True)
        _score_columns = st.columns(5)
        for column, (label, value) in zip(
            _score_columns,
            (
                ("Health", latest.website_health_score),
                ("Maturity", latest.digital_maturity_score),
                ("AI Readiness", latest.ai_readiness_score),
                ("Automation", latest.automation_potential_score),
                ("Lead Priority", latest.lead_priority_score),
            ),
            strict=True,
        ):
            with column:
                kpi_card(label, value, "⌕")
        view, run, _ = st.columns([1.8, 1.2, 4])
        if view.button(
            "View Full Discovery Report", key=f"company-report-{company.id}"
        ):
            st.session_state.discovery_mode = "report"
            st.session_state.discovery_scan_id = latest.id
            navigate(st.session_state, "Discovery")
            st.rerun()
        if run.button("Rescan", key=f"company-rescan-{company.id}"):
            st.session_state.discovery_mode = "run"
            st.session_state.discovery_company_id = company.id
            navigate(st.session_state, "Discovery")
            st.rerun()
        st.caption(
            f"{len(container.discovery.history_for_company(company.id))} scan(s) in history"
        )
    elif st.button(
        "Run Discovery", key=f"company-discovery-{company.id}", type="primary"
    ):
        st.session_state.discovery_mode = "run"
        st.session_state.discovery_company_id = company.id
        navigate(st.session_state, "Discovery")
        st.rerun()

    section_header("Record Metadata")
    metadata = st.columns(2)
    with metadata[0]:
        _field("Created Date", company.created_at.strftime("%d %B %Y, %H:%M"))
    with metadata[1]:
        _field("Updated Date", company.updated_at.strftime("%d %B %Y, %H:%M"))

    section_header("Future Workspace", "Reserved for upcoming LeadPilot modules.")
    for column, (name, icon) in zip(
        st.columns(4),
        (
            ("Contacts", "◎"),
            ("Activities", "↻"),
            ("AI Insights", "✦"),
            ("Discovery Audit", "⌕"),
        ),
        strict=True,
    ):
        with column:
            st.markdown(
                f'<div class="lp-preview"><div>{icon}</div><h3>{name}</h3>'
                '<span class="lp-coming">Future milestone</span></div>',
                unsafe_allow_html=True,
            )


def _delete_confirmation(container: Container, company: Company) -> None:
    page_header(
        "Delete Company",
        "Review this irreversible action before confirming.",
        eyebrow="Confirmation required",
    )
    st.markdown(
        f'<div class="lp-panel"><div class="lp-eyebrow">Permanent deletion</div>'
        f"<h3>{escape(company.name)}</h3><p>This company record and its notes will be "
        "deleted. This action cannot be undone.</p></div>",
        unsafe_allow_html=True,
    )
    confirmed = st.checkbox(
        f"I confirm that I want to permanently delete {company.name}",
        key=f"confirm-delete-{company.id}",
    )
    cancel, remove, _ = st.columns([1, 1.5, 3])
    if cancel.button("Cancel", use_container_width=True):
        _go_to("view", company.id)
    if remove.button(
        "Delete Company",
        type="primary",
        disabled=not confirmed,
        use_container_width=True,
    ):
        try:
            container.companies.delete_company(company.id)
        except CompanyNotFoundError:
            alert_message(
                "This company no longer exists. Returning to the company list.",
                kind="warning",
            )
        return_to_company_list(st.session_state)
        st.session_state.company_flash = f"{company.name} was deleted."
        st.rerun()


def _filters(companies: Sequence[Company]) -> tuple[str, str, str, str, str]:
    for key, value in FILTER_DEFAULTS.items():
        st.session_state.setdefault(key, value)
    toolbar = st.columns([2.2, 1, 1, 1, 1.25])
    query = toolbar[0].text_input(
        "Search",
        key="company_search",
        placeholder="Search companies…",
    )
    status = toolbar[1].selectbox(
        "Status", ("All", *COMPANY_STATUSES), key="company_status"
    )
    industries = sorted({item.industry for item in companies if item.industry})
    industry = toolbar[2].selectbox(
        "Industry", ("All", *industries), key="company_industry"
    )
    countries = sorted({item.country for item in companies if item.country})
    country = toolbar[3].selectbox(
        "Country", ("All", *countries), key="company_country"
    )
    sort = toolbar[4].selectbox("Sort", SORT_OPTIONS, key="company_sort")
    if st.button("Clear Filters"):
        reset_company_filters(st.session_state)
        st.rerun()
    signature = (query, status, industry, country, sort)
    sync_filter_page(st.session_state, signature)
    return query, status, industry, country, sort


def _company_row(company: Company) -> None:
    info, details, status_col, updated, actions = st.columns([2.1, 1.5, 1, 1, 1.45])
    with info:
        st.markdown(f"**{company.name}**")
        if company.website:
            st.markdown(f"[{company.website}]({company.website})")
        else:
            st.caption("No website")
    with details:
        st.markdown(company.industry or "Industry not provided")
        st.caption(
            ", ".join(filter(None, (company.city, company.country)))
            or "Location not provided"
        )
        st.caption(f"Size: {company.company_size or 'Not provided'}")
    with status_col:
        st.markdown(status_badge(company.status), unsafe_allow_html=True)
    with updated:
        st.caption(company.updated_at.strftime("%d %b %Y"))
    view, edit, delete = actions.columns(3)
    if view.button("View", key=f"view-{company.id}", help=f"View {company.name}"):
        _go_to("view", company.id)
    if edit.button("Edit", key=f"edit-{company.id}", help=f"Edit {company.name}"):
        _go_to("edit", company.id)
    if delete.button(
        "Delete", key=f"delete-{company.id}", help=f"Delete {company.name}"
    ):
        _go_to("delete", company.id)
    st.divider()


def _pagination(page_number: int, page_count: int) -> None:
    previous, label, next_page = st.columns([1, 3, 1])
    if previous.button(
        "← Previous",
        disabled=page_number == 1,
        use_container_width=True,
    ):
        st.session_state.company_page = page_number - 1
        st.rerun()
    label.markdown(
        f"<div style='text-align:center;padding:.5rem'>Page {page_number} of "
        f"{page_count}</div>",
        unsafe_allow_html=True,
    )
    if next_page.button(
        "Next →",
        disabled=page_number == page_count,
        use_container_width=True,
    ):
        st.session_state.company_page = page_number + 1
        st.rerun()


def _list_view(container: Container) -> None:
    heading, action = st.columns([6, 1.2])
    with heading:
        page_header(
            "Companies",
            "Search, qualify, and manage every company in your lead pipeline.",
            eyebrow="Lead workspace",
        )
    if action.button("＋ Add Company", type="primary", use_container_width=True):
        _go_to("add")

    flash = st.session_state.pop("company_flash", None)
    if flash:
        alert_message(flash, kind="success")

    companies = container.companies.list_companies()
    metrics = container.companies.metrics()
    summary = st.columns(5)
    for column, (label, value, icon) in zip(
        summary,
        (
            ("Total", metrics.total, "▦"),
            ("New", metrics.new, "✦"),
            ("Qualified", metrics.qualified, "✓"),
            ("Contacted", metrics.contacted, "↗"),
            ("Proposal", metrics.proposal, "▤"),
        ),
        strict=True,
    ):
        with column:
            kpi_card(label, value, icon)

    section_header("Company Directory", "Use filters and sorting to focus your list.")
    query, status, industry, country, sort = _filters(companies)
    filtered = filter_companies(
        companies, query=query, status=status, industry=industry, country=country
    )
    ordered = sort_companies(filtered, sort)
    page = build_page(ordered, st.session_state.get("company_page", 1))
    st.session_state.company_page = page.number
    st.caption(
        f"{page.total_items} result{'s' if page.total_items != 1 else ''} · "
        f"Up to {PAGE_SIZE} per page"
    )
    if not companies:
        empty_state(
            "No companies yet",
            "Add your first company to start building and tracking your lead pipeline.",
            "▦",
        )
        if st.button("Add your first company", type="primary"):
            _go_to("add")
        return
    if not page.items:
        empty_state(
            "No matching companies",
            "Try changing your search or filters, or clear them to see every company.",
            "⌕",
        )
        return
    for company in page.items:
        _company_row(company)
    _pagination(page.number, page.count)


def render(container: Container) -> None:
    mode = st.session_state.get("company_mode", "list")
    if mode == "list":
        _list_view(container)
        return
    if mode == "add":
        _save_company(container)
        return

    company_id = st.session_state.get("selected_company")
    if not isinstance(company_id, int):
        return_to_company_list(st.session_state)
        alert_message("Choose a company from the list to continue.", kind="warning")
        _list_view(container)
        return
    try:
        company = container.companies.get_company(company_id)
    except CompanyNotFoundError:
        return_to_company_list(st.session_state)
        alert_message(
            "That company is no longer available. The list has been refreshed.",
            kind="warning",
        )
        _list_view(container)
        return
    if mode == "view":
        _detail(container, company)
    elif mode == "edit":
        _save_company(container, company)
    elif mode == "delete":
        _delete_confirmation(container, company)
    else:
        return_to_company_list(st.session_state)
        _list_view(container)
