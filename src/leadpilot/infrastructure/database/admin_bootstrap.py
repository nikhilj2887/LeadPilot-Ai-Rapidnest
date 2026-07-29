from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from leadpilot.application.auth import OrganizationRole, PlatformRole, UserStatus
from leadpilot.infrastructure.database.models import (
    AuditLogModel,
    OrganizationMembershipModel,
    OrganizationModel,
    UserModel,
)


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    user_id: int
    organization_id: int
    membership_id: int
    created_user: bool
    created_membership: bool


def bootstrap_platform_admin(
    session: Session,
    *,
    supabase_user_id: str,
    email: str,
    first_name: str,
    last_name: str,
    organization_slug: str,
    organization_role: OrganizationRole,
    platform_role: PlatformRole | None,
) -> BootstrapResult:
    try:
        normalized_uuid = str(UUID(supabase_user_id))
    except ValueError as exc:
        raise ValueError("Supabase user ID must be a valid UUID.") from exc
    normalized_email = email.strip().casefold()
    if not normalized_email or "@" not in normalized_email:
        raise ValueError("A valid email address is required.")

    organization = session.scalar(
        select(OrganizationModel).where(
            OrganizationModel.slug == organization_slug.strip().casefold()
        )
    )
    if organization is None:
        raise ValueError("Organization was not found. Seed RapidNest first.")

    users = list(
        session.scalars(
            select(UserModel).where(
                or_(
                    UserModel.supabase_user_id == normalized_uuid,
                    UserModel.email == normalized_email,
                )
            )
        )
    )
    if len(users) > 1:
        raise ValueError(
            "Email and Supabase user ID belong to different application users."
        )
    user = users[0] if users else None
    if user and user.supabase_user_id != normalized_uuid:
        raise ValueError("Email is already assigned to a conflicting user.")
    if user and user.email.casefold() != normalized_email:
        raise ValueError("Supabase user ID is already assigned to a conflicting email.")

    created_user = user is None
    if user is None:
        user = UserModel(
            supabase_user_id=normalized_uuid,
            email=normalized_email,
            status=UserStatus.ACTIVE.value,
        )
        session.add(user)
        session.flush()
    user.first_name = first_name.strip() or None
    user.last_name = last_name.strip() or None
    user.status = UserStatus.ACTIVE.value
    user.platform_role = platform_role.value if platform_role else None

    membership = session.scalar(
        select(OrganizationMembershipModel).where(
            OrganizationMembershipModel.organization_id == organization.id,
            OrganizationMembershipModel.user_id == user.id,
        )
    )
    created_membership = membership is None
    if membership is None:
        has_membership = session.scalar(
            select(OrganizationMembershipModel.id)
            .where(OrganizationMembershipModel.user_id == user.id)
            .limit(1)
        )
        membership = OrganizationMembershipModel(
            organization_id=organization.id,
            user_id=user.id,
            role=organization_role.value,
            status=UserStatus.ACTIVE.value,
            is_default=has_membership is None,
            joined_at=datetime.now(UTC),
        )
        session.add(membership)
    else:
        membership.role = organization_role.value
        membership.status = UserStatus.ACTIVE.value
        membership.joined_at = membership.joined_at or datetime.now(UTC)
    session.flush()
    session.add(
        AuditLogModel(
            organization_id=organization.id,
            user_id=user.id,
            action="BOOTSTRAP_PLATFORM_ADMIN",
            entity="user",
            entity_id=str(user.id),
            details_json=json.dumps(
                {
                    "organization_role": organization_role.value,
                    "platform_role": platform_role.value if platform_role else None,
                },
                sort_keys=True,
            ),
        )
    )
    session.flush()
    return BootstrapResult(
        user.id,
        organization.id,
        membership.id,
        created_user,
        created_membership,
    )
