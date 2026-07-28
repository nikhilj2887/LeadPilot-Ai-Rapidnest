from __future__ import annotations

from html import escape

import streamlit as st

from leadpilot.application.discovery import DISCOVERY_STATUSES, DiscoveryScan
from leadpilot.bootstrap import Container
from leadpilot.infrastructure.discovery_scoring import rating_label
from leadpilot.infrastructure.discovery_security import normalize_url
from leadpilot.presentation.streamlit.ai_report import render_ai_intelligence
from leadpilot.presentation.streamlit.components import (
    alert_message,
    empty_state,
    kpi_card,
    page_header,
    score_card,
    section_header,
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


def filter_scans(
    scans: list[DiscoveryScan],
    *,
    query: str = "",
    status: str = "All",
    rating: str = "All",
) -> list[DiscoveryScan]:
    needle = query.strip().casefold()
    return [
        scan
        for scan in scans
        if (status == "All" or scan.status == status)
        and (rating == "All" or rating_label(scan.lead_priority_score) == rating)
        and (not needle or needle in scan.website_url.casefold())
    ]


def score_badge(value: int) -> str:
    return f"{value}/100 · {rating_label(value)}"


def report_sections() -> tuple[str, ...]:
    return (
        "Executive Overview",
        "Website Health",
        "Technology Stack",
        "Business Signals",
        "Customer Engagement",
        "Social Presence",
        "Findings",
        "RapidNest Opportunities",
        "Contact Information",
        "Scan Metadata",
    )


def _open(mode: str, scan_id: int | None = None, company_id: int | None = None) -> None:
    st.session_state.discovery_mode = mode
    st.session_state.discovery_scan_id = scan_id
    if company_id is not None:
        st.session_state.discovery_company_id = company_id
    st.rerun()


def _run(container: Container) -> None:
    if st.button("← Back to Discovery"):
        _open("list")
    page_header(
        "Run Discovery",
        "Inspect a public company website and create an explainable intelligence report.",
        eyebrow="Website intelligence",
    )
    st.caption("Website Scan → Technology Detection → Rule-based Lead Intelligence")
    companies = container.companies.list_companies()
    if not companies:
        empty_state(
            "Add a company first",
            "Discovery scans must be linked to an existing company.",
            "Discovery",
        )
        return
    preferred = st.session_state.get("discovery_company_id")
    ids = [company.id for company in companies]
    index = ids.index(preferred) if preferred in ids else 0
    company = st.selectbox(
        "Company", companies, index=index, format_func=lambda item: item.name
    )
    website = st.text_input(
        "Website URL", value=company.website or "", placeholder="https://example.com"
    )
    if website:
        try:
            st.caption(f"Normalized URL: {normalize_url(website)}")
        except ValueError as exc:
            alert_message(str(exc), kind="warning")
    submitted = st.button(
        "Run Discovery",
        type="primary",
        disabled=bool(st.session_state.get("discovery_running")),
    )
    if submitted:
        st.session_state.discovery_running = True
        try:
            with st.spinner("Validating and scanning the public website…"):
                scan = container.discovery.run_scan(company.id, website)
        finally:
            st.session_state.discovery_running = False
        if scan.status == "Failed":
            alert_message(scan.error_message or "The scan failed safely.", kind="error")
        else:
            st.session_state.discovery_flash = "Discovery scan completed."
            _open("report", scan.id)


def _score_cards(scan: DiscoveryScan) -> None:
    for column, item in zip(st.columns(5), score_cards(scan), strict=True):
        with column:
            score_card(item.label, item.value, item.rating, item.explanation)


def _report(container: Container, scan: DiscoveryScan) -> None:
    company = container.companies.get_company(scan.company_id)
    back, rescan = st.columns([6, 1])
    if back.button("← Back"):
        _open("list")
    if rescan.button("Rescan", type="primary"):
        _open("run", company_id=company.id)
    page_header(
        company.name, scan.website_url, eyebrow=f"Discovery report · {scan.status}"
    )
    flash = st.session_state.pop("discovery_flash", None)
    if flash:
        alert_message(flash, kind="success")
    _score_cards(scan)
    details = scan.score_details or {}
    section_header("Executive Overview")
    st.markdown(
        f'<div class="lp-panel"><p>{escape(executive_summary(company.name, scan))}</p></div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Assessment is limited to observable public website indicators and does not "
        "confirm the company’s internal systems or requirements."
    )
    for key, title in (
        ("website_health_score", "Website Health"),
        ("digital_maturity_score", "Digital Maturity"),
        ("ai_readiness_score", "AI Readiness"),
        ("automation_potential_score", "Automation Potential"),
        ("lead_priority_score", "Lead Priority"),
    ):
        item = details.get(key, {})
        with st.expander(
            f"{title}: {item.get('value', 0)}/100 · {item.get('rating', 'Very Low')}"
        ):
            st.write(item.get("explanation", "No explanation available."))
            st.write(
                "Positive factors:",
                ", ".join(item.get("positive_factors", [])) or "None observed",
            )
            st.write(
                "Negative factors:",
                ", ".join(item.get("negative_factors", [])) or "None observed",
            )
    section_header("Website Health")
    st.dataframe(
        website_health_rows(scan),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Check": st.column_config.TextColumn(width="small"),
            "Result": st.column_config.TextColumn(width="small"),
            "Details": st.column_config.TextColumn(width="large"),
        },
    )
    section_header("Technology Stack")
    if scan.detected_technologies:
        technologies = [
            {
                **item,
                "evidence": "; ".join(item.get("evidence", [])),
            }
            for item in scan.detected_technologies
        ]
        st.dataframe(
            technologies,
            use_container_width=True,
            hide_index=True,
            column_config={
                "name": st.column_config.TextColumn("Technology", width="medium"),
                "category": st.column_config.TextColumn("Category", width="small"),
                "confidence": st.column_config.TextColumn("Confidence", width="small"),
                "evidence": st.column_config.TextColumn("Evidence", width="large"),
            },
        )
    else:
        st.info("No supported technology indicators were detected.")
    section_header("Business Signals")
    st.dataframe(
        signal_rows(scan),
        use_container_width=True,
        hide_index=True,
    )
    section_header("Customer Engagement")
    st.write(
        f"Live chat: {'Detected' if scan.live_chat_present else 'Not detected'} · Chatbot: {'Detected' if scan.chatbot_present else 'Not detected'}"
    )
    section_header("Social Presence")
    social_rows = social_link_rows(scan)
    if social_rows:
        st.dataframe(
            social_rows,
            use_container_width=True,
            hide_index=True,
            column_config={"URL": st.column_config.LinkColumn("Detected link")},
        )
    else:
        st.info("No usable social profile links were detected.")
    section_header("Findings")
    for finding in finding_rows(scan.findings):
        st.markdown(
            '<div class="lp-report-card">'
            f'<span class="lp-badge lp-researching">{escape(finding["Severity"])}</span>'
            f"<p><strong>{escape(finding['Title'])}</strong></p>"
            f"<p><b>Evidence:</b> {escape(finding['Evidence'])}</p>"
            f"<p>{escape(finding['Explanation'])}</p></div>",
            unsafe_allow_html=True,
        )
    section_header(
        "RapidNest Opportunities",
        "Evidence-supported assessment opportunities, not confirmed internal requirements.",
    )
    opportunities = opportunity_rows(scan.recommendations)
    if opportunities:
        st.dataframe(
            opportunities,
            use_container_width=True,
            hide_index=True,
            column_config={
                "RapidNest Service": st.column_config.TextColumn(width="medium"),
                "Opportunity": st.column_config.TextColumn(width="large"),
                "Evidence": st.column_config.TextColumn(width="large"),
                "Suggested Outcome": st.column_config.TextColumn(width="large"),
                "Priority": st.column_config.TextColumn(width="small"),
            },
        )
    else:
        st.info("No evidence-supported RapidNest opportunities were generated.")
    section_header("Contact Information")
    contacts = [
        *(
            {"Type": "Email", "Contact": value}
            for value in dict.fromkeys(scan.detected_emails)
        ),
        *(
            {"Type": "Phone", "Contact": value}
            for value in dict.fromkeys(scan.detected_phone_numbers)
        ),
    ]
    if contacts:
        st.dataframe(
            contacts,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No public email addresses or phone numbers were detected.")
    section_header("Scan Metadata")
    st.dataframe(
        [
            {"Field": "Started", "Value": str(scan.started_at or "Unavailable")},
            {"Field": "Completed", "Value": str(scan.completed_at or "Unavailable")},
            {"Field": "Final URL", "Value": scan.final_url or scan.website_url},
            {
                "Field": "HTTP Status",
                "Value": str(scan.http_status_code or "Unavailable"),
            },
        ],
        use_container_width=True,
        hide_index=True,
    )
    render_ai_intelligence(container, scan.id)


def _list(container: Container) -> None:
    header, action = st.columns([6, 1])
    with header:
        page_header(
            "Discovery",
            "Turn public website signals into explainable lead intelligence.",
            eyebrow="Website intelligence",
        )
    if action.button("Run Discovery", type="primary", use_container_width=True):
        _open("run")
    summary = container.discovery.dashboard_summary()
    for column, item in zip(
        st.columns(5),
        (
            ("Total Scans", summary.total),
            ("Completed", summary.completed),
            ("Failed", summary.failed),
            ("Average Lead Priority", summary.average_lead_priority),
            ("High Priority Leads", summary.high_priority),
        ),
        strict=True,
    ):
        with column:
            kpi_card(item[0], item[1], "")
    scans = container.discovery.recent_scans()
    section_header("Discovery Reports", "Filter scans by status, priority, or website.")
    filters = st.columns(3)
    query = filters[0].text_input("Company or website search")
    status = filters[1].selectbox("Status", ("All", *DISCOVERY_STATUSES))
    rating = filters[2].selectbox(
        "Lead Priority", ("All", "Very Low", "Low", "Moderate", "High", "Very High")
    )
    filtered = filter_scans(scans, query=query, status=status, rating=rating)
    if not scans:
        empty_state(
            "No discovery scans yet",
            "Select an existing company and run a safe, synchronous public website scan.",
            "Discovery",
        )
        return
    for scan in filtered:
        company = container.companies.get_company(scan.company_id)
        cols = st.columns([2, 2.5, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1])
        values = (
            company.name,
            scan.website_url,
            scan.status,
            scan.website_health_score,
            scan.digital_maturity_score,
            scan.ai_readiness_score,
            scan.automation_potential_score,
            scan.lead_priority_score,
        )
        for index, (col, value) in enumerate(zip(cols[:-1], values, strict=True)):
            if index == 2:
                col.markdown(
                    f'<span class="lp-badge lp-researching">{escape(str(value))}</span>',
                    unsafe_allow_html=True,
                )
            elif index >= 3:
                col.markdown(f"**{score_badge(int(value))}**")
            else:
                col.write(value)
        if cols[-1].button("View", key=f"scan-{scan.id}"):
            _open("report", scan.id)


def render(container: Container) -> None:
    mode = st.session_state.get("discovery_mode", "list")
    if mode == "run":
        _run(container)
    elif mode == "report" and isinstance(
        st.session_state.get("discovery_scan_id"), int
    ):
        _report(
            container, container.discovery.get_scan(st.session_state.discovery_scan_id)
        )
    else:
        _list(container)
