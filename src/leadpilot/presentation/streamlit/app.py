from __future__ import annotations

import logging
from collections.abc import Callable

import streamlit as st

from leadpilot.bootstrap import Container, bootstrap
from leadpilot.presentation.streamlit.components import health_badge
from leadpilot.presentation.streamlit.navigation import PAGES, navigation_label
from leadpilot.presentation.streamlit.theme import apply_theme

logger = logging.getLogger(__name__)


@st.cache_resource
def get_container() -> Container:
    return bootstrap()


def render_page_safely(
    renderer: Callable[[Container], None],
    container: Container,
    *,
    on_error: Callable[[str], None],
) -> bool:
    try:
        renderer(container)
    except Exception:
        logger.exception("Page rendering failed")
        on_error(
            "This page could not be displayed completely. "
            "Your saved data has not been affected."
        )
        return False
    return True


def main() -> None:
    st.set_page_config(
        page_title="LeadPilot AI",
        page_icon="L",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_theme()
    try:
        container = get_container()
    except Exception:
        logger.exception("LeadPilot startup failed")
        st.error("LeadPilot could not start. Check the application logs for details.")
        return

    st.sidebar.markdown(
        '<div class="lp-brand"><div class="lp-brand-name">'
        '<span class="lp-brand-mark">L</span>LeadPilot AI</div>'
        '<div class="lp-brand-subtitle">Lead Intelligence Workspace</div></div>',
        unsafe_allow_html=True,
    )
    selected_page = st.sidebar.radio(
        "Navigation",
        list(PAGES),
        key="navigation",
        format_func=navigation_label,
        label_visibility="collapsed",
    )
    render_page_safely(PAGES[selected_page], container, on_error=st.error)
    st.sidebar.divider()
    try:
        health = container.health_check.check()
        st.sidebar.markdown(
            '<div class="lp-health"><strong>System</strong><br>'
            f"{health_badge('Database', health.database_connected)}"
            f"<br><br>{health.environment.title()} environment</div>",
            unsafe_allow_html=True,
        )
    except Exception:
        logger.exception("Sidebar health check failed")
        st.sidebar.caption("System status temporarily unavailable")


if __name__ == "__main__":
    main()
