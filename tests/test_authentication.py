from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from leadpilot.application.admin import AdminService
from leadpilot.application.auth import (
    AuthenticationError,
    AuthenticationService,
    AuthorizationError,
    AuthSession,
    OrganizationRole,
    PlatformRole,
    Principal,
    UserStatus,
    can_manage_organization,
    can_manage_platform,
)
from leadpilot.application.companies import CompanyService
from leadpilot.application.organizations import OrganizationCreate
from leadpilot.infrastructure.database.base import Base
from leadpilot.infrastructure.database.identity_repository import IdentityRepository
from leadpilot.infrastructure.database.organization_repository import (
    OrganizationRepository,
)
from leadpilot.infrastructure.supabase_auth import SupabaseAuthProvider
from leadpilot.presentation.streamlit.navigation import pages_for_principal


class FakeAuthProvider:
    def __init__(self, user_id: str = "supabase-user", email: str = "user@example.com"):
        self.user_id = user_id
        self.email = email
        self.invited: list[str] = []
        self.signed_out: list[str] = []

    def session(self) -> AuthSession:
        return AuthSession("access", "refresh", 9999999999, self.user_id, self.email)

    def sign_in(self, email: str, password: str) -> AuthSession:
        if password == "wrong":
            raise AuthenticationError("Invalid credentials")
        self.email = email
        return self.session()

    def refresh(self, refresh_token: str) -> AuthSession:
        if refresh_token != "refresh":
            raise AuthenticationError("Invalid refresh token")
        return self.session()

    def sign_out(self, access_token: str) -> None:
        self.signed_out.append(access_token)

    def request_password_reset(self, email: str, redirect_url: str | None) -> None:
        return None

    def update_password(self, access_token: str, password: str) -> None:
        if len(password) < 10:
            raise AuthenticationError("Password too short")

    def invite_user(self, email: str, redirect_url: str | None) -> str:
        self.invited.append(email)
        return f"invited-{len(self.invited)}"


@pytest.fixture
def identity_stack():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    organizations = OrganizationRepository(factory)
    organization = organizations.create(
        OrganizationCreate(
            slug="test-organization",
            display_name="Test Organization",
            timezone="UTC",
            default_currency="USD",
        )
    )
    identities = IdentityRepository(factory)
    provider = FakeAuthProvider()
    auth = AuthenticationService(provider, identities)
    return organization, organizations, identities, provider, auth


def active_principal(identity_stack, role: OrganizationRole) -> Principal:
    organization, _, identities, provider, auth = identity_stack
    user = identities.sync_authenticated_user(provider.user_id, provider.email)
    identities.create_membership(
        organization.id, user.id, role, status=UserStatus.ACTIVE
    )
    _, principal = auth.login(provider.email, "correct-password")
    return auth.select_organization(principal, organization.id)


def test_login_restore_logout_and_audit(identity_stack) -> None:
    organization, _, identities, provider, auth = identity_stack
    user = identities.sync_authenticated_user(provider.user_id, provider.email)
    identities.create_membership(
        organization.id,
        user.id,
        OrganizationRole.ANALYST,
        status=UserStatus.ACTIVE,
        is_default=True,
    )
    session, principal = auth.login("USER@example.com", "correct-password")
    assert principal.user.email == "user@example.com"
    restored, restored_principal = auth.restore(session.refresh_token)
    assert restored.access_token == "access"
    assert restored_principal.memberships[0].organization_id == organization.id
    auth.logout(restored, restored_principal)
    assert provider.signed_out == ["access"]
    assert [item["action"] for item in identities.list_audit_logs()] == [
        "LOGOUT",
        "LOGIN",
    ]


def test_disabled_user_cannot_authenticate(identity_stack) -> None:
    _, _, identities, provider, auth = identity_stack
    user = identities.sync_authenticated_user(provider.user_id, provider.email)
    identities.update_user(user.id, status=UserStatus.DISABLED.value)
    with pytest.raises(AuthenticationError, match="not active"):
        auth.login(provider.email, "correct-password")


def test_membership_enforces_organization_access(identity_stack) -> None:
    organization, organizations, identities, provider, auth = identity_stack
    other = organizations.create(
        OrganizationCreate(
            slug="other-organization",
            display_name="Other Organization",
            timezone="UTC",
            default_currency="USD",
        )
    )
    user = identities.sync_authenticated_user(provider.user_id, provider.email)
    identities.create_membership(
        organization.id,
        user.id,
        OrganizationRole.VIEWER,
        status=UserStatus.ACTIVE,
    )
    _, principal = auth.login(provider.email, "correct-password")
    assert auth.select_organization(principal, organization.id).can_access_organization(
        organization.id
    )
    with pytest.raises(AuthorizationError):
        auth.select_organization(principal, other.id)


def test_invitation_acceptance_activates_user_and_membership(identity_stack) -> None:
    organization, _, identities, provider, auth = identity_stack
    invited = identities.create_invited_user(provider.user_id, provider.email)
    membership = identities.create_membership(
        organization.id,
        invited.id,
        OrganizationRole.ANALYST,
        status=UserStatus.INVITED,
    )
    _, principal = auth.login(provider.email, "correct-password")
    assert principal.user.status == UserStatus.ACTIVE
    updated = identities.list_memberships(invited.id)[0]
    assert updated.id == membership.id
    assert updated.status == UserStatus.ACTIVE
    assert updated.joined_at is not None


@pytest.mark.parametrize(
    ("role", "organization_admin"),
    [
        (OrganizationRole.OWNER, True),
        (OrganizationRole.ADMIN, True),
        (OrganizationRole.MANAGER, False),
        (OrganizationRole.ANALYST, False),
        (OrganizationRole.VIEWER, False),
    ],
)
def test_role_authorization_and_protected_navigation(
    identity_stack, role: OrganizationRole, organization_admin: bool
) -> None:
    principal = active_principal(identity_stack, role)
    assert can_manage_organization(principal) is organization_admin
    assert ("Team" in pages_for_principal(principal)) is organization_admin
    assert "Platform Admin" not in pages_for_principal(principal)
    if role == OrganizationRole.VIEWER:
        with pytest.raises(AuthorizationError):
            principal.require_role(OrganizationRole.ANALYST)


def test_only_super_admin_gets_platform_admin(identity_stack) -> None:
    principal = active_principal(identity_stack, OrganizationRole.VIEWER)
    super_user = replace(principal.user, platform_role=PlatformRole.SUPER_ADMIN)
    super_principal = replace(principal, user=super_user)
    support_user = replace(principal.user, platform_role=PlatformRole.SUPPORT_ADMIN)
    assert can_manage_platform(super_principal)
    assert "Platform Admin" in pages_for_principal(super_principal)
    assert not can_manage_platform(replace(principal, user=support_user))


def test_admin_invitation_and_role_change_are_audited(identity_stack) -> None:
    organization, organizations, identities, provider, auth = identity_stack
    principal = active_principal(identity_stack, OrganizationRole.OWNER)
    admin = AdminService(auth, organizations, identities)
    invited = admin.invite_user(
        principal,
        "new@example.com",
        organization.id,
        OrganizationRole.ANALYST,
    )
    membership = identities.list_memberships(invited.id)[0]
    admin.change_role(
        principal,
        organization.id,
        membership.id,
        OrganizationRole.MANAGER,
    )
    assert provider.invited == ["new@example.com"]
    assert identities.list_memberships(invited.id)[0].role == OrganizationRole.MANAGER
    actions = {item["action"] for item in identities.list_audit_logs()}
    assert {"CREATE_USER", "ROLE_CHANGE"} <= actions


def test_non_admin_cannot_invite(identity_stack) -> None:
    organization, organizations, identities, _, auth = identity_stack
    principal = active_principal(identity_stack, OrganizationRole.VIEWER)
    admin = AdminService(auth, organizations, identities)
    with pytest.raises(AuthorizationError):
        admin.invite_user(
            principal,
            "blocked@example.com",
            organization.id,
            OrganizationRole.VIEWER,
        )


def test_application_write_guard_runs_before_company_mutation() -> None:
    class Repository:
        def delete(self, company_id: int) -> bool:
            raise AssertionError("Repository must not be reached")

    def deny() -> None:
        raise AuthorizationError("Manager access is required.")

    service = CompanyService(Repository(), authorize_write=deny)  # type: ignore[arg-type]
    with pytest.raises(AuthorizationError, match="Manager"):
        service.delete_company(42)


def test_supabase_provider_uses_auth_api_without_exposing_credentials() -> None:
    provider = SupabaseAuthProvider("https://project.supabase.co", "anon-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["apikey"] == "anon-key"
        assert request.url.path == "/auth/v1/token"
        return httpx.Response(
            200,
            json={
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_at": 9999999999,
                "user": {"id": "abc", "email": "user@example.com"},
            },
        )

    provider._client = httpx.Client(transport=httpx.MockTransport(handler))
    session = provider.sign_in("user@example.com", "secure-password")
    assert session.supabase_user_id == "abc"


def test_auth_migration_creates_required_tables(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "auth.db"
    monkeypatch.setenv("LEADPILOT_DATABASE_URL", f"sqlite:///{database}")
    command.upgrade(Config("alembic.ini"), "head")
    inspector = inspect(create_engine(f"sqlite:///{database}"))
    assert {"users", "organization_memberships", "audit_logs"} <= set(
        inspector.get_table_names()
    )
    assert {
        "supabase_user_id",
        "status",
        "platform_role",
        "last_login_at",
    } <= {item["name"] for item in inspector.get_columns("users")}
    assert {"role", "status", "is_default", "joined_at"} <= {
        item["name"] for item in inspector.get_columns("organization_memberships")
    }
