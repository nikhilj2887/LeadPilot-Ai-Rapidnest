from __future__ import annotations

import argparse

from leadpilot.application.auth import OrganizationRole, PlatformRole
from leadpilot.infrastructure.database.admin_bootstrap import (
    bootstrap_platform_admin,
)
from leadpilot.infrastructure.database.engine import create_database_engine
from leadpilot.infrastructure.database.session import create_session_factory


def parse_organization_role(value: str) -> OrganizationRole:
    try:
        return OrganizationRole[value.strip().upper()]
    except KeyError as exc:
        raise argparse.ArgumentTypeError(
            "Role must be OWNER, ADMIN, MANAGER, ANALYST, or VIEWER."
        ) from exc


def parse_platform_role(value: str) -> PlatformRole:
    try:
        return PlatformRole[value.strip().upper()]
    except KeyError as exc:
        raise argparse.ArgumentTypeError(
            "Platform role must be SUPER_ADMIN or SUPPORT_ADMIN."
        ) from exc


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Link an existing Supabase Auth user to LeadPilot."
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--supabase-user-id", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--first-name", required=True)
    parser.add_argument("--last-name", required=True)
    parser.add_argument("--organization-slug", default="rapidnest")
    parser.add_argument(
        "--organization-role", type=parse_organization_role, default="OWNER"
    )
    parser.add_argument("--platform-role", type=parse_platform_role)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    if not args.yes:
        confirmation = input(
            "Update the LeadPilot application user and organization membership? [y/N] "
        )
        if confirmation.strip().casefold() not in {"y", "yes"}:
            print("Cancelled; no changes were made.")
            return

    engine = create_database_engine(args.database_url)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session, session.begin():
            result = bootstrap_platform_admin(
                session,
                supabase_user_id=args.supabase_user_id,
                email=args.email,
                first_name=args.first_name,
                last_name=args.last_name,
                organization_slug=args.organization_slug,
                organization_role=args.organization_role,
                platform_role=args.platform_role,
            )
    finally:
        engine.dispose()
    print(
        "Platform administrator bootstrap complete "
        f"(user ID {result.user_id}, membership ID {result.membership_id})."
    )


if __name__ == "__main__":
    main()
