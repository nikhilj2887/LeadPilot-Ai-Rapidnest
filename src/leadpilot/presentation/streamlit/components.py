from __future__ import annotations

from html import escape

import streamlit as st

from leadpilot.application.companies import COMPANY_STATUSES

STATUS_STYLES = {
    "New": "new",
    "Researching": "researching",
    "Qualified": "qualified",
    "Contacted": "contacted",
    "Proposal": "proposal",
    "Won": "won",
    "Lost": "lost",
}


def page_header(title: str, subtitle: str, *, eyebrow: str | None = None) -> None:
    eyebrow_html = f'<div class="lp-eyebrow">{escape(eyebrow)}</div>' if eyebrow else ""
    st.markdown(
        f'<div class="lp-page-header">{eyebrow_html}<h1>{escape(title)}</h1>'
        f"<p>{escape(subtitle)}</p></div>",
        unsafe_allow_html=True,
    )


def section_header(title: str, subtitle: str | None = None) -> None:
    detail = f"<p>{escape(subtitle)}</p>" if subtitle else ""
    st.markdown(
        f'<div class="lp-section"><h2>{escape(title)}</h2>{detail}</div>',
        unsafe_allow_html=True,
    )


def kpi_card(label: str, value: int | str, icon: str) -> None:
    st.markdown(
        '<div class="lp-kpi"><div class="lp-kpi-top">'
        f'<span>{escape(label)}</span><span class="lp-kpi-icon">{escape(icon)}</span>'
        f'</div><div class="lp-kpi-value">{escape(str(value))}</div></div>',
        unsafe_allow_html=True,
    )


def status_badge(status: str) -> str:
    css = STATUS_STYLES.get(status, "new")
    return (
        f'<span class="lp-badge lp-{css}"><span class="lp-dot"></span>'
        f"{escape(status)}</span>"
    )


def empty_state(title: str, message: str, icon: str = "◇") -> None:
    st.markdown(
        f'<div class="lp-empty"><div class="lp-empty-icon">{escape(icon)}</div>'
        f"<h3>{escape(title)}</h3><p>{escape(message)}</p></div>",
        unsafe_allow_html=True,
    )


def alert_message(message: str, *, kind: str = "info") -> None:
    getattr(st, kind if kind in {"info", "success", "warning", "error"} else "info")(
        message
    )


def form_section(title: str, helper: str) -> None:
    st.markdown(
        f'<div class="lp-form-section"><h3>{escape(title)}</h3>'
        f"<p>{escape(helper)}</p></div>",
        unsafe_allow_html=True,
    )


def loading_state(label: str = "Loading…"):
    return st.spinner(label)


def health_badge(label: str, healthy: bool) -> str:
    state = "Healthy" if healthy else "Unavailable"
    css = "healthy" if healthy else "unhealthy"
    return (
        f'<span class="lp-badge lp-{css}"><span class="lp-dot"></span>'
        f"{escape(label)}: {state}</span>"
    )


def is_empty(items: object) -> bool:
    return not bool(items)


def validate_status_styles() -> bool:
    return set(STATUS_STYLES) == set(COMPANY_STATUSES)
