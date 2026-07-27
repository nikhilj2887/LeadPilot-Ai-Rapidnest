from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from leadpilot.application.companies import (
    COMPANY_SIZES,
    COMPANY_STATUSES,
    Company,
    CompanyNotFoundError,
    CompanyValidationError,
)
from leadpilot.bootstrap import Container

PAGE_SIZE = 10


def filter_companies(
    companies: Sequence[Company],
    *,
    query: str = "",
    status: str = "All",
    industry: str = "All",
    country: str = "All",
) -> list[Company]:
    needle = query.strip().casefold()
    searchable = lambda company: (  # noqa: E731
        company.name,
        company.website,
        company.industry,
        company.country,
        company.city,
    )
    return [
        company
        for company in companies
        if (
            not needle
            or any(needle in (value or "").casefold() for value in searchable(company))
        )
        and (status == "All" or company.status == status)
        and (industry == "All" or company.industry == industry)
        and (country == "All" or company.country == country)
    ]


def paginate(companies: Sequence[Company], page: int) -> list[Company]:
    start = (page - 1) * PAGE_SIZE
    return list(companies[start : start + PAGE_SIZE])


def _save_company(container: Container, company: Company | None = None) -> None:
    action = "Update" if company else "Add"
    with st.form(f"company-form-{company.id if company else 'new'}"):
        name = st.text_input("Company name *", value=company.name if company else "")
        website = st.text_input(
            "Website", value=(company.website or "") if company else ""
        )
        left, right = st.columns(2)
        industry = left.text_input(
            "Industry", value=(company.industry or "") if company else ""
        )
        company_size = right.selectbox(
            "Company size",
            ("", *COMPANY_SIZES),
            index=("", *COMPANY_SIZES).index(company.company_size or "")
            if company
            else 0,
        )
        country = left.text_input(
            "Country", value=(company.country or "") if company else ""
        )
        city = right.text_input("City", value=(company.city or "") if company else "")
        status = left.selectbox(
            "Status",
            COMPANY_STATUSES,
            index=COMPANY_STATUSES.index(company.status) if company else 0,
        )
        source = right.text_input(
            "Source", value=(company.source or "") if company else ""
        )
        notes = st.text_area("Notes", value=(company.notes or "") if company else "")
        submitted = st.form_submit_button(f"{action} Company", type="primary")

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
        if company:
            container.companies.update_company(company.id, **values)
        else:
            container.companies.create_company(**values)
    except (CompanyValidationError, CompanyNotFoundError) as exc:
        st.error(str(exc))
    else:
        st.session_state.company_mode = "list"
        st.success(f"Company {action.lower()}d successfully.")
        st.rerun()


def _detail(container: Container, company: Company) -> None:
    if st.button("← Back to Companies"):
        st.session_state.company_mode = "list"
        st.rerun()
    st.subheader(company.name)
    if company.website:
        st.markdown(f"🌐 [{company.website}]({company.website})")
    left, right = st.columns(2)
    left.markdown(f"**Status:** {company.status}")
    left.markdown(f"**Industry:** {company.industry or '—'}")
    left.markdown(f"**Company size:** {company.company_size or '—'}")
    right.markdown(f"**Country:** {company.country or '—'}")
    right.markdown(f"**City:** {company.city or '—'}")
    right.markdown(f"**Source:** {company.source or '—'}")
    st.markdown("**Notes**")
    st.write(company.notes or "No notes provided.")
    st.caption(
        f"Added {company.created_at:%Y-%m-%d} · Updated {company.updated_at:%Y-%m-%d}"
    )


def _delete_confirmation(container: Container, company: Company) -> None:
    st.warning(f"Delete {company.name}? This action cannot be undone.")
    confirmed = st.checkbox("I confirm that I want to delete this company")
    cancel, remove = st.columns(2)
    if cancel.button("Cancel"):
        st.session_state.company_mode = "list"
        st.rerun()
    if remove.button("Delete Company", type="primary", disabled=not confirmed):
        try:
            container.companies.delete_company(company.id)
        except CompanyNotFoundError as exc:
            st.error(str(exc))
        else:
            st.session_state.company_mode = "list"
            st.rerun()


def _filters(companies: Sequence[Company]) -> tuple[str, str, str, str]:
    query = st.text_input(
        "Search",
        key="company_search",
        placeholder="Name, website, industry, country, or city",
    )
    columns = st.columns(3)
    status = columns[0].selectbox(
        "Status", ("All", *COMPANY_STATUSES), key="company_status"
    )
    industries = sorted({company.industry for company in companies if company.industry})
    industry = columns[1].selectbox(
        "Industry", ("All", *industries), key="company_industry"
    )
    countries = sorted({company.country for company in companies if company.country})
    country = columns[2].selectbox(
        "Country", ("All", *countries), key="company_country"
    )
    if st.button("Clear Filters"):
        for key in (
            "company_search",
            "company_status",
            "company_industry",
            "company_country",
        ):
            st.session_state[key] = "" if key == "company_search" else "All"
        st.session_state.company_page = 1
        st.rerun()
    return query, status, industry, country


def _list_view(container: Container, companies: list[Company]) -> None:
    query, status, industry, country = _filters(companies)
    filtered = filter_companies(
        companies, query=query, status=status, industry=industry, country=country
    )
    if not filtered:
        st.info("No companies match your filters. Clear filters or add a company.")
        return

    page_count = max(1, (len(filtered) + PAGE_SIZE - 1) // PAGE_SIZE)
    current = min(st.session_state.get("company_page", 1), page_count)
    st.session_state.company_page = current
    st.caption(f"{len(filtered)} compan{'y' if len(filtered) == 1 else 'ies'}")
    for company in paginate(filtered, current):
        with st.container(border=True):
            title, actions = st.columns([3, 2])
            title.markdown(f"### {company.name}")
            if company.website:
                title.markdown(f"[{company.website}]({company.website})")
            title.caption(
                " · ".join(
                    filter(None, (company.industry, company.country, company.city))
                )
                or "No details"
            )
            view, edit, delete = actions.columns(3)
            if view.button("View", key=f"view-{company.id}"):
                st.session_state.update(
                    company_mode="view", selected_company=company.id
                )
                st.rerun()
            if edit.button("Edit", key=f"edit-{company.id}"):
                st.session_state.update(
                    company_mode="edit", selected_company=company.id
                )
                st.rerun()
            if delete.button("Delete", key=f"delete-{company.id}"):
                st.session_state.update(
                    company_mode="delete", selected_company=company.id
                )
                st.rerun()
            st.caption(
                f"Status: {company.status} · Size: {company.company_size or '—'}"
            )
    if page_count > 1:
        selected_page = st.selectbox(
            "Page", range(1, page_count + 1), index=current - 1
        )
        if selected_page != current:
            st.session_state.company_page = selected_page
            st.rerun()


def render(container: Container) -> None:
    st.title("Companies")
    st.caption("Manage and qualify company leads.")
    mode = st.session_state.get("company_mode", "list")
    if mode == "list":
        if st.button("Add Company", type="primary"):
            st.session_state.company_mode = "add"
            st.rerun()
        companies = container.companies.list_companies()
        if not companies:
            st.info("No companies yet. Select Add Company to create your first lead.")
            return
        _list_view(container, companies)
        return
    if mode == "add":
        if st.button("← Cancel"):
            st.session_state.company_mode = "list"
            st.rerun()
        _save_company(container)
        return
    try:
        company = container.companies.get_company(st.session_state.selected_company)
    except CompanyNotFoundError as exc:
        st.error(str(exc))
        if st.button("Back to Companies"):
            st.session_state.company_mode = "list"
            st.rerun()
        return
    if mode == "view":
        _detail(container, company)
    elif mode == "edit":
        if st.button("← Cancel Edit"):
            st.session_state.company_mode = "list"
            st.rerun()
        _save_company(container, company)
    elif mode == "delete":
        _delete_confirmation(container, company)
