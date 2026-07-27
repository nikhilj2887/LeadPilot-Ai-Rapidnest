from __future__ import annotations

import streamlit as st

from leadpilot.bootstrap import Container


def render(container: Container) -> None:
    st.title("Settings")
    health = container.health_check.check()
    st.subheader("Application health")
    st.metric("Application", health.application_status.title())
    st.metric("Database", "Connected" if health.database_connected else "Unavailable")
    st.metric("Environment", health.environment)
    if health.database_error:
        st.error("The database is unavailable. See application logs for details.")
