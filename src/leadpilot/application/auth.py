from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INVITED = "INVITED"
    DISABLED = "DISABLED"
    LOCKED = "LOCKED"


class OrganizationRole(StrEnum):
    OWNER = "Owner"
    ADMIN = "Admin"
    MANAGER = "Manager"
    ANALYST = "Analyst"
    VIEWER = "Viewer"


class PlatformRole(StrEnum):
    SUPER_ADMIN = "Super Admin"
    SUPPORT_ADMIN = "Support Admin"


ROLE_LEVEL = {
    OrganizationRole.VIEWER: 1,
    OrganizationRole.ANALYST: 2,
    OrganizationRole.MANAGER: 3,
    OrganizationRole.ADMIN: 4,
    OrganizationRole.OWNER: 5,
}


class AuthenticationError(ValueError):
    pass


class AuthorizationError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class User:
    id: int
    supabase_user_id: str
    first_name: str | None
    last_name: str | None
    email: str
    phone: str | None
    avatar_url: str | None
    status: UserStatus
    platform_role: PlatformRole | None
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @property
    def display_name(self) -> str:
        name = " ".join(filter(None, (self.first_name, self.last_name))).strip()
        return name or self.email


@dataclass(frozen=True, slots=True)
class Membership:
    id: int
    organization_id: int
    user_id: int
    role: OrganizationRole
    status: UserStatus
    is_default: bool
    joined_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AuthSession:
    access_token: str
    refresh_token: str
    expires_at: int
    supabase_user_id: str
    email: str


@dataclass(frozen=True, slots=True)
class Principal:
    user: User
    memberships: tuple[Membership, ...]
    current_membership: Membership | None = None
    selected_organization_id: int | None = None

    @property
    def is_super_admin(self) -> bool:
        return self.user.platform_role == PlatformRole.SUPER_ADMIN

    def can_access_organization(self, organization_id: int) -> bool:
        return any(
            membership.organization_id == organization_id
            and membership.status == UserStatus.ACTIVE
            for membership in self.memberships
        )

    def require_role(self, minimum: OrganizationRole) -> None:
        if self.is_super_admin:
            return
        if self.current_membership is None:
            raise AuthorizationError("An organization membership is required.")
        if ROLE_LEVEL[self.current_membership.role] < ROLE_LEVEL[minimum]:
            raise AuthorizationError("You do not have permission for this action.")


class AuthProvider(Protocol):
    def sign_in(self, email: str, password: str) -> AuthSession: ...
    def refresh(self, refresh_token: str) -> AuthSession: ...
    def sign_out(self, access_token: str) -> None: ...
    def request_password_reset(self, email: str, redirect_url: str | None) -> None: ...
    def update_password(self, access_token: str, password: str) -> None: ...
    def invite_user(self, email: str, redirect_url: str | None) -> str: ...


class IdentityRepository(Protocol):
    def sync_authenticated_user(self, supabase_user_id: str, email: str) -> User: ...
    def get_user(self, user_id: int) -> User | None: ...
    def list_users(self) -> list[User]: ...
    def list_memberships(self, user_id: int) -> list[Membership]: ...
    def create_membership(
        self,
        organization_id: int,
        user_id: int,
        role: OrganizationRole,
        *,
        status: UserStatus,
        is_default: bool = False,
    ) -> Membership: ...
    def update_membership(
        self, membership_id: int, **values: Any
    ) -> Membership | None: ...
    def log(
        self,
        action: str,
        entity: str,
        *,
        organization_id: int | None = None,
        user_id: int | None = None,
        entity_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None: ...


class AuthenticationService:
    def __init__(self, provider: AuthProvider, repository: IdentityRepository) -> None:
        self.provider = provider
        self.repository = repository

    def login(self, email: str, password: str) -> tuple[AuthSession, Principal]:
        clean_email = email.strip().casefold()
        if not clean_email or not password:
            raise AuthenticationError("Email and password are required.")
        session = self.provider.sign_in(clean_email, password)
        user = self.repository.sync_authenticated_user(
            session.supabase_user_id, session.email
        )
        if user.status != UserStatus.ACTIVE:
            raise AuthenticationError("This user account is not active.")
        memberships = tuple(self.repository.list_memberships(user.id))
        principal = Principal(user, memberships)
        self.repository.log("LOGIN", "session", user_id=user.id)
        return session, principal

    def restore(self, refresh_token: str) -> tuple[AuthSession, Principal]:
        session = self.provider.refresh(refresh_token)
        user = self.repository.sync_authenticated_user(
            session.supabase_user_id, session.email
        )
        if user.status != UserStatus.ACTIVE:
            raise AuthenticationError("This user account is not active.")
        return session, Principal(
            user, tuple(self.repository.list_memberships(user.id))
        )

    def logout(self, session: AuthSession, principal: Principal) -> None:
        self.provider.sign_out(session.access_token)
        self.repository.log("LOGOUT", "session", user_id=principal.user.id)

    def select_organization(
        self, principal: Principal, organization_id: int
    ) -> Principal:
        membership = next(
            (
                item
                for item in principal.memberships
                if item.organization_id == organization_id
                and item.status == UserStatus.ACTIVE
            ),
            None,
        )
        if membership is None and not principal.is_super_admin:
            raise AuthorizationError("You do not belong to the selected organization.")
        previous_id = principal.selected_organization_id
        if previous_id != organization_id:
            self.repository.log(
                "ORGANIZATION_SWITCH",
                "organization",
                organization_id=organization_id,
                user_id=principal.user.id,
                entity_id=str(organization_id),
            )
        return Principal(
            principal.user, principal.memberships, membership, organization_id
        )


def can_manage_platform(principal: Principal) -> bool:
    return principal.user.platform_role == PlatformRole.SUPER_ADMIN


def can_manage_organization(principal: Principal) -> bool:
    if principal.is_super_admin:
        return True
    return bool(
        principal.current_membership
        and principal.current_membership.role
        in {OrganizationRole.OWNER, OrganizationRole.ADMIN}
    )
