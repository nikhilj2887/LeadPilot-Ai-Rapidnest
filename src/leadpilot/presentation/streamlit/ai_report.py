from __future__ import annotations

from html import escape

import streamlit as st

from leadpilot.application.discovery_ai import DiscoveryAIAnalysis, DiscoveryAIError
from leadpilot.presentation.streamlit.components import section_header


def label_badge(value: str) -> str:
    return f'<span class="lp-badge lp-researching">{escape(value)}</span>'


def render_ai_intelligence(container: object, scan_id: int) -> None:
    section_header(
        "AI Intelligence",
        "Structured interpretation grounded only in stored Discovery evidence.",
    )
    st.warning("AI-generated draft — review before client use.")
    available, availability = container.discovery_ai.availability
    latest = container.discovery_ai.latest_for_scan(scan_id)
    if not available:
        st.info(
            availability
            + " The deterministic Discovery Report remains fully available."
        )
        return
    st.caption(f"Provider/model: {availability}")
    if latest is None:
        st.write(
            "Generate an executive summary, risks, quick wins, recommended RapidNest services, roadmap, discovery questions, and outreach angles."
        )
        if st.button(
            "Generate AI Intelligence", type="primary", key=f"ai-generate-{scan_id}"
        ):
            _generate(container, scan_id, False)
        return
    history = container.discovery_ai.history_for_scan(scan_id)
    selected_id = st.selectbox(
        "AI Analysis History",
        [x.id for x in history],
        format_func=lambda value: _history_label(
            container, next(x for x in history if x.id == value)
        ),
        key=f"ai-history-{scan_id}",
    )
    analysis = container.discovery_ai.get(selected_id)
    if latest.status == "Failed":
        st.error(latest.error_message or "AI generation failed safely.")
    if analysis.status == "Completed":
        _completed(container, analysis)
    if st.button("Regenerate AI Intelligence", key=f"ai-regenerate-{scan_id}"):
        _generate(container, scan_id, True)


def _generate(container: object, scan_id: int, regenerate: bool) -> None:
    try:
        with st.spinner(
            "Generating structured AI Intelligence… this may take a moment."
        ):
            container.discovery_ai.generate(scan_id, regenerate=regenerate)
    except DiscoveryAIError as exc:
        st.error(str(exc))
    else:
        st.rerun()


def _history_label(container: object, item: DiscoveryAIAnalysis) -> str:
    current = "Current" if container.discovery_ai.is_current(item) else "Stale"
    return f"#{item.id} · {item.status} · {item.created_at:%d %b %Y %H:%M} · {current}"


def _completed(container: object, analysis: DiscoveryAIAnalysis) -> None:
    st.markdown(
        label_badge(
            "Current" if container.discovery_ai.is_current(analysis) else "Stale"
        ),
        unsafe_allow_html=True,
    )
    section_header("AI Executive Summary")
    st.write(analysis.executive_summary)
    st.caption(analysis.business_profile)
    for title, field in (
        ("Digital Strengths", "digital_strengths"),
        ("Improvement Areas", "improvement_areas"),
        ("Business Risks", "business_risks"),
        ("Quick Wins", "quick_wins"),
        ("Strategic Opportunities", "strategic_opportunities"),
        ("Recommended RapidNest Services", "recommended_services"),
        ("Implementation Roadmap", "implementation_roadmap"),
        ("Discovery Questions", "discovery_questions"),
        ("Outreach Angles", "outreach_angles"),
    ):
        section_header(title)
        values = getattr(analysis, field)
        if values:
            st.dataframe(values, use_container_width=True, hide_index=True)
        else:
            st.caption("No evidence-supported items were included.")
    section_header("Confidence and Validation Notes")
    st.write(analysis.confidence_notes)
    with st.expander("Generation Metadata"):
        st.write(
            {
                "Provider": analysis.provider,
                "Model": analysis.model,
                "Prompt version": analysis.prompt_version,
                "Schema version": analysis.schema_version,
                "Input tokens": analysis.input_token_count,
                "Output tokens": analysis.output_token_count,
                "Total tokens": analysis.total_token_count,
                "Estimated cost": analysis.estimated_cost,
                "Latency (ms)": analysis.latency_ms,
            }
        )
    section_header("Human Review")
    status = st.selectbox(
        "Review status",
        ("Unreviewed", "Reviewed", "Needs Changes"),
        index=("Unreviewed", "Reviewed", "Needs Changes").index(analysis.review_status),
        key=f"review-status-{analysis.id}",
    )
    notes = st.text_area(
        "Reviewer notes",
        value=analysis.reviewer_notes or "",
        key=f"review-notes-{analysis.id}",
    )
    if st.button("Save Review", key=f"save-review-{analysis.id}"):
        container.discovery_ai.update_review(analysis.id, status, notes)
        st.rerun()
