from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from leadpilot.application.auth import (
    ApplicationUserNotFoundError,
    Membership,
    OrganizationRole,
    PlatformRole,
    User,
    UserStatus,
)
from leadpilot.infrastructure.database.models import (
    AuditLogModel,
    OrganizationMembershipModel,
    UserModel,
)


class IdentityRepository:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def sync_authenticated_user(self, supabase_user_id: str, email: str) -> User:
        with self._session_factory() as session, session.begin():
            model = session.scalar(
                select(UserModel).where(UserModel.supabase_user_id == supabase_user_id)
            )
            if model is None:
                raise ApplicationUserNotFoundError(
                    "Your identity is authenticated but is not linked to a "
                    "LeadPilot application user. Ask an administrator to grant access."
                )
            else:
                model.email = email.casefold()
                if model.status == UserStatus.INVITED.value:
                    model.status = UserStatus.ACTIVE.value
                    for membership in model.memberships:
                        if membership.status == UserStatus.INVITED.value:
                            membership.status = UserStatus.ACTIVE.value
                            membership.joined_at = datetime.now(UTC)
            model.last_login_at = datetime.now(UTC)
            session.flush()
            session.refresh(model)
            return self._user(model)

    def create_invited_user(
        self,
        supabase_user_id: str,
        email: str,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        platform_role: PlatformRole | None = None,
    ) -> User:
        with self._session_factory() as session, session.begin():
            model = UserModel(
                supabase_user_id=supabase_user_id,
                email=email.strip().casefold(),
                first_name=first_name,
                last_name=last_name,
                status=UserStatus.INVITED.value,
                platform_role=platform_role.value if platform_role else None,
            )
            session.add(model)
            session.flush()
            session.refresh(model)
            return self._user(model)

    def get_user(self, user_id: int) -> User | None:
        with self._session_factory() as session:
            model = session.get(UserModel, user_id)
            return self._user(model) if model else None

    def get_by_supabase_id(self, supabase_user_id: str) -> User | None:
        with self._session_factory() as session:
            model = session.scalar(
                select(UserModel).where(UserModel.supabase_user_id == supabase_user_id)
            )
            return self._user(model) if model else None

    def list_users(self) -> list[User]:
        with self._session_factory() as session:
            return [
                self._user(model)
                for model in session.scalars(
                    select(UserModel).order_by(UserModel.email)
                )
            ]

    def update_user(self, user_id: int, **values: Any) -> User | None:
        with self._session_factory() as session, session.begin():
            model = session.get(UserModel, user_id)
            if model is None:
                return None
            for key, value in values.items():
                if key == "status":
                    value = UserStatus(value).value
                if key == "platform_role" and value is not None:
                    value = PlatformRole(value).value
                setattr(model, key, value)
            session.flush()
            session.refresh(model)
            return self._user(model)

    def list_memberships(self, user_id: int) -> list[Membership]:
        with self._session_factory() as session:
            models = session.scalars(
                select(OrganizationMembershipModel)
                .where(OrganizationMembershipModel.user_id == user_id)
                .order_by(
                    OrganizationMembershipModel.is_default.desc(),
                    OrganizationMembershipModel.id,
                )
            )
            return [self._membership(model) for model in models]

    def list_organization_members(
        self, organization_id: int
    ) -> list[tuple[Membership, User]]:
        with self._session_factory() as session:
            rows = session.execute(
                select(OrganizationMembershipModel, UserModel)
                .join(UserModel, UserModel.id == OrganizationMembershipModel.user_id)
                .where(OrganizationMembershipModel.organization_id == organization_id)
                .order_by(UserModel.email)
            )
            return [
                (self._membership(membership), self._user(user))
                for membership, user in rows
            ]

    def create_membership(
        self,
        organization_id: int,
        user_id: int,
        role: OrganizationRole,
        *,
        status: UserStatus,
        is_default: bool = False,
    ) -> Membership:
        with self._session_factory() as session, session.begin():
            model = OrganizationMembershipModel(
                organization_id=organization_id,
                user_id=user_id,
                role=role.value,
                status=status.value,
                is_default=is_default,
                joined_at=datetime.now(UTC) if status == UserStatus.ACTIVE else None,
            )
            session.add(model)
            session.flush()
            session.refresh(model)
            return self._membership(model)

    def update_membership(self, membership_id: int, **values: Any) -> Membership | None:
        with self._session_factory() as session, session.begin():
            model = session.get(OrganizationMembershipModel, membership_id)
            if model is None:
                return None
            for key, value in values.items():
                if key == "role":
                    value = OrganizationRole(value).value
                if key == "status":
                    value = UserStatus(value).value
                    if value == UserStatus.ACTIVE.value and model.joined_at is None:
                        model.joined_at = datetime.now(UTC)
                setattr(model, key, value)
            session.flush()
            session.refresh(model)
            return self._membership(model)

    def remove_membership(self, organization_id: int, membership_id: int) -> bool:
        with self._session_factory() as session, session.begin():
            model = session.scalar(
                select(OrganizationMembershipModel).where(
                    OrganizationMembershipModel.id == membership_id,
                    OrganizationMembershipModel.organization_id == organization_id,
                )
            )
            if model is None:
                return False
            session.delete(model)
            return True

    def log(
        self,
        action: str,
        entity: str,
        *,
        organization_id: int | None = None,
        user_id: int | None = None,
        entity_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self._session_factory() as session, session.begin():
            session.add(
                AuditLogModel(
                    organization_id=organization_id,
                    user_id=user_id,
                    action=action[:80],
                    entity=entity[:80],
                    entity_id=entity_id[:100] if entity_id else None,
                    details_json=json.dumps(details or {}, sort_keys=True),
                )
            )

    def list_audit_logs(
        self, *, organization_id: int | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        statement = select(AuditLogModel)
        if organization_id is not None:
            statement = statement.where(
                AuditLogModel.organization_id == organization_id
            )
        statement = statement.order_by(AuditLogModel.created_at.desc()).limit(limit)
        with self._session_factory() as session:
            return [
                {
                    "id": model.id,
                    "organization_id": model.organization_id,
                    "user_id": model.user_id,
                    "action": model.action,
                    "entity": model.entity,
                    "entity_id": model.entity_id,
                    "details": json.loads(model.details_json or "{}"),
                    "created_at": model.created_at,
                }
                for model in session.scalars(statement)
            ]

    @staticmethod
    def _user(model: UserModel) -> User:
        return User(
            id=model.id,
            supabase_user_id=model.supabase_user_id,
            first_name=model.first_name,
            last_name=model.last_name,
            email=model.email,
            phone=model.phone,
            avatar_url=model.avatar_url,
            status=UserStatus(model.status),
            platform_role=PlatformRole(model.platform_role)
            if model.platform_role
            else None,
            last_login_at=model.last_login_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _membership(model: OrganizationMembershipModel) -> Membership:
        return Membership(
            id=model.id,
            organization_id=model.organization_id,
            user_id=model.user_id,
            role=OrganizationRole(model.role),
            status=UserStatus(model.status),
            is_default=model.is_default,
            joined_at=model.joined_at,
            created_at=model.created_at,
        )
