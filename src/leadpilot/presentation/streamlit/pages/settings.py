from __future__ import annotations

import streamlit as st

from leadpilot.bootstrap import Container
from leadpilot.presentation.streamlit.components import (
    health_badge,
    page_header,
    section_header,
)


def render(container: Container) -> None:
    page_header(
        "Settings",
        "Review application identity, runtime environment, and service health.",
        eyebrow="Application",
    )
    health = container.health_check.check()
    section_header(
        "Application Health",
        "A safe operational summary without credentials or internal error details.",
    )
    cards = (
        (
            "Application Status",
            health.application_status.title(),
            health.application_status == "running",
        ),
        (
            "Database Status",
            "Connected" if health.database_connected else "Unavailable",
            health.database_connected,
        ),
        ("Environment", health.environment.title(), True),
        ("Application Name", container.settings.app_name, True),
    )
    for column, (label, value, healthy) in zip(st.columns(4), cards, strict=True):
        with column:
            st.markdown(
                '<div class="lp-kpi"><div class="lp-kpi-top">'
                f'<span>{label}</span></div><div class="lp-value" '
                f'style="margin:.75rem 0">{value}</div>'
                f"{health_badge('Healthy' if healthy else 'Attention', healthy)}</div>",
                unsafe_allow_html=True,
            )
    if health.database_error:
        st.error(
            "The database is currently unavailable. Check application logs or contact "
            "the administrator; connection details are intentionally hidden."
        )
    else:
        st.success("All configured application services are operating normally.")
