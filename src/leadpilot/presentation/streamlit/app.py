from __future__ import annotations

import logging

import streamlit as st

from leadpilot.bootstrap import Container, bootstrap
from leadpilot.presentation.streamlit.components import health_badge
from leadpilot.presentation.streamlit.navigation import PAGES, navigation_label
from leadpilot.presentation.streamlit.theme import apply_theme

logger = logging.getLogger(__name__)


@st.cache_resource
def get_container() -> Container:
    return bootstrap()


def main() -> None:
    st.set_page_config(
        page_title="LeadPilot AI",
        page_icon="◈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_theme()
    try:
        container = get_container()
        st.sidebar.markdown(
            '<div class="lp-brand"><div class="lp-brand-name">'
            '<span class="lp-brand-mark">L</span>LeadPilot AI</div>'
            '<div class="lp-brand-subtitle">AI-Powered Lead Intelligence</div></div>',
            unsafe_allow_html=True,
        )
        selected_page = st.sidebar.radio(
            "Navigation",
            list(PAGES),
            key="navigation",
            format_func=navigation_label,
            label_visibility="collapsed",
        )
        PAGES[selected_page](container)
        st.sidebar.divider()
        health = container.health_check.check()
        st.sidebar.markdown(
            '<div class="lp-health"><strong>System</strong><br>'
            f"{health_badge('Database', health.database_connected)}"
            f"<br><br>{health.environment.title()} environment</div>",
            unsafe_allow_html=True,
        )
    except Exception:
        logger.exception("Unhandled error while rendering LeadPilot")
        st.error("LeadPilot could not start. Check the application logs for details.")


if __name__ == "__main__":
    main()
