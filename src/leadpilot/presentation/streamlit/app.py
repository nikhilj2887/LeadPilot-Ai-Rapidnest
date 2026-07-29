from __future__ import annotations

import logging
from collections.abc import Callable
from html import escape
from pathlib import Path

import streamlit as st

from leadpilot.application.admin import AdminService
from leadpilot.application.auth import (
    AuthenticationError,
    Principal,
    UserStatus,
)
from leadpilot.bootstrap import (
    Container,
    bootstrap,
    bootstrap_auth,
    list_active_organizations,
)
from leadpilot.config import get_settings
from leadpilot.presentation.streamlit.auth_ui import (
    clear_authenticated_state,
    render_access_denied,
    render_login,
)
from leadpilot.presentation.streamlit.components import health_badge
from leadpilot.presentation.streamlit.navigation import (
    PAGES,
    navigation_label,
    pages_for_principal,
)
from leadpilot.presentation.streamlit.state import switch_organization
from leadpilot.presentation.streamlit.theme import apply_theme
from leadpilot.presentation.streamlit.views import platform_admin, team

logger = logging.getLogger(__name__)
ASSET_DIRECTORY = Path(__file__).with_name("assets")
LOGO_PATH = ASSET_DIRECTORY / "leadpilot-logo.png"
ICON_PATH = ASSET_DIRECTORY / "leadpilot-icon.png"


@st.cache_resource
def get_container(
    organization_id: int | None = None,
    user_id: int | None = None,
    organization_role=None,
) -> Container:
    return bootstrap(
        organization_id=organization_id,
        user_id=user_id,
        organization_role=organization_role,
    )


@st.cache_resource
def get_auth_service():
    return bootstrap_auth()


def organization_selector_required(active_count: int) -> bool:
    return active_count > 1


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
    settings = get_settings()
    if not settings.auth_enabled:
        render_access_denied(
            "Authentication has not been configured for this deployment.",
            next_action=(
                "Configure the required Supabase environment variables, then restart "
                "the application."
            ),
        )
        return
    try:
        auth = get_auth_service()
    except Exception:
        logger.exception("Authentication startup failed")
        render_access_denied(
            "The authentication service is temporarily unavailable.",
            next_action="Ask the deployment administrator to review the configuration.",
        )
        return
    principal: Principal | None = st.session_state.get("principal")
    auth_session = st.session_state.get("auth_session")
    if principal is None and auth_session is not None:
        try:
            refreshed, principal = auth.restore(auth_session.refresh_token)
            st.session_state.auth_session = refreshed
            st.session_state.principal = principal
        except AuthenticationError:
            clear_authenticated_state()
    if principal is None:
        render_login(auth, settings.auth_redirect_url)
        return
    try:
        all_active = list_active_organizations(settings)
        membership_ids = {
            item.organization_id
            for item in principal.memberships
            if item.status == UserStatus.ACTIVE
        }
        active = [
            organization
            for organization in all_active
            if principal.is_super_admin or organization.id in membership_ids
        ]
        if not active:

            def denied_logout() -> None:
                try:
                    auth.logout(st.session_state.auth_session, principal)
                finally:
                    clear_authenticated_state()
                st.rerun()

            has_active_membership = any(
                item.status == UserStatus.ACTIVE for item in principal.memberships
            )
            has_invitation = any(
                item.status == UserStatus.INVITED for item in principal.memberships
            )
            has_inactive_membership = bool(principal.memberships) and not (
                has_active_membership or has_invitation
            )
            if has_active_membership:
                message = "Your assigned organization is not currently active."
                next_action = "Contact a platform administrator."
            elif has_invitation:
                message = "Your organization invitation has not been activated yet."
                next_action = "Ask an organization administrator to activate access."
            elif has_inactive_membership:
                message = "Your organization membership is inactive."
                next_action = "Ask an organization administrator to restore access."
            else:
                message = (
                    "Your account is authenticated but has not been assigned to an "
                    "organization."
                )
                next_action = "Ask an organization administrator to grant access."
            render_access_denied(
                message, next_action=next_action, on_logout=denied_logout
            )
            return
        valid_ids = {organization.id for organization in active}
        default_membership = next(
            (
                item
                for item in principal.memberships
                if item.is_default and item.organization_id in valid_ids
            ),
            None,
        )
        fallback_id = (
            default_membership.organization_id if default_membership else active[0].id
        )
        requested_id = st.session_state.get("organization_id", fallback_id)
        if requested_id not in valid_ids:
            requested_id = fallback_id
        principal = auth.select_organization(principal, requested_id)
        st.session_state.principal = principal
        st.session_state.organization_id = requested_id
        effective_role = (
            principal.current_membership.role if principal.current_membership else None
        )
        container = get_container(requested_id, principal.user.id, effective_role)
    except Exception:
        logger.exception("LeadPilot startup failed")
        render_access_denied(
            "LeadPilot could not reach its application database.",
            next_action="Try again later or ask the deployment administrator for help.",
        )
        return

    st.sidebar.image(str(LOGO_PATH), width="stretch")
    st.sidebar.markdown(
        '<div class="lp-product-subtitle">Lead Intelligence Workspace</div>',
        unsafe_allow_html=True,
    )
    current_name = container.organization_context.organization.display_name
    st.sidebar.markdown(
        '<div class="lp-organization">'
        '<div class="lp-organization-label">Organization</div>'
        f'<div class="lp-organization-name" title="{escape(current_name)}">'
        f"{escape(current_name)}</div></div>",
        unsafe_allow_html=True,
    )
    if organization_selector_required(len(active)):
        names = {item.id: item.display_name for item in active}
        chosen = st.sidebar.selectbox(
            "Switch organization",
            [item.id for item in active],
            index=[item.id for item in active].index(requested_id),
            format_func=names.__getitem__,
        )
        if chosen != requested_id and switch_organization(
            st.session_state, chosen, valid_ids
        ):
            st.session_state.principal = auth.select_organization(principal, chosen)
            st.rerun()
    role = (
        principal.current_membership.role.value
        if principal.current_membership
        else principal.user.platform_role.value
        if principal.user.platform_role
        else "Platform access"
    )
    st.sidebar.markdown(
        f'<div class="lp-user"><strong>{escape(principal.user.display_name)}</strong>'
        f"<span>{escape(role)}</span></div>",
        unsafe_allow_html=True,
    )
    if st.sidebar.button("Log out", width="stretch"):
        try:
            auth.logout(st.session_state.auth_session, principal)
        finally:
            clear_authenticated_state()
        st.rerun()
    available_pages = pages_for_principal(principal)
    if st.session_state.get("navigation") not in available_pages:
        st.session_state.navigation = "Dashboard"
    selected_page = st.sidebar.radio(
        "Navigation",
        available_pages,
        key="navigation",
        format_func=navigation_label,
        label_visibility="collapsed",
    )
    admin = AdminService(auth, container.organizations, container.identities)
    if selected_page == "Team":
        render_page_safely(
            lambda current: team.render(current, principal, admin),
            container,
            on_error=st.error,
        )
    elif selected_page == "Platform Admin":
        render_page_safely(
            lambda current: platform_admin.render(current, principal, admin),
            container,
            on_error=st.error,
        )
    else:
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
