from __future__ import annotations

import pandas as pd
import streamlit as st

from leadpilot.bootstrap import Container
from leadpilot.presentation.streamlit.components import (
    empty_state,
    kpi_card,
    page_header,
    section_header,
    status_badge,
)
from leadpilot.presentation.streamlit.state import navigate, open_company_mode

KPI_MAPPING = (
    ("Total Companies", "total", "▦"),
    ("New Leads", "new", "✦"),
    ("Qualified Leads", "qualified", "✓"),
    ("Contacted Leads", "contacted", "↗"),
    ("Proposal Stage", "proposal", "▤"),
)


def kpi_values(metrics: object) -> list[tuple[str, int, str]]:
    return [
        (label, int(getattr(metrics, attribute)), icon)
        for label, attribute, icon in KPI_MAPPING
    ]


def render(container: Container) -> None:
    header, refresh = st.columns([6, 1])
    with header:
        page_header(
            "Dashboard",
            "Monitor your lead pipeline and focus on the companies moving forward.",
            eyebrow="Pipeline workspace",
        )
    if refresh.button("↻ Refresh", use_container_width=True):
        st.rerun()

    metrics = container.companies.metrics()
    columns = st.columns(5)
    for column, (label, value, icon) in zip(columns, kpi_values(metrics), strict=True):
        with column:
            kpi_card(label, value, icon)

    if metrics.total == 0:
        section_header("Lead Pipeline Overview")
        empty_state(
            "Your pipeline is ready",
            "Add your first company to see pipeline KPIs, status distribution, and "
            "recent activity here.",
            "◎",
        )
        if st.button("＋ Add Company", type="primary"):
            open_company_mode(st.session_state, "add")
            navigate(st.session_state, "Companies")
            st.rerun()
        return

    section_header(
        "Lead Pipeline Overview",
        "A live view of pipeline distribution and recent company activity.",
    )
    left, right = st.columns([1.05, 1])
    with left:
        section_header("Companies by Status", "All seven pipeline stages.")
        chart_data = pd.DataFrame(
            {
                "Status": list(metrics.by_status),
                "Companies": list(metrics.by_status.values()),
            }
        ).set_index("Status")
        st.bar_chart(chart_data, color="#6d5dfc", horizontal=True)
    with right:
        section_header("Recent Companies", "Your five most recently updated records.")
        for company in container.companies.recent_companies(5):
            row, action = st.columns([5, 1])
            with row:
                st.markdown(
                    f"**{company.name}** &nbsp; {status_badge(company.status)}",
                    unsafe_allow_html=True,
                )
                st.caption(
                    f"{company.industry or 'Industry not specified'} · "
                    f"{company.country or 'Location not specified'} · "
                    f"Updated {company.updated_at:%d %b %Y}"
                )
            if action.button("View", key=f"recent-view-{company.id}"):
                open_company_mode(st.session_state, "view", company.id)
                navigate(st.session_state, "Companies")
                st.rerun()
            st.divider()

    section_header("Quick Actions", "Move directly to your next task.")
    add, companies, discovery, _ = st.columns(4)
    if add.button("＋ Add Company", type="primary", use_container_width=True):
        open_company_mode(st.session_state, "add")
        navigate(st.session_state, "Companies")
        st.rerun()
    if companies.button("▦ View Companies", use_container_width=True):
        open_company_mode(st.session_state, "list")
        navigate(st.session_state, "Companies")
        st.rerun()
    if discovery.button("⌕ Open Discovery", use_container_width=True):
        navigate(st.session_state, "Discovery")
        st.rerun()
