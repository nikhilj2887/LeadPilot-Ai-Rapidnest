from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from leadpilot.infrastructure.database.models import (
    OrganizationBrandingModel,
    OrganizationModel,
    OrganizationServiceModel,
)

RAPIDNEST = {
    "slug": "rapidnest",
    "legal_name": "RapidNest Software Solutions",
    "display_name": "RapidNest Software Solutions",
    "status": "active",
    "default_currency": "INR",
    "timezone": "Asia/Kolkata",
    "website": "www.therapidnest.com",
    "contact_email": "contact@therapidnest.com",
    "contact_phone": "+91 63006 75410",
}
RAPIDNEST_SERVICES = (
    "AI Chatbots and Conversational Automation",
    "Business Process Automation",
    "Websites and Web Applications",
    "Mobile Applications",
    "Custom CRM and ERP Solutions",
    "Cloud and Digital Transformation",
)


def seed_rapidnest(session_factory: Callable[[], Session]) -> int:
    with session_factory() as session, session.begin():
        organization = session.scalar(
            select(OrganizationModel).where(OrganizationModel.slug == "rapidnest")
        )
        if organization is None:
            organization = OrganizationModel(**RAPIDNEST)
            session.add(organization)
            session.flush()
        if session.get(OrganizationBrandingModel, organization.id) is None:
            session.add(
                OrganizationBrandingModel(
                    organization_id=organization.id,
                    brand_name="RapidNest Software Solutions",
                    logo_reference="assets/leadpilot-logo.png",
                    primary_color="#2563EB",
                    secondary_color="#0F172A",
                    accent_color="#14B8A6",
                    proposal_footer=(
                        "RapidNest Software Solutions · www.therapidnest.com"
                    ),
                    email_signature="RapidNest Software Solutions",
                )
            )
        existing_services = set(
            session.scalars(
                select(OrganizationServiceModel.name).where(
                    OrganizationServiceModel.organization_id == organization.id
                )
            )
        )
        for order, name in enumerate(RAPIDNEST_SERVICES, 1):
            if name not in existing_services:
                session.add(
                    OrganizationServiceModel(
                        organization_id=organization.id,
                        name=name,
                        short_description=name,
                        category="Digital Solutions",
                        is_active=True,
                        display_order=order,
                    )
                )
        session.flush()
        return organization.id
