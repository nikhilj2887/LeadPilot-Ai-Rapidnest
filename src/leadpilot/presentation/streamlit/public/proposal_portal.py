from __future__ import annotations

import streamlit as st

from leadpilot.application.proposal_portal import (
    PortalDownloadDisabledError,
    PortalLinkExpiredError,
    PortalLinkUnavailableError,
    PortalPasswordInvalidError,
    PortalPasswordRequiredError,
    PortalRateLimitError,
    ProposalPortalAccessRequest,
    ProposalPortalError,
)
from leadpilot.bootstrap import bootstrap_public_portal


def render() -> None:
    st.set_page_config(
        page_title="Secure Proposal",
        page_icon=None,
        layout="centered",
        initial_sidebar_state="collapsed",
    )
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
        [data-testid="stHeader"], [data-testid="stToolbar"] {display:none !important;}
        .block-container {max-width: 900px; padding-top: 2rem;}
        @media (max-width: 640px) {.block-container {padding: 1rem;}}
        </style>
        """,
        unsafe_allow_html=True,
    )
    token = str(st.query_params.get("portal_token", ""))
    if not token:
        _unavailable("Proposal unavailable")
        return
    service = bootstrap_public_portal()
    context = st.session_state.get("public_portal_context")
    if context is not None and not service.context_matches_token(context, token):
        st.session_state.pop("public_portal_context", None)
        context = None
    if context is None:
        context = _resolve(service, token)
        if context is None:
            return
        st.session_state.public_portal_context = context
    try:
        view = service.get_public_proposal_view(context)
    except ProposalPortalError:
        _unavailable("Proposal unavailable")
        return
    _proposal(view, service, context)


def _resolve(service: object, token: str):
    try:
        return service.resolve_portal_access(ProposalPortalAccessRequest(token))  # type: ignore[attr-defined]
    except PortalPasswordRequiredError:
        st.title("Protected proposal")
        st.write("Enter the password supplied by the proposal sender.")
        with st.form("portal_password"):
            password = st.text_input(
                "Password", type="password", max_chars=256, autocomplete="off"
            )
            submit = st.form_submit_button("View proposal", type="primary")
        if submit:
            try:
                return service.resolve_portal_access(  # type: ignore[attr-defined]
                    ProposalPortalAccessRequest(token, password=password)
                )
            except (PortalPasswordInvalidError, PortalRateLimitError):
                st.error("Proposal unavailable. Check the link and password.")
        return None
    except PortalLinkExpiredError:
        _unavailable("This proposal link has expired")
    except (PortalLinkUnavailableError, PortalRateLimitError):
        _unavailable("Proposal unavailable")
    return None


def _proposal(view: object, service: object, context: object) -> None:
    branding = view.branding  # type: ignore[attr-defined]
    proposal = view.proposal  # type: ignore[attr-defined]
    company = view.company  # type: ignore[attr-defined]
    primary = branding.get("primary_color") or "#2563EB"
    st.markdown(
        f'<div style="border-top:6px solid {primary};padding-top:20px"></div>',
        unsafe_allow_html=True,
    )
    st.title(str(branding.get("brand_name") or "Proposal"))
    st.caption("Confidential client proposal")
    st.header(str(proposal.get("title") or "Proposal"))
    st.write(f"**Proposal:** {proposal.get('number', '')}")
    st.write(f"**Prepared for:** {company.get('name', '')}")
    if proposal.get("valid_until"):
        st.write(f"**Valid until:** {proposal['valid_until']}")
    for section in view.sections:  # type: ignore[attr-defined]
        st.subheader(str(section.get("title") or ""))
        st.write(str(section.get("content") or ""))
    if view.commercial is not None:  # type: ignore[attr-defined]
        st.subheader("Commercial Summary")
        st.dataframe(
            [
                {
                    "Offering": item.get("title"),
                    "Quantity": item.get("quantity"),
                    "Unit price": item.get("unit_price"),
                    "Total": item.get("line_total"),
                }
                for item in view.items  # type: ignore[attr-defined]
            ],
            hide_index=True,
            width="stretch",
        )
        commercial = view.commercial  # type: ignore[attr-defined]
        st.write(
            f"**Total: {commercial.get('currency', '')} {commercial.get('total', '')}**"
        )
    if view.allow_pdf_download:  # type: ignore[attr-defined]
        try:
            filename, content = service.download_public_proposal_pdf(context)  # type: ignore[attr-defined]
        except (PortalDownloadDisabledError, PortalLinkUnavailableError):
            st.info("PDF download is unavailable.")
        else:
            st.download_button(
                "Download proposal PDF",
                content,
                file_name=filename,
                mime="application/pdf",
            )
    contact = " · ".join(
        str(value)
        for value in (branding.get("contact_email"), branding.get("contact_phone"))
        if value
    )
    if contact:
        st.divider()
        st.write(contact)
    if branding.get("proposal_footer"):
        st.caption(str(branding["proposal_footer"]))
    if view.expires_at:  # type: ignore[attr-defined]
        st.caption(f"Secure link expires {view.expires_at}")  # type: ignore[attr-defined]


def _unavailable(title: str) -> None:
    st.title(title)
    st.write("Please contact the proposal sender if you need assistance.")
