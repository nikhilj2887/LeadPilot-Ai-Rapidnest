from __future__ import annotations

from html import escape

import streamlit as st

from leadpilot.application.discovery import DISCOVERY_STATUSES, DiscoveryScan
from leadpilot.bootstrap import Container
from leadpilot.infrastructure.discovery_scoring import rating_label
from leadpilot.infrastructure.discovery_security import normalize_url
from leadpilot.presentation.streamlit.components import (
    alert_message,
    empty_state,
    kpi_card,
    page_header,
    section_header,
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
            "⌕",
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
    fields = (
        ("Website Health", "website_health_score"),
        ("Digital Maturity", "digital_maturity_score"),
        ("AI Readiness", "ai_readiness_score"),
        ("Automation Potential", "automation_potential_score"),
        ("Lead Priority", "lead_priority_score"),
    )
    for column, (label, field) in zip(st.columns(5), fields, strict=True):
        with column:
            value = int(getattr(scan, field, 0))
            kpi_card(label, value, "◈")
            st.caption(rating_label(value))


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
    st.write(
        f"This deterministic report found a {rating_label(scan.lead_priority_score).lower()} "
        "lead-priority profile using public website signals. It does not represent internal systems."
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
    health = {
        "HTTPS": scan.is_https,
        "SSL valid": scan.ssl_valid,
        "HTTP status": scan.http_status_code,
        "Response time": f"{scan.response_time_ms or 0} ms",
        "Title": scan.page_title or "Missing",
        "Meta description": scan.meta_description or "Missing",
        "Mobile viewport": scan.mobile_viewport_present,
        "robots.txt": scan.robots_txt_present,
        "Sitemap": scan.sitemap_present,
    }
    st.json(health)
    section_header("Technology Stack")
    if scan.detected_technologies:
        st.dataframe(
            scan.detected_technologies, use_container_width=True, hide_index=True
        )
    else:
        st.info("No supported technology indicators were detected.")
    section_header("Business Signals")
    signal_names = (
        "contact_page_present",
        "about_page_present",
        "careers_page_present",
        "blog_present",
        "booking_system_present",
        "ecommerce_present",
        "contact_form_present",
        "newsletter_present",
        "whatsapp_present",
        "phone_present",
        "email_present",
    )
    st.dataframe(
        [
            {
                "Signal": name.replace("_present", "").replace("_", " ").title(),
                "Detected": bool(getattr(scan, name)),
            }
            for name in signal_names
        ],
        use_container_width=True,
        hide_index=True,
    )
    section_header("Customer Engagement")
    st.write(
        f"Live chat: {'Detected' if scan.live_chat_present else 'Not detected'} · Chatbot: {'Detected' if scan.chatbot_present else 'Not detected'}"
    )
    section_header("Social Presence")
    st.write(
        "\n".join(f"- {url}" for url in scan.detected_social_links)
        or "No supported social links detected."
    )
    section_header("Findings")
    for finding in scan.findings:
        st.markdown(f"**{escape(finding['severity'])} — {escape(finding['title'])}**")
        st.caption(finding["explanation"])
    section_header("RapidNest Opportunities")
    for item in scan.recommendations:
        st.markdown(
            f"**{escape(item['service_category'])}** — {escape(item['opportunity'])}"
        )
        st.caption(f"Evidence: {item['evidence']}")
    section_header("Contact Information")
    st.write("Emails:", ", ".join(scan.detected_emails) or "None detected")
    st.write(
        "Phone numbers:", ", ".join(scan.detected_phone_numbers) or "None detected"
    )
    section_header("Scan Metadata")
    st.write(
        {
            "Started": scan.started_at,
            "Completed": scan.completed_at,
            "Final URL": scan.final_url,
            "HTTP status": scan.http_status_code,
        }
    )


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
            kpi_card(item[0], item[1], "⌕")
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
            "⌕",
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
        for col, value in zip(cols[:-1], values, strict=True):
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
