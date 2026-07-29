from __future__ import annotations

from collections.abc import Callable
from html import escape

import streamlit as st

from leadpilot.application.auth import AuthenticationError, AuthenticationService

AUTH_CSS = """
<style>
.lp-auth-brand {
  min-height:610px; padding:clamp(2rem,5vw,4.5rem); border-radius:24px;
  background:
    radial-gradient(circle at 80% 12%,rgba(124,108,255,.35),transparent 34%),
    linear-gradient(145deg,#15132f,#24205c 58%,#17152e);
  border:1px solid rgba(153,142,255,.28); color:#f8f7ff;
  box-shadow:0 28px 80px rgba(11,10,30,.25);
}
.lp-auth-mark {font-size:1rem;font-weight:800;letter-spacing:.02em;color:#fff}
.lp-auth-brand h1 {font-size:clamp(2.2rem,4vw,3.8rem);line-height:1.04;
  letter-spacing:-.055em;max-width:650px;margin:5.5rem 0 1.2rem}
.lp-auth-brand>p {font-size:1.08rem;line-height:1.65;color:#cbc8e9;max-width:580px}
.lp-auth-benefits {display:grid;gap:.8rem;margin-top:3rem}
.lp-auth-benefit {padding:.9rem 1rem;border-radius:12px;
  background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1)}
.lp-auth-card {max-width:520px;margin:clamp(1rem,7vh,5rem) auto 0}
.lp-auth-card h2 {font-size:2rem;letter-spacing:-.04em;margin-bottom:.3rem}
.lp-auth-card .lp-auth-copy {color:var(--lp-muted);margin-bottom:1.5rem}
.lp-auth-card div[data-testid="stForm"] {padding:1.35rem}
.lp-auth-card input:focus {box-shadow:0 0 0 3px rgba(109,93,252,.28)}
.lp-denied-card {max-width:620px;margin:12vh auto 0;padding:2rem;border-radius:18px;
 border:1px solid var(--lp-border);background:var(--secondary-background-color)}
[data-testid="stToolbar"] {opacity:.55;transition:opacity .18s ease}
[data-testid="stToolbar"]:hover,[data-testid="stToolbar"]:focus-within {opacity:1}
@media(max-width:850px){
  .lp-auth-brand{display:none}
  .lp-auth-card{margin:2rem auto}
  [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:first-child{display:none}
}
</style>
"""


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
    st.markdown(AUTH_CSS, unsafe_allow_html=True)
    brand, form_column = st.columns((1.15, 0.85), gap="large")
    with brand:
        st.markdown(
            """
            <section class="lp-auth-brand">
              <div class="lp-auth-mark">◆ LeadPilot AI</div>
              <h1>Turn market signals into meaningful conversations.</h1>
              <p>A focused lead-intelligence workspace for teams that want to
              research faster, qualify confidently, and act with context.</p>
              <div class="lp-auth-benefits">
                <div class="lp-auth-benefit">Discover actionable company signals</div>
                <div class="lp-auth-benefit">Prioritize opportunities with AI-assisted insight</div>
                <div class="lp-auth-benefit">Keep every organization securely separated</div>
              </div>
            </section>
            """,
            unsafe_allow_html=True,
        )
    with form_column:
        st.markdown('<div class="lp-auth-card">', unsafe_allow_html=True)
        st.markdown("<h2>Welcome back</h2>", unsafe_allow_html=True)
        st.markdown(
            '<p class="lp-auth-copy">Sign in with your authorized business account.</p>',
            unsafe_allow_html=True,
        )
        login_tab, forgot_tab, reset_tab = st.tabs(
            ("Sign in", "Forgot password", "Reset password")
        )
    with form_column, login_tab, st.form("login_form"):
        email = st.text_input("Email", key="login_email", autocomplete="email")
        password = st.text_input(
            "Password",
            type="password",
            key="login_password",
            autocomplete="current-password",
        )
        remember = st.checkbox("Remember this session", value=True)
        pending_error = st.session_state.pop("auth_login_error", None)
        if pending_error:
            st.error(pending_error)
        if st.form_submit_button("Sign in", type="primary", width="stretch"):
            try:
                session, principal = auth.login(email, password)
                st.session_state.auth_session = session
                st.session_state.principal = principal
                st.session_state.auth_remember = remember
                st.session_state.navigation = "Dashboard"
                st.rerun()
            except AuthenticationError as exc:
                st.session_state.auth_login_error = str(exc)
                st.session_state.pop("login_password", None)
                st.rerun()
    with form_column, forgot_tab, st.form("forgot_password_form"):
        recovery_email = st.text_input("Account email", autocomplete="email")
        if st.form_submit_button("Send reset link", width="stretch"):
            try:
                auth.provider.request_password_reset(
                    recovery_email.strip().casefold(), redirect_url
                )
            except AuthenticationError:
                pass
            st.success(
                "If an account exists for this email, password reset instructions "
                "have been sent."
            )
    with form_column, reset_tab, st.form("reset_password_form"):
        new_password = st.text_input(
            "New password", type="password", autocomplete="new-password"
        )
        confirm = st.text_input(
            "Confirm password", type="password", autocomplete="new-password"
        )
        if st.form_submit_button("Update password", width="stretch"):
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
    with form_column:
        st.markdown("</div>", unsafe_allow_html=True)


def render_access_denied(
    message: str,
    *,
    next_action: str = "Contact an administrator if you believe this is incorrect.",
    on_logout: Callable[[], None] | None = None,
) -> None:
    st.markdown(AUTH_CSS, unsafe_allow_html=True)
    st.markdown(
        '<section class="lp-denied-card"><div class="lp-eyebrow">ACCOUNT ACCESS</div>'
        "<h1>LeadPilot access is not available</h1>"
        f"<p>{escape(message)}</p><p><strong>Next step:</strong> "
        f"{escape(next_action)}</p></section>",
        unsafe_allow_html=True,
    )
    _, center, _ = st.columns((1, 1, 1))
    if on_logout is not None and center.button(
        "Log out and return to sign in", type="primary", width="stretch"
    ):
        on_logout()
