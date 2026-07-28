"""Development-only organization seed.

Run with ``python -m leadpilot.infrastructure.demo_organization``.
Use ``--remove`` to remove only the demo organization and its owned data.
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from leadpilot.config import get_settings
from leadpilot.infrastructure.database.engine import create_database_engine
from leadpilot.infrastructure.database.models import (
    OrganizationBrandingModel,
    OrganizationModel,
    OrganizationServiceModel,
)
from leadpilot.infrastructure.database.session import create_session_factory


def seed_demo(*, remove: bool = False) -> str:
    engine = create_database_engine(get_settings().database_url)
    factory = create_session_factory(engine)
    try:
        with factory() as session, session.begin():
            existing = session.scalar(
                select(OrganizationModel).where(
                    OrganizationModel.slug == "demo-digital-agency"
                )
            )
            if remove:
                if existing is not None:
                    session.delete(existing)
                    return "Demo Digital Agency removed."
                return "Demo Digital Agency was not present."
            if existing is not None:
                return "Demo Digital Agency already exists."
            organization = OrganizationModel(
                slug="demo-digital-agency",
                legal_name="Demo Digital Agency",
                display_name="Demo Digital Agency",
                status="active",
                default_currency="USD",
                timezone="UTC",
                website="demo.example",
                contact_email="hello@demo.example",
            )
            session.add(organization)
            session.flush()
            session.add(
                OrganizationBrandingModel(
                    organization_id=organization.id,
                    brand_name="Demo Digital Agency",
                    logo_reference=None,
                    primary_color="#7C3AED",
                    secondary_color="#1E1B4B",
                    accent_color="#F59E0B",
                    proposal_footer="Demo Digital Agency",
                    email_signature="Demo Digital Agency",
                )
            )
            for order, name in enumerate(
                ("Digital Strategy", "Experience Design", "Marketing Automation"), 1
            ):
                session.add(
                    OrganizationServiceModel(
                        organization_id=organization.id,
                        name=name,
                        short_description=name,
                        category="Agency Services",
                        is_active=True,
                        display_order=order,
                    )
                )
            return "Demo Digital Agency created without company data."
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()
    print(seed_demo(remove=args.remove))


if __name__ == "__main__":
    main()
