from __future__ import annotations

"""Proposal views rendered only through the protected app entry point."""

import streamlit as st

from leadpilot.presentation.streamlit.components import page_header, section_header


def render(container: object) -> None:
    page_header(
        "Proposals",
        "A future workspace for turning qualified opportunities into clear, consistent "
        "client proposals.",
        eyebrow="Future proposal workspace",
    )
    st.info(
        "Proposal generation remains a visual preview. Milestone 3 does not generate "
        "content, pricing, or files."
    )
    section_header(
        "Proposal Building Blocks",
        "The planned components of a complete RapidNest proposal.",
    )
    previews = (
        ("⌕", "Discovery Audit", "Bring opportunity findings into the proposal."),
        ("▤", "Scope of Work", "Define outcomes, deliverables, and timelines."),
        ("◇", "Pricing", "Present clear packages and commercial terms."),
        ("↓", "PDF Export", "Create a polished, shareable client document."),
    )
    for column, (icon, title, description) in zip(st.columns(4), previews, strict=True):
        with column:
            st.markdown(
                f'<div class="lp-preview"><div>{icon}</div><h3>{title}</h3>'
                f'<p>{description}</p><span class="lp-coming">Upcoming</span></div>',
                unsafe_allow_html=True,
            )
    st.button("Proposal tools are coming soon", disabled=True, type="primary")
