from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from leadpilot.application.auth import OrganizationRole, PlatformRole, UserStatus
from leadpilot.infrastructure.database.admin_bootstrap import (
    bootstrap_platform_admin,
)
from leadpilot.infrastructure.database.base import Base
from leadpilot.infrastructure.database.data_migration import (
    APPLICATION_TABLES,
    migrate_application_data,
    validate_migration_engines,
)
from leadpilot.infrastructure.database.models import (
    OrganizationMembershipModel,
    OrganizationModel,
    UserModel,
)
from leadpilot.infrastructure.database.seed import seed_rapidnest


def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def test_migration_requires_sqlite_source_and_postgresql_target() -> None:
    sqlite = create_engine("sqlite:///:memory:")
    with pytest.raises(ValueError, match="Target"):
        validate_migration_engines(sqlite, sqlite)


def test_dry_run_never_writes_and_table_order_is_foreign_key_safe(tmp_path) -> None:
    source = create_engine(f"sqlite:///{tmp_path / 'source.db'}")
    target = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(source)
    Base.metadata.create_all(target)
    seed_rapidnest(session_factory(source))
    target.dialect.name = "postgresql"
    results = migrate_application_data(source, target, dry_run=True)
    assert tuple(result.table for result in results) == APPLICATION_TABLES
    assert results[0].source_count == 1
    assert all(result.inserted_count == 0 for result in results)
    with target.connect() as connection:
        assert (
            connection.scalar(select(func.count()).select_from(OrganizationModel)) == 0
        )


def test_migration_skips_existing_rows_when_rerun(tmp_path) -> None:
    source = create_engine(f"sqlite:///{tmp_path / 'source-rerun.db'}")
    target = create_engine(f"sqlite:///{tmp_path / 'target-rerun.db'}")
    Base.metadata.create_all(source)
    Base.metadata.create_all(target)
    seed_rapidnest(session_factory(source))
    target.dialect.name = "postgresql"
    with patch(
        "leadpilot.infrastructure.database.data_migration._reset_postgresql_sequences"
    ):
        first = migrate_application_data(source, target, dry_run=False)
        second = migrate_application_data(source, target, dry_run=False)
    assert first[0].inserted_count == 1
    assert second[0].inserted_count == 0
    assert second[0].skipped_count == 1


def test_bootstrap_creates_owner_and_is_safe_to_rerun() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    organization_id = seed_rapidnest(factory)
    auth_id = str(uuid4())
    with factory() as session, session.begin():
        first = bootstrap_platform_admin(
            session,
            supabase_user_id=auth_id,
            email="owner@example.com",
            first_name="First",
            last_name="Owner",
            organization_slug="rapidnest",
            organization_role=OrganizationRole.OWNER,
            platform_role=PlatformRole.SUPER_ADMIN,
        )
    with factory() as session, session.begin():
        second = bootstrap_platform_admin(
            session,
            supabase_user_id=auth_id,
            email="OWNER@example.com",
            first_name="Updated",
            last_name="Owner",
            organization_slug="rapidnest",
            organization_role=OrganizationRole.OWNER,
            platform_role=PlatformRole.SUPER_ADMIN,
        )
    assert first.created_user and first.created_membership
    assert not second.created_user and not second.created_membership
    with factory() as session:
        user = session.scalar(select(UserModel))
        memberships = list(session.scalars(select(OrganizationMembershipModel)))
        assert user is not None
        assert user.first_name == "Updated"
        assert user.platform_role == PlatformRole.SUPER_ADMIN.value
        assert len(memberships) == 1
        assert memberships[0].organization_id == organization_id
        assert memberships[0].role == OrganizationRole.OWNER.value
        assert memberships[0].status == UserStatus.ACTIVE.value
        assert memberships[0].is_default


def test_bootstrap_missing_organization_and_identity_conflicts_fail_safely() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    auth_id = str(uuid4())
    with (
        factory() as session,
        session.begin(),
        pytest.raises(ValueError, match="Organization"),
    ):
        bootstrap_platform_admin(
            session,
            supabase_user_id=auth_id,
            email="owner@example.com",
            first_name="First",
            last_name="Owner",
            organization_slug="missing",
            organization_role=OrganizationRole.OWNER,
            platform_role=None,
        )
    seed_rapidnest(factory)
    with factory() as session, session.begin():
        session.add(
            UserModel(
                supabase_user_id=str(uuid4()),
                email="owner@example.com",
                status=UserStatus.ACTIVE.value,
            )
        )
    with (
        factory() as session,
        session.begin(),
        pytest.raises(ValueError, match="conflicting"),
    ):
        bootstrap_platform_admin(
            session,
            supabase_user_id=auth_id,
            email="owner@example.com",
            first_name="First",
            last_name="Owner",
            organization_slug="rapidnest",
            organization_role=OrganizationRole.OWNER,
            platform_role=None,
        )
