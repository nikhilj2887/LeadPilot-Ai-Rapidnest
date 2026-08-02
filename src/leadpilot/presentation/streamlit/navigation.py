from __future__ import annotations

from collections.abc import Callable

from leadpilot.application.auth import (
    Principal,
    can_manage_organization,
    can_manage_platform,
)
from leadpilot.bootstrap import Container
from leadpilot.presentation.streamlit.views import (
    companies,
    crm,
    dashboard,
    discovery,
    proposals,
    service_catalog,
    settings,
)

PageRenderer = Callable[[Container], None]

PAGE_ICONS = {
    "Dashboard": "Home",
    "Companies": "Companies",
    "CRM": "CRM",
    "Discovery": "Discovery",
    "Service Catalog": "Service Catalog",
    "Proposals": "Proposals",
    "Settings": "Settings",
    "Team": "Team",
    "Platform Admin": "Platform Admin",
}

PAGES: dict[str, PageRenderer] = {
    "Dashboard": dashboard.render,
    "Companies": companies.render,
    "CRM": crm.render,
    "Discovery": discovery.render,
    "Service Catalog": service_catalog.render,
    "Proposals": proposals.render,
    "Settings": settings.render,
}


def navigation_label(page: str) -> str:
    return PAGE_ICONS[page]


def pages_for_principal(principal: Principal) -> tuple[str, ...]:
    pages = [page for page in PAGES if page != "Settings"]
    if can_manage_organization(principal):
        pages.extend(("Settings", "Team"))
    if can_manage_platform(principal):
        pages.append("Platform Admin")
    return tuple(pages)
