from __future__ import annotations

import logging

import streamlit as st

from leadpilot.bootstrap import Container, bootstrap
from leadpilot.presentation.streamlit.navigation import PAGES

logger = logging.getLogger(__name__)


@st.cache_resource
def get_container() -> Container:
    return bootstrap()


def main() -> None:
    st.set_page_config(page_title="LeadPilot AI", page_icon="🚀", layout="wide")
    try:
        container = get_container()
        st.sidebar.title(container.settings.app_name)
        selected_page = st.sidebar.radio("Navigation", list(PAGES))
        PAGES[selected_page](container)
        st.sidebar.divider()
        health = container.health_check.check()
        status_icon = "🟢" if health.is_healthy else "🔴"
        st.sidebar.caption(f"{status_icon} {health.application_status.title()}")
        st.sidebar.caption(f"Environment: {health.environment}")
        st.sidebar.caption(
            f"Database: {'Connected' if health.database_connected else 'Unavailable'}"
        )
    except Exception:
        logger.exception("Unhandled error while rendering LeadPilot")
        st.error("LeadPilot could not start. Check the application logs for details.")


if __name__ == "__main__":
    main()
