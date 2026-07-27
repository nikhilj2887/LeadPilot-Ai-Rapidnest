from __future__ import annotations

import streamlit as st

from leadpilot.presentation.streamlit.components import page_header, section_header


def render(container: object) -> None:
    page_header(
        "Discovery",
        "A preview of how LeadPilot will turn a company website into actionable lead "
        "intelligence.",
        eyebrow="Future intelligence workspace",
    )
    st.info(
        "Discovery is a non-functional preview in Milestone 3. No website scans or "
        "external calls are performed."
    )
    section_header(
        "Discovery Workflow",
        "A guided path from a website URL to a prioritized opportunity.",
    )
    stages = (
        ("01", "Website Scan", "Review public website structure and key pages."),
        ("02", "Technology Detection", "Identify the visible technology footprint."),
        ("03", "Digital Maturity", "Assess the company's current digital experience."),
        (
            "04",
            "Opportunity Analysis",
            "Surface areas where RapidNest can create value.",
        ),
    )
    for column, (number, title, description) in zip(st.columns(4), stages, strict=True):
        with column:
            st.markdown(
                f'<div class="lp-preview"><div class="lp-eyebrow">{number}</div>'
                f"<h3>{title}</h3><p>{description}</p>"
                '<span class="lp-coming">Upcoming</span></div>',
                unsafe_allow_html=True,
            )
    st.button(
        "Coming in a future milestone",
        disabled=True,
        type="primary",
        help="Discovery capabilities are not enabled in Milestone 3.",
    )
