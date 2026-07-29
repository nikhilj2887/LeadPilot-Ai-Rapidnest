from __future__ import annotations

"""Platform admin view rendered only through the protected app entry point."""

import streamlit as st

from leadpilot.application.admin import AdminService
from leadpilot.application.auth import (
    OrganizationRole,
    PlatformRole,
    Principal,
    UserStatus,
    can_manage_platform,
)
from leadpilot.application.organizations import OrganizationCreate, OrganizationUpdate
from leadpilot.bootstrap import Container
from leadpilot.presentation.streamlit.auth_ui import render_access_denied
from leadpilot.presentation.streamlit.components import page_header, section_header


def render(container: Container, principal: Principal, admin: AdminService) -> None:
    if not can_manage_platform(principal):
        render_access_denied("Super Admin access is required.")
        return
    page_header(
        "Platform Admin",
        "Manage organizations, users, invitations, and platform audit history.",
        eyebrow="Administration",
    )
    organizations_tab, users_tab, audit_tab = st.tabs(
        ("Organizations", "Users", "Audit Logs")
    )
    with organizations_tab:
        section_header("Organizations", "All active and inactive customers.")
        organizations = container.organizations.list_all()
        st.dataframe(
            [
                {
                    "ID": item.id,
                    "Organization": item.display_name,
                    "Slug": item.slug,
                    "Status": item.status.title(),
                }
                for item in organizations
            ],
            width="stretch",
            hide_index=True,
        )
        with (
            st.expander("Create organization"),
            st.form("platform_create_organization"),
        ):
            name = st.text_input("Display name")
            slug = st.text_input("Slug")
            email = st.text_input("Contact email")
            if st.form_submit_button("Create organization", type="primary"):
                try:
                    admin.create_organization(
                        principal,
                        OrganizationCreate(
                            slug=slug,
                            display_name=name,
                            contact_email=email or None,
                        ),
                    )
                    st.success("Organization created.")
                except ValueError as exc:
                    st.error(str(exc))
        with (
            st.expander("Change organization status"),
            st.form("platform_organization_status"),
        ):
            organization_id = st.selectbox(
                "Organization",
                [item.id for item in organizations],
                format_func={
                    item.id: item.display_name for item in organizations
                }.__getitem__,
            )
            status = st.selectbox("Status", ("active", "suspended", "archived"))
            if st.form_submit_button("Update status"):
                admin.update_organization(
                    principal,
                    organization_id,
                    OrganizationUpdate(status=status),
                )
                st.success("Organization status updated.")
    with users_tab:
        users = container.identities.list_users()
        section_header("Users", "Platform user profiles and account status.")
        st.dataframe(
            [
                {
                    "ID": user.id,
                    "User": user.display_name,
                    "Email": user.email,
                    "Status": user.status.value,
                    "Platform role": user.platform_role.value
                    if user.platform_role
                    else "—",
                }
                for user in users
            ],
            width="stretch",
            hide_index=True,
        )
        organizations = container.organizations.list_active()
        with st.expander("Invite user"), st.form("platform_invite_user"):
            email = st.text_input("Email")
            organization_id = st.selectbox(
                "Organization",
                [item.id for item in organizations],
                format_func={
                    item.id: item.display_name for item in organizations
                }.__getitem__,
            )
            role = st.selectbox(
                "Organization role", [item.value for item in OrganizationRole]
            )
            platform_role = st.selectbox(
                "Platform role",
                ["None", *[item.value for item in PlatformRole]],
            )
            if st.form_submit_button("Send invitation", type="primary"):
                try:
                    admin.invite_user(
                        principal,
                        email,
                        organization_id,
                        OrganizationRole(role),
                        redirect_url=container.settings.auth_redirect_url,
                        platform_role=PlatformRole(platform_role)
                        if platform_role != "None"
                        else None,
                    )
                    st.success("Invitation sent.")
                except ValueError as exc:
                    st.error(str(exc))
        if users:
            with st.expander("Change user status"), st.form("platform_user_status"):
                user_id = st.selectbox(
                    "User",
                    [user.id for user in users],
                    format_func={user.id: user.email for user in users}.__getitem__,
                )
                status = st.selectbox(
                    "Account status", [item.value for item in UserStatus]
                )
                if st.form_submit_button("Update user"):
                    container.identities.update_user(user_id, status=status)
                    st.success("User updated.")
                if st.form_submit_button("Send password reset"):
                    email = next(user.email for user in users if user.id == user_id)
                    try:
                        admin.auth.provider.request_password_reset(
                            email, container.settings.auth_redirect_url
                        )
                        st.success("Password reset email requested.")
                    except ValueError as exc:
                        st.error(str(exc))
    with audit_tab:
        section_header("Audit Logs", "Recent security and administration events.")
        logs = container.identities.list_audit_logs()
        st.dataframe(logs, width="stretch", hide_index=True)
