from __future__ import annotations

import logging

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

logger = logging.getLogger(__name__)

KPI_MAPPING = (
    ("Total Companies", "total", ""),
    ("New Leads", "new", ""),
    ("Qualified Leads", "qualified", ""),
    ("Contacted Leads", "contacted", ""),
    ("Proposal Stage", "proposal", ""),
)


def kpi_values(metrics: object) -> list[tuple[str, int, str]]:
    return [
        (label, int(getattr(metrics, attribute)), icon)
        for label, attribute, icon in KPI_MAPPING
    ]


def discovery_metric_values(summary: object) -> list[tuple[str, int | float, str]]:
    return [
        ("Completed Scans", int(summary.completed), ""),
        ("High Priority Leads", int(summary.high_priority), ""),
        (
            "Average Automation Potential",
            float(summary.average_automation_potential),
            "",
        ),
        (
            "Average AI Readiness",
            float(getattr(summary, "average_ai_readiness", 0)),
            "",
        ),
    ]


def _discovery_intelligence(container: Container) -> None:
    section_header(
        "Discovery Intelligence",
        "Website-observable opportunity and readiness signals.",
    )
    try:
        summary = container.discovery.dashboard_summary()
        columns = st.columns(4)
        for column, (label, value, icon) in zip(
            columns, discovery_metric_values(summary), strict=True
        ):
            with column:
                kpi_card(label, value, icon)
        if summary.recent:
            section_header(
                "Recently Scanned Companies",
                "The latest website intelligence activity.",
            )
            rows = []
            for scan in summary.recent:
                company = container.companies.get_company(scan.company_id)
                rows.append(
                    {
                        "Company": company.name,
                        "Status": scan.status,
                        "Lead Priority": scan.lead_priority_score,
                        "Automation Potential": scan.automation_potential_score,
                        "Scanned": scan.completed_at or scan.created_at,
                    }
                )
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.caption(
                "No completed website scans yet. Open Discovery when you are ready."
            )
    except Exception:
        logger.exception("Discovery Intelligence dashboard section failed")
        st.warning(
            "Discovery Intelligence is temporarily unavailable. "
            "Your company pipeline is still available."
        )


def _quick_actions() -> None:
    section_header("Quick Actions", "Move directly to your next task.")
    add, companies, discovery = st.columns(3)
    if add.button("Add Company", type="primary", use_container_width=True):
        open_company_mode(st.session_state, "add")
        navigate(st.session_state, "Companies")
        st.rerun()
    if companies.button("View Companies", use_container_width=True):
        open_company_mode(st.session_state, "list")
        navigate(st.session_state, "Companies")
        st.rerun()
    if discovery.button("Open Discovery", use_container_width=True):
        navigate(st.session_state, "Discovery")
        st.rerun()


def _ai_intelligence(container: Container) -> None:
    summary = container.discovery_ai.dashboard_summary()
    if not any((summary["completed"], summary["failed"], summary["awaiting_review"])):
        return
    section_header(
        "AI Intelligence",
        "Generation activity and drafts awaiting human review.",
    )
    for column, (label, value) in zip(
        st.columns(3),
        (
            ("Completed AI Analyses", summary["completed"]),
            ("Failed AI Analyses", summary["failed"]),
            ("Awaiting Review", summary["awaiting_review"]),
        ),
        strict=True,
    ):
        with column:
            kpi_card(label, value, "")
    if summary["top_services"]:
        st.caption(
            "Top recommended services: "
            + " · ".join(
                f"{service} ({count})" for service, count in summary["top_services"]
            )
        )


def render(container: Container) -> None:
    header, refresh = st.columns([6, 1])
    with header:
        page_header(
            "Dashboard",
            "Monitor your lead pipeline and focus on the companies moving forward.",
            eyebrow="Pipeline workspace",
        )
    if refresh.button("Refresh", use_container_width=True):
        st.rerun()

    metrics = container.companies.metrics()
    columns = st.columns(5)
    for column, (label, value, icon) in zip(columns, kpi_values(metrics), strict=True):
        with column:
            kpi_card(label, value, icon)

    if metrics.total == 0:
        section_header("Start Building Your Lead Pipeline")
        empty_state(
            "Add your first company",
            "Create a company record first. You can then run website discovery and "
            "review explainable lead intelligence from this dashboard.",
            "Start",
        )
        if st.button("Add Company", type="primary"):
            open_company_mode(st.session_state, "add")
            navigate(st.session_state, "Companies")
            st.rerun()
        return

    section_header(
        "Lead Pipeline Overview",
        "Pipeline distribution and recently updated companies.",
    )
    left, right = st.columns([1, 1])
    with left:
        section_header("Companies by Status", "All seven pipeline stages.")
        chart_data = pd.DataFrame(
            {
                "Status": list(metrics.by_status),
                "Companies": list(metrics.by_status.values()),
            }
        ).set_index("Status")
        st.bar_chart(
            chart_data,
            color="#6d5dfc",
            horizontal=True,
            height=360,
            use_container_width=True,
        )
    with right:
        section_header("Recent Companies", "Five recently updated records.")
        for company in container.companies.recent_companies(5):
            row, action = st.columns([4, 1])
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
            if action.button(
                "View", key=f"recent-view-{company.id}", use_container_width=True
            ):
                open_company_mode(st.session_state, "view", company.id)
                navigate(st.session_state, "Companies")
                st.rerun()
            st.divider()

    _discovery_intelligence(container)
    _ai_intelligence(container)
    _quick_actions()
