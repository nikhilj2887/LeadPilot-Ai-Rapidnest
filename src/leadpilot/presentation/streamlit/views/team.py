from __future__ import annotations

"""Team admin view rendered only through the protected app entry point."""

import streamlit as st

from leadpilot.application.admin import AdminService
from leadpilot.application.auth import (
    OrganizationRole,
    Principal,
    UserStatus,
    can_manage_organization,
)
from leadpilot.bootstrap import Container
from leadpilot.presentation.streamlit.auth_ui import render_access_denied
from leadpilot.presentation.streamlit.components import page_header, section_header


def render(container: Container, principal: Principal, admin: AdminService) -> None:
    if not can_manage_organization(principal):
        render_access_denied("Owner or Admin access is required.")
        return
    organization_id = container.organization_context.organization_id
    page_header(
        "Team",
        "Invite members and manage organization roles.",
        eyebrow="Organization Admin",
    )
    members = container.identities.list_organization_members(organization_id)
    section_header("Members", "Access is enforced through organization memberships.")
    st.dataframe(
        [
            {
                "Member": user.display_name,
                "Email": user.email,
                "Role": membership.role.value,
                "Status": membership.status.value,
                "Joined": membership.joined_at,
            }
            for membership, user in members
        ],
        width="stretch",
        hide_index=True,
    )
    with st.expander("Invite team member"), st.form("team_invite_user"):
        email = st.text_input("Email")
        role = st.selectbox("Role", [item.value for item in OrganizationRole])
        if st.form_submit_button("Send invitation", type="primary"):
            try:
                admin.invite_user(
                    principal,
                    email,
                    organization_id,
                    OrganizationRole(role),
                    redirect_url=container.settings.auth_redirect_url,
                )
                st.success("Invitation sent.")
            except ValueError as exc:
                st.error(str(exc))
    if members:
        with st.expander("Update membership"), st.form("team_update_membership"):
            membership_id = st.selectbox(
                "Member",
                [item.id for item, _ in members],
                format_func={item.id: user.email for item, user in members}.__getitem__,
            )
            role = st.selectbox("New role", [item.value for item in OrganizationRole])
            status = st.selectbox(
                "Membership status",
                [UserStatus.ACTIVE.value, UserStatus.DISABLED.value],
            )
            if st.form_submit_button("Update membership"):
                admin.change_role(
                    principal,
                    organization_id,
                    membership_id,
                    OrganizationRole(role),
                )
                container.identities.update_membership(membership_id, status=status)
                st.success("Membership updated.")
        with st.expander("Remove member"), st.form("team_remove_member"):
            membership_id = st.selectbox(
                "Membership",
                [item.id for item, _ in members],
                format_func={item.id: user.email for item, user in members}.__getitem__,
            )
            confirm = st.checkbox("I confirm this member should be removed")
            if st.form_submit_button("Remove member", disabled=not confirm):
                container.identities.remove_membership(organization_id, membership_id)
                st.success("Member removed.")
