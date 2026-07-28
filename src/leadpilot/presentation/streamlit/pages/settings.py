from __future__ import annotations

import streamlit as st
from pydantic import ValidationError

from leadpilot.application.organizations import OrganizationUpdate
from leadpilot.bootstrap import Container
from leadpilot.presentation.streamlit.components import (
    health_badge,
    page_header,
    section_header,
)


def render(container: Container) -> None:
    page_header(
        "Settings",
        "Manage the selected organization profile, branding, and service catalogue.",
        eyebrow="Organization",
    )
    organization = container.organization_context.organization
    repository = container.organizations

    section_header("Organization Profile", "Customer-facing identity and defaults.")
    with st.form("organization_profile"):
        left, right = st.columns(2)
        display_name = left.text_input("Display name", organization.display_name)
        legal_name = right.text_input("Legal name", organization.legal_name or "")
        website = left.text_input("Website", organization.website or "")
        contact_email = right.text_input(
            "Contact email", organization.contact_email or ""
        )
        contact_phone = left.text_input(
            "Contact phone", organization.contact_phone or ""
        )
        default_currency = right.selectbox(
            "Default currency",
            ("AUD", "CAD", "EUR", "GBP", "INR", "USD"),
            index=("AUD", "CAD", "EUR", "GBP", "INR", "USD").index(
                organization.default_currency
            ),
        )
        timezone = left.text_input("Timezone", organization.timezone)
        right.text_input("Status", organization.status.title(), disabled=True)
        if st.form_submit_button("Save profile", type="primary"):
            try:
                repository.update(
                    organization.id,
                    OrganizationUpdate(
                        display_name=display_name,
                        legal_name=legal_name or None,
                        website=website or None,
                        contact_email=contact_email or None,
                        contact_phone=contact_phone or None,
                        default_currency=default_currency,
                        timezone=timezone,
                    ),
                )
                st.success("Organization profile saved.")
            except (ValidationError, ValueError) as exc:
                st.error(str(exc))

    branding = repository.get_branding(organization.id)
    section_header("Branding", "Reusable proposal and communication identity.")
    if branding:
        with st.form("organization_branding"):
            brand_name = st.text_input("Brand name", branding.brand_name)
            colors = st.columns(3)
            primary = colors[0].text_input("Primary color", branding.primary_color)
            secondary = colors[1].text_input(
                "Secondary color", branding.secondary_color
            )
            accent = colors[2].text_input("Accent color", branding.accent_color)
            logo = st.text_input(
                "Logo reference",
                branding.logo_reference or "",
                help="Safe references must remain under the application assets folder.",
            )
            footer = st.text_area(
                "Proposal footer", branding.proposal_footer or "", max_chars=2000
            )
            signature = st.text_area(
                "Email signature", branding.email_signature or "", max_chars=2000
            )
            if st.form_submit_button("Save branding"):
                try:
                    repository.update_branding(
                        organization.id,
                        {
                            "brand_name": brand_name.strip(),
                            "primary_color": primary,
                            "secondary_color": secondary,
                            "accent_color": accent,
                            "logo_reference": logo or None,
                            "proposal_footer": footer or None,
                            "email_signature": signature or None,
                        },
                    )
                    st.success("Branding saved.")
                except ValueError as exc:
                    st.error(str(exc))
    else:
        st.info(
            "No logo or branding has been configured. The organization name is used."
        )

    section_header(
        "Service Catalogue",
        "AI Intelligence may recommend only active services listed here.",
    )
    services = repository.list_services(organization.id)
    for service in services:
        with (
            st.expander(
                f"{service.display_order}. {service.name}"
                + ("" if service.is_active else " · Inactive")
            ),
            st.form(f"service_{service.id}"),
        ):
            name = st.text_input("Service name", service.name)
            description = st.text_area(
                "Short description", service.short_description or ""
            )
            category = st.text_input("Category", service.category or "")
            active = st.checkbox("Active", service.is_active)
            order = st.number_input(
                "Display order", min_value=0, value=service.display_order
            )
            if st.form_submit_button("Update service"):
                repository.update_service(
                    organization.id,
                    service.id,
                    name=name.strip(),
                    short_description=description.strip() or None,
                    category=category.strip() or None,
                    is_active=active,
                    display_order=int(order),
                )
                st.success("Service updated.")
    with st.expander("Add service"), st.form("add_service"):
        new_name = st.text_input("Service name")
        new_description = st.text_area("Short description")
        new_category = st.text_input("Category")
        new_order = st.number_input(
            "Display order", min_value=0, value=len(services) + 1
        )
        if st.form_submit_button("Add service", type="primary"):
            if not new_name.strip():
                st.error("Service name is required.")
            else:
                repository.create_service(
                    organization.id,
                    name=new_name.strip(),
                    short_description=new_description.strip() or None,
                    full_description=None,
                    category=new_category.strip() or None,
                    is_active=True,
                    display_order=int(new_order),
                )
                st.success("Service added.")

    section_header("Workspace Information", "Stable organization identifiers.")
    info = st.columns(3)
    info[0].text_input("Organization slug", organization.slug, disabled=True)
    info[1].text_input("Organization ID", str(organization.id), disabled=True)
    info[2].text_input(
        "Created", organization.created_at.strftime("%Y-%m-%d"), disabled=True
    )

    section_header("Application Health", "Operational status without credentials.")
    health = container.health_check.check()
    cards = (
        (
            "Application Status",
            health.application_status.title(),
            health.application_status == "running",
        ),
        (
            "Database Status",
            "Connected" if health.database_connected else "Unavailable",
            health.database_connected,
        ),
        ("Environment", health.environment.title(), True),
        ("Application Name", container.settings.app_name, True),
    )
    for column, (label, value, healthy) in zip(st.columns(4), cards, strict=True):
        with column:
            st.markdown(
                '<div class="lp-kpi"><div class="lp-kpi-top">'
                f'<span>{label}</span></div><div class="lp-value" '
                f'style="margin:.75rem 0">{value}</div>'
                f"{health_badge('Healthy' if healthy else 'Attention', healthy)}</div>",
                unsafe_allow_html=True,
            )
    if health.database_error:
        st.error(
            "The database is currently unavailable. Check application logs or contact "
            "the administrator; connection details are intentionally hidden."
        )
    else:
        st.success("All configured application services are operating normally.")
