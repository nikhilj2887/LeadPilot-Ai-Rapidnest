from __future__ import annotations

import pandas as pd
import streamlit as st

from leadpilot.bootstrap import Container


def render(container: Container) -> None:
    st.title("Dashboard")
    st.caption("A snapshot of your company lead pipeline.")
    metrics = container.companies.metrics()
    columns = st.columns(5)
    for column, label, value in zip(
        columns,
        (
            "Total Companies",
            "New Leads",
            "Qualified Leads",
            "Contacted Leads",
            "Proposal Stage",
        ),
        (
            metrics.total,
            metrics.new,
            metrics.qualified,
            metrics.contacted,
            metrics.proposal,
        ),
        strict=True,
    ):
        column.metric(label, value)

    left, right = st.columns(2)
    with left:
        st.subheader("Recent Companies")
        recent = container.companies.recent_companies(5)
        if recent:
            for company in recent:
                st.markdown(f"**{company.name}** · {company.status}")
                st.caption(company.industry or "Industry not specified")
        else:
            st.info("No companies have been added yet.")
    with right:
        st.subheader("Companies by Status")
        chart_data = pd.DataFrame(
            {
                "Status": list(metrics.by_status),
                "Companies": list(metrics.by_status.values()),
            }
        ).set_index("Status")
        st.bar_chart(chart_data)
