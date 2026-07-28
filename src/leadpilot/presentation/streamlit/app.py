from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import streamlit as st

from leadpilot.bootstrap import Container, bootstrap
from leadpilot.presentation.streamlit.components import health_badge
from leadpilot.presentation.streamlit.navigation import PAGES, navigation_label
from leadpilot.presentation.streamlit.state import switch_organization
from leadpilot.presentation.streamlit.theme import apply_theme

logger = logging.getLogger(__name__)
ASSET_DIRECTORY = Path(__file__).with_name("assets")
LOGO_PATH = ASSET_DIRECTORY / "leadpilot-logo.png"
ICON_PATH = ASSET_DIRECTORY / "leadpilot-icon.png"


@st.cache_resource
def get_container(organization_id: int | None = None) -> Container:
    return bootstrap(organization_id=organization_id)


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
        page_icon=str(ICON_PATH),
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_theme()
    try:
        default_container = get_container()
        active = default_container.organizations.list_active()
        valid_ids = {organization.id for organization in active}
        requested_id = st.session_state.get(
            "organization_id", default_container.organization_context.organization_id
        )
        if requested_id not in valid_ids:
            requested_id = default_container.organization_context.organization_id
        container = get_container(requested_id)
    except Exception:
        logger.exception("LeadPilot startup failed")
        st.error("LeadPilot could not start. Check the application logs for details.")
        return

    st.logo(
        str(LOGO_PATH),
        size="large",
        icon_image=str(ICON_PATH),
    )
    st.sidebar.image(str(LOGO_PATH), width="stretch")
    st.sidebar.markdown(
        '<div class="lp-product-subtitle">Lead Intelligence Workspace</div>',
        unsafe_allow_html=True,
    )
    if len(active) > 1:
        names = {item.id: item.display_name for item in active}
        chosen = st.sidebar.selectbox(
            "Organization",
            [item.id for item in active],
            index=[item.id for item in active].index(requested_id),
            format_func=names.__getitem__,
        )
        if chosen != requested_id and switch_organization(
            st.session_state, chosen, valid_ids
        ):
            st.rerun()
    else:
        st.sidebar.caption(
            f"Organization · {container.organization_context.organization.display_name}"
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
            f"<br><br>{health.environment.title()} environment"
            '<div class="lp-attribution">Built by RapidNest</div></div>',
            unsafe_allow_html=True,
        )
    except Exception:
        logger.exception("Sidebar health check failed")
        st.sidebar.markdown(
            '<div class="lp-health">System status temporarily unavailable'
            '<div class="lp-attribution">Built by RapidNest</div></div>',
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
