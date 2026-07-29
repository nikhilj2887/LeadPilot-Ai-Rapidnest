from __future__ import annotations

from typing import Any

from leadpilot.application.auth import (
    AuthenticationService,
    AuthorizationError,
    OrganizationRole,
    PlatformRole,
    Principal,
    User,
    UserStatus,
    can_manage_organization,
    can_manage_platform,
)
from leadpilot.application.organizations import OrganizationCreate, OrganizationUpdate


class AdminService:
    def __init__(
        self,
        auth: AuthenticationService,
        organizations: Any,
        identities: Any,
    ) -> None:
        self.auth = auth
        self.organizations = organizations
        self.identities = identities

    def create_organization(
        self, principal: Principal, values: OrganizationCreate
    ) -> Any:
        self._platform(principal)
        return self.organizations.create(values)

    def update_organization(
        self,
        principal: Principal,
        organization_id: int,
        values: OrganizationUpdate,
    ) -> Any:
        self._platform(principal)
        return self.organizations.update(organization_id, values)

    def invite_user(
        self,
        principal: Principal,
        email: str,
        organization_id: int,
        role: OrganizationRole,
        *,
        redirect_url: str | None = None,
        platform_role: PlatformRole | None = None,
    ) -> User:
        if platform_role is not None:
            self._platform(principal)
        elif not can_manage_organization(principal):
            raise AuthorizationError("Organization administration is required.")
        elif not principal.is_super_admin and (
            principal.current_membership is None
            or principal.current_membership.organization_id != organization_id
        ):
            raise AuthorizationError("You cannot invite users to this organization.")
        supabase_id = self.auth.provider.invite_user(email, redirect_url)
        user = self.identities.create_invited_user(
            supabase_id, email, platform_role=platform_role
        )
        self.identities.create_membership(
            organization_id,
            user.id,
            role,
            status=UserStatus.INVITED,
        )
        self.identities.log(
            "CREATE_USER",
            "user",
            organization_id=organization_id,
            user_id=principal.user.id,
            entity_id=str(user.id),
            details={"role": role.value},
        )
        return user

    def change_role(
        self,
        principal: Principal,
        organization_id: int,
        membership_id: int,
        role: OrganizationRole,
    ) -> Any:
        if not can_manage_organization(principal):
            raise AuthorizationError("Organization administration is required.")
        if (
            not principal.is_super_admin
            and principal.current_membership
            and principal.current_membership.organization_id != organization_id
        ):
            raise AuthorizationError("You cannot modify this organization.")
        membership = self.identities.update_membership(membership_id, role=role.value)
        self.identities.log(
            "ROLE_CHANGE",
            "organization_membership",
            organization_id=organization_id,
            user_id=principal.user.id,
            entity_id=str(membership_id),
            details={"role": role.value},
        )
        return membership

    @staticmethod
    def _platform(principal: Principal) -> None:
        if not can_manage_platform(principal):
            raise AuthorizationError("Super Admin access is required.")
