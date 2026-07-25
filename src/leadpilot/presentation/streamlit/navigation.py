from __future__ import annotations

from collections.abc import Callable

from leadpilot.presentation.streamlit.pages import (
    companies,
    dashboard,
    discovery,
    proposals,
    settings,
)

PageRenderer = Callable[[object], None]

PAGES: dict[str, PageRenderer] = {
    "Dashboard": dashboard.render,
    "Companies": companies.render,
    "Discovery": discovery.render,
    "Proposals": proposals.render,
    "Settings": settings.render,
}
