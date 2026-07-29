from __future__ import annotations

import streamlit as st

from leadpilot.application.auth import AuthenticationError, AuthenticationService


def clear_authenticated_state() -> None:
    for key in tuple(st.session_state):
        if key.startswith(
            (
                "auth_",
                "organization_",
                "selected_",
                "company_",
                "discovery_",
                "ai_",
            )
        ) or key in {"navigation", "principal"}:
            st.session_state.pop(key, None)


def render_login(auth: AuthenticationService, redirect_url: str | None) -> None:
    st.markdown('<div class="lp-login-shell">', unsafe_allow_html=True)
    st.title("Sign in to LeadPilot AI")
    st.caption("Use your authorized business account to continue.")
    login_tab, forgot_tab, reset_tab = st.tabs(
        ("Sign in", "Forgot password", "Reset password")
    )
    with login_tab, st.form("login_form"):
        email = st.text_input("Email", autocomplete="email")
        password = st.text_input(
            "Password", type="password", autocomplete="current-password"
        )
        remember = st.checkbox("Remember this session", value=True)
        if st.form_submit_button("Sign in", type="primary"):
            try:
                session, principal = auth.login(email, password)
                st.session_state.auth_session = session
                st.session_state.principal = principal
                st.session_state.auth_remember = remember
                st.session_state.navigation = "Dashboard"
                st.rerun()
            except AuthenticationError as exc:
                st.error(str(exc))
    with forgot_tab, st.form("forgot_password_form"):
        recovery_email = st.text_input("Account email", autocomplete="email")
        if st.form_submit_button("Send reset link"):
            try:
                auth.provider.request_password_reset(
                    recovery_email.strip().casefold(), redirect_url
                )
                st.success("If that account exists, Supabase will send a reset link.")
            except AuthenticationError as exc:
                st.error(str(exc))
    with reset_tab, st.form("reset_password_form"):
        new_password = st.text_input(
            "New password", type="password", autocomplete="new-password"
        )
        confirm = st.text_input(
            "Confirm password", type="password", autocomplete="new-password"
        )
        if st.form_submit_button("Update password"):
            session = st.session_state.get("auth_session")
            if session is None:
                st.error("Open this page from your authenticated reset session.")
            elif new_password != confirm:
                st.error("Passwords do not match.")
            else:
                try:
                    auth.provider.update_password(session.access_token, new_password)
                    st.success("Password updated. You can now sign in.")
                except AuthenticationError as exc:
                    st.error(str(exc))
    st.markdown("</div>", unsafe_allow_html=True)


def render_access_denied(message: str) -> None:
    st.title("Access denied")
    st.warning(message)
    st.caption(
        "Contact an organization administrator if you believe this is incorrect."
    )
